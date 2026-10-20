"""Write each service's OpenAPI spec to a folder (default docs-build/api-specs).

Services are loaded by file path: their folders (api-gateway, risk-scorer, ...) are not
importable package names. Run with ENVIRONMENT=test so no secrets are needed.

    ENVIRONMENT=test python scripts/export_openapi.py [out_dir]
"""

import importlib.util
import json
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SERVICES = {
    "gateway": "apps/api-gateway/main.py",
    "coordinator": "services/coordinator/main.py",
    "ingestion": "services/ingestion/main.py",
    "chat": "services/chat/main.py",
    "planner": "services/planner/main.py",
    "researcher": "services/researcher/main.py",
    "executor": "services/executor/main.py",
    "reviewer": "services/reviewer/main.py",
    "risk-scorer": "services/risk-scorer/main.py",
    "discovery": "services/discovery/main.py",
    "procurement": "services/procurement/main.py",
    "simulator": "services/simulator/main.py",
    "component-tracker": "services/component-tracker/main.py",
}


def main() -> int:
    out = Path(sys.argv[1] if len(sys.argv) > 1 else ROOT / "docs-build" / "api-specs")
    out.mkdir(parents=True, exist_ok=True)
    sys.path.insert(0, str(ROOT))
    os.environ.setdefault("ENVIRONMENT", "test")
    failed = []
    for name, rel in SERVICES.items():
        try:
            spec = importlib.util.spec_from_file_location(f"openapi_{name.replace('-', '_')}", ROOT / rel)
            module = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(module)
            (out / f"{name}.json").write_text(json.dumps(module.app.openapi(), indent=2), encoding="utf-8")
            print(f"{name}: {len(module.app.openapi().get('paths', {}))} paths")
        except Exception as exc:  # report every service, then fail
            failed.append(name)
            print(f"{name}: FAILED ({type(exc).__name__}: {exc})", file=sys.stderr)
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
