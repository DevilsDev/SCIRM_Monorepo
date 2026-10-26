# Validation pack

If you use SCIRM for records that regulations cover, you validate it for your intended use.
Examples are signed supplier assessments under 21 CFR Part 11 and due diligence
documentation under the LkSG. The validation pack is evidence to support that work. It
shows which automated tests ran against a given version of SCIRM, on which database, and
their outcome, traced to the requirements they demonstrate. It does not establish that
SCIRM is validated for your use: that conclusion is yours.

A risk-based approach such as FDA's *Computer Software Assurance for Production and Quality
Management System Software* (final guidance, February 2026) lets you rely on a supplier's
testing like this where the risk allows. You then focus your own testing on how you
configure and use SCIRM.

## What it contains

| File | What it is |
|---|---|
| `matrix.md`, `matrix.csv` | The traceability matrix: each requirement, its regulation reference, the tests that show it, the backend each test ran on, and the outcome. |
| `requirements.json` | The same, machine-readable. |
| `reports/memory.json`, `reports/postgres.json` | Every test's outcome from the two CI test runs (in-memory store and PostgreSQL). |
| `reports/*-junit.xml` | The same runs in JUnit format. |
| `environment.json` | Commit, CI run and link, database migration head, PostgreSQL server version, Python versions, installed packages, and times. |
| `MANIFEST.sha256` | The SHA-256 of every other file, to check nothing was changed (`sha256sum -c MANIFEST.sha256`). |

## How to read the matrix

- **passed**: every test mapped to the requirement passed on every backend it must pass
  on. Controls the database enforces, such as append-only tables, row-level security and
  refused deletes, must pass on PostgreSQL. API behaviour must pass on both backends.
- **failed**: at least one of those tests failed.
- **not shown**: a test was skipped or did not run. That is not counted as passed.
- **customer procedure**: a duty SCIRM cannot test, for example verifying identity before
  issuing electronic signatures (21 CFR 11.100(b)), the certification letter to FDA
  (11.100(c)), training, and your own validation. It is listed so the matrix is complete.

The requirements cover the controls described in
[electronic signatures](electronic-signatures.md), the audit trail, access and tenant
isolation, records that must be kept, the limits on AI agents, API keys, and
[due diligence](due-diligence.md). The list is in `libs/validation/requirements.py`. A test
in the repository checks that every test it names exists.

## Getting it

The pack is built by the **Validation pack** job of the CI workflow, from the reports of the
test runs in the same workflow run; it never runs the tests again. It is published as the
artifact `validation-pack-<commit>` and kept for 90 days. GitHub artifacts need a signed-in
account with access to the repository. Download the pack for the version you deploy and
keep it with your validation records. The job fails if any tested requirement is not
passed.

The pack is not built for the `main` branch: releases are a separate decision.

To build it yourself from your own test runs:

```bash
SCIRM_TEST_REPORT=reports/memory.json pytest tests/security tests/ai_trust tests/intel \
  tests/evidence tests/erp tests/scenarios tests/validation --junitxml=reports/memory-junit.xml
SCIRM_TEST_REPORT=reports/postgres.json STORE_BACKEND=postgres TEST_POSTGRES_URL=... \
  pytest tests/security tests/db tests/evidence --junitxml=reports/postgres-junit.xml
python scripts/validation_pack.py --report memory=reports/memory.json \
  --report postgres=reports/postgres.json --evidence reports/memory-junit.xml \
  --evidence reports/postgres-junit.xml --out validation-pack
```
