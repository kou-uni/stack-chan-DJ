#!/usr/bin/env python3
"""反映役。**実機の状態を書くのはここだけ。**（設計 §4 I1）

`Presence`（あるべき姿）と、いま実機がどうなっているかの記録を突き合わせ、
**違うところだけ**送る。

## なぜ「差分だけ」か

毎周期ぜんぶ送ると、実機との往復が増えて音声の取り込みを邪魔する。
2026-09-08、命令を 0.4 秒間隔で投げて拍が取れなくなった。

## なぜ周期的に送り直すか

送りっぱなしだと、外から誰かが乱したときに戻らない。
実機を再起動したとき、診断ツールを流したとき、手で叩いたとき——
**乱れても、次の周期で必ず戻る。**
"""
from __future__ import annotations

import asyncio
import contextlib


class Reconciler:
    """あるべき姿を実機へ反映する。**唯一の書き手。**"""

    def __init__(self, gw, presence, period_s: float = 0.25,
                 resync_s: float = 20.0, quiet: bool = False):
        self.gw, self.presence = gw, presence
        self.period_s, self.resync_s = period_s, resync_s
        self.quiet = quiet
        self._applied: dict = {}                  # 最後に送った内容
        self._since = 0.0                         # 全部送り直すまでの残り
        self.writes = 0                           # 送った回数（試験と診断用）

    async def apply(self, force: bool = False) -> list[str]:
        """1回ぶん反映する。送ったものの名前を返す。"""
        want = self.presence.desired()
        sent = []

        async def put(key, tool, **args):
            if not force and self._applied.get(key) == want[key]:
                return
            with contextlib.suppress(Exception):
                await self.gw.call(tool, **args)
                self._applied[key] = want[key]
                self.writes += 1
                sent.append(key)

        # ★順番に意味がある。
        #   顔を出してから瞬きを決める（顔を変えると実機側で瞬きが乱れる）。
        await put("face", "set_avatar", face=want["face"])
        await put("blink", "set_blink", enabled=want["blink"])
        # ★踊らせるかはモードが決める。OFF なら必ず切る（I3）
        await put("beat_motion", "beat_mode_update",
                  motion_enabled=want["beat_motion"],
                  led_enabled=want["beat_motion"])
        await put("led_rgb", "set_all_leds",
                  r=want["led_rgb"][0], g=want["led_rgb"][1], b=want["led_rgb"][2])
        return sent

    def forget(self) -> None:
        """記録を捨てる。実機が入れ替わったあとに呼ぶ（次回に全部送り直す）。"""
        self._applied.clear()

    async def loop(self):
        """周期的に反映し続ける。乱されても戻る。"""
        while True:
            await asyncio.sleep(self.period_s)
            self._since += self.period_s
            force = self._since >= self.resync_s
            if force:
                self._since = 0.0
            sent = await self.apply(force=force)
            if sent and not self.quiet:
                d = self.presence.desired()
                print(f"  ▸ {'/'.join(sent)} → 顔={d['face']} 瞬き="
                      f"{'ON' if d['blink'] else 'OFF'}")
