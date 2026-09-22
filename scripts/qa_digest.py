#!/usr/bin/env python3
"""聞かれたことをまとめる。**F① の「あなたのDJスタイル」の材料。**

    ./.venv/bin/python scripts/qa_digest.py

★**答えられなかったものを、先に出す。**そこに配布物の穴が出る（与件C22）。
★誰が聞いたかは、そもそも記録していない。
"""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "app" / "dj"))

import ask  # noqa: E402


def main() -> int:
    rows = ask.recall()
    if not rows:
        print("まだ1件も聞かれていません。")
        return 0
    d = ask.digest(rows)
    print(f"\n聞かれた数 {d['count']}  ／ 答えられた {d['answered']}"
          f"  ／ 答えの速さ（中央）{d['median_sec']}秒")
    print(f"  口の使われ方: " + " / ".join(f"{k} {v}件" for k, v in d["modes"].items()))

    if d["unanswered"]:
        print(f"\n★答えられなかった {len(d['unanswered'])}件 ← **ここに配布物の穴が出る**")
        for r in d["unanswered"]:
            print(f"   {r['at'][11:16]}  [{r['mode']}]  {r['q']}")

    if d["docs"]:
        print("\n  よく効いた資料")
        for name, n in d["docs"][:6]:
            print(f"   {n:3}回  {name}")

    print("\n  聞かれたこと（全部）")
    for r in rows:
        mark = "○" if r.get("answered") else "×"
        print(f"   {mark} [{r['mode']:5}] {r['q']}")
    print("\n★F① では、まず本人に返す。**それから同意を取る。**")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
