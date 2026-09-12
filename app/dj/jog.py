#!/usr/bin/env python3
"""DJの右レコード（ジョグ）を、照明の向きに変える。仕様は tests/test_jog.py。

## なぜ（2026-09-12 本人の要望）

**演者の手の動きが、そのまま照明になる。**
ただし **触っていないときは自動に返す。** ずっと持っていないと動かない照明は、
演奏の邪魔になる。

## 実測

右ジョグは **ch1 CC#34、中心64の相対値**（63〜66 が来る）。
**絶対位置ではない。** 差分を積んで、離れたら中心へ戻す。
"""
from __future__ import annotations

import time

CENTER = 64
# ★「どこまで回したか」ではなく「いま どっちへ どれだけ速く回しているか」。
#   位置として積むと、数回こすっただけで端に張り付いて**動かなく見える**
#   （2026-09-12 実測：すぐ 1.00 に到達して止まった）
GAIN = 0.16            # 正味1目盛りあたりの振れ
RELAX_S = 0.22         # 手を止めると、この速さで中心へ戻る
DECAY_S = 1.4          # 手を離してから中心へ戻るまで
HOLD_S = 0.35          # これより新しければ「触っている」
JUMP = 8               # これを超える差分は回り込み。速度として数えない

# ★静止中も 63/65 が毎秒190回流れてくる（2026-09-12 実測）。
#   1つずつ足すと、触っていないのに勝手に振れて戻らなくなる。
#   **行ったり来たりは動きではない。短い窓の「正味」で見る。**
WINDOW_S = 0.12
NET_MIN = 3            # 窓の中で、この量を超えて片寄ったら「回している」


class Jog:
    """回した量を覚えて、離れたら中心へ返す。**実機も時計も触らない。**"""

    def __init__(self):
        self._v = 0.0
        self._at = -1e9
        self._recent: list[tuple[float, int]] = []

    def feed(self, raw: int, now: float | None = None) -> None:
        now = time.time() if now is None else now
        d = int(raw) - CENTER
        if abs(d) > JUMP:
            return                       # ★回り込み。速度として数えない
        if d == 0:
            return
        self._recent.append((now, d))
        cut = now - WINDOW_S
        self._recent = [(x, y) for x, y in self._recent if x >= cut]
        net = sum(y for _, y in self._recent)
        if abs(net) < NET_MIN:
            return                       # ★ゆらぎ。動きとして数えない
        # ★速度として扱う。前の値へ寄せるのではなく、いまの速さで上書きする
        self._v = max(-1.0, min(1.0, net * GAIN))
        self._at = now
        self._recent.clear()             # 同じ回転を二度数えない

    def weight(self, now: float | None = None) -> float:
        """手が勝っている割合 0..1。**離すと自動に返る。**"""
        now = time.time() if now is None else now
        age = now - self._at
        if age <= HOLD_S:
            return 1.0
        return max(0.0, 1.0 - (age - HOLD_S) / DECAY_S)

    def value(self, now: float | None = None) -> float:
        """いまの振れ -1..1。**手を止めれば、すぐ中心へ戻る。**

        ★位置ではなく速度。**往復すれば、照明も往復する。**
        """
        now = time.time() if now is None else now
        age = max(0.0, now - self._at)
        relax = max(0.0, 1.0 - age / RELAX_S)    # 止めたら素早く抜ける
        return self._v * relax * self.weight(now)
