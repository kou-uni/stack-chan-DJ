#!/usr/bin/env python3
"""受け入れテストを、**スタックチャン自身が声で読み上げて**、1つずつ確かめる。

    ./.venv/bin/python scripts/acceptance.py            # 全部
    ./.venv/bin/python scripts/acceptance.py --block A  # Aブロックだけ
    ./.venv/bin/python scripts/acceptance.py --quiet    # 声を出さない（画面だけ）

## なぜ声で読むのか（2026-09-15 本人の指示）

> **「スタックチャンが一つずつ声で確かめながら聞いてくれるUXはすごく良かった」**

チェックリストを**紙で読む**と、確かめる人が画面に張り付く。
**当日いちばん見てほしいのは実機**なのに、視線が手元に落ちる。

読み上げれば、**手も目も実機に向いたまま確かめられる。**
しかも「これから何をするか」を本人の声で聞くので、**台本の練習も同時に終わる。**

## 答え方

- **頭をタップする** … はい（実機が繋がっていれば）
- **Enter** … はい / `n` … いいえ / `s` … 飛ばす / `q` … やめる

## 結果

`event/acceptance-log/YYYYMMDD-HHMM.md` に落ちる。
**落ちた項目だけを次の日の持ち越しにする。**
"""
from __future__ import annotations

import argparse
import asyncio
import json
import re
import sys
import time
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "app" / "dj"))

SRC = ROOT / "event" / "acceptance.md"
OUTDIR = ROOT / "event" / "acceptance-log"
EVENTS = Path.home() / ".claude" / "stackchan-events.jsonl"
SPEAKER_ID = 14                     # ★実機と同じ声（app/dj と揃える）


# ── 読み上げる文を、チェックリストから作る ──────────────────
def load_items(md: Path) -> list[dict]:
    """`event/acceptance.md` の表から項目を拾う。**台本を2箇所に書かない。**"""
    items: list[dict] = []
    block = ""
    for line in md.read_text(encoding="utf-8").splitlines():
        h = re.match(r"^##\s+(.+)$", line)
        if h:
            block = h.group(1).strip()
            continue
        # | A-2 | 頭をなでる | 合格の条件 | 落ちたとき |
        m = re.match(r"^\|\s*(★?\s*[0-9A-F]+-\d+)\s*\|(.+?)\|(.+?)\|(.*)\|\s*$", line)
        if not m:
            continue
        num, do, ok, alt = (s.strip() for s in m.groups())
        if num.startswith("#") or do.startswith("-"):
            continue
        items.append({
            "id": num.replace("★", "").strip(),
            "block": block,
            "do": _plain(do),
            "ok": _plain(ok),
            "alt": _plain(alt),
            "critical": "★" in (num + do + ok),
        })
    return items


def _plain(s: str) -> str:
    """読み上げ用に、飾りを落とす。**記号をそのまま読ませない。**"""
    s = re.sub(r"\*\*(.+?)\*\*", r"\1", s)
    s = re.sub(r"`(.+?)`", r"\1", s)
    s = s.replace("★", "").replace("⚠️", "").replace("→", "、")
    return re.sub(r"\s+", " ", s).strip()


def line_for(item: dict) -> str:
    """1項目ぶんの読み上げ。★長いと聞けない。**やることと合格だけ。**"""
    return f"{item['do']}。{item['ok']} なら、はい。"


# ── 実機に喋らせる ────────────────────────────────
class Voice:
    """実機の口。**繋がっていなければ黙って画面だけで進む。**"""

    def __init__(self, quiet: bool):
        self.quiet = quiet
        self.gw = None

    async def __aenter__(self):
        if self.quiet:
            return self
        try:
            from gateway import Gateway
            self._ctx = Gateway("http://127.0.0.1:8767/mcp")
            self.gw = await self._ctx.__aenter__()
        except Exception as exc:                      # noqa: BLE001
            print(f"  （実機に繋がらないので、声は出しません: {exc}）")
            self.gw = None
        return self

    async def __aexit__(self, *a):
        if self.gw is not None:
            await self._ctx.__aexit__(*a)

    async def say(self, text: str) -> None:
        if self.gw is None:
            return
        try:
            await self.gw.call("say", text=text, speaker_id=SPEAKER_ID)
            # ★鳴り終わる前に次へ行くと、聞いている人が置いていかれる
            await asyncio.sleep(min(6.0, 0.13 * len(text) + 0.6))
        except Exception:                             # noqa: BLE001
            pass


# ── 頭タップで「はい」 ────────────────────────────
class Tap:
    """頭のタップを拾う。**手が実機から離れないための入り口。**"""

    def __init__(self):
        self.at = 0
        try:
            self.at = EVENTS.stat().st_size
        except OSError:
            self.at = 0

    def tapped(self) -> bool:
        """前に見たところから先に、タップが来ていれば True。"""
        try:
            size = EVENTS.stat().st_size
        except OSError:
            return False
        if size <= self.at:
            self.at = min(self.at, size)
            return False
        with EVENTS.open("rb") as f:
            f.seek(self.at)
            chunk = f.read()
        self.at = size
        for raw in chunk.decode("utf-8", "replace").splitlines():
            try:
                ev = json.loads(raw)
            except ValueError:
                continue
            if ev.get("event_type") == "touch":
                return True
        return False


def ask(prompt: str, tap: Tap) -> str:
    """答えを1つもらう。**頭タップ か キーボード。**"""
    import select
    print(prompt, end="", flush=True)
    while True:
        if tap.tapped():
            print("  ← 頭タップ")
            return "y"
        r, _, _ = select.select([sys.stdin], [], [], 0.25)
        if r:
            s = sys.stdin.readline().strip().lower()
            return s or "y"


async def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--block", help="ブロックで絞る（A / D など）")
    ap.add_argument("--quiet", action="store_true", help="声を出さない")
    args = ap.parse_args()

    items = load_items(SRC)
    if args.block:
        items = [i for i in items if i["id"].upper().startswith(args.block.upper())]
    if not items:
        print("項目が見つかりません（event/acceptance.md を確かめてください）")
        return 1

    print(f"受け入れテスト — {len(items)}項目")
    print("  頭タップ か Enter＝はい / n＝いいえ / s＝飛ばす / q＝やめる\n")

    results: list[tuple[dict, str, str]] = []
    tap = Tap()
    async with Voice(args.quiet) as voice:
        await voice.say("受け入れテストを始めます。一つずつ聞きます。")
        block = None
        for item in items:
            if item["block"] != block:
                block = item["block"]
                print(f"\n── {block}")
                await voice.say(block.split("（")[0])
            print(f"\n  [{item['id']}]{' ★' if item['critical'] else ''} {item['do']}")
            print(f"        合格: {item['ok']}")
            await voice.say(line_for(item))
            a = ask("        → ", tap)
            if a.startswith("q"):
                print("\n  やめました。ここまでを記録します。")
                break
            if a.startswith("s"):
                results.append((item, "skip", "")); continue
            if a.startswith("n"):
                note = input("\n        何が起きた？ ").strip()
                results.append((item, "ng", note))
                if item["alt"]:
                    print(f"        代替: {item['alt']}")
                    await voice.say(f"落ちました。{item['alt']}")
                continue
            results.append((item, "ok", ""))

        ng = [r for r in results if r[1] == "ng"]
        crit = [r for r in ng if r[0]["critical"]]
        await voice.say(
            f"終わりました。{len(results)}項目中、落ちたのは{len(ng)}件です。"
            + ("重要なものが落ちています。" if crit else "重要なものは通っています。"))

    # ── 記録 ───────────────────────────────────
    OUTDIR.mkdir(parents=True, exist_ok=True)
    out = OUTDIR / f"{datetime.now():%Y%m%d-%H%M}.md"
    mark = {"ok": "○", "ng": "×", "skip": "－"}
    lines = [f"# 受け入れテスト {datetime.now():%Y-%m-%d %H:%M}", "",
             f"{len(results)}項目 / 落ち {len([r for r in results if r[1]=='ng'])}件", "",
             "| | 項目 | やること | 起きたこと |", "|---|---|---|---|"]
    for item, st, note in results:
        lines.append(f"| {mark[st]} | {item['id']}{'★' if item['critical'] else ''} "
                     f"| {item['do']} | {note} |")
    ng = [(i, n) for i, s, n in results if s == "ng"]
    if ng:
        lines += ["", "## 持ち越し", ""]
        lines += [f"- **{i['id']} {i['do']}** — {n or '（未記入）'}"
                  f"{'  ／ 代替: ' + i['alt'] if i['alt'] else ''}" for i, n in ng]
    out.write_text("\n".join(lines) + "\n", encoding="utf-8")

    print(f"\n記録: {out.relative_to(ROOT)}")
    for item, st, note in results:
        if st == "ng":
            print(f"  × {item['id']} {item['do']}  {note}")
    return 1 if any(s == "ng" and i["critical"] for i, s, _ in results) else 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
