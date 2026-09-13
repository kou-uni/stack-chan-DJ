#!/usr/bin/env python3
"""どのつまみをメーターに出すかを1つに決める。

## なぜ要るか（2026-09-13 本人の指摘）

> **「大きくなったり小さくなったり、かなり波打ってる」**

DDJ は**複数のCCを同時に流し続ける。** そのすべてを「つまみの値」として
バーに出していたので、バーが自分で暴れていた。実測したログ:

    CC ch0 #0  = 127      ← 14bit の上位
    CC ch0 #32 = 24       ← **その下位バイト。値として意味がない**
    CC ch0 #0  = 69
    CC ch0 #32 = 92

MIDI では **CC 32〜63 は CC 0〜31 の下位バイト**と決まっている。
上位が 1 増えるだけで下位は 0..127 を一周するので、
下位をそのままバーにすると**端から端まで飛ぶ**。

## 決めごと

1. **下位バイト（32〜63）は見ない**（割り当て済みのものは別。人が決めたのだから従う）
2. **同時に出すのは1つだけ。** いま回しているつまみが持ち主
3. 持ち主が決まってから少しの間は**譲らない**。取り合うとちらつく
4. **最初の1発では判断しない。** 差分が取れないと「回している」か分からない

★状態を持つだけ。実機も時計も触らない（呼ぶ側が時刻を渡す）。
"""
from __future__ import annotations

LSB_LO, LSB_HI = 32, 63          # MIDI: CC32-63 は CC0-31 の下位バイト


class MeterPicker:
    """いまバーに出すべき値を1つ返す。**出さないなら None。**"""

    OWN_S = 0.45                 # 一度選んだら、この間は譲らない
    MOVE = 4                     # これ以上動いたら「回している」とみなす

    def __init__(self) -> None:
        self._last: dict[tuple[int, int], int] = {}
        self.owner: tuple[int, int] | None = None
        self.owner_at = 0.0

    def feed(self, ch: int, num: int, value: int, now: float,
             mapped: bool = False) -> float | None:
        """CC が1つ届いた。バーに出す値 0..1 を返す（出さないなら None）。"""
        if not mapped and LSB_LO <= num <= LSB_HI:
            return None                      # 下位バイト。値として意味がない
        key = (ch, num)
        prev = self._last.get(key)
        self._last[key] = value

        if mapped:                           # 人が割り当てたものは常に優先
            self.owner, self.owner_at = key, now
            return value / 127.0

        if prev is None:
            return None                      # 差分が取れない。まだ判断しない
        if abs(value - prev) < self.MOVE:
            # 動いていない。**持ち主なら出し続ける**（バーが消えない）
            return value / 127.0 if self.owner == key else None
        # ★持ち主が居ないときは、そのまま受け取る（居ないのに譲らないのは変）
        if (self.owner is not None and self.owner != key
                and now - self.owner_at < self.OWN_S):
            return None                      # ほかのつまみを回している最中
        self.owner, self.owner_at = key, now
        return value / 127.0
