#!/usr/bin/env python3
"""受け入れ試験の判定。**ファームを焼く前後で、劣化を見逃さない。**

## なぜ要るか

2026-09-12、タッチの不具合（上流 PR #374）を直すためにファームを焼き替える。
**焼くと全部が変わりうる** —— 首・LED・カメラ・マイク・スピーカー・表情・
ストリーム・beat mode・聞き取り・発話。

**直った1つの陰で、他が壊れても気づけない。** だから、

    焼く前  基準を記録する
    焼く後  同じ試験を回して、**差分だけ**を見る

## 4種類の差分

| | 意味 | どうする |
|---|---|---|
| **デグレ** | 動いていたものが動かない | **戻す判断をする** |
| **劣化** | 動くが遅くなった | 数字で見て判断 |
| 改善 | 動かなかったものが動く | 焼いた意味 |
| **未確認** | 試験できなかった | **「壊れた」と混ぜない**。判断を誤らせる |

## 判定はここ、実機を叩くのは別

この中に実機を触るコードを入れない。**判定は実機なしで試験できる。**
"""
from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class Result:
    """1項目の結果。

    ok : True=動く / False=動かない / None=測れなかった
    value : 数字で比べたいときだけ（秒数など。小さいほど良い）
    """

    name: str
    ok: bool | None
    detail: str = ""
    value: float | None = None


@dataclass
class Diff:
    name: str
    kind: str          # デグレ / 劣化 / 改善 / 未確認
    before: str
    after: str


# 調べる項目。★焼くと全部変わりうるので、主要機能を全部見る。
#   manual=True は人の手が要るもの。**当日回せる数に抑える**
CHECKS: dict[str, dict] = {
    "tools":       {"label": "道具の数",        "manual": False},
    "head":        {"label": "首が動く",        "manual": False},
    "leds":        {"label": "本体のLED",       "manual": False},
    "led_strip":   {"label": "外付けLEDテープ",  "manual": False},
    "avatar":      {"label": "表情の読み込み",   "manual": False},
    "screen":      {"label": "画面の明るさ",     "manual": False},
    "touch":       {"label": "頭なで",          "manual": True},
    "mic":         {"label": "マイクが音を拾う", "manual": True},
    "speaker":     {"label": "スピーカーが鳴る", "manual": True},
    "camera":      {"label": "カメラで撮れる",   "manual": False},
    "pose_stream": {"label": "首のストリーム",   "manual": False},
    "led_stream":  {"label": "LEDのストリーム",  "manual": False},
    "beat":        {"label": "音を聴いて踊る",   "manual": False},
    "stt":         {"label": "聞き取り",        "manual": True},
    "tts":         {"label": "発話",            "manual": False},
    "servo_power": {"label": "サーボ電源",       "manual": False},
}


def compare(before: dict[str, Result], after: dict[str, Result],
            worse_ratio: float = 1.5) -> list[Diff]:
    """焼く前と後を突き合わせる。**差分だけ返す。**

    worse_ratio : 何倍遅くなったら「劣化」とみなすか
    """
    out: list[Diff] = []
    for name in CHECKS:
        b, a = before.get(name), after.get(name)
        if b is None or a is None:
            continue

        # ★「測れなかった」を「壊れた」と混ぜない
        if a.ok is None and b.ok is not None:
            out.append(Diff(name, "未確認", _txt(b), _txt(a)))
            continue
        if b.ok is None:
            continue

        if b.ok and a.ok is False:
            out.append(Diff(name, "デグレ", _txt(b), _txt(a)))
            continue
        if b.ok is False and a.ok:
            out.append(Diff(name, "改善", _txt(b), _txt(a)))
            continue

        # 両方動いている。数字が悪化していないか
        if (b.ok and a.ok and b.value is not None and a.value is not None
                and b.value > 0 and a.value > b.value * worse_ratio):
            out.append(Diff(name, "劣化", _txt(b), _txt(a)))

    # ★重い順に。デグレを先頭に置く
    order = {"デグレ": 0, "劣化": 1, "未確認": 2, "改善": 3}
    return sorted(out, key=lambda d: order.get(d.kind, 9))


def _txt(r: Result) -> str:
    mark = "○" if r.ok else ("×" if r.ok is False else "—")
    v = f" {r.value:.2f}s" if r.value is not None else ""
    return f"{mark}{v} {r.detail}".strip()


def summarize(diffs: list[Diff]) -> str:
    """人が読む形にする。**結論から。**"""
    bad = [d for d in diffs if d.kind == "デグレ"]
    worse = [d for d in diffs if d.kind == "劣化"]
    unknown = [d for d in diffs if d.kind == "未確認"]
    good = [d for d in diffs if d.kind == "改善"]

    if bad:
        head = f"★デグレ {len(bad)}件。焼く前に戻すか判断してください"
    elif worse:
        head = f"★劣化 {len(worse)}件。数字を見て判断してください"
    elif unknown:
        head = f"未確認が {len(unknown)}件。測り直してください"
    elif good:
        head = f"問題なし。改善 {len(good)}件"
    else:
        head = "問題なし。変化なし"

    lines = [head, ""]
    for d in diffs:
        label = CHECKS.get(d.name, {}).get("label", d.name)
        lines.append(f"  [{d.kind}] {label}（{d.name}）")
        lines.append(f"      前: {d.before}")
        lines.append(f"      後: {d.after}")
    return "\n".join(lines)
