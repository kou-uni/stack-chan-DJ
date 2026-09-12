#!/usr/bin/env python3
"""背景スクリーン（iPad）と、スマホの操作パネルの土台。

## これは何か

console が持っている「いまの音の状態」を、**そのままブラウザへ流す**だけのサーバ。

    実機のマイク ──▶ gateway ──▶ console ──▶ iPad の背景
                                        └──▶ スマホの操作パネル（あとで）

★「スタックチャンが指令している」は**事実**。
  背景を動かしているのは、実機が聴いた音そのもの。演出ではない。

★サーバは1本にする。背景と操作パネルで分けない。
  Phase 2（スマホから触れる）がそのままここに乗る。

## 送るもの

**小さく保つ。** 毎拍たくさん送ると、iPad より先にネットワークが詰まる。
絵をどう描くかは**ブラウザ側の仕事**。ここは状態だけを渡す。
"""
from __future__ import annotations

import asyncio
import contextlib
import json
import time
from pathlib import Path

HERE = Path(__file__).resolve().parent

# ★会場では IP も機械名も変わる（家＝Mac Studio／会場＝MacBook、テザリング）。
#   **変わらない名前を1つ作って、そこに全部ぶら下げる。**
#   iPad はいつでも http://stackchan.local:8779/ を開けばよい。
STAGE_HOST = "stackchan.local"


def stage_state(led, presence, now: float | None = None) -> dict:
    """いまの状態を、画面が使う形にして返す。**純粋な変換。**

    - `beat` は秒ではなく**拍の中の位置 0..1**。画面はこれで光る
    - `series` は LED と**同じ関数**から採る（テープと画面で色が食い違わない）
    """
    n, ph = led._phase()
    return {
        "bpm": float(led.bpm or 0.0),
        "n": int(n),
        "beat": float(ph),
        "series": led._series_name(n),
        "dancing": bool(led.enabled),
        "drop": bool(led.flash_white),
        "groove": float(getattr(led, "groove", 1.0)),
        "mode": presence.mode,
        "talk": presence.talk,
    }


async def run_stage(con, host: str, port: int, hz: float = 20.0):
    """背景と操作パネルを配る。**実機が無くても落ちない。**"""
    from aiohttp import web, WSMsgType

    async def index(_req):
        return web.FileResponse(HERE / "stage.html")

    async def ws(req):
        sock = web.WebSocketResponse(heartbeat=20)
        await sock.prepare(req)
        print(f"→ 背景スクリーンが繋がりました: {req.remote}")
        try:
            while not sock.closed:
                await sock.send_str(json.dumps(
                    stage_state(con.led, con.presence)))
                await asyncio.sleep(1.0 / hz)
        except (ConnectionResetError, asyncio.CancelledError):
            raise
        except Exception:
            pass
        finally:
            with contextlib.suppress(Exception):
                await sock.close()
            print("← 背景スクリーンが切れました")
        return sock

    app = web.Application()
    app.add_routes([web.get("/", index), web.get("/ws", ws)])
    runner = web.AppRunner(app, access_log=None)
    await runner.setup()
    site = web.TCPSite(runner, host, port)
    await site.start()
    ip = current_ip()
    print(f"\n背景スクリーン {'='*40}")
    print(f"  iPad で開く: {stage_url(port)}")
    print(f"  （届かないときは http://{ip or '<LAN IP>'}:{port}/ ）\n")
    print_qr(stage_url(port))
    print()
    try:
        await asyncio.Future()
    finally:
        with contextlib.suppress(Exception):
            await runner.cleanup()


def stage_url(port: int) -> str:
    """iPad で開く URL。**機械名にも IP にも依存しない。**"""
    return f"http://{STAGE_HOST}:{port}/"


def current_ip() -> str:
    """いまの LAN IP。★既定経路のインターフェースから取る。

    列挙順で拾うと、有線と Wi-Fi が同じ網に居るときに日替わりで変わる。
    """
    import subprocess
    out = subprocess.run(["route", "-n", "get", "default"],
                         capture_output=True, text=True).stdout
    iface = next((l.split()[-1] for l in out.splitlines() if "interface:" in l), "")
    if not iface:
        return ""
    return subprocess.run(["ipconfig", "getifaddr", iface],
                          capture_output=True, text=True).stdout.strip()


def print_qr(url: str) -> None:
    """端末に QR を出す。**会場では iPad のカメラで読むのが一番速い。**"""
    try:
        import qrcode
    except ImportError:
        return
    q = qrcode.QRCode(border=1)
    q.add_data(url)
    q.make(fit=True)
    m = q.get_matrix()
    # 上下2行を1行にまとめて、端末で正方形に見せる
    for y in range(0, len(m), 2):
        row = ""
        for x in range(len(m[0])):
            top = m[y][x]
            bot = m[y + 1][x] if y + 1 < len(m) else False
            row += ("█" if top and bot else "▀" if top else "▄" if bot else " ")
        print("  " + row)


class Advertiser:
    """mDNS で `stackchan.local` を名乗る。

    ★IP は毎回変わる（家 → テザリング）。**名前で引けるようにする。**
      名乗ったまま IP が変わると引けなくなるので、変化を見て名乗り直す。

    ★同期版の zeroconf を asyncio の中から呼ぶと、自分のループを待って固まる
      （実測：TimeoutError）。**非同期版を使う。**

    ★ここが失敗しても console は止めない。
      名前で引けなくても、IP を直接叩けば画面は出る。**degrade して動かす。**
    """

    def __init__(self, port: int):
        self.port, self._zc, self._info, self.ip = port, None, None, ""
        self.ok = False

    async def advertise(self, ip: str) -> bool:
        import socket
        from zeroconf import ServiceInfo
        from zeroconf.asyncio import AsyncZeroconf

        await self.stop()
        if not ip:
            return False
        try:
            self._zc = AsyncZeroconf()
            self._info = ServiceInfo(
                "_http._tcp.local.",
                "stackchan-stage._http._tcp.local.",
                addresses=[socket.inet_aton(ip)],
                port=self.port,
                server=f"{STAGE_HOST}.",       # ← この名前で A レコードが出る
                properties={"path": "/"},
            )
            await self._zc.async_register_service(self._info)
        except Exception as exc:
            print(f"⚠ {STAGE_HOST} を名乗れませんでした（{exc}）。"
                  f"IP で開いてください: http://{ip}:{self.port}/")
            self._zc = self._info = None
            self.ok = False
            self.ip = ip                       # IP は覚える（再試行を繰り返さない）
            return False
        self.ip, self.ok = ip, True
        return True

    async def stop(self) -> None:
        with contextlib.suppress(Exception):
            if self._zc and self._info:
                await self._zc.async_unregister_service(self._info)
            if self._zc:
                await self._zc.async_close()
        self._zc = self._info = None
        self.ok = False


async def watch_network(adv: Advertiser, period_s: float = 5.0):
    """IP が変わったら名乗り直す。**家 → 会場のテザリングで必ず変わる。**"""
    try:
        while True:
            ip = current_ip()
            if ip and ip != adv.ip:
                was = adv.ip
                if await adv.advertise(ip):
                    print(f"\n  ■ ネットワークが変わりました "
                          f"{was or '(なし)'} → {ip}")
                    print(f"    iPad で開く: {stage_url(adv.port)}\n")
            await asyncio.sleep(period_s)
    finally:
        await adv.stop()
