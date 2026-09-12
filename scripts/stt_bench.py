#!/usr/bin/env python3
"""聞き取りの精度を測る。**感想ではなく数字で。**

    ./.venv/bin/python scripts/stt_bench.py

★同じ文を何回か読んで、一致率を出す。
  設定を変えたあと、これで比べる。**良くなったかどうかを推測で決めない。**
"""
import asyncio
import json
import re
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "app" / "dj"))
from gateway import Gateway     # noqa: E402
from talk import say_and_wait   # noqa: E402

# 当日ありそうな質問。★これで測る
PHRASES = [
    "ファームってなんですか",
    "バックアップは必要ですか",
    "スタックチャンは何ができますか",
    "アンバインドってなんですか",
    "自分でも作れますか",
]


def norm(s: str) -> str:
    """比べるための正規化。記号と空白を落とす。"""
    return re.sub(r"[\s、。，．!！?？・「」]", "", s or "")


def score(want: str, got: str) -> float:
    """文字の一致率（0..1）。編集距離ベース。"""
    a, b = norm(want), norm(got)
    if not a:
        return 0.0
    prev = list(range(len(b) + 1))
    for i, ca in enumerate(a, 1):
        cur = [i]
        for j, cb in enumerate(b, 1):
            cur.append(min(prev[j] + 1, cur[-1] + 1, prev[j - 1] + (ca != cb)))
        prev = cur
    return max(0.0, 1.0 - prev[-1] / max(len(a), len(b)))


def _j(r):
    c = getattr(r, "content", None)
    return json.loads(c[0].text) if c else {}


async def main() -> int:
    async with Gateway("http://127.0.0.1:8767/mcp") as gw:
        await gw.call("beat_mode_stop")
        await asyncio.sleep(0.6)
        results = []
        for i, want in enumerate(PHRASES, 1):
            print(f"\n[{i}/{len(PHRASES)}] 「{want}」と読んでください")
            # ★タイミングが分かりにくいと、測っているのが「人の反応」になってしまう。
            #   画面でカウントダウンしてから録る
            await say_and_wait(gw, "どうぞ")
            for c in ("3…", "2…", "1…"):
                print(f"   {c}", flush=True)
                await asyncio.sleep(0.7)
            print("   ▶▶▶ どうぞ！（読んでください）", flush=True)
            t0 = time.time()
            d = _j(await gw.call("listen", duration_ms=8000,
                                 language="ja", model="small"))
            got = (d.get("text") or "").strip()
            s = score(want, got)
            results.append(s)
            mark = "○" if s >= 0.9 else ("△" if s >= 0.6 else "×")
            print(f"   {mark} {s:.0%}  {time.time()-t0:.1f}秒  「{got}」")
            await asyncio.sleep(0.6)

        avg = sum(results) / len(results)
        ok = sum(1 for s in results if s >= 0.9)
        print(f"\n{'='*46}")
        print(f"  一致率 平均 {avg:.0%}   ほぼ完全 {ok}/{len(results)}")
        print(f"{'='*46}")
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
