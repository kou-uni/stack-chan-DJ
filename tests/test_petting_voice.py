"""撫でられたときの声。

## なぜ（2026-09-12 本人の指摘）

> **「違いがあまり出ないなー、声を出してくれたらいいかも」**

6つの反応を作ったが、**顔と首だけでは違いが伝わらなかった。**
実機は小さく、首の振り幅も限られる。**声が一番わかりやすい差になる。**

## 気をつけること

- **短く。** 長いと、撫でた瞬間から離れてしまう
- **同じ言葉を続けない。** 2回目で機械に戻る
- **喋っている最中は割り込まない。** 会話を潰さない
"""
import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "app" / "dj"))
from petting import REACTIONS, VOICE, pick_voice   # noqa: E402


def test_六つ全部にセリフがある():
    for name in REACTIONS:
        assert VOICE.get(name), f"{name} に声がない"


def test_短い():
    """★長いと、撫でた瞬間から離れてしまう。"""
    for name, lines in VOICE.items():
        for l in lines:
            assert len(l) <= 14, f"{name}: 「{l}」が長い"


def test_反応ごとに言葉が違う():
    """★同じことを言うなら、6つに分けた意味がない。"""
    seen = {}
    for name, lines in VOICE.items():
        for l in lines:
            assert l not in seen, f"「{l}」が {seen.get(l)} と {name} で重複"
            seen[l] = name


def test_同じ言葉を続けて言わない():
    said = []
    for _ in range(12):
        said.append(pick_voice("shy", said[-1] if said else None))
    assert all(a != b for a, b in zip(said, said[1:])), said


def test_知らない反応でも落ちない():
    assert pick_voice("そんな反応はない", None) == ""


# ── 顔は6つしか焼かれていない（2026-09-12 実物確認）────────
#
# app/avatar/frames: idle / happy / thinking / sad / surprised / embarrassed
# **反応も6つ。1対1で当てられる。**
#
# 実物を見て決めた（faces6.png）:
#   thinking は**半目**。とろけた目に見える → melt はこれ
#   happy は∩の笑い目 → くすぐったい
#   embarrassed は頬が赤い → 照れ

BAKED = {"idle", "happy", "thinking", "sad", "surprised", "embarrassed"}


def test_焼かれていない顔を使わない():
    """★angry や sleepy は焼いていない。指定しても出ない。"""
    for name, r in REACTIONS.items():
        assert r.face in BAKED, f"{name} が焼かれていない顔 {r.face} を使っている"


def test_顔が重複していない():
    """★同じ顔だと、声が違っても差が伝わらない。"""
    faces = [r.face for r in REACTIONS.values()]
    assert len(set(faces)) == len(faces), faces
