import json, re
from contextlib import asynccontextmanager
from fastapi import BackgroundTasks, Depends, FastAPI, HTTPException, status
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
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_credentials=True, allow_methods=["*"], allow_headers=["*"])

def resolve_llm_config():
    cfg = settings()
    provider = (cfg.llm_provider or "auto").lower().strip()

    openrouter_key = (cfg.openrouter_api_key or "").strip()
    openai_key = (cfg.openai_api_key or "").strip()
    gemini_key = (cfg.gemini_api_key or "").strip()
    groq_key = (cfg.groq_api_key or "").strip()
    deepseek_key = (cfg.deepseek_api_key or "").strip()
    generic_key = (cfg.llm_api_key or "").strip()
    base_url_val = (cfg.llm_base_url or "").strip()

    is_gemini_key = lambda k: k.startswith("AIzaSy") or k.startswith("AQ.")

    # 1. Google Gemini (explicit provider, GEMINI_API_KEY, AQ./AIzaSy key format, or Gemini base URL)
    if (
        provider == "gemini"
        or gemini_key
        or is_gemini_key(generic_key)
        or is_gemini_key(openai_key)
        or "generativelanguage.googleapis.com" in base_url_val.lower()
    ):
        key = gemini_key or (openai_key if is_gemini_key(openai_key) else generic_key)
        if key:
            model = cfg.llm_model or cfg.gemini_model or "gemini-flash-latest"
            if model == "gemini-2.0-flash":
                model = "gemini-flash-latest"
            endpoint = base_url_val if "generativelanguage" in base_url_val else "https://generativelanguage.googleapis.com/v1beta/openai/"
            return {
                "name": "Google Gemini",
                "api_key": key,
                "base_url": endpoint,
                "model": model,
                "headers": {"X-goog-api-key": key},
            }

    # 2. xkiro (starts with sk-xt- or explicit provider)
    if provider == "xkiro" or openai_key.startswith("sk-xt-") or generic_key.startswith("sk-xt-"):
        key = (openai_key if openai_key.startswith("sk-xt-") else generic_key) or cfg.llm_api_key
        if key:
            return {
                "name": "xkiro (DeepSeek)",
                "api_key": key.strip(),
                "base_url": "https://api.xkiro.com/v1",
                "model": cfg.llm_model or "deepseek/deepseek-v4-pro",
                "headers": {},
            }

    # 3. OpenRouter (starts with sk-or-v1- or explicit provider)
    if provider == "openrouter" or openrouter_key or openai_key.startswith("sk-or-v1-") or generic_key.startswith("sk-or-v1-"):
        key = openrouter_key or (openai_key if openai_key.startswith("sk-or-v1-") else generic_key)
        if key:
            return {
                "name": "OpenRouter",
                "api_key": key,
                "base_url": "https://openrouter.ai/api/v1",
                "model": cfg.llm_model or cfg.openrouter_model or "nex-agi/nex-n2.5-mini:free",
                "headers": {
                    "HTTP-Referer": "http://localhost:3000",
                    "X-Title": "RepoSage",
                },
            }

    # 4. Groq (starts with gsk_ or explicit provider)
    if provider == "groq" or groq_key or openai_key.startswith("gsk_") or generic_key.startswith("gsk_"):
        key = groq_key or (openai_key if openai_key.startswith("gsk_") else generic_key)
        if key:
            return {
                "name": "Groq",
                "api_key": key,
                "base_url": "https://api.groq.com/openai/v1",
                "model": cfg.llm_model or cfg.groq_model or "llama-3.3-70b-versatile",
                "headers": {},
            }

    # 5. DeepSeek
    if provider == "deepseek" or deepseek_key:
        key = deepseek_key or generic_key
        if key:
            return {
                "name": "DeepSeek",
                "api_key": key,
                "base_url": "https://api.deepseek.com/v1",
                "model": cfg.llm_model or cfg.deepseek_model or "deepseek-chat",
                "headers": {},
            }

    # 6. Ollama (Local free models, zero cost, no key needed)
    if provider == "ollama":
        return {
            "name": "Ollama (Local)",
            "api_key": "ollama",
            "base_url": cfg.ollama_base_url or "http://host.docker.internal:11434/v1",
            "model": cfg.llm_model or cfg.ollama_model or "llama3",
            "headers": {},
        }

    # 7. Custom / Generic OpenAI-compatible endpoint (LLM_BASE_URL)
    if base_url_val:
        name = "xkiro (DeepSeek)" if "xkiro" in base_url_val.lower() else f"Custom ({base_url_val})"
        default_model = "deepseek/deepseek-v4-pro" if "xkiro" in base_url_val.lower() else "gpt-4o-mini"
        return {
            "name": name,
            "api_key": (generic_key or openai_key or "not-needed"),
            "base_url": base_url_val,
            "model": cfg.llm_model or default_model,
            "headers": {},
        }

    # 8. OpenAI
    if openai_key and not openai_key.startswith("sk-or-v1-") and not is_gemini_key(openai_key) and not openai_key.startswith("gsk_"):
        return {
            "name": "OpenAI",
            "api_key": openai_key,
            "base_url": None,
            "model": cfg.llm_model or cfg.openai_model or "gpt-4o-mini",
            "headers": {},
        }

    if generic_key:
        return {
            "name": "OpenAI-compatible",
            "api_key": generic_key,
            "base_url": None,
            "model": cfg.llm_model or "gpt-4o-mini",
            "headers": {},
        }

    return None

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

_redis_checked = None

def dispatch_indexing(repo_id: str, background_tasks: BackgroundTasks):
    global _redis_checked
    if _redis_checked is None:
        try:
            import redis
            r = redis.from_url(settings().redis_url, socket_connect_timeout=0.1, socket_timeout=0.1)
            _redis_checked = bool(r.ping())
        except Exception:
            _redis_checked = False

    if _redis_checked:
        try:
            index_repository.delay(repo_id)
            return
        except Exception:
            pass
    background_tasks.add_task(index, repo_id)

@app.post("/api/v1/repositories", response_model=RepoOut, status_code=201)
def create_repository(payload: RepoCreate, background_tasks: BackgroundTasks, user: User = Depends(current_user), db: Session = Depends(get_db)):
    url = str(payload.url).rstrip("/")
    match = re.fullmatch(r"https://github\.com/([\w.-]+)/([\w.-]+)", url)
    if not match: raise HTTPException(422, "Only canonical public GitHub repository URLs are supported")
    existing = db.scalar(select(Repository).where(Repository.url == url, Repository.owner_id == user.id))
    if existing:
        if existing.status in {"queued", "failed"}:
            existing.status = "queued"; db.commit()
            dispatch_indexing(existing.id, background_tasks)
        return existing
    repo = Repository(owner_id=user.id, url=url, name=match.group(2), default_branch=payload.branch or "main")
    db.add(repo); db.commit(); db.refresh(repo)
    dispatch_indexing(repo.id, background_tasks)
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
def reindex(repository_id: str, background_tasks: BackgroundTasks, user: User = Depends(current_user), db: Session = Depends(get_db)):
    repo = db.get(Repository, repository_id)
    if not repo or repo.owner_id != user.id: raise HTTPException(404, "Repository not found")
    repo.status = "queued"; db.commit()
    dispatch_indexing(repo.id, background_tasks)
    return {"status": "queued"}

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
    context = "\n\n".join(f"[{i+1}] {c.path}:{c.start_line}-{c.end_line} ({c.symbol_kind}: {c.symbol_name or 'module'})\n{c.content}" for i, (c, _) in enumerate(results))[:24000]

    async def stream():
        yield f"event: citations\ndata: {json.dumps(citations)}\n\n"
        if not results:
            msg = "No indexed code chunks matched this question. Try re-indexing or asking about a different component."
            for token in msg.split(" "): yield f"event: token\ndata: {json.dumps(token + ' ')}\n\n"
            yield "event: done\ndata: {}\n\n"
            return

        llm_config = resolve_llm_config()
        if llm_config:
            try:
                from openai import AsyncOpenAI
                client = AsyncOpenAI(
                    api_key=llm_config["api_key"],
                    base_url=llm_config["base_url"],
                    default_headers=llm_config.get("headers") or None,
                )
                system_prompt = (
                    "You are RepoSage, an expert AI codebase architect and code search assistant. "
                    "Answer the user's question clearly, thoroughly, and technically using the provided repository code sections and citations. "
                    "Always mention relevant file paths, line ranges, symbols (functions, classes), and explain the implementation logic. "
                    "Use formatted markdown with code snippets where helpful."
                )
                user_msg = f"User Question: {request.question}\n\nRepository Context:\n{context}"
                create_kwargs = {
                    "model": llm_config["model"],
                    "messages": [
                        {"role": "system", "content": system_prompt},
                        {"role": "user", "content": user_msg},
                    ],
                    "stream": True,
                }
                if llm_config.get("name") == "OpenRouter":
                    create_kwargs["extra_body"] = {"reasoning": {"enabled": True}}

                response = await client.chat.completions.create(**create_kwargs)
                async for chunk in response:
                    if chunk.choices and chunk.choices[0].delta:
                        delta = chunk.choices[0].delta
                        token = getattr(delta, "content", None)
                        if not token:
                            token = getattr(delta, "reasoning_content", None) or getattr(delta, "reasoning", None)
                        if not token and hasattr(delta, "model_extra") and delta.model_extra:
                            token = delta.model_extra.get("reasoning") or delta.model_extra.get("reasoning_details")
                        if token:
                            yield f"event: token\ndata: {json.dumps(token)}\n\n"
                yield "event: done\ndata: {}\n\n"
                return
            except Exception as e:
                err_str = str(e)
                provider_name = llm_config["name"]
                if "User not found" in err_str:
                    err_notice = (
                        f"> **{provider_name} Notice:** Authentication failed (User not found). "
                        f"Your OpenRouter key was rejected by OpenRouter. Please generate a fresh key from [openrouter.ai/keys](https://openrouter.ai/keys) and verify your email at OpenRouter.\n\n"
                        f"Showing the offline AST code intelligence summary below:\n\n"
                    )
                elif "invalid_api_key" in err_str or "Incorrect API key" in err_str or "401" in err_str:
                    err_notice = (
                        f"> **{provider_name} Notice:** Authentication failed (Error 401 - Invalid API Key). "
                        f"Please verify your key in the `.env` file.\n\n"
                        f"Showing the offline AST code intelligence summary below:\n\n"
                    )
                elif "insufficient_quota" in err_str or "credit_balance_exhausted" in err_str or "429" in err_str:
                    err_notice = (
                        f"> **{provider_name} Notice:** Quota or rate limit reached (Error 429 - Insufficient credits). "
                        f"You can switch to another model provider (such as Gemini, Groq, or Ollama) in `.env`.\n\n"
                        f"Showing the offline AST code intelligence summary below:\n\n"
                    )
                elif "503" in err_str or "UNAVAILABLE" in err_str:
                    err_notice = (
                        f"> **{provider_name} Notice:** Service temporarily busy / high demand (Error 503). "
                        f"Please retry your prompt in a few moments.\n\n"
                        f"Showing the offline AST code intelligence summary below:\n\n"
                    )
                else:
                    err_notice = f"> **{provider_name} Error:** {err_str}\n\nShowing the offline AST code intelligence summary below:\n\n"
                for token in err_notice.split(" "): yield f"event: token\ndata: {json.dumps(token + ' ')}\n\n"

        # Deterministic / Offline RAG synthesis (runs when no provider key is configured or provider errors)
        summary_intro = (
            f"### Code Intelligence Analysis for: \"{request.question}\"\n\n"
            f"Found **{len(results)} relevant code sections** using hybrid Reciprocal Rank Fusion (AST symbols + keyword + vector embeddings):\n\n"
        )
        for token in summary_intro.split(" "): yield f"event: token\ndata: {json.dumps(token + ' ')}\n\n"

        for i, (chunk, score) in enumerate(results, 1):
            symbol_label = f" • `{chunk.symbol_name}` ({chunk.symbol_kind})" if chunk.symbol_name else ""
            imports_label = f" | Imports: {', '.join(chunk.imports[:4])}" if chunk.imports else ""
            snippet = "\n".join(chunk.content.strip().splitlines()[:10])
            card = (
                f"#### [{i}] `{chunk.path}` (lines {chunk.start_line}–{chunk.end_line}){symbol_label}{imports_label}\n"
                f"```\n{snippet}\n```\n\n"
            )
            for token in card.split(" "): yield f"event: token\ndata: {json.dumps(token + ' ')}\n\n"

        footer = (
            "---\n\n"
            "> **Note:** To enable conversational LLM answers, configure any provider (Google Gemini, Groq, Ollama, DeepSeek, OpenRouter, or OpenAI) in `.env`."
        )
        for token in footer.split(" "): yield f"event: token\ndata: {json.dumps(token + ' ')}\n\n"

        yield "event: done\ndata: {}\n\n"

    return StreamingResponse(stream(), media_type="text/event-stream", headers={"Cache-Control": "no-cache"})
