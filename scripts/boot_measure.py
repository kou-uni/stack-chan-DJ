#!/usr/bin/env python3
"""実機の起動を測る。**リセット → 顔が出るまで**を USB シリアルで読み、区間ごとの秒を出す。

    ./.venv/bin/python scripts/boot_measure.py            # 1回
    ./.venv/bin/python scripts/boot_measure.py --n 14     # 14回（中央値・最小・最大を出す）
    ./.venv/bin/python scripts/boot_measure.py --n 14 --tag old --out /tmp/boot.csv   # 記録も残す
    ./.venv/bin/python scripts/boot_measure.py --wait-power-on   # ★電源ONの起動を測る（リセットしない。USBを挿して待ち、電源を入れる）

★1回では計測にならない（2026-09-26：同じファームで 33 秒と 18 秒が出た。OTA 待ちが 14 秒→1 秒）。
  ファームを比べるときは **両方を同じ本数**測る。本数の既定は 1 だが、比較は `--n 14`。
"""
from __future__ import annotations

import argparse
import csv
import re
import statistics
import sys
import time
from pathlib import Path

MARKS = [
    ("wifi", "Wi-Fi 接続", r"wifi:connected with"),
    ("ip", "IP", r"Got IP"),
    ("ota", "OTA 応答", r"Ota: Current is the latest|Ota: No mqtt"),
    ("ws", "WebSocket", r"WS: Connected to websocket|WebSocket handshake done"),
    ("face", "顔", r"set_avatar: face=idle applied=1"),
]
ANSI = re.compile(r"\x1b\[[0-9;]*m")


def find_port() -> str | None:
    from serial.tools import list_ports
    for p in list_ports.comports():
        if p.vid == 0x303A and p.pid == 0x1001:
            return p.device
    return None


def parse(lines: list[str]) -> dict:
    """ログの行から、区間ごとの秒（実機の時計＝行頭の (ms)）を拾う。"""
    out: dict = {}
    for key, _label, pat in MARKS:
        for l in lines:
            if re.search(pat, l):
                m = re.search(r"\((\d+)\)", l)
                if m:
                    out[key] = int(m.group(1)) / 1000
                    break
    pm = next((l for l in lines if "wifi:pm start" in l), None)
    m = re.search(r"type: (\d)", pm) if pm else None
    # esp_wifi の値: 0=NONE（省電力なし） 1=MIN_MODEM 2=MAX_MODEM。行が無ければ「不明」
    out["pm"] = {"0": "none", "1": "MIN_MODEM", "2": "MAX_MODEM"}.get(m.group(1), pm.strip()[-30:]) if m else ("unknown" if pm is None else pm.strip()[-30:])
    return out


def read_boot(s, limit_s: float = 45.0) -> list[str]:
    """開いたシリアルから、顔が出るか時間切れまで読む。★リセットはしない（電源ONの計測でも使う）。"""
    t0 = time.time(); lines: list[str] = []
    while time.time() - t0 < limit_s:
        l = s.readline().decode("utf-8", "replace").rstrip()
        if l:
            lines.append(ANSI.sub("", l))
            if "set_avatar: face=idle applied=1" in l:
                break
    return lines


def one_boot(port: str, limit_s: float = 45.0, reset: bool = True) -> dict:
    import serial
    s = serial.Serial(port, 115200, timeout=1)
    if reset:
        s.dtr = False; s.rts = True; time.sleep(0.1); s.rts = False   # リセット
    lines = read_boot(s, limit_s)
    s.close()
    return parse(lines)


def wait_power_on(timeout_s: float = 600.0) -> dict | None:
    """USB が現れるのを待ち、現れたら**リセットせずに**起動ログを読む。
    電源を入れると USB-Serial/JTAG が数百 ms で現れ、起動ログの頭から読める。"""
    print("  電源を入れてください（USB が現れるのを待っています。Ctrl-C でやめる）", flush=True)
    t0 = time.time()
    while time.time() - t0 < timeout_s:
        port = find_port()
        if port:
            try:
                return one_boot(port, limit_s=60.0, reset=False)
            except Exception as exc:                          # noqa: BLE001  現れた直後は開けないことがある
                print(f"  （開けなかった: {exc}。もう一度）", flush=True); time.sleep(0.5); continue
        time.sleep(0.2)
    return None


def show(r: dict) -> str:
    prev = 0.0; cells = []
    for key, label, _ in MARKS:
        t = r.get(key)
        if t is None:
            cells.append(f"{label} --")
        else:
            cells.append(f"{label} {t:5.1f}(+{t - prev:4.1f})"); prev = t
    return "  ".join(cells) + f"  省電力={r['pm']}"


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--n", type=int, default=1)
    ap.add_argument("--port")
    ap.add_argument("--tag", default="")
    ap.add_argument("--out", type=Path)
    ap.add_argument("--rest", type=float, default=2.0, help="回と回の間に置く秒")
    ap.add_argument("--wait-power-on", action="store_true", help="リセットせず、電源ONの起動を待って測る")
    a = ap.parse_args()
    if a.wait_power_on:
        r = wait_power_on()
        if r is None:
            print("★ 時間内に USB が現れませんでした"); return 1
        print(f"  電源ON {show(r)}")
        if a.out:
            new = not a.out.exists()
            with a.out.open("a", newline="") as f:
                w = csv.writer(f)
                if new: w.writerow(["tag", "pm"] + [k for k, _, _ in MARKS])
                w.writerow([a.tag or "power-on", r["pm"]] + [r.get(k, "") for k, _, _ in MARKS])
        return 0
    port = a.port or find_port()
    if not port:
        print("★ 実機の USB が見えません（上の箱の USB-C をデータ線で）"); return 1
    runs: list[dict] = []
    for i in range(a.n):
        r = one_boot(port); runs.append(r)
        print(f"  #{i + 1:2d} {show(r)}", flush=True)
        if a.out:
            new = not a.out.exists()
            with a.out.open("a", newline="") as f:
                w = csv.writer(f)
                if new: w.writerow(["tag", "pm"] + [k for k, _, _ in MARKS])
                w.writerow([a.tag, r["pm"]] + [r.get(k, "") for k, _, _ in MARKS])
        if i + 1 < a.n: time.sleep(a.rest)
    if a.n > 1:
        faces = [r["face"] for r in runs if "face" in r]
        otas = [r["ota"] - r["ip"] for r in runs if "ota" in r and "ip" in r]
        wifis = [r["wifi"] for r in runs if "wifi" in r]
        print(f"\n  {a.tag or '結果'}: {len(faces)}/{a.n} 回で顔まで到達")
        if faces:
            print(f"   顔まで     中央 {statistics.median(faces):5.1f}s  最小 {min(faces):5.1f}  最大 {max(faces):5.1f}")
        if wifis:
            print(f"   Wi-Fi接続  中央 {statistics.median(wifis):5.1f}s  最小 {min(wifis):5.1f}  最大 {max(wifis):5.1f}")
        if otas:
            print(f"   IP→OTA応答 中央 {statistics.median(otas):5.1f}s  最小 {min(otas):5.1f}  最大 {max(otas):5.1f}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
