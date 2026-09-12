#!/usr/bin/env python3
"""文字起こしを、締めの素材にする。

    ./.venv/bin/python scripts/highlights.py                 # 最新のを出す
    ./.venv/bin/python scripts/highlights.py 20260929-1300   # 指定

**読むのは人（と Claude Code）。** ここでは要約しない。
**何が起きたかを時刻つきで並べるだけ。** セリフに何を織り込むかは、書く側が決める。
"""
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "app" / "dj"))
from meeting import Transcript, highlights   # noqa: E402

REC = ROOT / "event" / "rec"


def main() -> int:
    name = sys.argv[1] if len(sys.argv) > 1 else None
    if name:
        d = REC / name
    else:
        ds = sorted([p for p in REC.glob("*") if (p / "transcript.jsonl").exists()])
        if not ds:
            print("録音がありません")
            return 1
        d = ds[-1]
    tr = Transcript(d / "transcript.jsonl")
    rows = tr.lines()
    print(f"── {d.name}  {len(rows)} 行 ──\n")
    print(highlights(rows))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
