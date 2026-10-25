"""Shared by every test directory.

When SCIRM_TEST_REPORT names a file, each test's outcome is written to it as JSON at the
end of the run, keyed by its pytest node id, for the validation pack
(scripts/validation_pack.py). A test counts as passed only if its setup, call and teardown
all passed; a failure in any phase makes it failed, and a skip (or an expected failure)
makes it skipped, never passed.
"""

import json
import os
import platform
import sys
from datetime import datetime, timezone

_OUTCOMES = {}


def pytest_runtest_logreport(report):
    if not os.environ.get("SCIRM_TEST_REPORT"):
        return
    current = _OUTCOMES.get(report.nodeid)
    if report.failed:
        _OUTCOMES[report.nodeid] = "failed"
    elif report.skipped:
        if current != "failed":
            _OUTCOMES[report.nodeid] = "skipped"
    elif report.when == "call" and current is None:
        _OUTCOMES[report.nodeid] = "passed"


def _postgres_version():
    url = os.environ.get("TEST_POSTGRES_URL")
    if not url:
        return None
    try:
        import psycopg2
        with psycopg2.connect(url) as conn, conn.cursor() as cur:
            cur.execute("SELECT version()")
            return cur.fetchone()[0]
    except Exception as exc:  # the report is still written without it
        return f"unknown ({type(exc).__name__})"


def pytest_sessionfinish(session, exitstatus):
    path = os.environ.get("SCIRM_TEST_REPORT")
    if not path:
        return
    report = {
        "backend": os.environ.get("STORE_BACKEND") or "memory",
        "finished_at": datetime.now(timezone.utc).isoformat(),
        "exit_status": int(exitstatus),
        "python": sys.version.split()[0],
        "platform": platform.platform(),
        "postgres_server": _postgres_version(),
        "args": list(session.config.invocation_params.args),
        "outcomes": dict(sorted(_OUTCOMES.items())),
    }
    os.makedirs(os.path.dirname(os.path.abspath(path)), exist_ok=True)
    with open(path, "w", encoding="utf-8") as handle:
        json.dump(report, handle, indent=1)
