"""当日の音声を録って、文字起こしして、締めの素材にする仕様。

## 何のため（2026-09-12 本人の要望）

**その日に起きたこと・頑張ったことを、締めの挨拶に織り込む。**
台本を前もって書くのではなく、**その場で起きたことを喋る。** ライブ感。

## ゆずれないこと

**音声は部屋の外に出さない。** 当日のメッセージそのもの。
録音も文字起こしも、この Mac の中だけで終わる（faster-whisper）。

## 気をつけること

- **書きかけのファイルを掴まない。** ffmpeg が書いている途中のを読むと壊れる
- **同じ塊を二度処理しない。** 途中で落ちて再開しても重複しない
- **1つ失敗しても止まらない。** 3時間の録音の途中で死ぬのが一番困る
- **終わってから30分待たない。** 録りながら起こす
"""
import json
import sys
import time
from pathlib import Path
import tempfile

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "app" / "dj"))
from meeting import (Transcript, finished_chunks, highlights)   # noqa: E402


def touch(d: Path, name: str, mtime_ago: float = 10.0) -> Path:
    p = d / name
    p.write_bytes(b"x" * 100)
    t = time.time() - mtime_ago
    import os
    os.utime(p, (t, t))
    return p


def test_書きかけは掴まない():
    """★ffmpeg が書いている途中のを読むと壊れる。**落ち着くまで待つ。**"""
    d = Path(tempfile.mkdtemp())
    touch(d, "c000.wav", mtime_ago=30)
    touch(d, "c001.wav", mtime_ago=0.1)      # いま書かれている
    got = [p.name for p in finished_chunks(d, quiet_s=5.0)]
    assert got == ["c000.wav"], got


def test_順番どおりに返す():
    d = Path(tempfile.mkdtemp())
    for n in ("c002.wav", "c000.wav", "c001.wav"):
        touch(d, n, mtime_ago=30)
    assert [p.name for p in finished_chunks(d)] == ["c000.wav", "c001.wav", "c002.wav"]


def test_同じ塊を二度処理しない():
    """★途中で落ちて再開しても重複しない。"""
    d = Path(tempfile.mkdtemp())
    t = Transcript(d / "t.jsonl")
    t.add("c000.wav", 0.0, "はじめまして")
    assert t.done("c000.wav")
    assert not t.done("c001.wav")
    t2 = Transcript(d / "t.jsonl")           # 再起動
    assert t2.done("c000.wav")


def test_壊れた行があっても読める():
    d = Path(tempfile.mkdtemp())
    p = d / "t.jsonl"
    p.write_text('{"chunk":"a","text":"ok"}\nこわれた行\n', encoding="utf-8")
    assert Transcript(p).done("a")


def test_空の文字起こしは残さない():
    """★無音の塊で埋まると、素材が読めなくなる。"""
    d = Path(tempfile.mkdtemp())
    t = Transcript(d / "t.jsonl")
    t.add("c000.wav", 0.0, "   ")
    assert t.done("c000.wav"), "処理済みの印は残す"
    assert t.lines() == [], "空を素材に混ぜている"


def test_素材は時刻つきで出る():
    d = Path(tempfile.mkdtemp())
    t = Transcript(d / "t.jsonl")
    t.add("c000.wav", 0.0, "はじめます")
    t.add("c001.wav", 60.0, "できました")
    h = highlights(t.lines())
    assert "0:00" in h and "1:00" in h
    assert "はじめます" in h


def test_同じ言葉の繰り返しは畳む():
    """★whisper は無音で同じ語を繰り返す。素材が汚れる。"""
    d = Path(tempfile.mkdtemp())
    t = Transcript(d / "t.jsonl")
    for i in range(5):
        t.add(f"c{i:03d}.wav", i * 60.0, "ご視聴ありがとうございました")
    t.add("c009.wav", 600.0, "うごいた")
    h = highlights(t.lines())
    assert h.count("ご視聴") <= 1, h
    assert "うごいた" in h
