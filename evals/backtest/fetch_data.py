"""
Download the openFDA drug recall history used by the back-test and save a
trimmed snapshot (data/fda_enforcement.jsonl.gz). The snapshot is committed so
results are reproducible; rerun this to refresh it.

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

OUT = Path(__file__).parent / "data" / "fda_enforcement.jsonl.gz"
FIELDS = ("recall_number", "event_id", "recalling_firm", "classification", "report_date",
          "recall_initiation_date", "center_classification_date", "country", "status")


async def fetch(since_year: int):
    records = []
    async with sources.http_client() as client:
        for year in range(since_year, date.today().year + 1):
            batch = await sources._openfda_all(client, "/drug/enforcement.json",
                                               f"report_date:[{year}0101 TO {year}1231]")
            print(f"{year}: {len(batch)} records", file=sys.stderr)
            records.extend({k: r.get(k) for k in FIELDS} for r in batch)
    return records


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--since", type=int, default=2018)
    args = parser.parse_args()
    records = asyncio.run(fetch(args.since))
    records.sort(key=lambda r: (r["report_date"] or "", r["recall_number"] or ""))
    OUT.parent.mkdir(parents=True, exist_ok=True)
    with gzip.open(OUT, "wt", encoding="utf-8") as f:
        f.write(json.dumps({"snapshot_date": date.today().isoformat(), "source": "openFDA drug/enforcement"}) + "\n")
        for r in records:
            f.write(json.dumps(r, separators=(",", ":")) + "\n")
    print(f"wrote {len(records)} records to {OUT}", file=sys.stderr)


if __name__ == "__main__":
    main()
