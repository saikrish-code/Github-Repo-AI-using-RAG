import os, sys, json, time, math
from collections import defaultdict

sys.path.append(os.path.join(os.path.dirname(__file__), ".."))
from app.db import SessionLocal
from app.services import hybrid_search
from app.indexer import index

def load_dataset():
    path = os.path.join(os.path.dirname(__file__), "datasets", "qas.jsonl")
    queries = []
    with open(path, "r") as f:
        for line in f:
            queries.append(json.loads(line))
    return queries

def evaluate_retrieval(query_data, results):
    ground_truth = query_data["ground_truth"][0]
    gt_file = ground_truth["file_path"]
    gt_start = ground_truth.get("start_line", -1)
    gt_end = ground_truth.get("end_line", 999999)
    gt_symbol = ground_truth.get("symbol")
    
    hits = []
    for chunk, score in results:
        is_hit = False
        if chunk.path == gt_file:
            overlap_start = max(chunk.start_line, gt_start)
            overlap_end = min(chunk.end_line, gt_end)
            if overlap_start <= overlap_end:
                is_hit = True
            elif gt_symbol and chunk.symbol_name == gt_symbol:
                is_hit = True
        hits.append(is_hit)
        
    metrics = {}
    for k in [1, 3, 5, 10]:
        hits_at_k = hits[:k]
        num_hits = sum(hits_at_k)
        metrics[f"precision@{k}"] = num_hits / k if k > 0 else 0
        metrics[f"recall@{k}"] = 1.0 if num_hits > 0 else 0.0
        metrics[f"hit_rate@{k}"] = 1.0 if any(hits_at_k) else 0.0
        
    mrr = 0
    for i, h in enumerate(hits):
        if h:
            mrr = 1.0 / (i + 1)
            break
    metrics["mrr"] = mrr
    
    ndcg = 0
    for i, h in enumerate(hits[:10]):
        if h:
            ndcg += 1.0 / math.log2(i + 2)
    metrics["ndcg@10"] = ndcg
            
    return metrics, hits

def run_ablation(queries, mode="hybrid", db_session=None):
    print(f"Running ablation: {mode}")
    metrics_sum = defaultdict(float)
    latencies = []
    raw_results = []
    
    for q in queries:
        start_time = time.time()
        
        if mode == "hybrid":
            results = hybrid_search(db_session, q["repo"], q["question"], limit=10)
        elif mode == "vector":
            from app.services import VectorStore, Embedder
            client = VectorStore().get_client()
            embedder = Embedder()
            from qdrant_client.models import Filter, FieldCondition, MatchValue
            if client:
                res = client.query_points(VectorStore.collection, query=embedder.embed(q["question"]), query_filter=Filter(must=[FieldCondition(key="repository_id", match=MatchValue(value=q["repo"]))]), limit=10).points
                ids = [r.id for r in res]
                from app.models import CodeChunk
                chunks = db_session.query(CodeChunk).filter(CodeChunk.id.in_(ids)).all()
                chunk_dict = {c.id: c for c in chunks}
                results = [(chunk_dict[i], r.score) for i, r in zip(ids, res) if i in chunk_dict]
            else:
                results = []
        elif mode == "keyword":
            import re
            from sqlalchemy import select
            from app.models import CodeChunk
            rows = db_session.scalars(select(CodeChunk).where(CodeChunk.repository_id == q["repo"])).all()
            terms = set(re.findall(r"\w+", q["question"].lower()))
            keyword_ranked = sorted(rows, key=lambda c: sum(c.content.lower().count(t) for t in terms), reverse=True)[:10]
            results = [(c, 0) for c in keyword_ranked]
            
        latency = (time.time() - start_time) * 1000
        latencies.append(latency)
        q_metrics, hits = evaluate_retrieval(q, results)
        for k, v in q_metrics.items():
            metrics_sum[k] += v
            
        raw_results.append({
            "id": q["id"],
            "question": q["question"],
            "type": q["query_type"],
            "metrics": q_metrics,
            "hits": hits
        })
        
    num_q = len(queries)
    avg_metrics = {k: v / num_q for k, v in metrics_sum.items()}
    latencies.sort()
    avg_metrics["latency_p50"] = latencies[int(len(latencies) * 0.5)]
    avg_metrics["latency_p95"] = latencies[int(len(latencies) * 0.95)]
    avg_metrics["latency_p99"] = latencies[int(len(latencies) * 0.99)]
    
    return avg_metrics, raw_results

def main():
    queries = load_dataset()
    db = SessionLocal()
    
    os.environ["CHUNK_MODE"] = "ast"
    results_hybrid_ast, raw_hybrid_ast = run_ablation(queries, "hybrid", db)
    results_vector_ast, _ = run_ablation(queries, "vector", db)
    results_keyword_ast, _ = run_ablation(queries, "keyword", db)
    
    print("Re-indexing for fixed chunk ablation...")
    os.environ["CHUNK_MODE"] = "fixed"
    repos = set(q["repo"] for q in queries)
    for rid in repos:
        index(rid)
        
    results_hybrid_fixed, _ = run_ablation(queries, "hybrid", db)
    
    summary = {
        "timestamp": time.time(),
        "config": {
            "num_questions": len(queries),
            "chunk_modes": ["ast", "fixed"],
            "llm": os.environ.get("LLM_MODEL", "meta-llama/llama-3.3-70b-instruct"),
            "embedder": "local_bag_of_words_64d",
            "k_values": [1, 3, 5, 10]
        },
        "results": {
            "hybrid_ast": results_hybrid_ast,
            "vector_ast": results_vector_ast,
            "keyword_ast": results_keyword_ast,
            "hybrid_fixed": results_hybrid_fixed
        }
    }
    
    out_dir = os.path.join(os.path.dirname(__file__), "results")
    os.makedirs(out_dir, exist_ok=True)
    with open(os.path.join(out_dir, "summary.json"), "w") as f:
        json.dump(summary, f, indent=2)
        
    with open(os.path.join(out_dir, f"{int(time.time())}_raw.json"), "w") as f:
        json.dump(raw_hybrid_ast, f, indent=2)
        
    print("Evaluation complete.")

if __name__ == "__main__":
    main()
