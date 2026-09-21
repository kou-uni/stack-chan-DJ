#!/usr/bin/env python3
"""質疑応答の口が「何を見ているか」を出す。

    ./.venv/bin/python scripts/qa_sources.py          # 両モードの一覧
    ./.venv/bin/python scripts/qa_sources.py --ask "質問"   # どの節を選ぶか

## なぜ要るか（2026-09-21）

★**配っていないものを、口だけが知っている状態にしない。**
実測で、進行表を読んで参加者に手の内を答えた。**目で見えないと、また混ざる。**
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "app" / "dj"))

import ask  # noqa: E402


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--ask", help="この質問で、どの節が選ばれるかを見る")
    ap.add_argument("--mode", help="today / uni。省略すると両方")
    args = ap.parse_args()

    names = [args.mode] if args.mode else list(ask.MODES)
    for name in names:
        m = ask.get_mode(name)
        paths = ask.paths_for(m)
        index = ask.build_index(paths)
        print(f"\n━━ {m.label}（{m.name}）━━  資料 {len(paths)}件 / 節 {len(index)}")
        print(f"   きく内容: {m.hint}")

        groups: dict[str, int] = {}
        for p in paths:
            key = p.parent.name if p.parent.name != "pages" else "配布物"
            groups[key] = groups.get(key, 0) + 1
        for k, v in sorted(groups.items(), key=lambda t: -t[1]):
            print(f"     {k:14} {v:4}件")

        if m.name == "today":
            for p in paths:
                print(f"       ・{p.relative_to(ROOT)}")
            print(f"     ★外しているもの: {', '.join(sorted(ask.NOT_FOR_GUESTS))}")
        else:
            print(f"     ★見る層だけを数えている: {', '.join(ask.VAULT_LAYERS)}")
            print("     ★生ログ（raw / Daily / Inbox / rsi-cycles）には経路が無い")

        if args.ask:
            picked = ask.pick(index, args.ask)
            print(f"\n   「{args.ask}」で選ばれる節 {len(picked)}件")
            for s in picked:
                print(f"     ・{s.title[:40]:42} {s.source}")
            if not picked:
                print("     （無し → 「記憶にありません」と答える）")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
