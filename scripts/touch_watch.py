#!/usr/bin/env python3
"""頭なでの記録係。**裏で走らせて、届く条件を見つける。**

    ./.venv/bin/python scripts/touch_watch.py &

★2026-09-12、タッチ通知が届いたり届かなかったりした。
  対話で15秒ずつ試すより、**普通に使いながら記録を貯めるほうが確実**。

出力は `~/.claude/stackchan-touch-watch.log`。
イベントが来た時刻と、そのときの実機・ストリームの状態を並べて残す。
"""
import asyncio
import json
import sys
import time
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "app" / "dj"))
from gateway import Gateway          # noqa: E402
from touch_events import TouchEvents  # noqa: E402

OUT = Path.home() / ".claude" / "stackchan-touch-watch.log"


def note(msg: str) -> None:
    line = f"{datetime.now():%m-%d %H:%M:%S}  {msg}"
    print(line, flush=True)
    with OUT.open("a", encoding="utf-8") as f:
        f.write(line + "\n")


async def main() -> int:
    te = TouchEvents(max_age_s=120.0, max_stroke_ms=10 ** 9)
    te.catch_up()
    note("── 記録係を開始 ──")
    last_state = None
    async with Gateway("http://127.0.0.1:8767/mcp") as gw:
        while True:
            ev = te.poll()
            if ev:
                note(f"★撫でられた {ev['duration_ms']}ms  ({last_state})")
            # 30秒ごとに、そのときの状態を残す（あとで突き合わせるため）
            if int(time.time()) % 30 == 0:
                try:
                    def j(r):
                        c = getattr(r, "content", None)
                        return json.loads(c[0].text) if c else {}
                    b = j(await gw.call("beat_meta_snapshot"))
                    l = j(await gw.call("stackchan_follow_led_stream", action="status"))
                    state = (f"beat={'ON' if b.get('active') else 'OFF'} "
                             f"led={'ON' if l.get('running') else 'OFF'}")
                    if state != last_state:
                        note(f"  状態が変わった: {state}")
                        last_state = state
                except Exception as exc:
                    note(f"  状態を取れない: {exc}")
                await asyncio.sleep(1.2)
            await asyncio.sleep(0.4)


if __name__ == "__main__":
    try:
        raise SystemExit(asyncio.run(main()))
    except KeyboardInterrupt:
        note("── 記録係を停止 ──")
