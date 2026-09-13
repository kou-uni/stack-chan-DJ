"""バーに出すつまみを1つに絞る。

★2026-09-13 本人の指摘：「大きくなったり小さくなったり、かなり波打ってる」
  DDJ が同時に流す全部のCCを拾っていたのが原因。
"""
import sys
import pathlib

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent / "app" / "dj"))

from meter import MeterPicker            # noqa: E402


def test_下位バイトは見ない():
    """★CC32-63 は CC0-31 の下位。上位が1増えるだけで0..127を一周する。"""
    p = MeterPicker()
    assert p.feed(0, 32, 24, 0.0) is None
    assert p.feed(0, 32, 92, 0.1) is None
    assert p.feed(0, 63, 5, 0.2) is None


def test_割り当て済みなら下位番号でも従う():
    """★人が割り当てたものは、番号がいくつでも人の意図が勝つ。"""
    p = MeterPicker()
    assert p.feed(0, 32, 64, 0.0, mapped=True) == 64 / 127


def test_最初の1発では出さない():
    p = MeterPicker()
    assert p.feed(6, 23, 40, 0.0) is None


def test_回しているつまみが出る():
    p = MeterPicker()
    p.feed(6, 23, 40, 0.0)
    assert p.feed(6, 23, 60, 0.05) == 60 / 127
    assert p.feed(6, 23, 90, 0.10) == 90 / 127


def test_ほかのつまみは割り込めない():
    """★取り合うとバーがちらつく。持ち主が決まったら少しの間は譲らない。"""
    p = MeterPicker()
    p.feed(6, 23, 40, 0.0)
    p.feed(6, 23, 60, 0.05)             # 6/23 が持ち主
    p.feed(0, 7, 10, 0.06)
    assert p.feed(0, 7, 120, 0.07) is None


def test_しばらく置けば別のつまみに移る():
    p = MeterPicker()
    p.feed(6, 23, 40, 0.0)
    p.feed(6, 23, 60, 0.05)
    p.feed(0, 7, 10, 0.06)
    assert p.feed(0, 7, 120, 1.0) == 120 / 127


def test_持ち主は動いていなくても出し続ける():
    """★バーが途中で消えない。"""
    p = MeterPicker()
    p.feed(6, 23, 40, 0.0)
    p.feed(6, 23, 60, 0.05)
    assert p.feed(6, 23, 61, 0.10) == 61 / 127


def test_他人の微動はバーを動かさない():
    p = MeterPicker()
    p.feed(6, 23, 40, 0.0)
    p.feed(6, 23, 60, 0.05)
    p.feed(0, 7, 10, 0.06)
    assert p.feed(0, 7, 11, 0.07) is None


def test_実測したDDJの流れで暴れない():
    """★実際のログ（2026-09-13）をそのまま流す。上位下位が交互に来る。"""
    p = MeterPicker()
    stream = [(0, 0, 127), (0, 32, 24), (0, 0, 69), (0, 32, 92),
              (0, 7, 62), (0, 39, 101), (0, 11, 65), (0, 43, 9)]
    out = []
    for i, (ch, num, v) in enumerate(stream):
        r = p.feed(ch, num, v, i * 0.01)
        if r is not None:
            out.append(r)
    # 下位は全部落ち、上位も持ち主1つぶんしか出ない
    assert len(out) <= 1, out
