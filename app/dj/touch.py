#!/usr/bin/env python3
"""頭を撫でられたときの反応。仕様は tests/test_touch_reactions.py。

## 2026-09-12 に作り直した理由

ここは `get_touch_state` を0.8秒ごとに**問い合わせて**いた。
ところが実機は**押し出し型で通知を送る**（`touch_events.py` の冒頭を読むこと）。
問い合わせても `idle` しか返らない経路だったので、**一度も反応していなかった。**

撫でて動いていたのは**ファーム自身の反応**（顔＋サーボの揺れ）。
こちらで用意した6つの反応（`petting.py`）は死んでいた。

> **モジュールが在ることと、呼ばれていることは別。**

## 作り

    JSONL（押し出し）→ TouchEvents → Petting が反応を選ぶ → TouchReactor が出す

実機も時計も触らない `Petting` に判断を任せ、
`TouchReactor` は**出すだけ**にする。だから実機なしで試験できる。

## 触っても状態は変えない

**可愛いから触る人がいる。** その動作に機能を割り当てると
「触ったら勝手に挙動が変わった」になって体験が壊れる。
**意図せず起きる操作に、状態を変える意味を持たせない。**
"""
from __future__ import annotations

import asyncio

from petting import Petting

# ★どこまでを「撫で」とみなすか。**実際の使われ方から決める。想像で決めない。**
#
#   2026-09-12 実測: 9499ms / 52690ms / 92700ms
#   → **手を置いたまま撫でる人**がいる。8秒で切ると全部捨てることになる。
#
#   250899ms は何かが載っている（実測）。そこは合図にしない。
MAX_STROKE_MS = 150000


class TouchReactor:
    """撫でられた通知を、顔と首の動きにする。**出すだけ。**"""

    def __init__(self, presence, pose, face_s: float = 3.0,
                 max_stroke_ms: int = MAX_STROKE_MS, quiet: bool = False):
        self.presence, self.pose = presence, pose
        self.face_s, self.max_stroke_ms, self.quiet = face_s, max_stroke_ms, quiet
        self.petting = Petting()
        self._task: asyncio.Task | None = None

    async def handle(self, ev: dict, now: float) -> None:
        dur = int(ev.get("duration_ms") or 0)
        if dur > self.max_stroke_ms:
            return                                  # ★置きっぱなし

        r = self.petting.react(dur, now)
        if not self.quiet:
            print(f"    ♡ {r.name}（{dur}ms）")
        self.presence.overlay("touch", r.face, self.face_s)

        # ★前の反応が残っていたら止める。待たせると反応の遅い機械に見える
        if self._task and not self._task.done():
            self._task.cancel()
        self._task = asyncio.ensure_future(self._play(r))
        await self._task

    async def _play(self, r) -> None:
        """首の動きを順に出して、**必ず戻す。**

        ★戻さないと傾いたままになる。cancel されても戻す（finally）。
        """
        try:
            for yaw, pitch in r.moves:
                self.pose.hold = (yaw * r.scale, pitch * r.scale)
                await asyncio.sleep(r.step_s)
        except asyncio.CancelledError:
            raise
        finally:
            self.pose.hold = None


class TouchMixin:
    """console 側の入口。**押し出し型で受け、押し出し型で出す。**"""

    async def touch_loop(self):
        from touch_events import TouchEvents, notify_config_ok

        ok, why = notify_config_ok()
        if not ok:
            # ★沈黙は故障と見分けがつかない。届かないなら起動時に言う
            print(f"    ★ 頭なでが届きません: {why}")

        te = TouchEvents(max_stroke_ms=10 ** 9)     # 選別は TouchReactor 側で
        te.catch_up()                                # 起動前の分は無視する
        reactor = TouchReactor(self.presence, self.pose,
                               face_s=self.args.touch_face_s)
        loop = asyncio.get_running_loop()
        while True:
            ev = te.poll()
            if ev is None:
                await asyncio.sleep(0.12)
                continue
            await reactor.handle(ev, now=loop.time())
