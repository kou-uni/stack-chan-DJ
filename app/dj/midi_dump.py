#!/usr/bin/env python3
"""DDJ-FLX2 が何を送ってくるかを見るためだけのスクリプト。

実機（スタックチャン）もサーバーも要らない。DDJ-FLX2 と Mac だけで動く。

    ~/stackchan-lab/.venv/bin/python app/dj/midi_dump.py
    ~/stackchan-lab/.venv/bin/python app/dj/midi_dump.py --save

Ctrl-C で止めると、触ったコントロールの一覧表が出る。
--save を付けると docs/dj-midi-map.md に書き出す（これがマッピングの元になる）。
"""
from __future__ import annotations

import argparse
import sys
import time
from collections import OrderedDict
from pathlib import Path

try:
    import mido
except ImportError:
    sys.exit("mido が無い。 ~/stackchan-lab/.venv/bin/pip install mido python-rtmidi")

# ふるまいの判定に使うしきい値
ABSOLUTE_SPAN = 40   # 値の幅がこれ以上なら「絶対値（つまみ・フェーダー）」とみなす
RELATIVE_BAND = 8    # 値が 64 の周辺だけ／0と127付近だけなら「相対値（ジョグ）」


class Control:
    """1つのコントロール（CC番号やノート番号）の観測記録。"""

    def __init__(self, kind: str, ch: int, num: int):
        self.kind, self.ch, self.num = kind, ch, num
        self.count = 0
        self.lo, self.hi = 128, -1
        self.values: set[int] = set()
        self.first_seen = time.time()

    def add(self, value: int) -> None:
        self.count += 1
        self.lo = min(self.lo, value)
        self.hi = max(self.hi, value)
        if len(self.values) < 200:
            self.values.add(value)

    @property
    def span(self) -> int:
        return self.hi - self.lo

    def guess(self) -> str:
        """つまみか、ジョグか、ボタンか。"""
        if self.kind == "note":
            return "ボタン／パッド"
        if self.span >= ABSOLUTE_SPAN:
            return "つまみ・フェーダー（絶対値）"
        near_center = all(abs(v - 64) <= RELATIVE_BAND for v in self.values)
        near_edges = all(v <= RELATIVE_BAND or v >= 127 - RELATIVE_BAND for v in self.values)
        if self.count >= 8 and (near_center or near_edges):
            return "ジョグ・エンコーダ（相対値）★積算が要る"
        if self.values <= {0, 127}:
            return "ボタン（CC）"
        return "不明（もっと動かす）"

    def suggest(self) -> str:
        """スタックチャンの何に繋ぐと良さそうか。"""
        g = self.guess()
        if g.startswith("つまみ"):
            return "首の角度に線形マッピング"
        if g.startswith("ジョグ"):
            return "★首の追従（最初に作る）"
        if g.startswith("ボタン"):
            return "表情・LED の切り替え"
        return "—"


def pick_port(explicit: str | None) -> str:
    names = mido.get_input_names()
    if not names:
        sys.exit(
            "MIDI入力が1つも見つからない。\n"
            "  - DDJ-FLX2 を USB-C で繋いだか\n"
            "  - 充電専用ケーブルではないか\n"
            "  - 本体の電源が入っているか"
        )

    print("見つかった MIDI 入力:")
    for i, n in enumerate(names):
        print(f"  [{i}] {n}")
    print()

    if explicit:
        for n in names:
            if explicit.lower() in n.lower():
                return n
        sys.exit(f"'{explicit}' に一致するポートが無い")

    for kw in ("ddj", "flx", "pioneer", "alphatheta"):
        for n in names:
            if kw in n.lower():
                print(f"→ '{n}' を使う（'{kw}' に一致）\n")
                return n

    print(f"→ DDJ らしき名前が無いので [0] '{names[0]}' を使う")
    print("  違うなら --port <名前の一部> で指定する\n")
    return names[0]


def _stream(inport, deadline: float | None):
    """deadline を過ぎたら止まるメッセージ列。deadline が None なら無限。"""
    if deadline is None:
        yield from inport
        return
    while time.time() < deadline:
        got = False
        for msg in inport.iter_pending():
            got = True
            yield msg
        if not got:
            time.sleep(0.005)


def render_table(controls: dict) -> str:
    if not controls:
        return "（何も受信しなかった）\n"
    rows = ["| 種別 | ch | 番号 | 回数 | 値の範囲 | 推定 | 繋ぎ先の候補 |",
            "|---|---|---|---|---|---|---|"]
    for c in sorted(controls.values(), key=lambda c: (c.kind, c.ch, c.num)):
        kind = "CC" if c.kind == "cc" else "Note"
        rows.append(
            f"| {kind} | {c.ch} | {c.num} | {c.count} | {c.lo}–{c.hi} | {c.guess()} | {c.suggest()} |"
        )
    return "\n".join(rows) + "\n"


def main() -> int:
    ap = argparse.ArgumentParser(description="DDJ-FLX2 の MIDI を眺める")
    ap.add_argument("--port", help="ポート名の一部（省略すると DDJ を自動で探す）")
    ap.add_argument("--save", action="store_true", help="docs/dj-midi-map.md に書き出す")
    ap.add_argument("--quiet", action="store_true", help="1件ずつの表示を止め、集計だけ取る")
    ap.add_argument("--seconds", type=float, help="指定秒で自動終了して集計を出す（Ctrl-C の代わり）")
    args = ap.parse_args()

    port_name = pick_port(args.port)
    controls: OrderedDict[tuple, Control] = OrderedDict()

    print("=" * 68)
    print("触ってください。つまみ → フェーダー → ジョグ → PLAY → パッド の順が分かりやすい。")
    print("★ rekordbox を起動した状態でも試すこと（同時に読めるかがここで分かる）")
    print("Ctrl-C で終了 → 一覧表が出ます")
    print("=" * 68 + "\n")

    deadline = time.time() + args.seconds if args.seconds else None
    if deadline:
        print(f"（{args.seconds:.0f} 秒で自動終了します）\n")

    try:
        with mido.open_input(port_name) as inport:
            for msg in _stream(inport, deadline):
                if msg.type == "control_change":
                    key, num, val = ("cc", msg.channel, msg.control), msg.control, msg.value
                elif msg.type in ("note_on", "note_off"):
                    key, num = ("note", msg.channel, msg.note), msg.note
                    val = msg.velocity if msg.type == "note_on" else 0
                else:
                    if not args.quiet:
                        print(f"  (その他) {msg}")
                    continue

                c = controls.get(key)
                if c is None:
                    c = controls[key] = Control(key[0], key[1], num)
                    if not args.quiet:
                        print(f"\n★ 新しいコントロール: {key[0].upper()} ch{key[1]} #{num}")
                c.add(val)

                if not args.quiet:
                    bar = "█" * round(val / 127 * 24)
                    print(f"  {key[0]:4} ch{key[1]:<2} #{num:<3} {val:>3} |{bar:<24}|", end="\r")
    except KeyboardInterrupt:
        print("\n")
    except Exception as exc:  # ポートが奪われた等
        print(f"\n受信が止まりました: {exc}\n")

    table = render_table(controls)
    print("=" * 68)
    print(f"触ったコントロール: {len(controls)} 種\n")
    print(table)

    if args.save:
        out = Path(__file__).resolve().parents[2] / "docs" / "dj-midi-map.md"
        stamp = time.strftime("%Y-%m-%d %H:%M")
        out.write_text(
            f"# DDJ-FLX2 MIDI マップ\n\n"
            f"`app/dj/midi_dump.py --save` で自動生成（{stamp}）。\n"
            f"ポート: `{port_name}`\n\n"
            f"{table}\n"
            f"## 次にやること\n\n"
            f"- ★ の付いたジョグを `move_head` に繋ぐ（Phase 3 の最初の一手）\n"
            f"- 絶対値のつまみは 0–127 を首の角度に線形マッピング\n"
            f"- ボタンは `set_avatar` / `set_mouth` に割り当てる\n",
            encoding="utf-8",
        )
        print(f"書き出しました: {out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
