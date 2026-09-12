#!/usr/bin/env python3
"""スタックチャンのマイクが「いま何を聞いているか」を測る。

    ./.venv/bin/python scripts/hear.py           # 8秒ぶん測る
    ./.venv/bin/python scripts/hear.py --sec 15

beat mode が動いているときだけ使える（録音のリングバッファから取り出すため）。

## なぜ要るか

「踊らない」とき、原因は3つに分かれる。

    ① 音が届いていない（音量・距離）
    ② 音は届いているが拍が立っていない（曲の性質）
    ③ 拾えているのに設定で止めている（感度・タイムアウト）

**耳が聞いている音を測れば①と②が切り分けられる。** 推測しなくてよくなる。
当日の会場でも、感度を決めるのにそのまま使える。
"""
from __future__ import annotations

import argparse
import array
import asyncio
import contextlib
import json
import math
import wave

from mcp import ClientSession
from mcp.client.streamable_http import streamablehttp_client

# beat/mode.py の定数
FLOOR_MOST, FLOOR_DEFAULT, FLOOR_LEAST = 0.001, 0.004, 0.025


async def grab(url: str, seconds: float) -> str | None:
    async with contextlib.AsyncExitStack() as st:
        rd, wr, _ = await st.enter_async_context(streamablehttp_client(url))
        s = await st.enter_async_context(ClientSession(rd, wr))
        await s.initialize()
        r = await s.call_tool("beat_clip_save", {"seconds": seconds})
        for b in getattr(r, "content", []) or []:
            t = getattr(b, "text", None)
            if t:
                d = json.loads(t)
                if not d.get("ok"):
                    print(f"取れませんでした: {d}")
                    return None
                return d["path"]
    return None


def analyse(path: str) -> None:
    w = wave.open(path)
    n, sr = w.getnframes(), w.getframerate()
    a = array.array("h")
    a.frombytes(w.readframes(n))
    w.close()

    rms = math.sqrt(sum(v * v for v in a) / len(a)) / 32768
    peak = max(abs(v) for v in a) / 32768
    print(f"{n/sr:.1f}秒 / {sr}Hz\n")

    step = sr // 4
    print("0.25秒ごとの音量")
    loud = 0
    for i in range(0, len(a) - step, step):
        seg = a[i:i + step]
        r = math.sqrt(sum(v * v for v in seg) / len(seg)) / 32768
        if r >= FLOOR_DEFAULT:
            loud += 1
        mark = "■" if r >= FLOOR_LEAST else ("●" if r >= FLOOR_DEFAULT else
               ("·" if r >= FLOOR_MOST else " "))
        print(f"  {i/sr:5.2f}s {r:.5f} {mark} {'█' * min(46, int(r * 500))}")

    frac = loud / max(1, (len(a) // step))

    # ★平均音量だけ見ても足りない。拍の検出は「平均からどれだけ突出するか」を見ている。
    #   tracker.py: threshold_ratio=1.65（直近平均の1.65倍）, rise_ratio=1.18（立ち上がり）
    #   なだらかに上下しているだけの音は、いくら大きくても拍にならない。
    #   短い窓のRMSを並べて、平均の1.65倍を超える山がいくつあるかを数える。
    fine = sr // 20                       # 50ms
    win = []
    for i in range(0, len(a) - fine, fine):
        seg = a[i:i + fine]
        win.append(math.sqrt(sum(v * v for v in seg) / len(seg)) / 32768)
    avg = sum(win) / max(1, len(win))
    spikes = sum(1 for v in win if v >= avg * 1.65)
    spikes_per_sec = spikes / max(0.001, n / sr)
    crest = peak / rms if rms > 0 else 0

    print(f"\n全体   RMS={rms:.5f}   ピーク={peak:.4f}   ピーク/RMS={crest:.1f}")
    print(f"既定の下限({FLOOR_DEFAULT})を超えていた時間: {frac*100:.0f}%")
    print(f"平均の1.65倍を超える山: {spikes}回 = {spikes_per_sec:.2f}回/秒")

    print("\n判定")
    ok_level = rms >= FLOOR_DEFAULT
    ok_punch = spikes_per_sec >= 1.2      # 拍として使えるのは毎秒1回以上

    if not ok_level:
        print("  ✗ 音量が足りない。マイクに届いていない → **音量を上げるか近づける**")
    elif not ok_punch:
        print("  ✗ 音量は足りているが、**立ち上がりが無い**。")
        print("     拍の検出は『平均の1.65倍に跳ねる瞬間』を探すので、")
        print("     なだらかな曲・音量が小さめの曲は、いくら鳴っていても踊らない。")
        print("     → **もっと音量を上げる**（山が大きくなる）")
        print("     → **キックがはっきりした曲にする**")
    else:
        print("  ◎ 拍として使える。踊るはず")

    if crest < 6:
        print(f"  ⚠ ピーク/RMS が {crest:.1f} と低い。音が潰れている（圧縮のかけすぎ・音量不足）")
    if peak > 0.9:
        print("  ⚠ ピークが振り切れている。歪んで立ち上がりが潰れる")


def main() -> int:
    ap = argparse.ArgumentParser(description="スタックチャンの耳が聞いている音を測る")
    ap.add_argument("--gateway", default="http://127.0.0.1:8767/mcp")
    ap.add_argument("--sec", type=float, default=8.0)
    a = ap.parse_args()
    path = asyncio.run(grab(a.gateway, a.sec))
    if not path:
        print("beat mode が動いていない可能性があります（beat_mode_start が要ります）")
        return 1
    print(f"録音: {path}\n")
    analyse(path)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
