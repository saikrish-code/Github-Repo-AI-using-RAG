import os, sys, json, random, time
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

# Make app importable
sys.path.append(os.path.join(os.path.dirname(__file__), ".."))

from app.db import SessionLocal, Base, engine
from app.models import Repository, CodeChunk, User
from app.indexer import index

os.environ["CHUNK_MODE"] = "ast" # Force AST mode for initial generation

REPOS = [
    {"url": "https://github.com/expressjs/express", "name": "express", "branch": "master"},
    {"url": "https://github.com/psf/requests", "name": "requests", "branch": "main"}
]

def main():
    db = SessionLocal()
    # Create demo user if needed
    user = db.query(User).filter(User.email == "demo@example.com").first()
    if not user:
        user = User(email="demo@example.com", password_hash="dummy")
        db.add(user)
        db.commit()

    repo_ids = []
    for r in REPOS:
        repo = db.query(Repository).filter(Repository.url == r["url"]).first()
        if not repo:
            repo = Repository(owner_id=user.id, url=r["url"], name=r["name"], default_branch=r["branch"])
            db.add(repo)
            db.commit()
            db.refresh(repo)
        print(f"Indexing {r['name']}...")
        index(repo.id)
        repo_ids.append(repo.id)
        
    print("Generating queries...")
    queries = []
    
    for rid in repo_ids:
        chunks = db.query(CodeChunk).filter(CodeChunk.repository_id == rid).all()
        if not chunks: 
            print(f"No chunks found for {rid}")
            continue
        
        # Pick 25 chunks to get around 50 total questions
        samples = random.sample(chunks, min(25, len(chunks)))
        
        for i, c in enumerate(samples):
            # We want exact identifiers when we have a symbol, and conceptual otherwise,
            # or a mix.
            has_symbol = bool(c.symbol_name)
            
            if has_symbol and i % 2 == 0:
                q = f"Where is {c.symbol_name} defined?"
                q_type = "exact"
            else:
                target = c.symbol_name or os.path.basename(c.path)
                q = f"How does {target} work?"
                q_type = "conceptual"
                
            queries.append({
                "id": f"q_{rid}_{i}",
                "repo": c.repository_id,
                "commit_sha": c.commit_hash,
                "question": q,
                "query_type": q_type,
                "ground_truth": [{
                    "file_path": c.path,
                    "symbol": c.symbol_name,
                    "start_line": c.start_line,
                    "end_line": c.end_line
                }]
            })
            
    out_dir = os.path.join(os.path.dirname(__file__), "datasets")
    os.makedirs(out_dir, exist_ok=True)
    with open(os.path.join(out_dir, "qas.jsonl"), "w") as f:
        for q in queries:
            f.write(json.dumps(q) + "\n")
            
    print(f"Generated {len(queries)} queries.")

if __name__ == "__main__":
    main()
