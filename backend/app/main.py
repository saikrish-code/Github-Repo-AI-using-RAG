import json, re
from contextlib import asynccontextmanager
from fastapi import Depends, FastAPI, HTTPException, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse
from sqlalchemy import select
from sqlalchemy.orm import Session
from .core import settings
from .db import Base, engine, get_db
from .indexer import index
from .models import Repository, User
from .schemas import ChatRequest, LoginRequest, RegisterRequest, RepoCreate, RepoOut, SearchResult, TokenResponse
from .security import create_token, current_user, hash_password, verify_password
from .services import hybrid_search
from .worker import index_repository

@asynccontextmanager
async def lifespan(app: FastAPI):
    Base.metadata.create_all(engine)
    yield
app = FastAPI(title="RepoSage API", version="1.0.0", lifespan=lifespan, openapi_url="/api/v1/openapi.json", docs_url="/docs")
app.add_middleware(CORSMiddleware, allow_origins=settings().cors_origins.split(","), allow_credentials=True, allow_methods=["*"], allow_headers=["*"])

@app.get("/health")
def health(): return {"status": "ok"}

@app.post("/api/v1/auth/register", response_model=TokenResponse, status_code=status.HTTP_201_CREATED)
def register(payload: RegisterRequest, db: Session = Depends(get_db)):
    if db.scalar(select(User).where(User.email == payload.email)): raise HTTPException(409, "Email is already registered")
    user = User(email=str(payload.email), password_hash=hash_password(payload.password)); db.add(user); db.commit()
    return TokenResponse(access_token=create_token(user.id))

@app.post("/api/v1/auth/login", response_model=TokenResponse)
def login(payload: LoginRequest, db: Session = Depends(get_db)):
    user = db.scalar(select(User).where(User.email == payload.email))
    if not user or not verify_password(payload.password, user.password_hash): raise HTTPException(401, "Invalid email or password")
    return TokenResponse(access_token=create_token(user.id))

@app.get("/api/v1/auth/me")
def me(user: User = Depends(current_user)): return {"id": user.id, "email": user.email, "is_admin": user.is_admin}

@app.get("/api/v1/repositories", response_model=list[RepoOut])
def repositories(user: User = Depends(current_user), db: Session = Depends(get_db)):
    return db.scalars(select(Repository).where(Repository.owner_id == user.id).order_by(Repository.created_at.desc())).all()

@app.post("/api/v1/repositories", response_model=RepoOut, status_code=201)
def create_repository(payload: RepoCreate, user: User = Depends(current_user), db: Session = Depends(get_db)):
    url = str(payload.url).rstrip("/")
    match = re.fullmatch(r"https://github\.com/([\w.-]+)/([\w.-]+)", url)
    if not match: raise HTTPException(422, "Only canonical public GitHub repository URLs are supported")
    existing = db.scalar(select(Repository).where(Repository.url == url, Repository.owner_id == user.id))
    if existing:
        if existing.status in {"queued", "failed"}:
            existing.status = "queued"; db.commit()
            try: index_repository.delay(existing.id)
            except Exception: pass
        return existing
    repo = Repository(owner_id=user.id, url=url, name=match.group(2), default_branch=payload.branch or "main")
    db.add(repo); db.commit(); db.refresh(repo)
    try: index_repository.delay(repo.id)
    except Exception: pass
    return repo

@app.get("/api/v1/repositories/{repository_id}", response_model=RepoOut)
def repository(repository_id: str, user: User = Depends(current_user), db: Session = Depends(get_db)):
    repo = db.get(Repository, repository_id)
    if not repo or repo.owner_id != user.id: raise HTTPException(404, "Repository not found")
    return repo

@app.delete("/api/v1/repositories/{repository_id}", status_code=204)
def delete_repository(repository_id: str, user: User = Depends(current_user), db: Session = Depends(get_db)):
    repo = db.get(Repository, repository_id)
    if not repo or repo.owner_id != user.id: raise HTTPException(404, "Repository not found")
    db.delete(repo); db.commit()

@app.post("/api/v1/repositories/{repository_id}/index")
def reindex(repository_id: str, user: User = Depends(current_user), db: Session = Depends(get_db)):
    repo = db.get(Repository, repository_id)
    if not repo or repo.owner_id != user.id: raise HTTPException(404, "Repository not found")
    try: index_repository.delay(repo.id); return {"status": "queued"}
    except Exception: return index(repo.id)

@app.get("/api/v1/repositories/{repository_id}/search", response_model=list[SearchResult])
def search(repository_id: str, q: str, user: User = Depends(current_user), db: Session = Depends(get_db)):
    repo = db.get(Repository, repository_id)
    if not repo or repo.owner_id != user.id: raise HTTPException(404, "Repository not found")
    return [SearchResult(content=c.content, score=s, citation={"path": c.path, "start_line": c.start_line, "end_line": c.end_line, "symbol": c.symbol_name}) for c, s in hybrid_search(db, repo.id, q)]

@app.post("/api/v1/repositories/{repository_id}/chat")
def chat(repository_id: str, request: ChatRequest, user: User = Depends(current_user), db: Session = Depends(get_db)):
    repo = db.get(Repository, repository_id)
    if not repo or repo.owner_id != user.id: raise HTTPException(404, "Repository not found")
    results = hybrid_search(db, repo.id, request.question)
    citations = [{"path": c.path, "start_line": c.start_line, "end_line": c.end_line, "symbol": c.symbol_name} for c, _ in results]
    context = "\n\n".join(f"[{i+1}] {c.path}:{c.start_line}-{c.end_line}\n{c.content}" for i, (c, _) in enumerate(results))[:24000]
    answer = "No indexed code matched that question." if not results else f"I found {len(results)} relevant code sections. Review the cited locations for the implementation details."
    async def stream():
        yield f"event: citations\ndata: {json.dumps(citations)}\n\n"
        for token in answer.split(" "): yield f"event: token\ndata: {json.dumps(token + ' ')}\n\n"
        yield "event: done\ndata: {}\n\n"
    return StreamingResponse(stream(), media_type="text/event-stream", headers={"Cache-Control": "no-cache"})
