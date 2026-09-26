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
    # ★OTA スタブ。落ちていると実機は「6桁コード」か「更新確認失敗」で止まり、gateway に来ない。
    #   2026-09-26：これが落ちていて半日探した。**沈黙は故障と見分けがつかない。見えるようにする。**
    ota = subprocess.run(["lsof", "-nP", "-iTCP:8778", "-sTCP:LISTEN", "-t"],
                         capture_output=True, text=True).stdout.split()
    print(f"{_mark(bool(ota))} OTAスタブ     {'8778 で待っている' if ota else '止まっている ← 実機が gateway に来ません（service.sh install）'}")
    # ★声。落ちていると say が全部失敗し、撫でも NFC も無言になる（2026-09-26。誰も気づかなかった）
    vv = subprocess.run(["lsof", "-nP", "-iTCP:50021", "-sTCP:LISTEN", "-t"],
                        capture_output=True, text=True).stdout.split()
    print(f"{_mark(bool(vv))} VOICEVOX      {'50021 で待っている' if vv else '止まっている ← 声が出ません（service.sh install）'}")

    try:
        async with Gateway("http://127.0.0.1:8767/mcp") as gw:
            async def j(name, **a):
                return json.loads((await gw.call(name, **a)).content[0].text)

            # ★実機が居ないときに「gateway に繋がらない」と出していた（2026-09-14）。
            #   gateway は動いているので、**嘘の案内で人を遠回りさせる。**
            #   繋がっていないことは、繋がっていないと言う
            st = await j("get_status")
            if not st.get("connected"):
                print("× 実機         繋がっていない"
                      "（電源・Wi-Fi・mDNS を見る。gateway は動いています）")
                return
            head = await j("get_head_angles")
            print(f"○ 実機         繋がっている  首 yaw={head['yaw']} pitch={head['pitch']}")
            # ★実機はどこを見に来ているか。mDNS が入っていない build なので固定 IP。
            #   当日、別の Mac で受けるときに真っ先に見る行（2026-09-26）
            try:
                cfg = await j("gateway_config_get")
                print(f"  実機の向き先  {cfg.get('connected_url') or cfg.get('url')}"
                      f"  mDNS探索={'あり' if cfg.get('discovery_compiled_in') else 'なし（固定IP）'}")
            except Exception:
                pass

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
