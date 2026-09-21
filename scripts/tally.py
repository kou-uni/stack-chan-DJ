#!/usr/bin/env python3
"""配布物の数字を数え直して、ページに書き戻す。

    ./.venv/bin/python scripts/tally.py          # 数えて表示
    ./.venv/bin/python scripts/tally.py --write  # ページに書き戻す

## なぜ要るか（2026-09-21）

「作ったもの、全部」に数字が6つ載っている。**手で書くと必ず古くなる。**
当日まで作り続けるので、**最後に1コマンドで更新できる形**にしておく。

★数え方もここに1回だけ書く。**2箇所に書かない。**
"""
from __future__ import annotations

import argparse
import re
import subprocess
import sys
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PAGE = ROOT / "docs" / "pages" / "src" / "tsukutta-mono.html"


def sh(*args: str) -> str:
    return subprocess.run(args, cwd=ROOT, capture_output=True, text=True).stdout.strip()


def tally() -> list[tuple[str, str]]:
    commits = len(sh("git", "log", "--oneline").splitlines())
    first = sh("git", "log", "--format=%ad", "--date=short").splitlines()[-1]
    y, m, d = (int(x) for x in first.split("-"))
    days = (date.today() - date(y, m, d)).days + 1

    code = sum(len(p.read_text(encoding="utf-8", errors="replace").splitlines())
               for p in list((ROOT / "app").rglob("*.py")) + [ROOT / "app/dj/stage.html"]
               if p.is_file())

    out = subprocess.run([str(ROOT / ".venv/bin/python"), "-m", "pytest", "tests/", "-q"],
                         cwd=ROOT, capture_output=True, text=True).stdout
    m2 = re.search(r"(\d+) passed", out)
    tests = int(m2.group(1)) if m2 else 0

    learn = len((ROOT / "docs/learnings.md").read_text(encoding="utf-8").splitlines())

    # ★実機の道具は gateway に聞く。落ちていたら前の値を残す
    tools = current_tools()
    try:
        got = ask_tools()
        if got:
            tools = got
    except Exception:                                  # noqa: BLE001
        pass

    return [(f"{commits}", "コミット"),
            (f"{days}日", f"{first[5:].replace('-', '/')} → 今日"),
            (f"{code:,}", "行（本体＋背景）"),
            (f"{tests}", "自動テスト"),
            (f"{learn:,}", "行の失敗記録"),
            (f"{tools}", "実機の道具（MCP）")]


def ask_tools() -> int | None:
    import asyncio
    sys.path.insert(0, str(ROOT / "app" / "dj"))
    from gateway import Gateway                        # noqa: PLC0415

    async def go():
        async with Gateway("http://127.0.0.1:8767/mcp") as gw:
            return len((await gw._session.list_tools()).tools)
    return asyncio.run(go())


def current_tools() -> str:
    m = re.search(r'<b>(\d+)</b><span>実機の道具', PAGE.read_text(encoding="utf-8"))
    return m.group(1) if m else "49"


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--write", action="store_true", help="ページに書き戻す")
    args = ap.parse_args()

    rows = tally()
    for big, small in rows:
        print(f"  {big:>8}  {small}")
    if not args.write:
        print("\n書き戻すなら --write")
        return 0

    t = PAGE.read_text(encoding="utf-8")
    block = "\n".join(f'    <div class="num"><b>{b}</b><span>{s}</span></div>' for b, s in rows)
    new = re.sub(r'(<div class="nums">\n)(.*?)(\n  </div>)',
                 lambda m: m.group(1) + block + m.group(3), t, flags=re.S)
    if new == t:
        print("\n★ 書き戻す場所が見つかりません（nums の入れ物を確かめてください）")
        return 1

    # ★本文にも同じ数字が出てくる。1箇所だけ直して満足しない
    tests = rows[3][0]
    new = re.sub(r"<b>テスト [\d,]+件</b>", f"<b>テスト {tests}件</b>", new)
    new = re.sub(r"から[\d,]+件のテストが通る", f"から{tests}件のテストが通る", new)
    # ★過去の事件の件数（363件）は当時の値。書き換えない
    PAGE.write_text(new, encoding="utf-8")
    subprocess.run([str(ROOT / ".venv/bin/python"), "scripts/pack-page.py", "tsukutta-mono"],
                   cwd=ROOT)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
