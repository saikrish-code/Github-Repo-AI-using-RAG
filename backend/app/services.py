import hashlib, math, re, os
from collections import Counter
from pathlib import Path
from typing import Iterator
from qdrant_client import QdrantClient
from qdrant_client.models import Distance, Filter, FieldCondition, MatchValue, PointStruct, VectorParams
from sqlalchemy import select
from sqlalchemy.orm import Session
from .core import settings
from .models import CodeChunk

IGNORED = {".git", "node_modules", "venv", ".venv", "dist", "build", "__pycache__", "coverage"}
EXTENSIONS = {".py":"Python", ".ts":"TypeScript", ".tsx":"TypeScript", ".js":"JavaScript", ".jsx":"JavaScript", ".go":"Go", ".rs":"Rust", ".java":"Java", ".c":"C", ".cpp":"C++", ".h":"C/C++", ".md":"Markdown", ".json":"JSON", ".yml":"YAML", ".yaml":"YAML", ".html":"HTML", ".css":"CSS"}
SYMBOL = re.compile(r"^(?:async\s+def|def|class|function|export\s+(?:default\s+)?(?:function|class)|(?:public|private|protected)\s+[\w<>\[\]]+\s+)([A-Za-z_$][\w$]*)", re.M)

def language(path: Path) -> str: return "Dockerfile" if path.name == "Dockerfile" else EXTENSIONS.get(path.suffix.lower(), "Text")
def chunks_for_file(path: Path, root: Path) -> Iterator[dict]:
    if path.stat().st_size > 1_000_000: return
    try: text = path.read_text(encoding="utf-8")
    except (UnicodeDecodeError, OSError): return
    lines = text.splitlines()
    if not lines: return

    chunk_mode = os.environ.get("CHUNK_MODE", "ast")
    if chunk_mode == "fixed":
        chunk_size = 50
        overlap = 10
        for i in range(0, len(lines), chunk_size - overlap):
            segment_start = i + 1
            segment_end = min(len(lines), i + chunk_size)
            if segment_start > segment_end: break
            body = "\n".join(lines[segment_start - 1:segment_end])
            if body.strip():
                yield {"path": str(path.relative_to(root)).replace("\\", "/"), "language": language(path), "symbol_name": None, "symbol_kind": "module", "start_line": segment_start, "end_line": segment_end, "content": body, "imports": [], "exports": []}
            if segment_end == len(lines): break
        return

    matches = list(SYMBOL.finditer(text))
    starts = [text[:m.start()].count("\n") + 1 for m in matches]
    names = [m.group(1) for m in matches]

    # If first symbol starts after line 1, include the module header/imports
    if starts and starts[0] > 1:
        starts.insert(0, 1)
        names.insert(0, None)
    elif not starts:
        starts = [1]
        names = [None]

    for index, start in enumerate(starts):
        end = starts[index + 1] - 1 if index + 1 < len(starts) else len(lines)
        if start > end: continue
        # modules and oversized symbols are segmented with line overlap.
        for segment_start in range(start, end + 1, 180):
            segment_end = min(end, segment_start + 219)
            body = "\n".join(lines[segment_start - 1:segment_end])
            if body.strip(): yield {"path": str(path.relative_to(root)).replace("\\", "/"), "language": language(path), "symbol_name": names[index], "symbol_kind": "symbol" if names[index] else "module", "start_line": segment_start, "end_line": segment_end, "content": body, "imports": re.findall(r"(?:import|from|require)\s*[\(\s]*[\"']?([\w./@-]+)", body) if language(path) not in ("Markdown", "Text", "JSON", "YAML", "HTML", "CSS") else [], "exports": re.findall(r"(?:export|__all__)\s+(?:default\s+)?([\w$]+)", body)}

class Embedder:
    dimension = 64
    def embed(self, text: str) -> list[float]:
        # Stable local fallback; replace through this interface with any provider.
        values = [0.0] * self.dimension
        for token in re.findall(r"\w+", text.lower()): values[int(hashlib.sha256(token.encode()).hexdigest(), 16) % self.dimension] += 1
        norm = math.sqrt(sum(v*v for v in values)) or 1
        return [v / norm for v in values]

_qdrant_client = None
_qdrant_available = None

class VectorStore:
    collection = "code_chunks_v1"

    @classmethod
    def get_client(cls):
        global _qdrant_client, _qdrant_available
        if _qdrant_client is not None:
            return _qdrant_client if _qdrant_available else None
        
        qdrant_url = settings().qdrant_url
        try:
            client = QdrantClient(url=qdrant_url, timeout=0.2)
            client.get_collection(cls.collection)
            _qdrant_client = client
            _qdrant_available = True
            return _qdrant_client
        except Exception:
            try:
                client = QdrantClient(url=qdrant_url, timeout=0.2)
                client.create_collection(cls.collection, vectors_config=VectorParams(size=Embedder.dimension, distance=Distance.COSINE))
                _qdrant_client = client
                _qdrant_available = True
                return _qdrant_client
            except Exception:
                _qdrant_available = False
                _qdrant_client = None
                return None

    def upsert(self, chunk: CodeChunk):
        self.upsert_many([chunk])

    def upsert_many(self, chunks: list[CodeChunk]):
        if not chunks: return
        client = self.get_client()
        if not client: return
        try:
            embedder = Embedder()
            points = []
            for chunk in chunks:
                payload = {"repository_id": chunk.repository_id, "path": chunk.path, "start_line": chunk.start_line, "end_line": chunk.end_line, "symbol_name": chunk.symbol_name or ""}
                points.append(PointStruct(id=chunk.id, vector=embedder.embed(chunk.content), payload=payload))
            client.upsert(self.collection, points)
        except Exception:
            pass

    def semantic(self, repo_id: str, query: str, limit: int = 20):
        client = self.get_client()
        if not client: return []
        try:
            return client.query_points(self.collection, query=Embedder().embed(query), query_filter=Filter(must=[FieldCondition(key="repository_id", match=MatchValue(value=repo_id))]), limit=limit).points
        except Exception:
            return []

def hybrid_search(db: Session, repo_id: str, query: str, limit: int = 8) -> list[tuple[CodeChunk, float]]:
    rows = db.scalars(select(CodeChunk).where(CodeChunk.repository_id == repo_id)).all()
    if not rows: return []

    terms = set(re.findall(r"\w+", query.lower()))
    keyword = sorted(rows, key=lambda c: sum(c.content.lower().count(t) for t in terms), reverse=True)
    ranked: dict[str, float] = {}
    for rank, chunk in enumerate(keyword[:30], 1):
        score = sum(chunk.content.lower().count(t) for t in terms)
        if score > 0:
            ranked[chunk.id] = ranked.get(chunk.id, 0) + 1 / (60 + rank)
    
    # 1. Semantic query against Qdrant if running
    qdrant_points = VectorStore().semantic(repo_id, query)
    if qdrant_points:
        for rank, point in enumerate(qdrant_points, 1):
            ranked[str(point.id)] = ranked.get(str(point.id), 0) + 1 / (60 + rank)
    else:
        # 2. Resilient local in-memory cosine similarity fallback
        embedder = Embedder()
        q_vec = embedder.embed(query)
        def cosine_sim(chunk: CodeChunk) -> float:
            c_vec = embedder.embed(chunk.content)
            return sum(a * b for a, b in zip(q_vec, c_vec))
        vector_ranked = sorted(rows, key=cosine_sim, reverse=True)
        for rank, chunk in enumerate(vector_ranked[:20], 1):
            ranked[chunk.id] = ranked.get(chunk.id, 0) + 1 / (60 + rank)

    by_id = {c.id: c for c in rows}
    return [(by_id[id_], score) for id_, score in sorted(ranked.items(), key=lambda x: x[1], reverse=True)[:limit] if id_ in by_id]
