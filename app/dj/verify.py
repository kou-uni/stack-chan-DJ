#!/usr/bin/env python3
"""`--verify` の中身。**実際に送った角度を測って報告する。**

## なぜ要るか

2026-09-08、pitch の単位を取り違えて**首が真下を向いたまま**になっていた。
「直しました」と3回報告して、3回とも直っていなかった。
ソースを読んでも気づけない。**送っている値を見るまで分からない。**

だから、目で見て判断する前に、機械が数える。
"""
from __future__ import annotations

import asyncio
import json
import time

from constants import YAW_MIN, YAW_MAX, PITCH_REL_MIN, PITCH_REL_MAX

PITCH_CENTER = 45.0                 # gateway が足す中心角
# ★向きを決め打ちしない。**両端を守る。**
#
#   2026-09-12 に実写で測ると pitch 80 は天井（＝上）だった。
#   ところが 2026-09-08 の事故記録は「45 を送って 90 になり真下に張り付いた」。
#   **記録と実測が食い違っている。**
#
#   どちらが正しいかを決めなくても、守りたいことは同じ:
#   **端に張り付いたまま戻らない状態を捕まえる。** だから両端を見る。
PITCH_EXTREME_LOW = 10.0            # これ以下は端に張り付いている
PITCH_EXTREME_HIGH = 80.0           # これ以上も同じ


def judge(ys: list[float], ps: list[float]) -> list[str]:
    """角度の並びを見て、問題を挙げる。**純関数。実機なしで試験できる。**

    ys : yaw（度）      ps : pitch の「45度からの差」
    """
    bad = []
    for y in ys:
        if not (YAW_MIN <= y <= YAW_MAX):
            bad.append(f"yaw {y:.1f} が可動範囲外")
    for p in ps:
        if not (PITCH_REL_MIN <= p <= PITCH_REL_MAX):
            bad.append(f"pitch差 {p:.1f} が可動範囲外（gateway が黙って丸める）")
        a = PITCH_CENTER + p
        if a <= PITCH_EXTREME_LOW or a >= PITCH_EXTREME_HIGH:
            bad.append(f"pitch {a:.0f}° = 端に張り付いている（安全域 "
                       f"{PITCH_EXTREME_LOW:.0f}〜{PITCH_EXTREME_HIGH:.0f}）")
    return bad


async def watch(host: str, port: int, seconds: float = 10.0) -> int:
    """pose ストリームを覗いて、送っている角度を数える。戻り値は終了コード。"""
    import websockets

    ys, ps = [], []
    print(f"\n{seconds:.0f}秒ぶん、実際に送っている角度を測ります …")
    print("（曲を流していない場合はフレームが出ません。それは正常です）\n")

    try:
        async with websockets.connect(f"ws://{host}:{port}/") as ws:
            end = time.time() + seconds
            while time.time() < end:
                try:
                    msg = await asyncio.wait_for(ws.recv(), timeout=max(0.1, end - time.time()))
                except (TimeoutError, asyncio.TimeoutError):
                    break
                d = json.loads(msg)
                if "yaw" not in d:
                    continue
                y, p = float(d["yaw"]), float(d["pitch"])
                ys.append(y); ps.append(p)
    except OSError as exc:
        print(f"★ pose ストリームに繋がらない（{exc}）。console は動いていますか？")
        return 1

    bad = judge(ys, ps)

    if not ys:
        print("フレーム0件。首は静止しています（曲が鳴っていない状態では正常）")
        return 0

    print(f"  {len(ys)}フレーム")
    print(f"  yaw     {min(ys):+6.1f} 〜 {max(ys):+6.1f}   （幅 {max(ys)-min(ys):.0f}°／上限 ±{YAW_MAX:.0f}）")
    print(f"  pitch   {PITCH_CENTER+min(ps):6.1f} 〜 {PITCH_CENTER+max(ps):6.1f}   "
          f"（中心 {PITCH_CENTER:.0f}°。安全域 {PITCH_EXTREME_LOW:.0f}〜{PITCH_EXTREME_HIGH:.0f}）")
    up = sum(1 for p in ps if p < -2)
    print(f"  上向き  {up*100//len(ps)}%   頷き(下向き7°以上) {sum(1 for p in ps if p > 7)}回")

    if bad:
        seen = sorted(set(bad))
        print(f"\n★ 問題 {len(bad)}件:")
        for b in seen[:5]:
            print(f"    {b}")
        return 1

    print("\n問題なし。可動範囲に収まっていて、端にも張り付いていません")
    return 0
