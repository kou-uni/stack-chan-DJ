#!/usr/bin/env python3
"""撫でられたときの反応。設計は docs/ux-conversation.md §6.5。

## なぜ作り込むか

**同じ反応を繰り返した瞬間に、機械に戻る。**
振り付けのときと同じ学び。一定の往復は、どれだけ滑らかでも機械に見えた。

**人は同じことをされても、そのときで違う返しをする。**

## 一番効くのは「嫌がる」

**いつも喜ぶ相手は、機械に見える。**
拒否できる相手には人格を感じる。

ただし**嫌がったまま終わらせない**。少し置けば機嫌が戻る。
戻らないと、ただ壊れて見える。

## 状態を持つだけ

実機も時計も触らない。**呼ぶ側が時刻を渡す**（試験できるように）。
"""
from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(frozen=True)
class Reaction:
    """1つの反応。顔と、首の動きの並び。

    moves は (yaw, pitch差) の列。**pitch は45度からの差**（gateway が45を足す）。
    """

    name: str
    face: str
    moves: tuple[tuple[float, float], ...]
    step_s: float = 0.12
    scale: float = 1.0          # 慣れると小さくなる


REACTIONS: dict[str, Reaction] = {
    # 久しぶりに触られた。★いきなり照れるのは慣れすぎ
    "surprised": Reaction(
        "surprised", "surprised",
        ((0, -16), (0, -10), (0, 2), (0, -4), (0, 0)), step_s=0.09),

    # ふつうに撫でられた。首をかしげて小さく揺れる
    "shy": Reaction(
        "shy", "embarrassed",
        ((14, 6), (10, 9), (16, 6), (12, 8), (13, 7)), step_s=0.14),

    # 短く何度も触られた。小刻みに首を振る
    "ticklish": Reaction(
        "ticklish", "happy",
        ((-8, 4), (8, 6), (-7, 3), (7, 5), (-4, 4), (0, 2)), step_s=0.07),

    # 3秒以上撫でられた。ゆっくり傾いて、戻らない
    "melt": Reaction(
        "melt", "happy",
        ((6, 4), (12, 8), (18, 12), (22, 15), (24, 16)), step_s=0.22),

    # ★しつこい。顔を背ける
    "annoyed": Reaction(
        "annoyed", "sad",
        ((-34, -2), (-36, -4), (-34, -2), (-36, -3)), step_s=0.16),

    # 何度も撫でられたあと。反応が小さくなる
    "used_to_it": Reaction(
        "used_to_it", "idle",
        ((5, 3), (3, 4), (4, 3)), step_s=0.16),
}

# 「久しぶり」とみなす間隔。これを超えていたら初回として驚く
FRESH_AFTER_S = 25.0

# 「しつこい」の判定。この秒数の間に、この回数以上
NAGGY_WINDOW_S = 8.0
NAGGY_COUNT = 4

# 嫌がったあと、機嫌が戻るまで
SULK_S = 45.0

# 「とろける」に入る撫での長さ
MELT_MS = 3000

# ★これより長く触られ続けたら嫌がる。**ずっと喜び続けるのは機械。**
#   実測で1分以上の撫でが来る（手を置いたままの人）
TOO_LONG_MS = 25000

# 慣れの効き方
FAMILIAR_AFTER = 3          # これを超えたら慣れてくる
MIN_SCALE = 0.45


@dataclass
class Petting:
    """撫でられた履歴から、次の反応を決める。"""

    _times: list[float] = field(default_factory=list)
    _last: str | None = None
    _sulk_until: float = 0.0

    def react(self, duration_ms: int, now: float) -> Reaction:
        """撫でられた。**どう返すか。**"""
        self._times = [t for t in self._times if now - t <= 120.0]
        recent = [t for t in self._times if now - t <= NAGGY_WINDOW_S]
        gap = now - self._times[-1] if self._times else 1e9
        self._times.append(now)

        name = self._choose(duration_ms, gap, len(recent), now)
        # ★直前と同じなら、ずらす。2回続くとそこで機械に戻る
        if name == self._last:
            name = self._alternative(name)
        self._last = name

        base = REACTIONS[name]
        return Reaction(base.name, base.face, base.moves, base.step_s,
                        self._scale(len(self._times), name))

    # ── どれを出すか ────────────────────────────────
    def _choose(self, duration_ms: int, gap: float, recent: int,
                now: float) -> str:
        if now < self._sulk_until:
            return "annoyed"
        if recent >= NAGGY_COUNT:               # ★しつこい
            self._sulk_until = now + SULK_S
            return "annoyed"
        # ★長さが先。通知は「離した瞬間」に来るので、長さは確定情報。
        #   久しぶりでも、3秒撫でられたなら驚きではなく「とろける」が正しい
        if duration_ms >= TOO_LONG_MS:          # ★長すぎる。さすがに嫌がる
            self._sulk_until = now + SULK_S
            return "annoyed"
        if duration_ms >= MELT_MS:              # 長く撫でられた
            return "melt"
        if gap >= FRESH_AFTER_S:                # 久しぶり
            return "surprised"
        if gap < 1.5:                           # 短く何度も
            return "ticklish"
        if len(self._times) > FAMILIAR_AFTER:   # 慣れてきた
            return "used_to_it"
        return "shy"

    def _alternative(self, name: str) -> str:
        """直前と同じになったときの逃げ先。**近い気分のものへ。**"""
        near = {
            "shy": "ticklish", "ticklish": "shy",
            "surprised": "shy", "melt": "shy",
            "used_to_it": "shy", "annoyed": "used_to_it",
        }
        return near.get(name, "shy")

    def _scale(self, count: int, name: str) -> float:
        """慣れると小さくなる。★ずっと全力だと疲れる。"""
        if name in ("annoyed", "surprised"):
            return 1.0
        if count <= FAMILIAR_AFTER:
            return 1.0
        return max(MIN_SCALE, 1.0 - (count - FAMILIAR_AFTER) * 0.12)
