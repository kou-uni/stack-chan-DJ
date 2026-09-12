#!/usr/bin/env python3
"""健康診断。詰まったらこれを叩く。

    ./.venv/bin/python scripts/doctor.py          点検だけ
    ./.venv/bin/python scripts/doctor.py --fix    直せるものは直す
"""
import argparse
import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "app" / "dj"))
import doctor  # noqa: E402


def main() -> int:
    ap = argparse.ArgumentParser(description="スタックチャンの健康診断")
    ap.add_argument("--fix", action="store_true", help="直せるものは直す")
    a = ap.parse_args()
    return doctor.show(asyncio.run(doctor.run(fix=a.fix)))


if __name__ == "__main__":
    raise SystemExit(main())
