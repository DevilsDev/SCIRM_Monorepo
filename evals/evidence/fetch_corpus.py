"""
Snapshot the public signals (all five sources, last two years) used to evaluate
the Evidence Engine: data/corpus.jsonl.gz. Committed so the evaluation is
reproducible; rerun to refresh it.

    python evals/evidence/fetch_corpus.py [--days 730]
"""

import argparse
import asyncio
import gzip
import json
import sys
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from libs.intel import sources  # noqa: E402

OUT = Path(__file__).parent / "data" / "corpus.jsonl.gz"


async def fetch(days: int):
    async with sources.http_client() as client:
        results = await sources.collect(client, days)
    for r in results:
        print(f"{r.source}: {r.status} {len(r.signals)}", file=sys.stderr)
        if r.status != "ok":
            raise SystemExit(f"{r.source} failed ({r.error}); not writing a partial corpus")
    return [s for r in results for s in r.signals]


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--days", type=int, default=730)
    args = parser.parse_args()
    signals = sorted(asyncio.run(fetch(args.days)), key=lambda s: (s["source"], s["external_id"]))
    OUT.parent.mkdir(parents=True, exist_ok=True)
    with gzip.open(OUT, "wt", encoding="utf-8") as f:
        f.write(json.dumps({"snapshot_date": date.today().isoformat(), "days": args.days}) + "\n")
        for s in signals:
            f.write(json.dumps(s, separators=(",", ":"), default=str) + "\n")
    print(f"wrote {len(signals)} signals to {OUT}", file=sys.stderr)


if __name__ == "__main__":
    main()
