"""長いセリフを喋らせる仕様。

## 何のため（2026-09-12 本人の要望）

Claude Code が**複雑なセリフを書いて、スタックチャンに読ませる。**
感想を述べたり、込み入った解説をしたり。**一方通行でよい。**

Ollama の短い返答とは役割が違う。**こちらは長くてよく、質が要る。**

## 気をつけること

- **文の途中で切らない。** 切れ目で区切って、順番に読ませる
- **読み終わるまで次を出さない。** かぶると聞き取れない
- 表情を混ぜられる。**棒読みの長話は聞かれない**
"""
import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "app" / "dj"))
from panel import Line, split_speech   # noqa: E402


def test_文の切れ目で区切る():
    # ★limit を超えるときだけ割る（20 だと 18 字なのでまとまってしまう）
    out = split_speech("これは一文目です。これは二文目です。", limit=12)
    assert [l.text for l in out] == ["これは一文目です。", "これは二文目です。"]


def test_短ければまとめる():
    """★1文ずつ細切れに読むと、間が空いて不自然。"""
    out = split_speech("はい。そうです。わかりました。", limit=40)
    assert len(out) == 1


def test_切れ目の無い長文も途中で切る():
    """★切れ目が無いからと丸ごと投げない。読み上げが壊れる。"""
    out = split_speech("あ" * 300, limit=80)
    assert out and all(len(l.text) <= 80 for l in out)
    assert "".join(l.text for l in out) == "あ" * 300


def test_表情を指定できる():
    out = split_speech("[happy]うれしいです。[sad]かなしいです。")
    assert [(l.face, l.text) for l in out] == [
        ("happy", "うれしいです。"), ("sad", "かなしいです。")]


def test_表情のない行は前の表情を引き継がない():
    """★指定が無ければ console に任せる。勝手に固定しない。"""
    out = split_speech("[happy]わあ。\nふつうです。")
    assert out[0].face == "happy"
    assert out[1].face is None


def test_知らない表情は無視して読む():
    """★セリフが読まれないほうが困る。**表情は飾り、本体は言葉。**"""
    out = split_speech("[そんな顔はない]よみます。")
    assert out[0].text.endswith("よみます。")
    assert out[0].face is None


def test_空白だけなら何も返さない():
    assert split_speech("   \n  ") == []


def test_間を置ける():
    out = split_speech("ここで。[pause=1.5]つづき。")
    assert out[1].pause_before == 1.5


def test_改行は必ず割る():
    """★間の取り方は書き手のもの。改行を無視して繋げない。"""
    out = split_speech("いちぎょうめ。\nにぎょうめ。", limit=200)
    assert [l.text for l in out] == ["いちぎょうめ。", "にぎょうめ。"]


# ── 喋っている間、LEDが消えていた（2026-09-12 実地）──────────
#
# 締めの挨拶を読ませたら、**背景のLEDが真っ暗だった。**
# `presence.talk` は立てていたが、**LED側に伝えていなかった**
# （console は set_talk() で両方に配る作りだった）。
#
# ★状態を持つ場所が2つあるなら、**配るところを1つに通す。**

def test_台本からLEDの模様を指定できる():
    out = split_speech("[led=laser]はじまります。")
    assert out[0].led == "laser"
    assert out[0].text == "はじまります。"


def test_知らない模様は無視して読む():
    out = split_speech("[led=そんな模様はない]よみます。")
    assert out[0].led is None
    assert out[0].text.endswith("よみます。")


def test_LED指定がなければ触らない():
    out = split_speech("ふつうに よみます。")
    assert out[0].led is None


# ── 首が動かなかった（2026-09-12 実地）────────────────
#
# > **「首振りとか頷きがないな今度はw」**
#
# 顔とLEDと声は出たが、**からだが止まっていた。**
# 話しているのに固まっていると、**読み上げ機に見える。**

def test_台本から動きを指定できる():
    out = split_speech("[nod]はい、そうです。")
    assert out[0].move == "nod"
    assert out[0].text == "はい、そうです。"


def test_知らない動きは無視して読む():
    out = split_speech("[move=そんな動きはない]よみます。")
    assert out[0].move == "idle", "知らない指示が動きとして残っている"
    assert out[0].text.endswith("よみます。")


def test_動きの種類がそろっている():
    from panel import MOVES
    for m in ("nod", "tilt", "look_l", "look_r", "scan", "perk"):
        assert m in MOVES, m
        assert MOVES[m], f"{m} の中身が空"


def test_動きは可動域を超えない():
    """★超えるとサーボが潰れる。yaw±90 / pitch差±40。"""
    from panel import MOVES
    for name, steps in MOVES.items():
        for y, p in steps:
            assert -90 <= y <= 90, (name, y)
            assert -40 <= p <= 40, (name, p)


# ── 喋っている間ずっと動く（2026-09-12 本人の指摘）──────────
#
# > **「足りないです。動きが全然なさすぎて。もっといっぱいはしゃいでほしい」**
#
# 動きは4ステップ＝約1.1秒で終わっていた。1行を読むのは3〜5秒。
# **残りは固まっていた。**
#
# ★動きの長さを、**喋りの長さに合わせる。** 決め打ちの回数で終わらせない。

def test_指定がなくても動く():
    """★止まっている行を作らない。**固まった瞬間に読み上げ機に見える。**"""
    out = split_speech("ふつうに よみます。")
    assert out[0].move is not None, "無指定の行が止まっている"


def test_動きは繰り返せる():
    """★喋り終わるまで続けるので、頭とお尻が繋がること。"""
    from panel import MOVES
    for name, steps in MOVES.items():
        assert len(steps) >= 3, f"{name} が短すぎる"


def test_はしゃぐ動きがある():
    from panel import MOVES
    for m in ("bounce", "shake", "swing"):
        assert m in MOVES, m
