#!/usr/bin/env python3
"""つまみを1つ動かして、mapping.json に割り当てる。

★番号を推測しない。**動かしてもらえば確実に分かる。**
  DDJ-FLX2 のCC番号は機種と世代で違う。「たぶんこれ」で書くと、
  当日そのつまみだけ効かない、という壊れ方をする（2026-09-13）。

    ./.venv/bin/python scripts/learn_cc.py burst "右の音量ゲージ（バースト）"

console を止めてから実行すること（MIDIポートは1つしか開けない）。
"""
from __future__ import annotations

import json
import pathlib
import sys
import time

import mido

HERE = pathlib.Path(__file__).resolve().parent.parent / "app" / "dj"
MAP = HERE / "mapping.json"


def main() -> int:
    if len(sys.argv) < 3:
        print(__doc__)
        return 2
    slot, label = sys.argv[1], sys.argv[2]
    span = float(sys.argv[3]) if len(sys.argv) > 3 else 8.0
    cfg = json.loads(MAP.read_text(encoding="utf-8"))
    known = {(c["ch"], c["num"]) for c in cfg["controls"].values()
             if c["kind"] == "cc" and cfg["controls"].get(slot) is not c}

    names = mido.get_input_names()
    port = next((n for n in names if cfg.get("port_hint", "DDJ").lower() in n.lower()),
                names[0] if names else None)
    if not port:
        print("⚠ MIDI入力が見つからない。DJ機材を挿してください")
        return 1

    print(f"MIDI: {port}")
    print(f"\n★ {label} を、下から上まで**ゆっくり1往復**させてください")
    print(f"  （待っています。動かした時点で確定します／最長 {span:.0f}秒）\n",
          flush=True)
    # ★時間で締め切らない。**人の準備を待つ。**
    #   8秒で切っていたら、読んで手を伸ばす間に終わっていた（2026-09-13）
    seen: dict[tuple[int, int], list] = {}
    t0 = time.time()
    done_at = None
    with mido.open_input(port) as inp:
        while time.time() - t0 < span:
            for m in inp.iter_pending():
                if m.type != "control_change":
                    continue
                k = (m.channel, m.control)
                s = seen.setdefault(k, [m.value, m.value, 0])
                s[0] = min(s[0], m.value); s[1] = max(s[1], m.value); s[2] += 1
                if s[1] - s[0] >= 100 and k not in known and done_at is None:
                    # 端から端まで動いた。あと1.5秒だけ拾って締める
                    done_at = time.time() + 1.5
                    print(f"  ✓ 見つけました: CC ch{k[0]} #{k[1]}", flush=True)
            if done_at and time.time() > done_at:
                break
            time.sleep(0.005)

    if not seen:
        print("何も届かなかった。console が動いていると横取りされます")
        return 1
    print("  ch  CC   回数   範囲")
    for (ch, num), (lo, hi, n) in sorted(seen.items(), key=lambda x: -x[1][2]):
        mark = "  ← 既に割当済み" if (ch, num) in known else ""
        print(f"  {ch:>2} {num:>3} {n:>6}   {lo}..{hi}{mark}")

    # ★いちばん動いたもの＝いま触ったもの。可動域が広いことも条件にする
    #   （ジョグは回数が多いが範囲が狭い。取り違えない）
    cand = [(k, v) for k, v in seen.items()
            if v[1] - v[0] >= 60 and k not in known]
    if not cand:
        print("\n可動域の広いつまみが見つからなかった。もう一度ゆっくり動かしてください")
        return 1
    (ch, num), (lo, hi, n) = max(cand, key=lambda x: x[1][2])
    cfg["controls"][slot] = {
        "kind": "cc", "ch": ch, "num": num, "label": label,
        "type": "absolute", "value_range_observed": [lo, hi],
        "confirmed": time.strftime("%Y-%m-%d"),
    }
    MAP.write_text(json.dumps(cfg, ensure_ascii=False, indent=2) + "\n",
                   encoding="utf-8")
    print(f"\n✓ {slot} = CC ch{ch} #{num}（{lo}..{hi}）を mapping.json に書きました")
    print("  console を立ち上げ直すと効きます")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
