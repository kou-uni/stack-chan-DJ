#!/usr/bin/env python3
"""書いた台本を、スタックチャンに読ませる。

## 何のため

**Claude Code が複雑なセリフを書いて、実機に読ませる**（2026-09-12 本人の要望）。
Ollama の短い返答とは役割が違う。**こちらは長くてよく、質が要る。一方通行でよい。**

## 使い方

    ./.venv/bin/python scripts/speak.py "こんにちは。今日はいい天気ですね。"
    ./.venv/bin/python scripts/speak.py --file 台本.txt
    echo "..." | ./.venv/bin/python scripts/speak.py
    ./.venv/bin/python scripts/speak.py --dry "..."     # 鳴らさず割り方だけ見る

## 台本の書き方

    [happy]うれしいです。
    [pause=1.5]
    [thinking]でも、少し考えます。

- **改行で区切る。** 間の取り方は書き手のもの
- 表情: happy / surprised / embarrassed / sad / thinking / idle / sleepy
- **知らない指示は捨てて、言葉は読む。** セリフが読まれないほうが困る

★console 経由で送る。**実機を直接叩かない**（書き手は console だけ・I2）。
"""
import argparse
import json
import sys
import urllib.error
import urllib.request
from pathlib import Path

PORT = 8779
TOKEN = Path.home() / ".config" / "stackchan" / "panel-token"


def main() -> int:
    ap = argparse.ArgumentParser(description="スタックチャンに台本を読ませる")
    ap.add_argument("script", nargs="?", help="台本（省略時は標準入力）")
    ap.add_argument("--file", help="台本のファイル")
    ap.add_argument("--dry", action="store_true", help="鳴らさず割り方だけ見る")
    ap.add_argument("--port", type=int, default=PORT)
    a = ap.parse_args()

    if a.file:
        text = Path(a.file).read_text(encoding="utf-8")
    elif a.script:
        text = a.script
    else:
        text = sys.stdin.read()
    if not text.strip():
        print("台本が空です")
        return 2

    try:
        token = TOKEN.read_text(encoding="utf-8").strip()
    except OSError:
        print(f"鍵がありません（{TOKEN}）。console を一度起動してください")
        return 1

    req = urllib.request.Request(
        f"http://127.0.0.1:{a.port}/api/speak?k={token}",
        data=json.dumps({"script": text, "dry": a.dry}).encode(),
        headers={"Content-Type": "application/json"})
    try:
        d = json.loads(urllib.request.urlopen(req, timeout=300).read())
    except urllib.error.HTTPError as e:
        print(json.loads(e.read()).get("error", e.reason))
        return 1
    except OSError as e:
        print(f"console に繋がりません（{e}）")
        return 1

    if a.dry:
        for l in d["lines"]:
            tag = f"[{l['face']}]" if l["face"] else "      "
            gap = f" ({l['pause']}秒あけて)" if l["pause"] else ""
            print(f"  {tag}{gap} {l['text']}")
        print(f"\n  {len(d['lines'])} かたまり")
    else:
        print(f"  読ませました: {d['lines']} かたまり / {d['chars']} 字")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
