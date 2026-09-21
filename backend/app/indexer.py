import os, shutil, stat, logging
from pathlib import Path
from tempfile import mkdtemp
from git import Repo
from sqlalchemy import delete
from .db import SessionLocal
from .models import Repository, CodeChunk
from .services import IGNORED, chunks_for_file, VectorStore
from qdrant_client.models import Filter, FieldCondition, MatchValue

def _remove_readonly(func, path, excinfo):
    try:
        os.chmod(path, stat.S_IWRITE)
        func(path)
    except Exception:
        pass

def index(repository_id: str) -> dict:
    db, temp = SessionLocal(), Path(mkdtemp(prefix="reposage-"))
    cloned = None
    try:
        repo = db.get(Repository, repository_id)
        if not repo: return {"error": "repository not found"}
        repo.status = "indexing"; db.commit()
        db.execute(delete(CodeChunk).where(CodeChunk.repository_id == repo.id)); db.commit()
        try:
            VectorStore().get_client().delete(VectorStore.collection, points_selector=Filter(must=[FieldCondition(key="repository_id", match=MatchValue(value=repo.id))]))
        except Exception:
            pass
        
        # Resilient git clone: Try configured branch, fallback to remote default HEAD if not found
        source = temp / "source"
        branch_to_try = repo.default_branch or "main"
        try:
            cloned = Repo.clone_from(repo.url, source, depth=1, branch=branch_to_try)
        except Exception:
            shutil.rmtree(source, onerror=_remove_readonly, ignore_errors=True)
            cloned = Repo.clone_from(repo.url, source, depth=1)
        
        try:
            repo.default_branch = cloned.active_branch.name
        except Exception:
            pass
        repo.commit_hash = cloned.head.commit.hexsha
        total = 0; languages = {}; vector_store = VectorStore(); pending: list[CodeChunk] = []
        for file in source.rglob("*"):
            if not file.is_file() or any(part in IGNORED for part in file.parts): continue
            for data in chunks_for_file(file, source) or []:
                chunk = CodeChunk(repository_id=repo.id, branch=repo.default_branch, commit_hash=repo.commit_hash, **data)
                pending.append(chunk); total += 1; languages[data["language"]] = languages.get(data["language"], 0) + 1
                if len(pending) >= 100:
                    db.add_all(pending); db.flush()
                    try: vector_store.upsert_many(pending)
                    except Exception as e: logging.error(f"Vector upsert failed: {e}")
                    db.commit(); pending.clear()
        if pending:
            db.add_all(pending); db.flush()
            try: vector_store.upsert_many(pending)
            except Exception as e: logging.error(f"Vector upsert failed: {e}")
        repo.status = "ready"; repo.stats = {"chunks": total, "languages": languages}; db.commit()
        return repo.stats
    except Exception:
        if 'repo' in locals() and repo: repo.status = "failed"; db.commit()
        raise
    finally:
        if cloned:
            try: cloned.close()
            except Exception: pass
        db.close()
        shutil.rmtree(temp, onerror=_remove_readonly, ignore_errors=True)
