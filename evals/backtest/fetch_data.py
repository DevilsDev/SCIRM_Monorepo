"""
Download the history used by the back-test and save trimmed snapshots:

- data/fda_enforcement.jsonl.gz: openFDA drug recalls since 2018
- data/fda_warning_letters.jsonl.gz: FDA warning letters (FDA's index starts in
  2021); tobacco letters excluded

The snapshots are committed so results are reproducible; rerun this to refresh them.

    python evals/backtest/fetch_data.py [--since 2018]
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

DATA = Path(__file__).parent / "data"
RECALLS_OUT = DATA / "fda_enforcement.jsonl.gz"
LETTERS_OUT = DATA / "fda_warning_letters.jsonl.gz"
FIELDS = ("recall_number", "event_id", "recalling_firm", "classification", "report_date",
          "recall_initiation_date", "center_classification_date", "country", "status")


async def fetch_recalls(since_year: int):
    records = []
    async with sources.http_client() as client:
        for year in range(since_year, date.today().year + 1):
            batch = await sources._openfda_all(client, "/drug/enforcement.json",
                                               f"report_date:[{year}0101 TO {year}1231]")
            print(f"recalls {year}: {len(batch)}", file=sys.stderr)
            # listed_product: the recalled product maps to an FDA-listed drug (has an NDC in openFDA).
            # Tainted supplements sold as drugs usually do not; pharma buyers source listed products.
            records.extend({**{k: r.get(k) for k in FIELDS},
                            "listed_product": bool((r.get("openfda") or {}).get("product_ndc"))} for r in batch)
    records.sort(key=lambda r: (r["report_date"] or "", r["recall_number"] or ""))
    return records


async def fetch_letters():
    async with sources.http_client() as client:
        result = await sources.fetch_warning_letters(client, date(2000, 1, 1), date.today())
    letters = [{**{k: s["raw"][k] for k in ("company", "office", "subject", "letter_issue_date", "posted_date", "product_area")},
                "id": s["external_id"], "severity": s["severity"]} for s in result.signals]
    letters.sort(key=lambda r: (r["posted_date"] or "", r["id"]))
    return letters


def write(path: Path, source: str, records) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with gzip.open(path, "wt", encoding="utf-8") as f:
        f.write(json.dumps({"snapshot_date": date.today().isoformat(), "source": source}) + "\n")
        for r in records:
            f.write(json.dumps(r, separators=(",", ":")) + "\n")
    print(f"wrote {len(records)} records to {path}", file=sys.stderr)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--since", type=int, default=2018)
    args = parser.parse_args()
    write(RECALLS_OUT, "openFDA drug/enforcement", asyncio.run(fetch_recalls(args.since)))
    write(LETTERS_OUT, "fda.gov warning letters index", asyncio.run(fetch_letters()))


if __name__ == "__main__":
    main()
