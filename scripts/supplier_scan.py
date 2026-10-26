"""
Free supplier risk scan for a prospect: a CSV of suppliers in, a shareable HTML
report of their public FDA records out.

    python scripts/supplier_scan.py prospect_suppliers.csv -o scan.html --prepared-for "Acme Pharma"

By default it fetches fresh public data (FDA recalls and warning letters for the past
two years, FDA's current shortage and import-alert lists, and GDACS alerts) into
memory. Nothing is written to a database, and the prospect's list stays on this
machine. --corpus uses the committed evaluation snapshot instead (offline, for demos).

CSV: a header row with a name column ("name", "supplier", "company"...), and
optionally "country" (code or name) and "aliases" (separated by ';'). Comma or
semicolon separated, as Excel exports it.

Open the HTML in a browser and use Print -> Save as PDF for a PDF.
"""

import argparse
import asyncio
import gzip
import json
import os
import sys
from datetime import date, timedelta
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
os.environ.setdefault("ENVIRONMENT", "development")  # in-memory store only; nothing is persisted

from libs.common.store import MemoryStore  # noqa: E402
from libs.intel import scan, sources  # noqa: E402

CORPUS = ROOT / "evals" / "evidence" / "data" / "corpus.jsonl.gz"


async def load_live(days: int):
    async with sources.http_client() as client:
        results = await sources.collect(client, days)
    failed = [f"{r.source} ({r.error})" for r in results if r.status != "ok"]
    signals = [s for r in results if r.status == "ok" for s in r.signals]
    return signals, failed


def load_corpus():
    with gzip.open(CORPUS, "rt", encoding="utf-8") as f:
        meta = json.loads(f.readline())
        return [json.loads(line) for line in f if line.strip()], meta


async def main_async(args):
    text = Path(args.csv).read_text(encoding="utf-8-sig", errors="replace")
    suppliers, warnings = scan.parse_supplier_csv(text)
    if not suppliers:
        raise SystemExit("; ".join(warnings) or "No suppliers found.")
    store = MemoryStore(seed_demo=False)
    if args.corpus:
        signals, meta = load_corpus()
        coverage = f"snapshot of {meta['snapshot_date']}"
        failed = []
    else:
        print(f"Fetching public records ({args.days} days)...", file=sys.stderr)
        signals, failed = await load_live(args.days)
        coverage = (f"FDA recalls and warning letters since {(date.today() - timedelta(days=args.days)).isoformat()}; "
                    f"current FDA shortage and import-alert lists")
    if failed:
        # Never present a partial scan as complete.
        coverage += f"; UNAVAILABLE at scan time: {', '.join(failed)}"
    await store.upsert_signals(signals)
    report = await scan.run_scan(store, suppliers, coverage=coverage)
    Path(args.output).write_text(scan.render_html(report, prepared_for=args.prepared_for), encoding="utf-8")
    s = report["summary"]
    print(f"Scanned {s['scanned']} suppliers: {s['with_records']} with public records, {s['watch']} on Watch, "
          f"{s['to_check']} similar-name matches to check. Report: {args.output}", file=sys.stderr)
    for w in warnings + ([f"Sources unavailable: {', '.join(failed)}"] if failed else []):
        print(f"Note: {w}", file=sys.stderr)


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("csv")
    parser.add_argument("-o", "--output", default="supplier_scan.html")
    parser.add_argument("--prepared-for", default="")
    parser.add_argument("--days", type=int, default=730, help="history for recalls and warning letters")
    parser.add_argument("--corpus", action="store_true", help="use the committed snapshot (offline)")
    asyncio.run(main_async(parser.parse_args()))


if __name__ == "__main__":
    main()
