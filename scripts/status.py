#!/usr/bin/env python3
"""いまの状態を1画面で見る。立ち上げ前と立ち下げ後に叩く。

    ./.venv/bin/python scripts/status.py
"""
import asyncio
import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "app" / "dj"))
from gateway import Gateway                       # noqa: E402


def _mark(ok: bool) -> str:
    return "○" if ok else "×"


async def main() -> int:
    running = subprocess.run(["pgrep", "-f", "app/dj/console.py"],
                             capture_output=True, text=True).stdout.split()
    print(f"{_mark(bool(running))} console      {'動いている PID ' + ' '.join(running) if running else '止まっている'}")

    try:
        async with Gateway("http://127.0.0.1:8767/mcp") as gw:
            async def j(name, **a):
                return json.loads((await gw.call(name, **a)).content[0].text)

            head = await j("get_head_angles")
            print(f"○ 実機         繋がっている  首 yaw={head['yaw']} pitch={head['pitch']}")

            # ★タッチは電源で false に戻る。**見えないと故障と区別がつかない**
            #   （2026-09-13：撫でても無反応。ここを見るまで分からなかった）
            tz = await j("get_touch_sensor_enabled")
            print(f"{_mark(tz['enabled'])} 頭なで        "
                  + ("有効" if tz["enabled"] else
                     "無効 ← 撫でても反応しません。console を立ち上げ直すと入ります"))

            b = await j("beat_meta_snapshot")
            print(f"{_mark(b['capture_healthy'])} 音の取り込み  {b['capture_state']}  "
                  f"音量={b['level']:.5f}  BPM={b['bpm']}  beat={'ON' if b['active'] else 'OFF'}")

            for label, tool in (("pose ストリーム", "stackchan_follow_pose_stream"),
                                ("LED ストリーム ", "stackchan_follow_led_stream")):
                d = await j(tool, action="status")
                print(f"{_mark(d['running'])} {label} {'購読中' if d['running'] else '購読なし'}")
    except Exception as exc:
        print(f"× gateway      繋がらない（{exc}）")
        print("  scripts/gateway.sh を起動してください")
        return 1

    if not running:
        print("\n立ち上げ: ./.venv/bin/python app/dj/console.py")
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
