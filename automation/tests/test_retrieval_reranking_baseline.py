"""Frozen baseline for future retrieve → rerank experiments.

The fixture supplies a deliberately fixed candidate pool.  It measures the
existing multi-route RRF implementation, never performs model inference, and
keeps holdout cases unavailable to development runs.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import sys
import unittest

ROOT = Path(__file__).resolve().parents[2]
SCRIPTS = ROOT / "automation" / "scripts"
if str(SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SCRIPTS))

from material_query.query_plan import fuse
from memory.evaluation import ranking_metrics


FIXTURE = ROOT / "automation" / "tests" / "fixtures" / "retrieval_reranking" / "fixture.json"


def load_fixture(path=FIXTURE):
    """Load bytes once so the report can bind an exact frozen fixture hash."""
    raw = Path(path).read_bytes()
    return json.loads(raw.decode("utf-8")), hashlib.sha256(raw).hexdigest()


def candidate(canonical_id, route):
    """Make the minimal current-RRF candidate contract from a frozen ID."""
    return {"canonical_id": canonical_id, "refs": [{"canonical_id": canonical_id}],
            "channels": [route["channel"]], "hits": [{"canonical_id": canonical_id}]}


def rrf_ranking(query, routes):
    """Run the product RRF fusion, including its per-route duplicate protection."""
    by_id = {route["id"]: route for route in routes}
    batches = [(by_id[route_id], [candidate(cid, by_id[route_id]) for cid in ids])
               for route_id, ids in query["candidates"].items()]
    return fuse(batches)


def oracle_ranking(query):
    """Ideal grade order within exactly the frozen RRF candidate coverage."""
    labels = {row["canonical_id"]: row["grade"] for row in query["relevant"]}
    candidates = list(dict.fromkeys(cid for ids in query["candidates"].values() for cid in ids))
    return sorted(candidates, key=lambda cid: (-labels.get(cid, 0), cid))


def evaluate_fixture(*, split="development", phase="development", k=6, fixture_path=FIXTURE):
    """Return reproducible metrics; holdout needs an explicit final-evaluation phase."""
    if split == "holdout" and phase != "final":
        raise ValueError("holdout is reserved for the final evaluation phase")
    fixture, fixture_hash = load_fixture(fixture_path)
    rows = []
    for query in fixture["queries"]:
        if query["split"] != split:
            continue
        ranking = rrf_ranking(query, fixture["query_routes"])
        rrf_ids = [row["canonical_id"] for row in ranking]
        labels = {row["canonical_id"]: row["grade"] for row in query["relevant"]}
        coverage = ranking_metrics(labels, rrf_ids, k=max(len(rrf_ids), 1))
        baseline = ranking_metrics(labels, rrf_ids, k=k)
        oracle = ranking_metrics(labels, oracle_ranking(query), k=k)
        rows.append({"query_id": query["query_id"], "split": split, "conditions": query["conditions"],
                     "rrf_ranking": rrf_ids, "candidate_coverage": coverage,
                     "rrf_at_k": baseline, "oracle_at_k": oracle,
                     "oracle_gain_recall": None if baseline["recall"] is None else oracle["recall"] - baseline["recall"],
                     "oracle_gain_ndcg": None if baseline["ndcg"] is None else oracle["ndcg"] - baseline["ndcg"]})
    scored = [row for row in rows if row["rrf_at_k"]["recall"] is not None]
    def mean(path):
        return sum(path(row) for row in scored) / len(scored) if scored else None
    return {"fixture_version": fixture["fixture_version"], "fixture_sha256": fixture_hash,
            "split": split, "k": k, "method": "current query_plan.fuse weighted RRF over frozen candidate routes",
            "limitation": "Synthetic fixed candidates assess ranking headroom only; this is not business retrieval validation.",
            "rows": rows, "aggregate": {"scored_queries": len(scored),
                "candidate_coverage_recall": mean(lambda row: row["candidate_coverage"]["recall"]),
                "rrf_recall_at_k": mean(lambda row: row["rrf_at_k"]["recall"]),
                "rrf_ndcg_at_k": mean(lambda row: row["rrf_at_k"]["ndcg"]),
                "oracle_recall_at_k": mean(lambda row: row["oracle_at_k"]["recall"]),
                "oracle_ndcg_at_k": mean(lambda row: row["oracle_at_k"]["ndcg"])}}


class RetrievalRerankingBaselineTests(unittest.TestCase):
    def test_development_baseline_has_full_candidate_coverage_but_rrf_headroom(self):
        result = evaluate_fixture()
        aggregate = result["aggregate"]
        self.assertEqual(aggregate["scored_queries"], 2)
        self.assertEqual(aggregate["candidate_coverage_recall"], 1.0)
        self.assertLess(aggregate["rrf_recall_at_k"], aggregate["oracle_recall_at_k"])
        self.assertLess(aggregate["rrf_ndcg_at_k"], aggregate["oracle_ndcg_at_k"])

    def test_current_fuse_deduplicates_same_candidate_within_a_route(self):
        fixture, _ = load_fixture()
        query = next(row for row in fixture["queries"] if row["query_id"] == "DEV-BILINGUAL-DEDUP")
        ranking = [row["canonical_id"] for row in rrf_ranking(query, fixture["query_routes"])]
        self.assertEqual(ranking.count("DOC-COATING-3MM"), 1)

    def test_no_answer_has_no_positive_recall_and_no_candidate(self):
        result = evaluate_fixture()
        row = next(row for row in result["rows"] if row["query_id"] == "DEV-NOANSWER")
        self.assertEqual(row["rrf_ranking"], [])
        self.assertIsNone(row["rrf_at_k"]["recall"])

    def test_holdout_requires_explicit_split(self):
        with self.assertRaises(ValueError):
            evaluate_fixture(split="holdout")
        result = evaluate_fixture(split="holdout", phase="final")
        self.assertEqual([row["query_id"] for row in result["rows"]],
                         ["HOLDOUT-NOZZLE-NEGATION", "HOLDOUT-UNKNOWN-NOT-CONFLICT"])


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Run the frozen retrieval-reranking RRF baseline.")
    parser.add_argument("--split", choices=("development", "holdout"), default="development")
    parser.add_argument("--phase", choices=("development", "final"), default="development")
    parser.add_argument("--report", type=Path, required=True, help="Output JSON path; parent directory must exist.")
    args = parser.parse_args()
    args.report.write_text(json.dumps(evaluate_fixture(split=args.split, phase=args.phase), ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
