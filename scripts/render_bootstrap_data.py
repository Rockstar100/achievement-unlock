#!/usr/bin/env python
"""Seed Render persistent disk from bundled repo data on first boot."""
from __future__ import annotations

import os
import shutil
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))


def main() -> None:
    data_dir = Path(os.getenv("DATA_DIR", "data")).resolve()
    bundled = (ROOT / "data").resolve()
    if data_dir == bundled:
        return
    marker = data_dir / ".bootstrapped"
    if marker.exists():
        return
    data_dir.mkdir(parents=True, exist_ok=True)
    if bundled.exists():
        for item in bundled.iterdir():
            dest = data_dir / item.name
            if item.is_dir():
                shutil.copytree(item, dest, dirs_exist_ok=True)
            else:
                shutil.copy2(item, dest)
    marker.write_text("ok\n", encoding="utf-8")
    print(f"Bootstrapped {data_dir} from bundled data/")


if __name__ == "__main__":
    main()
