#!/usr/bin/env python3
"""どのモジュールからも使う定数と小道具。

★可動範囲は gateway 側（follow_pose_stream.py）と**必ず同じ値**にすること。
  ここを超えた角度は向こうで黙って丸められ、コードを読んでも気づけない。
  （2026-09-08、頷きが40度で潰れていた原因）
"""
from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
MAPPING = ROOT / "app" / "dj" / "mapping.json"

# gateway 側の可動範囲（follow_pose_stream.py と同じ値）
YAW_MIN, YAW_MAX = -90.0, 90.0
PITCH_REL_MIN, PITCH_REL_MAX = -40.0, 40.0   # 中心 45° からの相対値

MODE_IDLE = "off"   # 音に反応しない
MODE_DJ = "dj"      # 音に合わせて踊る

MODE_LABEL = {MODE_IDLE: "OFF（音に反応しない）", MODE_DJ: "DJ（音に反応する）"}
MODE_FACE = {MODE_IDLE: "idle", MODE_DJ: "happy"}
MODE_ORDER = (MODE_IDLE, MODE_DJ)


def _scale(v: int, lo: float, hi: float, in_lo: int = 0, in_hi: int = 127) -> float:
    """MIDI の 0..127 を角度などの範囲へ写す。"""
    span = max(1, in_hi - in_lo)
    t = (max(in_lo, min(in_hi, v)) - in_lo) / span
    return lo + t * (hi - lo)
