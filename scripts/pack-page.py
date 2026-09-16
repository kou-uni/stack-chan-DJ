#!/usr/bin/env python3
"""Artifact 用に書いたHTMLを、**単体で開けるファイル**にする。

    ./.venv/bin/python scripts/pack-page.py            # 全部
    ./.venv/bin/python scripts/pack-page.py firmware   # 1枚だけ

## なぜ要るか（2026-09-16）

Artifact は `<html>` や `<head>` を**公開時に被せてくれる**ので、
書いた側は中身だけを持っている。**そのままではブラウザで開けない。**

当日は電波が無いかもしれない。**配布物は手元のファイルで開けること。**
`docs/pages/src/*.html` が原本、`docs/pages/*.html` が配れる形。

原本を直したら、これを走らせて両方を更新する。**2箇所を手で書かない。**
"""
from __future__ import annotations

import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "docs" / "pages" / "src"
OUT = ROOT / "docs" / "pages"

SKELETON = """<!doctype html>
<html lang="ja">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<meta name="color-scheme" content="dark light">
{head}
</head>
<body>
{body}
</body>
</html>
"""


def pack(src: Path) -> Path:
    raw = src.read_text(encoding="utf-8")
    # <title>…</title> / <style>…</style> / <link …> を head へ、残りを body へ
    # ★閉じタグのあるものと、無いものを分けて拾う。
    #   1本の正規表現でまとめると、`<title>` の `>` で止まって
    #   中身が body に残る（2026-09-16 実際にそうなった）
    head_bits: list[str] = []
    for tag in ("title", "style"):
        head_bits += re.findall(rf"<{tag}\b[^>]*>[\s\S]*?</{tag}>", raw)
    head_bits += re.findall(r"<link\b[^>]*>", raw)
    body = raw
    for bit in head_bits:
        body = body.replace(bit, "", 1)
    out = OUT / src.name
    out.write_text(
        SKELETON.format(head="\n".join(head_bits).strip(), body=body.strip()),
        encoding="utf-8")
    return out


def main() -> int:
    want = sys.argv[1:]
    files = sorted(SRC.glob("*.html"))
    if want:
        files = [f for f in files if f.stem in want]
    if not files:
        print(f"原本がありません（{SRC}）")
        return 1
    for f in files:
        out = pack(f)
        title = re.search(r"<title>(.*?)</title>", f.read_text(encoding="utf-8"))
        name = title.group(1) if title else f.stem
        print(f"  ○ {out.relative_to(ROOT)}  — {name}  "
              f"{out.stat().st_size // 1024}KB")
    print(f"\nダブルクリックで開けます（{OUT.relative_to(ROOT)}/）")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
