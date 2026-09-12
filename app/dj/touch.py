#!/usr/bin/env python3
"""頭を撫でられたときの反応。

console.py の Console から切り出した mixin。**中身は1行も変えていない。**
Console がこれらを継承して1つのクラスになる。
"""
from __future__ import annotations

import asyncio
import json
import math
import random
import time

from constants import (ROOT, MAPPING, YAW_MIN, YAW_MAX, PITCH_REL_MIN,
                       PITCH_REL_MAX, MODE_IDLE, MODE_DJ, MODE_LABEL,
                       MODE_FACE, MODE_ORDER, _scale)  # noqa: F401


class TouchMixin:
    # ── 頭を撫でたら照れる（モードは変えない）
    async def touch_loop(self):
        """頭タッチは**反応にだけ使う**。モードの切り替えには使わない。

        ★可愛いから触る人がいる。その動作に機能を割り当てると、
          「触ったら勝手に挙動が変わった」になって体験が壊れる。
          **意図せず起きる操作に、状態を変える意味を持たせない。**

        ポーリングは遅めにする。音声と同じ WebSocket を使うので、
        速く回すと拍の検出を邪魔する（一度それで壊した）。
        """
        while True:
            await asyncio.sleep(self.args.touch_poll_s)
            d = self._as_json(await self.gw.call("get_touch_state")) or {}
            if not d.get("available"):
                continue
            ev, age = d.get("last_event"), d.get("last_event_age_ms")
            if ev in (None, "idle") or age is None:
                continue
            # ★ゾーンが押されっぱなしのことがある（実測：raw=56 が200秒以上固着）。
            #   その状態のイベントは信用しない。手が乗っている／誤検出のどちらか。
            raw = d.get("raw") or 0
            if raw == self._touch_raw_was:
                self._touch_stuck += 1
            else:
                self._touch_stuck = 0
                self._touch_raw_was = raw
            if self._touch_stuck >= self.args.touch_stuck_polls:
                continue
            # 同じイベントを二重に拾わないよう、発生時刻で照合する
            stamp = int(time.time() * 1000) - int(age)
            if self._touch_seen_ms is not None and abs(stamp - self._touch_seen_ms) < 1200:
                continue
            if age > self.args.touch_poll_s * 1000 + 1500:
                self._touch_seen_ms = stamp      # 起動前の古いイベントは無視
                continue
            self._touch_seen_ms = stamp
            await self.react_to_touch(ev)

    async def react_to_touch(self, ev: str) -> None:
        """撫でられたら照れる。触られたら驚く。数秒で戻る。

        ★戻す処理を自分で持たない。顔は期限つきの上書き、首は Arbiter のポーズ。
          以前はここで `set_avatar` と `move_head` を直接叩き、
          戻す前に次の出来事が来ると戻らなくなっていた（設計 I1 / I5）。
        """
        face = "embarrassed" if ev == "stroke" else "surprised"
        print(f"    ♡ 頭を{'なでられた' if ev == 'stroke' else '触られた'} → {face}")
        self.presence.overlay("touch", face, seconds=self.args.touch_face_s)

        if ev == "stroke":                       # 撫でられたら、うれしそうに少し首をかしげる
            if self._touch_task and not self._touch_task.done():
                self._touch_task.cancel()

            async def tilt():
                self.pose.hold = (12, 7)         # ★45 からの差。45 を送ると真下になる
                await asyncio.sleep(self.args.touch_face_s)
                self.pose.hold = None
            self._touch_task = asyncio.create_task(tilt())
