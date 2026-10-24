"""
Evidence Engine quality gate, on PostgreSQL (what ships), over the committed public
corpus and both question sets (evals/evidence). Fails the build if retrieval or the
citation checker gets worse.

Thresholds sit a little below the measured results (2026-10-21: set A recall@10
0.94, event recall@10 0.96; set B 0.82 and 0.83; negatives A 9/9, B 9/10; checker
catch rate 1.00 with no false rejections), so they catch regressions without failing
on noise. Set C is not evaluated here: it is run by hand, once per retrieval change. Set B is the
honest number: it was written after retrieval was developed and has not been
tuned on.
"""

import asyncio
import importlib.util
import os
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "tests"))
import pg_support  # noqa: E402

spec = importlib.util.spec_from_file_location("scirm_evidence_eval", ROOT / "evals" / "evidence" / "run_eval.py")
evaluation = importlib.util.module_from_spec(spec)
spec.loader.exec_module(evaluation)

GATE = {
    "A_tuned_on": {"recall_at_10": 0.85, "event_recall_at_10": 0.9, "mrr": 0.85, "negatives_correct": 0.85},
    "B_held_out": {"recall_at_10": 0.78, "event_recall_at_10": 0.78, "mrr": 0.85, "negatives_correct": 0.8},
}


def test_checker_on_corrupted_answers():
    """Runs everywhere (no database): catches injected errors, never rejects correct sentences."""
    result = evaluation.eval_checker(evaluation.load_corpus(), n=400)
    assert result["false_rejections"] == 0, result["false_rejection_examples"]
    assert result["overall_catch_rate"] >= 0.98
    for name, r in result["corruptions"].items():
        if r["applied"] >= 10:
            assert r["catch_rate"] >= 0.95, (name, r)


@pytest.mark.skipif(not pg_support.postgres_url(), reason="TEST_POSTGRES_URL not set")
def test_retrieval_gate_on_postgres():
    urls = pg_support.fresh_database("scirm_test_evidence", seed_demo=False)
    os.environ["DB_POOL"] = "null"
    from libs.common.store import PostgresStore

    async def go():
        store = PostgresStore(urls["app"])
        try:
            return await evaluation.run(store, sets=list(GATE))
        finally:
            await store.close()

    result = asyncio.run(go())
    print("\n" + evaluation.report(result))
    for name, floors in GATE.items():
        measured = result["retrieval"][name]
        for metric, floor in floors.items():
            assert measured[metric] >= floor, (name, metric, measured[metric], floor)
