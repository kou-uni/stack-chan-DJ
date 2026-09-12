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
