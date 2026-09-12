#!/usr/bin/env python3
"""首の主導権を1箇所に集める。

## なぜ要るか（2026-09-08 の実績）

リファクタ前、首を動かす経路が **19箇所・5系統**あった。

    つまみ / 踊り / キメのポーズ / 直接 move_head / gateway の beat_mode

**調停役がどこにもいなかった。** その日の重いバグは、ほぼ全部ここ発だった。

- pose ストリームが毎秒20回「正面」を送り続け、踊りを潰していた
- `beat_mode_start` が後から motion を有効にし、モード設定を上書きした
- `move_head`（絶対角度）と pose ストリーム（45からの差）の**単位が混在**し、
  45 を送って 90 → 85 にクランプされ、真下に張り付いた

## 決めごと

1. **角度を書けるのはこのクラスだけ。** 他のどこも `move_head` を呼ばない
2. **単位は「45からの差」に統一。** gateway が `pitch_center_deg(=45)` を足す
3. **優先順位は固定** ── つまみ > キメのポーズ > 踊り > 中立
4. 誰が主導権を持っているかは `owner` で常に取り出せる
"""
from __future__ import annotations

import time

# gateway 側の可動範囲（follow_pose_stream.py と同じ値）
YAW_MIN, YAW_MAX = -90.0, 90.0
PITCH_OFFSET_MIN, PITCH_OFFSET_MAX = -40.0, 40.0   # 中心45からの差


def clamp(v: float, lo: float, hi: float) -> float:
    return max(lo, min(hi, v))


class HeadArbiter:
    """首の狙い角度を決める唯一の場所。

    各系統は「こう向きたい」を置くだけで、実際にどれを採るかはここが決める。
    """

    # 大きいほど強い
    PRIORITY = ("knob", "pose", "dance")

    def __init__(self, knob_hold_s: float = 2.0):
        self.knob_hold_s = knob_hold_s
        self._knob: tuple[float, float] | None = None
        self._knob_at = 0.0
        self._pose: tuple[float, float] | None = None      # キメのポーズ
        self._dance: tuple[float, float] | None = None     # 踊り
        self.dancing = False                                # 踊りを流してよいか

    # ── 各系統からの入力 ──────────────────────────────
    def set_knob(self, yaw: float, pitch_offset: float) -> None:
        """つまみ。触っている間だけ最優先になる。"""
        self._knob = (yaw, pitch_offset)
        self._knob_at = time.time()

    def set_pose(self, yaw: float | None, pitch_offset: float = 0.0) -> None:
        """キメのポーズ。None で解除。"""
        self._pose = None if yaw is None else (yaw, pitch_offset)

    def set_dance(self, yaw: float, pitch_offset: float) -> None:
        """踊り。毎フレーム更新される。"""
        self._dance = (yaw, pitch_offset)

    # ── 判定 ─────────────────────────────────────
    def knob_active(self) -> bool:
        return self._knob is not None and \
            (time.time() - self._knob_at) <= self.knob_hold_s

    @property
    def owner(self) -> str | None:
        """いま誰が首を握っているか。何も出さないときは None。"""
        if self.knob_active():
            return "knob"
        if self._pose is not None:
            return "pose"
        if self.dancing and self._dance is not None:
            return "dance"
        return None

    def angles(self) -> tuple[float, float]:
        """採用する角度（yaw, pitch_offset）。範囲は必ずここで丸める。"""
        who = self.owner
        src = {"knob": self._knob, "pose": self._pose, "dance": self._dance}.get(who)
        yaw, pitch = src if src else (0.0, 0.0)
        return (clamp(yaw, YAW_MIN, YAW_MAX),
                clamp(pitch, PITCH_OFFSET_MIN, PITCH_OFFSET_MAX))

    def should_emit(self) -> bool:
        """いまフレームを送るべきか。

        ★誰も主導権を持たないとき、送らない。
          送り続けると「正面を向け」を毎秒20回投げることになり、
          gateway 側の踊り（beat_mode）を潰す。実際それで一度壊した。
        """
        return self.owner is not None
