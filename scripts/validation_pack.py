"""Build the validation pack: evidence from the CI test runs, traced to requirements.

    python scripts/validation_pack.py --report memory=reports/memory.json \
        --report postgres=reports/postgres.json --evidence reports/ --out validation-pack

Reads the per-test reports the test runs wrote (SCIRM_TEST_REPORT, tests/conftest.py); it
never runs tests itself, so the pack shows what those runs did. For each requirement in
libs/validation/requirements.py it looks up every mapped test on every backend it must pass
on. A requirement is passed only when all of them passed; otherwise it shows failed,
skipped or missing as they are. Customer procedures are listed and marked as such.

The pack (a folder and a zip of it) holds the traceability matrix (CSV and Markdown), the
raw reports and any other evidence files given, environment.json, and MANIFEST.sha256 with
the SHA-256 of every other file. Exit status 1 if any tested requirement is not passed.
"""

import argparse
import csv
import hashlib
import io
import json
import os
import platform
import shutil
import subprocess
import sys
import zipfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Tuple

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from libs.validation.requirements import REQUIREMENTS  # noqa: E402

BACKENDS = ("memory", "postgres")
PROCEDURE = "customer procedure"


def backends_for(spec: str) -> Tuple[str, ...]:
    return BACKENDS if spec == "both" else (spec,)


def outcome_of(outcomes: Dict[str, str], node: str) -> str:
    """A test's outcome. A parametrized test has one node id per case (node[case]): it
    passed only if every case passed."""
    if node in outcomes:
        return outcomes[node]
    cases = [v for k, v in outcomes.items() if k.startswith(node + "[")]
    if not cases:
        return "missing"
    for result in ("failed", "skipped"):
        if result in cases:
            return result
    return "passed"


def evaluate(requirements: List[Dict[str, Any]], reports: Dict[str, Dict[str, Any]]) -> List[Dict[str, Any]]:
    """Each requirement with a status and the outcome of every mapped test on every backend."""
    rows = []
    for req in requirements:
        checks = []
        for test in req["tests"]:
            for backend in backends_for(test["backend"]):
                outcomes = (reports.get(backend) or {}).get("outcomes") or {}
                checks.append({"node": test["node"], "backend": backend,
                               "outcome": outcome_of(outcomes, test["node"])})
        if not req["tests"]:
            status = PROCEDURE
        elif all(c["outcome"] == "passed" for c in checks):
            status = "passed"
        elif any(c["outcome"] == "failed" for c in checks):
            status = "failed"
        else:
            status = "not shown"  # skipped or missing somewhere, nothing failed
        rows.append({**req, "status": status, "checks": checks})
    return rows


def _git(*args: str) -> str:
    try:
        return subprocess.run(["git", *args], cwd=ROOT, capture_output=True, text=True, timeout=30).stdout.strip()
    except Exception:
        return ""


def _alembic_head() -> str:
    try:
        from alembic.config import Config
        from alembic.script import ScriptDirectory
        return ",".join(ScriptDirectory.from_config(Config(str(ROOT / "alembic.ini"))).get_heads())
    except Exception as exc:
        return f"unknown ({type(exc).__name__})"


def environment(reports: Dict[str, Dict[str, Any]]) -> Dict[str, Any]:
    server, repo, run = (os.environ.get(k) for k in ("GITHUB_SERVER_URL", "GITHUB_REPOSITORY", "GITHUB_RUN_ID"))
    try:
        freeze = subprocess.run([sys.executable, "-m", "pip", "freeze"], capture_output=True, text=True,
                                timeout=120).stdout.splitlines()
    except Exception:
        freeze = []
    return {
        "built_at": datetime.now(timezone.utc).isoformat(),
        "commit": os.environ.get("GITHUB_SHA") or _git("rev-parse", "HEAD"),
        "ref": os.environ.get("GITHUB_REF") or _git("rev-parse", "--abbrev-ref", "HEAD"),
        "ci_run": {"id": run, "url": f"{server}/{repo}/actions/runs/{run}" if server and repo and run else None},
        "alembic_head": _alembic_head(),
        "builder_python": platform.python_version(),
        # Installed from the same requirements-test.txt as the test runs.
        "builder_pip_freeze": freeze,
        "test_runs": {b: {k: r.get(k) for k in ("backend", "finished_at", "exit_status", "python", "platform",
                                                  "postgres_server", "args")} | {"tests": len(r.get("outcomes") or {})}
                      for b, r in reports.items()},
    }


def matrix_csv(rows: List[Dict[str, Any]]) -> str:
    out = io.StringIO()
    writer = csv.writer(out)
    writer.writerow(["requirement", "status", "regulation", "requirement_text", "test", "backend", "outcome", "note"])
    for row in rows:
        refs = "; ".join(row["refs"])
        if not row["checks"]:
            writer.writerow([row["id"], row["status"], refs, row["title"], "", "", "", row["note"]])
        for check in row["checks"]:
            writer.writerow([row["id"], row["status"], refs, row["title"], check["node"], check["backend"],
                             check["outcome"], row["note"]])
    return out.getvalue()


def matrix_markdown(rows: List[Dict[str, Any]], env: Dict[str, Any]) -> str:
    counts: Dict[str, int] = {}
    for row in rows:
        counts[row["status"]] = counts.get(row["status"], 0) + 1
    lines = ["# SCIRM validation pack: traceability matrix", "",
             f"Commit `{env['commit']}`, database migrations at `{env['alembic_head']}`, built {env['built_at']}.",
             f"CI run: {env['ci_run']['url'] or 'local build'}.", "",
             "Evidence to support your validation: it shows which automated tests ran, on which backend, and "
             "their outcome. It does not establish that SCIRM is validated for your intended use.", "",
             "Summary: " + ", ".join(f"{n} {s}" for s, n in sorted(counts.items())), "",
             "| Requirement | Status | Regulation | Requirement | Evidence |", "|---|---|---|---|---|"]
    for row in rows:
        evidence = "<br>".join(f"`{c['node'].split('::', 1)[1]}` ({c['backend']}): {c['outcome']}" for c in row["checks"]) \
            or row["note"]
        lines.append(f"| {row['id']} | {row['status']} | {'; '.join(row['refs'])} | {row['title']} | {evidence} |")
    return "\n".join(lines) + "\n"


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with open(path, "rb") as handle:
        for block in iter(lambda: handle.read(65536), b""):
            digest.update(block)
    return digest.hexdigest()


def build(reports: Dict[str, Path], evidence: List[Path], out: Path) -> Tuple[List[Dict[str, Any]], Path]:
    loaded = {name: json.loads(path.read_text(encoding="utf-8")) for name, path in reports.items()}
    rows = evaluate(REQUIREMENTS, loaded)
    env = environment(loaded)
    if out.exists():
        shutil.rmtree(out)
    (out / "reports").mkdir(parents=True)
    (out / "matrix.csv").write_text(matrix_csv(rows), encoding="utf-8", newline="\n")
    (out / "matrix.md").write_text(matrix_markdown(rows, env), encoding="utf-8", newline="\n")
    (out / "requirements.json").write_text(json.dumps(rows, indent=1), encoding="utf-8", newline="\n")
    (out / "environment.json").write_text(json.dumps(env, indent=1), encoding="utf-8", newline="\n")
    for name, path in reports.items():
        shutil.copyfile(path, out / "reports" / f"{name}.json")
    for path in evidence:
        for item in ([path] if path.is_file() else sorted(p for p in path.rglob("*") if p.is_file())):
            target = out / "reports" / item.name
            if not target.exists():
                shutil.copyfile(item, target)
    files = sorted(p for p in out.rglob("*") if p.is_file())
    manifest = "".join(f"{sha256(p)}  {p.relative_to(out).as_posix()}\n" for p in files)
    (out / "MANIFEST.sha256").write_text(manifest, encoding="utf-8", newline="\n")
    archive = out.with_suffix(".zip")
    with zipfile.ZipFile(archive, "w", zipfile.ZIP_DEFLATED) as zf:
        for p in sorted(out.rglob("*")):
            if p.is_file():
                zf.write(p, p.relative_to(out).as_posix())
    return rows, archive


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("--report", action="append", required=True, metavar="BACKEND=PATH",
                        help="a per-test report written by a test run (memory=..., postgres=...)")
    parser.add_argument("--evidence", action="append", default=[], type=Path,
                        help="other files or folders to include, for example JUnit XML")
    parser.add_argument("--out", type=Path, default=Path("validation-pack"))
    args = parser.parse_args(argv)
    reports = {}
    for item in args.report:
        name, _, path = item.partition("=")
        if name not in BACKENDS or not path:
            parser.error(f"--report takes memory=PATH or postgres=PATH, not {item!r}")
        reports[name] = Path(path)
    rows, archive = build(reports, args.evidence, args.out)
    not_passed = [r for r in rows if r["status"] not in ("passed", PROCEDURE)]
    for row in rows:
        print(f"{row['id']:<12} {row['status']}")
    print(f"Pack: {archive}")
    if not_passed:
        print(f"{len(not_passed)} tested requirement(s) not passed: {', '.join(r['id'] for r in not_passed)}",
              file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
