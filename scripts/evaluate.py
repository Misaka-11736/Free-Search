"""Evaluate a private fixed corpus without transmitting its files or judgments."""
from __future__ import annotations

import argparse
import hashlib
import json
import math
import os
import statistics
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))


def canonical(path):
    return os.path.normcase(os.path.abspath(path))


def file_metrics(results, expected):
    """Deduplicate chunks before computing file-level ranking metrics."""
    ranked = list(dict.fromkeys(canonical(r["path"]) for r in results))
    gold = {canonical(r["path"]) for r in expected}
    if not gold:
        raise ValueError("Positive retrieval metrics require at least one expected file")
    ranks = [i for i, path in enumerate(ranked, 1) if path in gold]
    return {
        "hit_at_1": float(any(r <= 1 for r in ranks)),
        "hit_at_5": float(any(r <= 5 for r in ranks)),
        "mrr_at_10": 1.0 / ranks[0] if ranks and ranks[0] <= 10 else 0.0,
        "recall_at_10": len(gold.intersection(ranked[:10])) / len(gold),
    }


def validate(dataset, corpus):
    if dataset.get("schema_version") != 1:
        raise ValueError("Unsupported evaluation schema")
    paths = {canonical(row["path"]): row for row in corpus}
    ids = set()
    for row in corpus:
        actual = hashlib.file_digest(open(row["path"], "rb"), "sha256").hexdigest()
        if actual != row["sha256"]:
            raise ValueError(f"Corpus hash changed: {row['id']}")
    for query in dataset["queries"]:
        if query["id"] in ids or not query["query"].strip():
            raise ValueError("Duplicate query id or empty query")
        ids.add(query["id"])
        if not query["expected"]:
            raise ValueError("Keep no-answer probes in a separate file")
        for target in query["expected"]:
            member = paths.get(canonical(target["path"]))
            if member is None or member["sha256"] != target["sha256"]:
                raise ValueError(f"Invalid corpus judgment: {query['id']}")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dataset", type=Path, default=Path("private/evaluation/queries.json"))
    parser.add_argument("--data-dir", type=Path, default=Path("private/evaluation/index"))
    parser.add_argument("--model-dir", type=Path, default=Path("models"))
    parser.add_argument("--report", type=Path, default=Path("private/evaluation/report.json"))
    parser.add_argument("--modes", nargs="+",
                        choices=["bm25", "vector", "hybrid_no_rerank", "hybrid"],
                        default=["bm25", "vector", "hybrid_no_rerank", "hybrid"])
    parser.add_argument("--index", action="store_true", help="Index exactly the frozen corpus")
    parser.add_argument("--validate-only", action="store_true")
    parser.add_argument("--no-answer-probes", type=Path)
    args = parser.parse_args()
    dataset = json.loads(args.dataset.read_text(encoding="utf-8"))
    corpus_path = args.dataset.parent / dataset["candidate_pool"]
    corpus = json.loads(corpus_path.read_text(encoding="utf-8"))
    validate(dataset, corpus)
    digest = hashlib.sha256(args.dataset.read_bytes()).hexdigest()
    if args.validate_only:
        print(json.dumps({"valid": True, "queries": len(dataset["queries"]),
                          "corpus_files": len(corpus), "dataset_sha256": digest}))
        return

    from free_search.engine import SearchEngine
    engine = SearchEngine(args.data_dir, args.model_dir)
    try:
        index_stats = engine.index_files([row["path"] for row in corpus]) if args.index else None
        stats = engine.stats()
        # A separate evaluation index is mandatory: unjudged unrelated files alter ranking.
        actual_paths = {canonical(row[0]) for row in engine.db.execute("SELECT path FROM files")}
        if actual_paths != {canonical(row["path"]) for row in corpus}:
            raise ValueError("Index candidate pool differs from corpus; use a fresh --data-dir with --index")
        models = stats["models"]
        report = {
            "schema_version": 1, "dataset_sha256": digest,
            "corpus_sha256": hashlib.sha256(corpus_path.read_bytes()).hexdigest(),
            "query_count": len(dataset["queries"]), "corpus_files": len(corpus),
            "dataset_status": dataset["status"], "provenance": dataset["provenance"],
            "limitations": dataset["limitations"], "engine_stats": stats,
            "index_run": index_stats, "modes": {},
        }
        for mode in args.modes:
            needs = (["text_embedding"] if mode != "bm25" else []) + (
                ["text_reranker"] if mode == "hybrid" else [])
            missing = [name for name in needs if not models.get(name)]
            if missing:
                report["modes"][mode] = {"status": "skipped_missing_models", "missing": missing}
                continue
            rows = []
            for query in dataset["queries"]:
                start = time.perf_counter()
                found = engine.search(query["query"], filters=query.get("filters"),
                                      limit=10, mode=mode)
                elapsed = time.perf_counter() - start
                rows.append({
                    "id": query["id"], "seconds": elapsed,
                    "metrics": file_metrics(found, query["expected"]),
                    "results": [{k: r.get(k) for k in ("path", "score", "locator", "ranking")}
                                for r in found],
                })
            aggregate = {key: statistics.mean(row["metrics"][key] for row in rows)
                         for key in rows[0]["metrics"]}
            latencies = sorted(row["seconds"] for row in rows)
            aggregate["latency_median_seconds"] = statistics.median(latencies)
            aggregate["latency_p95_seconds"] = latencies[math.ceil(len(latencies) * .95) - 1]
            aggregate["latency_p95_method"] = "nearest_rank_ceil_0.95_n"
            aggregate["includes_first_query_model_load"] = True
            result = {"status": "completed", "aggregate": aggregate, "queries": rows}
            if args.no_answer_probes:
                probes = json.loads(args.no_answer_probes.read_text(encoding="utf-8"))
                probe_rows = []
                for query in probes["queries"]:
                    found = engine.search(query["query"], limit=10, mode=mode)
                    probe_rows.append({"id": query["id"], "returned_files": len(found)})
                result["no_answer_probes"] = {
                    "status": probes["status"], "queries": probe_rows,
                    "empty_result_rate": statistics.mean(r["returned_files"] == 0 for r in probe_rows),
                    "interpretation": "Descriptive only: top-k ranking is not a calibrated abstention system.",
                }
            report["modes"][mode] = result
        args.report.parent.mkdir(parents=True, exist_ok=True)
        args.report.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
        print(json.dumps({mode: {k: v for k, v in row.items() if k != "queries"}
                          for mode, row in report["modes"].items()}, ensure_ascii=False, indent=2))
    finally:
        engine.close()


if __name__ == "__main__":
    main()
