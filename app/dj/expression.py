#!/usr/bin/env python3
"""表情と口。**実機には書かない。`presence` に「あるべき姿」を言うだけ。**

設計は docs/architecture.md。書くのは reconcile.Reconciler だけ（§4 I1）。

例外は2つ。どちらも「表示の状態」ではないため。
  - `set_auto_torque_release` 実機側の設定。起動時に一度だけ
  - `set_mouth_sequence`      口は実機のキュー再生。出力ストリームで持ち主は1人
"""
from __future__ import annotations

import asyncio
import contextlib
import json
import math
import random
import time

from constants import (ROOT, MAPPING, YAW_MIN, YAW_MAX, PITCH_REL_MIN,
                       PITCH_REL_MAX, MODE_IDLE, MODE_DJ, MODE_LABEL,
                       MODE_FACE, MODE_ORDER, _scale)  # noqa: F401


class ExpressionMixin:
    """表情まわり。**実機には書かない。`presence` に「あるべき姿」を言うだけ。**

    設計 §4 I1。書くのは reconcile.Reconciler だけ。
    """

    # ── ② まばたき。待機中の「生きている感」はこれで出す
    async def start_idle_behaviour(self):
        # 顔と瞬きは Presence の既定（待機）がそのまま正しいので、何も言わない。
        # 自動脱力は「表示の状態」ではなく実機の設定なので、ここで一度だけ入れる。
        await self.gw.call("set_auto_torque_release",
                           enabled=True, timeout_ms=self.args.auto_release_ms)
        print(f"まばたきON / 自動脱力 {self.args.auto_release_ms}ms")

    # ── 表情。押したら N 秒で idle に戻す（パッドを idle に使わない）
    async def show_face(self, face: str, slot: str):
        """ボタンで表情を出す。**期限つきの上書きとして置くだけ。**

        ★以前は「顔を出す」「N秒後に戻す」を自分でやっていて、
          戻す処理が走る前に別の顔が来ると戻らなくなった。
          期限を Presence に持たせれば、戻し忘れが構造的に起きない（設計 I5）。

        ★まばたきは Presence が決める。表情を出している間は自動で止まる。
          （まばたきのコマは「素の顔」なので、happy 中に瞬くと表情が壊れる）
        """
        self.presence.overlay("touch", face, seconds=self.idle_after)

        # ① しょんぼりは「脱力」とセット。顔と体を一致させる。
        #   トルクは「表示の状態」ではないので、ここで直接扱う（設計 §4 I1 の例外ではなく、
        #   首の持ち主＝Arbiter とも別の、実機の設定に近いもの）
        if slot == "btn_sad":
            if not self._torque_off:                      # 二重に切らない
                await self.set_torque(False)
                print("    （脱力: トルクを切りました）")
        else:
            # sad 以外の表情に移ったら、体も起こす。
            # つまみを触らずに次の曲へ行っても、脱力したままにならない
            await self.wake_servos()

    def _show_pose(self, moved: str) -> None:
        """つまみの現在値を1行で上書き表示する。動いているのが目で分かる。"""
        if self.args.quiet:
            return
        now = time.time()
        if now - self._last_pose_print < 0.1:      # 秒10回まで
            return
        self._last_pose_print = now
        bar = lambda v, lo, hi: "─" * round((v - lo) / (hi - lo) * 20)
        print(f"  yaw {self.pose.yaw:+6.1f}° |{bar(self.pose.yaw, YAW_MIN, YAW_MAX):<20}|"
              f"  pitch {self.pose.pitch:+6.1f}° "
              f"|{bar(self.pose.pitch, PITCH_REL_MIN, PITCH_REL_MAX):<20}|"
              f"  ({moved})", end="\r")
    # ── ③ 口をリズムに合わせる。デバイス側キュー再生なので拍がずれない
    async def mouth_to_beat(self):
        while True:
            await asyncio.sleep(self.args.mouth_period)
            if self.args.no_mouth:
                continue
            snap = await self.gw.call("beat_meta_snapshot")
            bpm = self._extract_bpm(snap) or self.args.fallback_bpm
            if not bpm:
                continue
            beat_ms = int(60000 / bpm)
            half = max(60, beat_ms // 2)
            steps = []
            for _ in range(4):                      # 2拍ぶんを先に積む
                steps.append({"shape": "open", "duration_ms": half})
                steps.append({"shape": "closed", "duration_ms": beat_ms - half})
            await self.gw.call("set_mouth_sequence", steps=steps)
            self.led.color = self.args.led_color
    async def knob_face_loop(self):
        """つまみを操作している間だけ顔を変え、離したら元に戻す。

        ★「いま人が触っている」ことを顔に出す。
          操作している側は自分の入力が届いているか分からないので、
          反応があると安心する。首が動くだけでは、
          自分が動かしたのか勝手に動いたのか区別がつかない。

        戻すのは**つまみの主導権を手放すのと同じタイミング**（--knob-hold）に合わせる。
        顔が先に戻ると「もう効いていない」ように見え、後だと間延びする。
        """
        if not self.args.knob_face:
            return
        while True:
            await asyncio.sleep(0.15)
            if self.pose.active():
                # 触っている間ずっと置き直す。離れれば期限で自然に消える。
                # ★戻すタイミングを自分で計算しない。--knob-hold と一致する。
                self.presence.overlay("knob", self.args.knob_face,
                                      seconds=self.args.knob_hold)
