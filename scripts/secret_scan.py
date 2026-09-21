#!/usr/bin/env python3
"""公開する前に、秘密が混じっていないか走査する。

    ./.venv/bin/python scripts/secret_scan.py          # git 管理下の全ファイル
    ./.venv/bin/python scripts/secret_scan.py --staged # これから commit する分だけ

## なぜ要るか（2026-09-21）

当日、**このリポジトリをQRで配る。** 配ってからでは取り消せない。
GitHub から消しても、**clone された分と履歴は戻らない。**

★**いちばん危ないのは鍵ではなくログ。**
鍵は形が決まっているので目に付く。会話ログ・文字起こし・録音は
「作業ファイル」の顔をしていて、**中に本名と雑談が入っている。**
"""
from __future__ import annotations

import argparse
import re
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

# ★形で見つかるもの。名前（API_KEY=）ではなく値の形で探す
PATTERNS: list[tuple[str, re.Pattern[str]]] = [
    ("OpenAI の鍵",      re.compile(r"sk-[A-Za-z0-9_-]{20,}")),
    ("Anthropic の鍵",   re.compile(r"sk-ant-[A-Za-z0-9_-]{20,}")),
    ("GitHub のトークン", re.compile(r"gh[pousr]_[A-Za-z0-9]{36,}")),
    ("Slack のトークン",  re.compile(r"xox[baprs]-[A-Za-z0-9-]{10,}")),
    ("AWS のキーID",      re.compile(r"AKIA[0-9A-Z]{16}")),
    ("秘密鍵ファイル",    re.compile(r"-----BEGIN (?:RSA |EC |OPENSSH )?PRIVATE KEY-----")),
    ("操作パネルの鍵",    re.compile(r"[?&]k=[0-9a-f]{32}")),
    ("Backlog の鍵",      re.compile(r"(?i)backlog_api_key\s*[:=]\s*['\"]?[A-Za-z0-9]{20,}")),
]

# ★中身を見ずに、そもそも公開に混ぜない種類
RISKY_SUFFIX = {".jsonl", ".log", ".wav", ".m4a", ".bin", ".env"}
RISKY_DIR = {"acceptance-log", "recordings", "transcripts"}
# ★backup/ は入れない。実機の状態ダンプ（秘密なし）を証拠として置いてある。
#   焼いたイメージは backup/*.bin で、拡張子のほうで止まる。
#   **ディレクトリ名で決めつけると、正しいものまで消させることになる。**

SKIP_SUFFIX = {".png", ".jpg", ".jpeg", ".gif", ".webp", ".pdf", ".ico", ".woff", ".woff2"}
# ★この検査自身と、その試験は「見本」を持っている。除外しないと必ず自分で落ちる。
#   ただし除外はこの2つだけ。**落ちたら消す、を面倒がって広げない。**
SAMPLE_FILES = {Path(__file__).name, "test_secret_scan.py"}
# ★どうしても本文に書きたい1行には、この印を同じ行に置く
ALLOW_MARK = "secret-scan: 見本"


def tracked(staged: bool) -> list[Path]:
    cmd = (["git", "diff", "--cached", "--name-only", "--diff-filter=ACM"]
           if staged else ["git", "ls-files"])
    out = subprocess.run(cmd, cwd=ROOT, capture_output=True, text=True).stdout
    return [ROOT / line for line in out.splitlines() if line]


def scan(paths: list[Path]) -> list[str]:
    hits: list[str] = []
    for p in paths:
        if not p.is_file():
            continue
        try:
            rel = p.relative_to(ROOT)
        except ValueError:          # ★リポジトリの外（テストの一時ファイル）
            rel = p

        if set(rel.parts) & RISKY_DIR or p.suffix in RISKY_SUFFIX:
            hits.append(f"{rel}: ★この種類は公開に混ぜない（ログ・録音・バイナリ・設定）")
            continue
        if p.suffix in SKIP_SUFFIX:
            continue
        if p.name in SAMPLE_FILES:
            continue

        try:
            text = p.read_text(encoding="utf-8")
        except (UnicodeDecodeError, OSError):
            continue
        for i, line in enumerate(text.splitlines(), 1):
            if ALLOW_MARK in line:
                continue
            for name, pat in PATTERNS:
                if pat.search(line):
                    hits.append(f"{rel}:{i}: ★{name}らしきものがあります")
    return hits


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--staged", action="store_true", help="commit 予定の分だけ見る")
    args = ap.parse_args()

    paths = tracked(args.staged)
    hits = scan(paths)
    print(f"{len(paths)} ファイルを見ました。")
    if not hits:
        print("  秘密らしきものはありませんでした。")
        return 0
    print()
    for h in hits:
        print("  " + h)
    print(f"\n★{len(hits)} 件。**配る前に消してください。**")
    print("  一度 push すると、消しても clone された分と履歴は戻りません。")
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
