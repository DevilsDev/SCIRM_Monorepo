"""
The validation pack: every requirement traces to tests that exist, and the builder reports
what the test runs showed (a skipped or missing test never counts as passed), with a
manifest that verifies every file.
"""

import ast
import hashlib
import importlib.util
import json
import zipfile
from pathlib import Path

import pytest

from libs.validation.requirements import REQUIREMENTS

ROOT = Path(__file__).resolve().parents[2]
spec = importlib.util.spec_from_file_location("validation_pack", ROOT / "scripts" / "validation_pack.py")
pack = importlib.util.module_from_spec(spec)
spec.loader.exec_module(pack)


def node_ids(path: Path) -> set:
    """Test node ids defined in a file: module-level test functions and Test* class methods."""
    tree = ast.parse(path.read_text(encoding="utf-8"))
    rel = path.relative_to(ROOT).as_posix()
    found = set()
    for item in tree.body:
        if isinstance(item, (ast.FunctionDef, ast.AsyncFunctionDef)) and item.name.startswith("test_"):
            found.add(f"{rel}::{item.name}")
        elif isinstance(item, ast.ClassDef) and item.name.startswith("Test"):
            for member in item.body:
                if isinstance(member, (ast.FunctionDef, ast.AsyncFunctionDef)) and member.name.startswith("test_"):
                    found.add(f"{rel}::{item.name}::{member.name}")
    return found


def all_nodes():
    return [t["node"] for r in REQUIREMENTS for t in r["tests"]]


def test_every_mapped_test_exists():
    files = {node.split("::", 1)[0] for node in all_nodes()}
    defined = set().union(*(node_ids(ROOT / f) for f in files))
    missing = sorted(set(all_nodes()) - defined)
    assert not missing, missing


def test_the_catalogue_is_well_formed():
    ids = [r["id"] for r in REQUIREMENTS]
    assert len(ids) == len(set(ids))
    for r in REQUIREMENTS:
        assert r["title"] and r["refs"], r["id"]
        assert r["tests"] or r["note"].startswith("Customer procedure"), r["id"]
        for t in r["tests"]:
            assert t["backend"] in ("both", "postgres", "memory"), r["id"]
            # Database-level tests only run on PostgreSQL.
            assert not t["node"].startswith("tests/db/") or t["backend"] == "postgres", t["node"]
    # Every Part 11 row of docs/electronic-signatures.md is traced.
    refs = {ref for r in REQUIREMENTS for ref in r["refs"]}
    for section in ("11.50", "11.70", "11.100(a)", "11.100(b)", "11.100(c)", "11.200(a)(1)", "11.200(a)(2)",
                    "11.200(a)(3)"):
        assert f"21 CFR {section}" in refs, section


REQS = [
    {"id": "A", "title": "a", "refs": ["x"], "note": "", "tests": [{"node": "t::one", "backend": "both"}]},
    {"id": "B", "title": "b", "refs": ["x"], "note": "", "tests": [{"node": "t::db", "backend": "postgres"}]},
    {"id": "C", "title": "c", "refs": ["x"], "note": "Customer procedure, not tested.", "tests": []},
]


@pytest.mark.parametrize("memory,postgres,expected", [
    ({"t::one": "passed"}, {"t::one": "passed", "t::db": "passed"}, ["passed", "passed"]),
    ({"t::one": "passed"}, {"t::one": "failed", "t::db": "passed"}, ["failed", "passed"]),
    ({"t::one": "skipped"}, {"t::one": "passed", "t::db": "skipped"}, ["not shown", "not shown"]),
    ({}, {"t::one": "passed"}, ["not shown", "not shown"]),  # missing
])
def test_a_requirement_passes_only_if_every_test_passed_on_every_backend(memory, postgres, expected):
    rows = pack.evaluate(REQS, {"memory": {"outcomes": memory}, "postgres": {"outcomes": postgres}})
    assert [r["status"] for r in rows] == expected + ["customer procedure"]
    checks = rows[0]["checks"]
    assert [c["backend"] for c in checks] == ["memory", "postgres"]


def test_a_parametrized_test_passes_only_if_every_case_passed():
    assert pack.outcome_of({"t::p[a]": "passed", "t::p[b]": "passed"}, "t::p") == "passed"
    assert pack.outcome_of({"t::p[a]": "passed", "t::p[b]": "skipped"}, "t::p") == "skipped"
    assert pack.outcome_of({"t::p[a]": "skipped", "t::p[b]": "failed"}, "t::p") == "failed"
    assert pack.outcome_of({"t::pp[a]": "passed"}, "t::p") == "missing"
    assert pack.outcome_of({"t::p": "passed"}, "t::p") == "passed"


def _report(tmp_path, name, outcomes):
    path = tmp_path / f"{name}.json"
    path.write_text(json.dumps({"backend": name, "outcomes": outcomes}), encoding="utf-8")
    return path


def test_the_pack_holds_the_matrix_the_evidence_and_a_manifest_that_verifies(tmp_path):
    passed = {node: "passed" for node in all_nodes()}
    junit = tmp_path / "memory-junit.xml"
    junit.write_text("<testsuites/>", encoding="utf-8")
    out = tmp_path / "pack"
    status = pack.main(["--report", f"memory={_report(tmp_path, 'memory', passed)}",
                        "--report", f"postgres={_report(tmp_path, 'postgres', passed)}",
                        "--evidence", str(junit), "--out", str(out)])
    assert status == 0
    files = {p.relative_to(out).as_posix() for p in out.rglob("*") if p.is_file()}
    assert {"matrix.csv", "matrix.md", "requirements.json", "environment.json", "MANIFEST.sha256",
            "reports/memory.json", "reports/postgres.json", "reports/memory-junit.xml"} <= files
    manifest = (out / "MANIFEST.sha256").read_text(encoding="utf-8").splitlines()
    listed = {}
    for line in manifest:
        digest, name = line.split("  ", 1)
        listed[name] = digest
    assert set(listed) == files - {"MANIFEST.sha256"}
    for name, digest in listed.items():
        assert hashlib.sha256((out / name).read_bytes()).hexdigest() == digest, name
    with zipfile.ZipFile(out.with_suffix(".zip")) as zf:
        assert set(zf.namelist()) == files
    env = json.loads((out / "environment.json").read_text(encoding="utf-8"))
    assert env["commit"] and env["alembic_head"] and env["test_runs"]["postgres"]["tests"] == len(passed)
    matrix = (out / "matrix.md").read_text(encoding="utf-8")
    assert "does not establish that SCIRM is validated" in matrix and "customer procedure" in matrix


def test_the_builder_fails_when_a_tested_requirement_is_not_passed(tmp_path):
    outcomes = {node: "passed" for node in all_nodes()}
    outcomes[REQUIREMENTS[0]["tests"][0]["node"]] = "skipped"
    status = pack.main(["--report", f"memory={_report(tmp_path, 'memory', outcomes)}",
                        "--report", f"postgres={_report(tmp_path, 'postgres', outcomes)}",
                        "--out", str(tmp_path / "pack")])
    assert status == 1
    rows = json.loads((tmp_path / "pack" / "requirements.json").read_text(encoding="utf-8"))
    assert rows[0]["status"] == "not shown"
