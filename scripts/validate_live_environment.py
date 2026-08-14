#!/usr/bin/env python3
"""Evaluate live readiness from outside the process, and write the record.

This is the operator's view of the same question the in-process activation gate answers:
*is this deployment ready to touch real money?* It runs standalone — no API server needed
— and writes ``data/runtime/live_readiness.json`` with every check's verdict, separating
two categories that must never be blurred:

* **VALIDATED** — executed here, in this environment, with the evidence named.
* **EXTERNAL_REQUIRED** — cannot be executed from this environment (no venue egress, no
  Docker daemon, ...) and is honestly labelled as such rather than guessed.

UNKNOWN counts as FAILED, in both this script and the gate it mirrors. Exit codes:
0 = LIVE_READY, 1 = NOT_READY, 3 = NOT_READY with external validation still required.
"""

from __future__ import annotations

import hashlib
import json
import shutil
import subprocess
import sys
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO / "packages" / "tia" / "src"))

VERIFY_MARKER = REPO / "data/runtime/verify_passed.json"
BINANCE_FACTS = REPO / "data/runtime/binance_validation.json"
ENDURANCE = REPO / "data/runtime/endurance_report.json"
OUT = REPO / "data/runtime/live_readiness.json"


def _read(path: Path) -> dict[str, Any] | None:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None


def _git_commit() -> str:
    try:
        git = shutil.which("git") or "git"
        return subprocess.run(  # noqa: S603 - fixed args, local metadata
            [git, "rev-parse", "HEAD"],
            capture_output=True, text=True, timeout=5, check=False, cwd=REPO,
        ).stdout.strip()
    except Exception:
        return "unknown"


def evaluate() -> dict[str, Any]:
    checks: dict[str, dict[str, Any]] = {}

    def check(name: str, status: str, evidence: str) -> None:
        checks[name] = {"status": status, "evidence": evidence}

    # ---- validated locally ------------------------------------------------
    marker = _read(VERIFY_MARKER)
    if marker and marker.get("passed"):
        check("tests", "PASS", f"make verify passed at {marker.get('at')} on {str(marker.get('commit'))[:8]}")
    else:
        check("tests", "FAIL", "no passing verify record; run `make verify`")

    try:
        import sqlite3

        db_url = (REPO / "data/runtime/tia.db")
        if db_url.exists():
            conn = sqlite3.connect(db_url)
            version = conn.execute("SELECT version FROM schema_info").fetchone()
            alembic = conn.execute(
                "SELECT version_num FROM alembic_version"
            ).fetchone() if conn.execute(
                "SELECT name FROM sqlite_master WHERE name='alembic_version'"
            ).fetchone() else None
            from tia.persistence.models import SCHEMA_VERSION

            if version and version[0] == SCHEMA_VERSION:
                check("migrations", "PASS", f"schema v{version[0]}, alembic {alembic[0] if alembic else 'adopted'}")
            else:
                check("migrations", "FAIL", f"schema {version} != required v{SCHEMA_VERSION}; run `make migrate`")
            evidence_rows = conn.execute("SELECT COUNT(*) FROM edge_outcomes").fetchone()[0]
            if evidence_rows > 0:
                check("edge_persistence", "PASS", f"{evidence_rows} persisted round trips")
            else:
                check("edge_persistence", "FAIL", "no persisted evidence; paper trade first")
        else:
            check("migrations", "FAIL", "no database yet; run `make migrate` then paper trade")
            check("edge_persistence", "FAIL", "no database yet")
    except Exception as exc:
        check("migrations", "FAIL", f"could not inspect the database: {exc}")
        check("edge_persistence", "FAIL", "unknown = failed")

    endurance = _read(ENDURANCE)
    if endurance and endurance.get("passed"):
        check(
            "endurance", "PASS",
            f"{endurance.get('bars_simulated')} simulated bars across "
            f"{len(endurance.get('sessions', []))} sessions, all checks green",
        )
    else:
        check("endurance", "FAIL", "no passing endurance report; run `make endurance`")

    from tia.core.config import get_settings

    try:
        settings = get_settings()
        problems = []
        if settings.security.jwt_secret.get_secret_value() == "change-me-in-any-real-deployment":
            problems.append("JWT secret is the placeholder")
        if settings.live.enabled and settings.live.max_live_capital <= 0:
            problems.append("live enabled with zero ceiling")
        if problems:
            check("configuration", "FAIL", "; ".join(problems))
        else:
            check("configuration", "PASS", f"env={settings.env.value}, ceiling={settings.live.max_live_capital}")
    except Exception as exc:
        check("configuration", "FAIL", str(exc)[:200])

    # ---- external ---------------------------------------------------------
    facts = _read(BINANCE_FACTS)
    if facts is None:
        check(
            "binance_validation", "EXTERNAL_REQUIRED",
            "no validation record; run scripts/validate_binance.py --account --json-out "
            "data/runtime/binance_validation.json from a machine with venue access",
        )
    else:
        age_ok = False
        try:
            generated = datetime.fromisoformat(facts["generated_at"])
            age_ok = (datetime.now(UTC) - generated).total_seconds() < 24 * 3600
        except (KeyError, ValueError):
            pass
        if age_ok:
            check("binance_validation", "PASS", f"validated {facts.get('generated_at')} on {facts.get('environment')}")
        else:
            check("binance_validation", "FAIL", "record exists but is stale or malformed; re-run the validator")

    docker = shutil.which("docker")
    daemon = False
    if docker:
        daemon = subprocess.run(  # noqa: S603 - fixed args
            [docker, "info"], capture_output=True, timeout=10, check=False
        ).returncode == 0
    if daemon:
        check("docker", "PASS", "daemon reachable; run `make docker-verify` for the full cycle")
    else:
        check("docker", "EXTERNAL_REQUIRED", "no Docker daemon here; run `make docker-verify` where one exists")

    import os

    if os.environ.get("ANTHROPIC_API_KEY") or os.environ.get("TIA_ANTHROPIC_API_KEY"):
        check("claude_api", "PASS", "key present in the environment (value not read by this script)")
    else:
        check(
            "claude_api", "EXTERNAL_REQUIRED",
            "no ANTHROPIC_API_KEY in the environment; the mock provider will be used — "
            "which is a valid configuration, stated rather than hidden",
        )

    # ---- verdict ----------------------------------------------------------
    failures = [n for n, c in checks.items() if c["status"] == "FAIL"]
    external = [n for n, c in checks.items() if c["status"] == "EXTERNAL_REQUIRED"]
    overall = "LIVE_READY" if not failures and not external else "NOT_READY"

    payload = {
        "generated_at": datetime.now(UTC).isoformat(),
        "git_commit": _git_commit(),
        "environment": "build-sandbox" if not facts else facts.get("environment", "unknown"),
        "checks": checks,
        "warnings": [],
        "failures": failures,
        "external_validation_required": external,
        "overall_status": overall,
    }
    canonical = json.dumps(payload["checks"], sort_keys=True, default=str).encode()
    payload["fingerprint"] = hashlib.blake2s(canonical, digest_size=16).hexdigest()
    return payload


def main() -> int:
    payload = evaluate()
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(payload, indent=2), encoding="utf-8")

    print(f"Live readiness — {payload['overall_status']}")
    for name, check in payload["checks"].items():
        print(f"  {check['status']:18s} {name}: {check['evidence'][:90]}")
    print(f"\nWritten to {OUT}")
    if payload["overall_status"] == "LIVE_READY":
        print(
            "\nLIVE_READY means every technical validation that could be verified passed. "
            "It is not a statement about profitability, which must be evaluated "
            "statistically and separately."
        )
        return 0
    if payload["external_validation_required"]:
        print(
            f"\nExternal validation still required: {payload['external_validation_required']}"
        )
        return 3
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
