#!/usr/bin/env python
"""Render cron entrypoint — India pipeline + US global signals."""
from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


def run(cmd: list[str]) -> None:
    env = os.environ.copy()
    env.setdefault("AMAZON_USE_PLAYWRIGHT", "never")
    env.setdefault("ENVIRONMENT", os.getenv("ENVIRONMENT", "staging"))
    env.setdefault("DATA_DIR", os.getenv("DATA_DIR", "data"))
    print(f"\n>>> {' '.join(cmd)}")
    result = subprocess.run(cmd, cwd=ROOT, env=env)
    if result.returncode != 0:
        raise SystemExit(result.returncode)


def main() -> None:
    py = sys.executable
    # India-native gold layer
    run([py, "scripts/run_local.py", "--sample-fallback"])
    # US supplementary (Amazon US live from Render US region; TikTok only with Partner API creds)
    run([py, "scripts/run_global_signals.py"])
    print("\nRender pipeline complete.")


if __name__ == "__main__":
    main()
