#!/usr/bin/env python3
"""LEDの模様を1つずつ見る。**曲がなくても動く。**

    ./.venv/bin/python scripts/led_demo.py strobe_hard      1つだけ見る
    ./.venv/bin/python scripts/led_demo.py --all            全部順に
    ./.venv/bin/python scripts/led_demo.py laser --bpm 140 --sec 12

★console の LED 購読を一時的に止めてから流し、終わったら戻す。
  止めないと、こちらと console が同じテープを取り合う。
"""
import argparse
import asyncio
import json
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "app" / "dj"))
from gateway import Gateway   # noqa: E402
from led import LedState      # noqa: E402

ORDER = ["strobe_hard", "laser", "sparks", "sweep", "build", "segments"]
LABEL = {
    "strobe_hard": "拍の頭で焼ける・16分で刻む",
    "laser": "細い光が高速で往復",
    "sparks": "粒がバラバラに飛ぶ",
    "sweep": "端から端へ走り抜ける",
    "build": "点滅がどんどん速くなる",
    "segments": "四角い塊が飛び飛びに並ぶ（回路図のような画）",
    "show": "全部を数拍ごとに切り替える",
}


async def play(gw, a, pattern, seconds, flash=False):
    s = LedState(count=a.count, pattern=pattern, max_brightness=a.brightness)
    s.bpm, s.enabled, s.flash_white = a.bpm, True, flash
    if a.series:                      # 色のシリーズを固定して見る
        s._series_name = lambda n, _s=a.series: _s
    t0 = time.time()
    s.beat0 = t0
    print(f"  ▸ {pattern:12s} {LABEL.get(pattern, '')}")
    while time.time() - t0 < seconds:
        await gw.call("port_b_ws2812_set_strip",
                      colors=json.loads(s.frame())["colors"])
        await gw.call("port_b_ws2812_refresh")
        await asyncio.sleep(1.0 / a.fps)


async def main(a) -> int:
    async with Gateway("http://127.0.0.1:8767/mcp") as gw:
        await gw.call("stackchan_follow_led_stream", action="stop")
        await gw.call("port_b_ws2812_init", led_count=a.count)
        print(f"BPM={a.bpm:.0f}  明るさ={a.brightness}  {a.count}個"
              + (f"  色={a.series}固定" if a.series else "  色=自動") + "\n")
        try:
            pats = ORDER if a.all else [a.pattern]
            for p in pats:
                await play(gw, a, p, a.sec)
            if a.drop:
                await play(gw, a, "strobe_hard", 4, flash=True)
                print("  ▸ ★サビ")
        finally:
            await gw.call("port_b_ws2812_clear")
            await gw.call("stackchan_follow_led_stream", action="start",
                          url="ws://127.0.0.1:8771/", target="port_b",
                          led_count=a.count)
            print("\n元に戻しました")
    return 0


if __name__ == "__main__":
    ap = argparse.ArgumentParser(description="LEDの模様を1つずつ見る")
    ap.add_argument("pattern", nargs="?", default="strobe_hard",
                    choices=list(LABEL))
    ap.add_argument("--all", action="store_true", help="全部順に流す")
    ap.add_argument("--drop", action="store_true", help="最後にサビを足す")
    ap.add_argument("--sec", type=float, default=8.0)
    ap.add_argument("--bpm", type=float, default=128.0)
    ap.add_argument("--count", type=int, default=30)
    ap.add_argument("--brightness", type=float, default=0.65)
    ap.add_argument("--series", choices=("blue", "red"), default=None,
                    help="色のシリーズを固定する（既定は曲中で自動で切り替わる）")
    ap.add_argument("--fps", type=float, default=30.0)
    raise SystemExit(asyncio.run(main(ap.parse_args())))
