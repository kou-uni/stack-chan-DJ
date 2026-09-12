"""MIDIを流し込んで、自分で確かめられるようにする。

## なぜ（2026-09-12 本人の指摘）

> **「テストしてよ、なんで僕が押すまでわかんないんだ。甘いよ」**

割り当てが効いているかを、**本人にパッドを押させて確かめていた。**
13個の割り当てを人手で確認するのは、毎回やっていられない。

★**人の手でしか確かめられない作りは、確かめられていないのと同じ。**
  実機に触る必要がある部分（サーボ・LEDの見え方）と、
  **合成した入力で確かめられる部分（割り当て・分岐）を分ける。**
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "app" / "dj"))
from panel import fake_note   # noqa: E402


def test_ノートの形になる():
    m = fake_note(9, 5)
    assert (m.type, m.channel, m.note) == ("note_on", 9, 5)
    assert m.velocity > 0


def test_離す動きも作れる():
    m = fake_note(9, 5, velocity=0)
    assert m.velocity == 0


def test_つまみも作れる():
    m = fake_note(6, 23, kind="cc", value=100)
    assert (m.type, m.channel, m.control, m.value) == ("control_change", 6, 23, 100)
