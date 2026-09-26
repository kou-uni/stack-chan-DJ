#!/usr/bin/env python3
"""2つの面（ota_1=旧 / ota_0=新）を交互に起動し、**しばらく放置してから**再起動を測る。

    ./.venv/bin/python scripts/boot_idle_ab.py --rounds 3 --idle-s 600 --out /tmp/boot.csv

★なぜ放置するか（2026-09-26）：続けざまの再起動は旧ファームでも 10 秒で顔が出た（14回中央値）。
  遅かった 33 秒・18 秒は、**長く動かした後の最初の再起動**。当日の「電源を入れる」はそちら。
  だから、比べるなら放置してから測る。1回ずつ交互にして、時間帯の偏りを両方に配る。
★USB シリアルを独占する。boot_measure.py と同時に走らせない。終わると ota_0（新）で止まる。
"""
from __future__ import annotations

import argparse
import subprocess
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PY = sys.executable


def run(*args: str) -> None:
    print(f"  $ {' '.join(args)}", flush=True)
    subprocess.run([PY, *args], cwd=ROOT, check=True)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--rounds", type=int, default=3)
    ap.add_argument("--idle-s", type=float, default=600)
    ap.add_argument("--settle-s", type=float, default=40, help="切り替え直後、繋がるまで待つ秒")
    ap.add_argument("--out", type=Path, required=True)
    a = ap.parse_args()
    for r in range(1, a.rounds + 1):
        for slot, tag in ((1, "old"), (0, "new")):
            print(f"\n== round {r} / {tag}（ota_{slot}） {time.strftime('%H:%M:%S')}", flush=True)
            run("scripts/ota_select.py", str(slot))
            time.sleep(a.settle_s)
            print(f"  放置 {a.idle_s:.0f} 秒…", flush=True)
            time.sleep(a.idle_s)
            run("scripts/boot_measure.py", "--n", "1", "--tag", f"idle-{tag}", "--out", str(a.out))
    print("\n  終わり。いまは ota_0（新）で動いています", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
