#!/usr/bin/env python3
"""実機を USB ケーブルで繋ぐ（有線 LAN）か、Wi-Fi で繋ぐかを切り替える。

    ./.venv/bin/python scripts/usb_wired.py          # いまの状態
    ./.venv/bin/python scripts/usb_wired.py on       # USB で繋ぐ（本番の形）
    ./.venv/bin/python scripts/usb_wired.py off      # Wi-Fi で繋ぐ（USB シリアルが戻る）

★会場の Wi-Fi が 5GHz だけでも・ログイン画面つきでも、USB なら繋がる（docs/venue-wifi.md）。
★gateway 経由で切り替えて、実機を再起動する。どちらのモードでも、繋がってさえいれば使える。
  電池があるので、ケーブルを抜いても再起動しない。だから再起動も gateway から送る。
★USB で繋いでいる間は USB シリアル（esptool・set_target.py）は使えない。使うときは off。
★要るファーム: firmware/xiaozhi-usb-20260929.bin 以降（ファームの boards/common/usb_wired.h）
"""
import asyncio
import json
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "app" / "dj"))
from gateway import Gateway   # noqa: E402

URL = "http://127.0.0.1:8767/mcp"


def text(r) -> str:
    return r.content[0].text


async def status(gw) -> dict:
    d = json.loads(text(await gw.call("get_device_info")))
    if "error" in d:
        return {}
    return d.get("network", {}).get("usb_wired", {})


async def wait_back(timeout: int = 90) -> dict:
    end = time.time() + timeout
    while time.time() < end:
        await asyncio.sleep(5)
        try:
            async with Gateway(URL) as gw:
                st = await status(gw)
                if st:
                    return st
        except Exception:
            pass
    return {}


def show(st: dict) -> None:
    if not st:
        print("  × 実機が gateway に繋がっていません。status.py で確かめる")
        return
    if "enabled" not in st:
        print("  × 実機のファームが古い（USB で繋ぐ機能が無い）。firmware/xiaozhi-usb-*.bin を入れる")
        return
    mode = "USB（有線 LAN）" if st.get("active") else "Wi-Fi"
    print(f"  ○ いま {mode} で繋がっています")
    print(f"    USB で繋ぐ設定: {'on' if st.get('enabled') else 'off'}"
          f"   起動時の結果: {st.get('boot_result')}"
          + (f"   Mac 側の番地: {st['mac_ip']}" if st.get("mac_ip") else ""))


async def main() -> int:
    want = sys.argv[1] if len(sys.argv) > 1 else ""
    if want not in ("", "on", "off"):
        print(__doc__)
        return 2
    async with Gateway(URL) as gw:
        st = await status(gw)
        if not want or not st or "enabled" not in st:
            show(st)
            return 0 if st else 1
        on = want == "on"
        if st.get("enabled") == on and st.get("active") == on:
            show(st)
            print("  もうその形です。何もしません")
            return 0
        r = json.loads(text(await gw.call("set_usb_wired", enabled=on)))
        if not r.get("ok"):
            print(f"  × 切り替えられませんでした: {r}")
            return 1
        print(f"  ○ USB で繋ぐ設定を {want} にしました。実機を再起動します…")
        try:
            await gw.call("reboot_device")
        except Exception:
            pass   # 再起動で切れるのが正常
    st = await wait_back()
    show(st)
    if st.get("active") != on:
        if on:
            print("  × USB で繋がりませんでした（Wi-Fi に逃げた）。USB-C が Mac 本体に挿さっているか見る")
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
