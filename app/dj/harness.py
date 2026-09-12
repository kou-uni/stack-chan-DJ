#!/usr/bin/env python3
"""受け入れ試験を**単独で**走らせる土台。仕様は tests/test_harness.py。

## 解く問題

`device_check.py` は首とLEDを直接書く。console は**唯一の書き手**（I2）で
20秒ごとに全部を書き直す。**二人が書けば、測った値が誰のものか分からない。**

しかもストリーム試験は console の 8770/8771 に繋ぎに行く。
console を止めるだけだと**偽の×**が出て、それを基準にすると比較が狂う。

## だからこうする

    console を止める → 自分でサーバを立てる → 測る → 必ず戻す

**焼く前と後で、同じ条件になる。** 比較が意味を持つのはそのときだけ。
"""
from __future__ import annotations

import contextlib
import socket
import subprocess
from pathlib import Path


def port_busy(port: int, host: str = "127.0.0.1") -> bool:
    """誰かが listen しているか。★プロセス名で探さない。

    以前、古い gateway が `pkill -f stackchan_mcp` で死なずに残った
    （プロセス名がただの "Python" だった）。**名前ではなく、口を見る。**
    """
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.settimeout(0.3)
        return s.connect_ex((host, port)) == 0


class LaunchCtl:
    """launchd の薄い口。試験では差し替える。"""

    def __init__(self, uid: int | None = None):
        import os
        self.uid = uid if uid is not None else os.getuid()

    def _domain(self, label: str) -> str:
        return f"gui/{self.uid}/{label}"

    def is_running(self, label: str) -> bool:
        r = subprocess.run(["launchctl", "print", self._domain(label)],
                           capture_output=True, text=True)
        return "state = running" in r.stdout

    def stop(self, label: str) -> None:
        subprocess.run(["launchctl", "bootout", self._domain(label)],
                       capture_output=True)

    def start(self, label: str) -> None:
        """止めたものを戻す。

        ★`bootout` は**読み込みごと消す**ので、`kickstart` では戻らない。
          2026-09-12、これで console が落ちたまま放置され、実機が全部無反応になった。
          **止める手段と戻す手段は、対になっていないといけない。**
        """
        plist = Path.home() / "Library" / "LaunchAgents" / f"{label}.plist"
        if plist.exists():
            subprocess.run(["launchctl", "bootstrap", f"gui/{self.uid}",
                            str(plist)], capture_output=True)
        subprocess.run(["launchctl", "kickstart", self._domain(label)],
                       capture_output=True)


class ConsolePause:
    """試験の間だけ console を黙らせる。**終わったら必ず戻す。**

    ★戻し忘れると、実機が沈黙したまま放置される。
      試験が例外で落ちても戻す（だから with 文にしてある）。
    ★もともと止まっていたなら触らない。**勝手に起動しない。**
    """

    def __init__(self, label: str = "com.uni.stackchan.console",
                 ctl: object | None = None):
        self.label = label
        self.ctl = ctl or LaunchCtl()
        self._was_running = False

    def __enter__(self):
        self._was_running = self.ctl.is_running(self.label)
        if self._was_running:
            self.ctl.stop(self.label)
        return self

    def __exit__(self, *exc):
        if self._was_running:
            self.ctl.start(self.label)
        return False        # ★例外は握りつぶさない


@contextlib.asynccontextmanager
async def throwaway_ws(port: int, host: str = "127.0.0.1"):
    """ストリーム試験のためだけの WebSocket サーバ。受け取って捨てる。

    ★`async with websockets.serve(...)` にしないこと。
      **開いている接続が閉じるまで待ち続ける。** 以前 --verify が
      これで終わらなくなった。明示的に close して wait_closed する。
    """
    import websockets

    async def handler(ws):
        try:
            async for _ in ws:
                pass
        except Exception:
            pass

    server = await websockets.serve(handler, host, port)
    try:
        yield server
    finally:
        server.close()
        with contextlib.suppress(Exception):
            import asyncio
            await asyncio.wait_for(server.wait_closed(), timeout=3)
