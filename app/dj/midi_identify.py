#!/usr/bin/env python3
"""つまみを1つずつ同定する。「これは何番か」を1個ずつ確定させる。

    ./.venv/bin/python app/dj/midi_identify.py

1つ動かす → 何番が動いたか表示 → 名前を付ける、を繰り返す。
14bit の MSB/LSB ペア（#n と #n+32）は自動でまとめ、MSB 側だけを採用する。
終わると docs/dj-midi-map.md に対応表を書き出す。
"""
from __future__ import annotations

import sys
import time
from collections import Counter
from pathlib import Path

try:
    import mido
except ImportError:
    sys.exit("./.venv/bin/pip install mido python-rtmidi")

SETTLE_S = 0.6      # 動きが止まったと判断するまでの無音時間
MIN_EVENTS = 4      # これ未満なら「ちゃんと動かせていない」とみなす

# 順に聞いていく対象。用途が先に決まっているものから並べる。
TARGETS = [
    ("yaw",   "首を左右に回すつまみ", "端から端まで大きく回してください"),
    ("pitch", "うなずかせるつまみ",   "別のつまみを、端から端まで"),
    ("extra1", "3つ目のつまみ（任意）", "使いそうなつまみをもう1つ。要らなければ Enter で飛ばす"),
    ("btn_happy", "笑わせるボタン",   "パッドかボタンを1回押す"),
    ("btn_neutral", "真顔に戻すボタン", "別のボタンを1回押す"),
    ("btn_doubt", "首をかしげるボタン（任意）", "もう1つボタンを。要らなければ Enter で飛ばす"),
]


def pick_port() -> str:
    names = mido.get_input_names()
    if not names:
        sys.exit("MIDI入力が無い。DDJ-FLX2 を USB-C で繋ぐ")
    for kw in ("ddj", "flx", "pioneer", "alphatheta"):
        for n in names:
            if kw in n.lower():
                return n
    return names[0]


def capture_one(inport) -> tuple[str, int, int, int] | None:
    """1つのコントロールが動くのを待って、(種別, ch, 番号, イベント数) を返す。

    動きが SETTLE_S 秒止まったら確定。MSB/LSB ペアは MSB 側を採る。
    """
    seen: Counter = Counter()
    last_at = None

    # まず何か来るまで待つ
    while True:
        for msg in inport.iter_pending():
            key = None
            if msg.type == "control_change":
                key = ("cc", msg.channel, msg.control)
            elif msg.type == "note_on" and msg.velocity > 0:
                key = ("note", msg.channel, msg.note)
            if key:
                seen[key] += 1
                last_at = time.time()
        if last_at and time.time() - last_at > SETTLE_S:
            break
        time.sleep(0.005)

    if not seen:
        return None

    # 14bit ペアを畳む: #n と #n+32 が同じ ch にいたら MSB(#n) にまとめる
    folded: Counter = Counter()
    for (kind, ch, num), cnt in seen.items():
        if kind == "cc" and num >= 32 and ("cc", ch, num - 32) in seen:
            folded[("cc", ch, num - 32)] += cnt
        else:
            folded[(kind, ch, num)] += cnt

    (kind, ch, num), cnt = folded.most_common(1)[0]
    return kind, ch, num, cnt


def main() -> int:
    port_name = pick_port()
    print(f"MIDI: {port_name}\n")
    print("=" * 62)
    print("1つずつ聞きます。指示されたものだけを動かしてください。")
    print("動かし終えて少し待つと、自動で確定します。")
    print("飛ばしたいときは、何も動かさずに Ctrl-C を1回。")
    print("=" * 62 + "\n")

    result: dict[str, dict] = {}

    with mido.open_input(port_name) as inport:
        for slot, label, hint in TARGETS:
            for msg in inport.iter_pending():   # 直前の残りを捨てる
                pass
            print(f"▶ {label}")
            print(f"  {hint}  … どうぞ")
            try:
                got = capture_one(inport)
            except KeyboardInterrupt:
                print("  → 飛ばしました\n")
                continue
            if not got:
                print("  → 取れませんでした\n")
                continue
            kind, ch, num, cnt = got
            if cnt < MIN_EVENTS and kind == "cc":
                print(f"  ⚠ イベントが {cnt} 件しかありません。もっと大きく動かした方が確実です")
            name = "CC" if kind == "cc" else "Note"
            print(f"  → {name} ch{ch} #{num}  （{cnt} 件）\n")
            result[slot] = {"kind": kind, "ch": ch, "num": num, "label": label, "count": cnt}

    if not result:
        print("何も取れませんでした")
        return 1

    print("=" * 62)
    print("確定した割り当て\n")
    rows = ["| 用途 | 種別 | ch | 番号 |", "|---|---|---|---|"]
    for slot, r in result.items():
        kind = "CC" if r["kind"] == "cc" else "Note"
        print(f"  {r['label']:<28} {kind} ch{r['ch']} #{r['num']}")
        rows.append(f"| {r['label']} | {kind} | {r['ch']} | {r['num']} |")

    yaw = result.get("yaw")
    pitch = result.get("pitch")
    cmd = ""
    if yaw and pitch:
        cmd = (f"./.venv/bin/python app/dj/pose_stream.py "
               f"--yaw-cc {yaw['num']} --pitch-cc {pitch['num']}")
        print(f"\n次のコマンドがそのまま使えます:\n  {cmd}")

    out = Path(__file__).resolve().parents[2] / "docs" / "dj-midi-map.md"
    out.write_text(
        "# DDJ-FLX2 MIDI マップ\n\n"
        f"`app/dj/midi_identify.py` で1つずつ同定（{time.strftime('%Y-%m-%d %H:%M')}）。\n"
        f"ポート: `{port_name}`\n\n"
        "14bit の MSB/LSB ペア（`#n` と `#n+32`）は MSB 側にまとめてある。\n\n"
        + "\n".join(rows) + "\n\n"
        + (f"## つまみ → 首\n\n```\n{cmd}\n```\n" if cmd else ""),
        encoding="utf-8",
    )
    print(f"\n書き出しました: {out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
