#!/usr/bin/env python3
"""いま鳴っている音に対して、一番よく拍が取れる感度を選ぶ。

    ./.venv/bin/python scripts/tune_beat.py

当日のサウンドチェックで、**実際にかける曲を流しながら**走らせる。
感度を振って、確信度が一番高く・BPMが一番安定する値を選んで設定する。

## なぜ「上げれば良い」ではないのか

感度は「拍とみなす音の下限」を決める。

  低い感度(0.2) → 下限が高い → キックだけ拾う
  高い感度(0.9) → 下限が低い → ハイハットや残響まで拾う

**音が大きいときに感度を上げると、細かい音まで拾って拍の間隔がバラバラになる。**
拍の不応期は0.24秒（毎秒4.2回が上限）なので、それを超える検出は
BPMを揺らすだけで害になる。実際、音量不足のときに感度を上げて悪化させた。

**音量と感度は逆に動かす。** 大きい音ほど感度は下げる。
"""
from __future__ import annotations

import argparse
import asyncio
import contextlib
import json
import statistics

from mcp import ClientSession
from mcp.client.streamable_http import streamablehttp_client


async def probe(s, sens: float, settle: float, samples: int):
    await s.call_tool("beat_mode_update", {"sensitivity": sens})
    await asyncio.sleep(settle)                 # 20秒窓が入れ替わるのを待つ
    confs, bpms = [], []
    for _ in range(samples):
        r = await s.call_tool("beat_meta_snapshot", {})
        for b in getattr(r, "content", []) or []:
            t = getattr(b, "text", None)
            if t:
                d = json.loads(t)
                confs.append(d.get("confidence") or 0.0)
                if d.get("bpm"):
                    bpms.append(d["bpm"])
        await asyncio.sleep(1)
    sd = statistics.pstdev(bpms) if len(bpms) > 1 else 99.0
    return (max(confs) if confs else 0.0,
            sum(confs) / len(confs) if confs else 0.0,
            statistics.mean(bpms) if bpms else 0.0, sd)


async def run(url: str, values, settle: float, samples: int, apply: bool):
    async with contextlib.AsyncExitStack() as st:
        rd, wr, _ = await st.enter_async_context(streamablehttp_client(url))
        s = await st.enter_async_context(ClientSession(rd, wr))
        await s.initialize()

        snap = await s.call_tool("beat_meta_snapshot", {})
        for b in getattr(snap, "content", []) or []:
            if getattr(b, "text", None) and not json.loads(b.text).get("active"):
                print("beat mode が動いていません。先に beat_mode_start が要ります")
                return

        print("感度    確信度(最大/平均)   BPM      ブレ    判定")
        rows = []
        for v in values:
            mx, av, bpm, sd = await probe(s, v, settle, samples)
            # 確信度が高く、BPMが安定しているものを良しとする
            score = av - min(1.0, sd / 5.0) * 0.3
            rows.append((score, v, mx, av, bpm, sd))
            print(f"  {v:<5}  {mx:.2f} / {av:.2f}       {bpm:6.1f}  ±{sd:5.2f}")

        rows.sort(reverse=True)
        best = rows[0]
        print(f"\n→ 推奨: 感度 {best[1]}  （確信度 {best[3]:.2f} / BPM {best[4]:.1f} ±{best[5]:.2f}）")
        if apply:
            await s.call_tool("beat_mode_update", {"sensitivity": best[1]})
            print(f"  設定しました。console.py には --sensitivity {best[1]} を渡すこと")


def main() -> int:
    ap = argparse.ArgumentParser(description="いまの音に合う感度を選ぶ")
    ap.add_argument("--gateway", default="http://127.0.0.1:8767/mcp")
    ap.add_argument("--values", type=float, nargs="+",
                    default=[0.2, 0.35, 0.5, 0.7, 0.9])
    ap.add_argument("--settle", type=float, default=3.0, help="感度を変えてから測るまでの待ち")
    ap.add_argument("--samples", type=int, default=6, help="各感度で何秒ぶん測るか")
    ap.add_argument("--no-apply", action="store_true", help="選ぶだけで設定しない")
    a = ap.parse_args()
    asyncio.run(run(a.gateway, a.values, a.settle, a.samples, not a.no_apply))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
