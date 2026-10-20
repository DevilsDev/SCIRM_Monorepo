"""
Evidence Engine evaluation on public data. This is a synthetic set built from FDA
and GDACS records, not the partner-labelled gold set the roadmap calls for.

1. Retrieval (questions.json, written separately from the retrieval code): for
   each question about a supplier, does keyword retrieval return the records a
   relevance rule over the raw FDA fields marks as relevant?
   - recall@10 and MRR on questions with relevant records;
   - for questions whose correct answer is "nothing matches", whether the engine
     answers "no records" or "insufficient evidence" instead of citing records.
2. Citation checker: correct sentences composed from records, then the same
   sentences corrupted on purpose (wrong date, firm, recall class, number, record
   type, citation, or none). Reports how many corruptions the checker catches and
   how many correct sentences it wrongly rejects.

    python evals/evidence/run_eval.py            # in-memory store (development)
    TEST_POSTGRES_URL=... python evals/evidence/run_eval.py --postgres   # what ships
"""

import argparse
import asyncio
import gzip
import json
import random
import re
import sys
from datetime import date, timedelta
from pathlib import Path
from typing import Any, Dict, List

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from libs.evidence import answer, retrieval, verify  # noqa: E402
from libs.intel import matching  # noqa: E402

HERE = Path(__file__).parent
CORPUS = HERE / "data" / "corpus.jsonl.gz"
# Set A was used while developing retrieval; set B was written afterwards and never tuned
# on, so B is the honest number. Both were written without access to the retrieval code.
QUESTION_SETS = {"A_tuned_on": HERE / "questions.json", "B_held_out": HERE / "questions_b.json",
                 # Written before vector search was tuned; the honest number for hybrid retrieval.
                 "C_held_out": HERE / "questions_c.json"}
K = 10


def load_corpus() -> List[Dict[str, Any]]:
    with gzip.open(CORPUS, "rt", encoding="utf-8") as f:
        f.readline()
        return [json.loads(line) for line in f if line.strip()]


def load_questions(name: str = "A_tuned_on") -> List[Dict[str, Any]]:
    path = QUESTION_SETS[name]
    return json.loads(path.read_text(encoding="utf-8")) if path.exists() else []


def relevant_ids(question: Dict[str, Any], corpus: List[Dict[str, Any]]) -> set:
    """The labelling rule, applied to raw record fields (independent of retrieval)."""
    rule = question["relevant"]
    patterns = [re.compile(p, re.IGNORECASE) for p in rule["any_regex"]]
    sources = set(rule.get("sources") or [])
    supplier = {"name": question["supplier"]}
    out = set()
    for r in corpus:
        if sources and r["source"] not in sources:
            continue
        m = matching.match_supplier(supplier, r)
        if not m or m["kind"] != "incident" or m["confidence"] < 0.6:
            continue
        fields = [r.get("title") or "", r.get("summary") or ""] + [str(v) for v in (r.get("raw") or {}).values()]
        if any(p.search(f) for p in patterns for f in fields):
            out.add((r["source"], r["external_id"]))
    return out


async def eval_retrieval(store, corpus, questions, embedder=None) -> Dict[str, Any]:
    rows = []
    # One FDA recall event is often many records (one per strength or pack). Event recall
    # asks how many of the distinct relevant events the top K covers; record recall
    # rewards returning the same event's records over and over.
    events = {(r["source"], r["external_id"]): matching.event_key(r) for r in corpus}
    for q in questions:
        relevant = relevant_ids(q, corpus)
        supplier = {"name": q["supplier"]}
        got = await retrieval.retrieve(store, q["question"], supplier, k=K, embedder=embedder)
        ids = [(x["record"]["source"], x["record"]["external_id"]) for x in got["results"]]
        if relevant:
            hits = [i for i in ids if i in relevant]
            first = next((n for n, i in enumerate(ids, 1) if i in relevant), None)
            # Recall@10 is capped by K: a question with 25 relevant records can find at most 10.
            denom = min(len(relevant), K)
            relevant_events = {events[i] for i in relevant}
            hit_events = {events[i] for i in hits}
            rows.append({"id": q["id"], "positive": True, "relevant": len(relevant), "recall": len(hits) / denom,
                         "event_recall": len(hit_events) / min(len(relevant_events), K),
                         "rr": 1 / first if first else 0.0, "returned": len(ids)})
        else:
            count = 0 if got["results"] else await retrieval.supplier_record_count(store, supplier)
            composed = await answer.compose(q["question"], supplier, got, count, use_llm=False)
            # Correct: nothing cited. Wrong: records returned for a topic the supplier has none of.
            rows.append({"id": q["id"], "positive": False, "returned": len(ids), "status": composed["status"],
                         "correct": not ids})
    pos = [r for r in rows if r["positive"]]
    neg = [r for r in rows if not r["positive"]]
    return {
        "questions": len(rows), "positives": len(pos), "negatives": len(neg),
        "recall_at_10": round(sum(r["recall"] for r in pos) / len(pos), 3) if pos else None,
        "event_recall_at_10": round(sum(r["event_recall"] for r in pos) / len(pos), 3) if pos else None,
        "mrr": round(sum(r["rr"] for r in pos) / len(pos), 3) if pos else None,
        "positives_with_no_hit": [r["id"] for r in pos if r["recall"] == 0],
        "negatives_correct": round(sum(r["correct"] for r in neg) / len(neg), 3) if neg else None,
        "negatives_wrong": [r["id"] for r in neg if not r["correct"]],
        "rows": rows,
    }


# --- citation checker -------------------------------------------------------

def _shift_date(text: str, rng: random.Random) -> str:
    found = verify.dates_in(text)
    if not found:
        return text
    d = date.fromisoformat(found[0]) + timedelta(days=rng.choice([-41, -17, 23, 58]))
    return text.replace(found[0], d.isoformat(), 1)


CORRUPTIONS = {
    "no_citation": lambda c, ctx, rng: {"text": re.sub(r"\s*\[S\d+\]", "", c["text"]), "citations": []},
    "unknown_citation": lambda c, ctx, rng: {"text": c["text"], "citations": ["S99"]},
    "wrong_date": lambda c, ctx, rng: {"text": _shift_date(c["text"], rng), "citations": c["citations"]},
    "wrong_firm": lambda c, ctx, rng: {"text": c["text"].replace(ctx["firm"], ctx["other_firm"], 1),
                                       "citations": c["citations"]},
    "wrong_class": lambda c, ctx, rng: {"text": re.sub(r"Class (III|II|I)\b",
                                                       lambda m: {"I": "Class II", "II": "Class I", "III": "Class I"}[m.group(1)],
                                                       c["text"], count=1), "citations": c["citations"]},
    "wrong_number": lambda c, ctx, rng: {"text": re.sub(r"\((\d+) ", lambda m: f"({int(m.group(1)) + 7} ", c["text"], count=1),
                                                        "citations": c["citations"]},
    "wrong_type": lambda c, ctx, rng: {"text": c["text"].replace("recall", "warning letter", 1)
                                       if "recall" in c["text"] else c["text"].replace("warning letter", "recall", 1),
                                       "citations": c["citations"]},
    "wrong_citation": lambda c, ctx, rng: {"text": re.sub(r"\[S\d+\]", "[S2]", c["text"]), "citations": ["S2"]},
    # Meaning-changing errors made of ordinary words, the kind a language model makes.
    "negation": lambda c, ctx, rng: {"text": _first_sub(c["text"], NEGATIONS), "citations": c["citations"]},
    "overgeneralise": lambda c, ctx, rng: {"text": _first_sub(c["text"], [(" of ", " of all "), (" about ", " about all ")]),
                                           "citations": c["citations"]},
    "invented_severity": lambda c, ctx, rng: {"text": _first_sub(c["text"], [(" a Class", " a minor Class"),
                                                                             (" a warning letter", " a serious warning letter"),
                                                                             (" a shortage", " a minor shortage")]),
                                              "citations": c["citations"]},
    "invented_count": lambda c, ctx, rng: {"text": _first_sub(c["text"], [(" a Class", " three Class"),
                                                                          (" a warning letter", " three warning letters"),
                                                                          (" a shortage", " two shortages")]),
                                           "citations": c["citations"]},
    # The date of one record attached to another record's facts, citing both.
    "cross_record_mix": lambda c, ctx, rng: {"text": _swap_date(c["text"], ctx["other_date"]) + " [S2]",
                                             "citations": c["citations"] + ["S2"]},
}
NEGATIONS = [("FDA published", "FDA never published"), ("FDA posted", "FDA never posted"),
             ("FDA has listed", "FDA has never listed"), ("has been on", "has never been on")]


def _first_sub(text: str, pairs) -> str:
    for old, new in pairs:
        if old in text:
            return text.replace(old, new, 1)
    return text


def _swap_date(text: str, other: str) -> str:
    found = verify.dates_in(text)
    return text.replace(found[0], other, 1) if found and other and other != found[0] else text


def eval_checker(corpus, n: int = 400, seed: int = 7) -> Dict[str, Any]:
    """Correct sentences from real records, then corrupted copies; who catches what."""
    rng = random.Random(seed)
    company_records = [r for r in corpus if r.get("entity_names") and r["signal_type"] != "disaster"]
    sample = rng.sample(company_records, min(n, len(company_records)))
    firms = sorted({r["entity_names"][0] for r in company_records})
    normalized = {f: matching.normalize(f) for f in firms}
    results = {name: {"applied": 0, "caught": 0} for name in CORRUPTIONS}
    false_rejections = []
    for record in sample:
        firm = record["entity_names"][0]
        # S2 is an unrelated record from a different firm, for the wrong-citation case.
        other = rng.choice([r for r in rng.sample(company_records, 20) if r["entity_names"][0] != firm] or company_records)
        evidence = {"S1": record, "S2": other}
        claim = {"text": f"{answer.describe(record, firm)} [S1]", "citations": ["S1"]}
        if verify.check_claim(claim["text"], claim["citations"], evidence):
            false_rejections.append(claim["text"])
            continue
        other_firm = rng.choice(firms)
        while normalized[other_firm] == normalized[firm]:
            other_firm = rng.choice(firms)
        ctx = {"firm": firm, "other_firm": other_firm, "other_date": str(other.get("published_at"))[:10]}
        for name, corrupt in CORRUPTIONS.items():
            bad = corrupt(claim, ctx, rng)
            if bad["text"] == claim["text"] and bad["citations"] == claim["citations"]:
                continue  # this corruption does not apply to this sentence (e.g. no number in it)
            if name == "wrong_firm" and firm not in claim["text"]:
                continue
            results[name]["applied"] += 1
            results[name]["caught"] += bool(verify.check_claim(bad["text"], bad["citations"], evidence))
    for r in results.values():
        r["catch_rate"] = round(r["caught"] / r["applied"], 3) if r["applied"] else None
    applied = sum(r["applied"] for r in results.values())
    caught = sum(r["caught"] for r in results.values())
    return {"sentences": len(sample), "false_rejections": len(false_rejections),
            "false_rejection_examples": false_rejections[:5],
            "corruptions": results, "overall_catch_rate": round(caught / applied, 3) if applied else None}


async def embed_corpus(store, embedder) -> int:
    from libs.common.store import text_hash
    from libs.evidence.embeddings import document_text
    done = 0
    while True:
        pending = await store.signals_needing_embedding(embedder.model_id, limit=500)
        if not pending:
            return done
        vectors = await embedder.embed_documents([document_text(r) for r in pending])
        written = await store.set_embeddings([(r["id"], text_hash(r), v) for r, v in zip(pending, vectors)],
                                             embedder.model_id)
        done += written
        if not written:
            return done


async def run(store, embedder=None, sets=None) -> Dict[str, Any]:
    corpus = load_corpus()
    await store.upsert_signals(corpus)
    embedded = await embed_corpus(store, embedder) if embedder else 0
    retrieval_results = {}
    for name in sets or QUESTION_SETS:
        questions = load_questions(name)
        if questions:
            retrieval_results[name] = await eval_retrieval(store, corpus, questions, embedder)
    return {"retrieval": retrieval_results, "checker": eval_checker(corpus), "corpus": len(corpus),
            "retrieval_mode": f"hybrid ({embedder.model_id}, {embedded} records embedded)" if embedder else "keyword"}


def report(result: Dict[str, Any]) -> str:
    lines = [f"Evidence Engine evaluation on public data ({result['corpus']} records; synthetic, not partner-labelled); "
             f"retrieval: {result.get('retrieval_mode', 'keyword')}"]
    for name, r in result["retrieval"].items():
        lines += [f"Retrieval, set {name}: {r['positives']} questions with relevant records, "
                  f"recall@10 {r['recall_at_10']}, event recall@10 {r['event_recall_at_10']}, MRR {r['mrr']}; no hit at all: {r['positives_with_no_hit'] or 'none'}",
                  f"  {r['negatives']} 'nothing matches' questions answered without citing records: {r['negatives_correct']}"
                  f" (wrong: {r['negatives_wrong'] or 'none'})"]
    c = result["checker"]
    lines.append(f"Citation checker: {c['sentences']} correct sentences, {c['false_rejections']} wrongly rejected; "
                 f"corruptions caught overall {c['overall_catch_rate']}")
    for name, v in c["corruptions"].items():
        lines.append(f"  {name:16} caught {v['caught']}/{v['applied']} ({v['catch_rate']})")
    return "\n".join(lines)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--postgres", action="store_true", help="evaluate on PostgreSQL (needs TEST_POSTGRES_URL)")
    parser.add_argument("--json", type=Path)
    parser.add_argument("--vectors", action="store_true",
                        help="hybrid retrieval with the configured embedder (EMBEDDINGS_PROVIDER=bedrock, AWS access); "
                             "needs --postgres")
    parser.add_argument("--sets", nargs="+", choices=list(QUESTION_SETS),
                        help="question sets to evaluate (default: all). While changing retrieval, use only "
                             "A_tuned_on and B_held_out; run C_held_out once, after the change is decided.")
    args = parser.parse_args()

    app_url = None
    if args.postgres:  # migrations run their own event loop, so set up the database first
        import os
        sys.path.insert(0, str(ROOT / "tests"))
        import pg_support
        app_url = pg_support.fresh_database("scirm_eval_evidence", seed_demo=False)["app"]
        os.environ["DB_POOL"] = "null"

    embedder = None
    if args.vectors:
        from libs.evidence.embeddings import get_embedder
        embedder = get_embedder()
        if embedder is None or not app_url:
            raise SystemExit("--vectors needs --postgres and EMBEDDINGS_PROVIDER=bedrock with EU model access")

    async def go():
        if app_url:
            from libs.common.store import PostgresStore
            store = PostgresStore(app_url)
        else:
            from libs.common.store import MemoryStore
            store = MemoryStore(seed_demo=False)
        try:
            return await run(store, embedder, args.sets)
        finally:
            await store.close()

    result = asyncio.run(go())
    print(report(result))
    if args.json:
        args.json.write_text(json.dumps(result, indent=2, default=str) + "\n", encoding="utf-8")


if __name__ == "__main__":
    main()
