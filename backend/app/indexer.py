import shutil
from pathlib import Path
from tempfile import mkdtemp
from git import Repo
from sqlalchemy import delete
from .db import SessionLocal
from .models import Repository, CodeChunk
from .services import IGNORED, chunks_for_file, VectorStore

def index(repository_id: str) -> dict:
    db, temp = SessionLocal(), Path(mkdtemp(prefix="reposage-"))
    try:
        repo = db.get(Repository, repository_id)
        if not repo: return {"error": "repository not found"}
        repo.status = "indexing"; db.commit()
        db.execute(delete(CodeChunk).where(CodeChunk.repository_id == repo.id)); db.commit()
        cloned = Repo.clone_from(repo.url, temp / "source", depth=1, branch=repo.default_branch)
        repo.commit_hash = cloned.head.commit.hexsha
        source = temp / "source"; total = 0; languages = {}; vector_store = VectorStore(); pending: list[CodeChunk] = []
        for file in source.rglob("*"):
            if not file.is_file() or any(part in IGNORED for part in file.parts): continue
            for data in chunks_for_file(file, source) or []:
                chunk = CodeChunk(repository_id=repo.id, branch=repo.default_branch, commit_hash=repo.commit_hash, **data)
                pending.append(chunk); total += 1; languages[data["language"]] = languages.get(data["language"], 0) + 1
                if len(pending) >= 100:
                    db.add_all(pending); db.flush(); vector_store.upsert_many(pending); db.commit(); pending.clear()
        if pending:
            db.add_all(pending); db.flush(); vector_store.upsert_many(pending)
        repo.status = "ready"; repo.stats = {"chunks": total, "languages": languages}; db.commit()
        return repo.stats
    except Exception:
        if 'repo' in locals(): repo.status = "failed"; db.commit()
        raise
    finally: db.close(); shutil.rmtree(temp, ignore_errors=True)
