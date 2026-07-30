#!/usr/bin/env python
"""Run tests, rebuild gold, sync bronze, and health-check (prod gate)."""
from __future__ import annotations

import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


def run(cmd: list[str]) -> int:
    print(f"\n>>> {' '.join(cmd)}")
    return subprocess.call(cmd, cwd=str(ROOT))


def main() -> int:
    steps = [
        [sys.executable, "-m", "pytest", "tests/", "-q", "--tb=line"],
        [sys.executable, "scripts/sync_bronze.py"],
        [sys.executable, "scripts/clean_and_rebuild.py"],
        [sys.executable, "scripts/healthcheck.py"],
    ]
    failed = []
    for cmd in steps:
        code = run(cmd)
        if code != 0:
            failed.append(" ".join(cmd))

    if failed:
        print("\nPROD READY: FAIL")
        for f in failed:
            print(f"  - {f}")
        return 1

    print("\nPROD READY: OK")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
