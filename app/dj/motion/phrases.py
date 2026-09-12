#!/usr/bin/env python3
"""振り付け。**状態を持たない純関数**として書く。

## なぜ純関数にするか

以前は `PoseState` のメソッドで、`self.bpm` `self._phrase` `self._groove_now` …
に依存していた。**実機を繋がないと動きを確かめられなかった。**

その結果、置換が空振りして「振り付けが一度も入っていない」状態に3回気づけなかった。

引数だけで決まる形にすれば、**実機なしで全フレーズの全時刻を検証できる。**

## 単位の約束

- `yaw`   : 度。負が左、正が右。±90 まで
- `pitch` : **中心45度からの差**。負が上、正が下。±40 まで
            （gateway の `follow_pose_stream` が 45 を足す）

## 客席の前提

**客は左右に広がっている。真上にも真下にもいない。**
横を大きく使い、縦は「乗っている」を出す補助に留める。
"""
from __future__ import annotations

import math

YAW_LIM, PITCH_LIM = 90.0, 40.0

# 振り付けの種類。順不同で切り替える
PHRASES = ("sway", "scan", "point_l", "point_r", "accent", "double",
           "front", "nod2", "yes")

# フレーズの長さ（拍）。★一定にしない。
# 8拍きっかりで律儀に変わると、変化そのものが「規則」になって機械に見える。
PHRASE_LENS = (8, 4, 8, 16, 6, 8, 12, 4)


def clamp(v: float, lim: float) -> float:
    return max(-lim, min(lim, v))


def pick(n: int, bpm: float, prev: str) -> str:
    """n 番目のフレーズを選ぶ。同じものを続けない。"""
    nxt = [p for p in PHRASES if p != prev]
    return nxt[(n * 7 + int(bpm)) % len(nxt)]


def phrase_len(n: int) -> int:
    return PHRASE_LENS[n % len(PHRASE_LENS)]


def angles(phrase: str, beat_t: float, in_phrase: float,
           sway: float, nod: float, dip: float | None = None) -> tuple[float, float]:
    """1フレーズぶんの角度を返す。

    beat_t    : 拍を単位にした時刻（1.0 = 1拍）
    in_phrase : フレーズ内の進み 0..1
    sway/nod  : ノリを反映済みの振り幅（度）
    dip       : 頷きの深さの基準。★ノリで薄めない（省略時は nod）
    """
    if dip is None:
        dip = nod
    w = beat_t * math.tau                       # 1拍で1周
    bob = -abs(math.sin(w)) * nod * 0.5         # 縦は控えめ。少し下を向く
    # ★pitch は大きいほど上（2026-09-12 実写で確認）。この式は下向き

    if phrase == "scan":                        # フロアを端から端へ見渡す
        base = math.sin(in_phrase * math.tau - math.pi / 2)
        y, d = base * sway * 1.2 + math.sin(w) * sway * 0.15, bob * 0.6
    elif phrase in ("point_l", "point_r"):      # 片側の客を煽る
        side = -1 if phrase == "point_l" else 1
        y, d = sway * 0.9 * side + math.sin(w) * sway * 0.28, bob
    elif phrase == "accent":                    # 1拍目だけ大きく
        k = 1.7 if (int(beat_t) % 4 == 0) else 0.40
        y, d = math.sin(w) * sway * k, bob * k
    elif phrase == "double":                    # 半拍で往復
        y, d = math.sin(w * 2) * sway * 0.85, bob * 0.8
    elif phrase == "front":                     # 正面で小さく刻む
        y, d = math.sin(w) * sway * 0.20, bob
    elif phrase == "nod2":
        # ★「うんうん」は sin では作れない。ゆっくり下がると頷きに見えない。
        #   拍の頭でガッと落として、拍の25%で戻す三角波にする。
        f = beat_t % 1.0
        tri = (1.0 - f / 0.25) if f < 0.25 else 0.0
        y, d = math.sin(w) * sway, tri * dip * 5.0
    elif phrase == "yes":                       # 「うんうん！」2連発
        f = beat_t % 2.0
        if f < 1.0:
            q = f % 0.5
            tri = (1.0 - q / 0.22) if q < 0.22 else 0.0
            y, d = math.sin(w) * sway, tri * dip * 6.0
        else:
            y, d = math.sin(w) * sway, bob
    else:                                       # sway : 基本の左右
        y, d = math.sin(w) * sway, bob

    return clamp(y, YAW_LIM), clamp(d, PITCH_LIM)
