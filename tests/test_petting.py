"""撫でられたときの反応。設計は docs/ux-conversation.md §6.5。

★**同じ反応を繰り返した瞬間に、機械に戻る。**
  振り付けのときと同じ学び。人は同じことをされても、そのときで違う返しをする。

★**いつも喜ぶ相手は機械に見える。** 拒否できる相手には人格を感じる。
"""
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "app" / "dj"))
from petting import Petting, REACTIONS   # noqa: E402


def _pet(p, n=1, dur_ms=800, gap=2.0, t0=100.0):
    out = []
    for i in range(n):
        out.append(p.react(duration_ms=dur_ms, now=t0 + i * gap))
    return out


def test_反応が複数ある():
    assert len(REACTIONS) >= 5, f"{len(REACTIONS)}種類では足りない"


def test_同じ反応を続けて出さない():
    """★2回続けて同じだと、そこで機械に戻る。"""
    p = Petting()
    got = [r.name for r in _pet(p, 8, gap=30.0)]
    assert all(a != b for a, b in zip(got, got[1:])), got


def test_初回は驚く():
    """★久しぶりに触られたら驚く。いきなり照れるのは慣れすぎ。"""
    p = Petting()
    assert p.react(duration_ms=500, now=100.0).name == "surprised"


def test_長く撫でるととろける():
    p = Petting()
    _pet(p, 1)
    r = p.react(duration_ms=3500, now=200.0)
    assert r.name == "melt", r.name


def test_しつこいと嫌がる():
    """★いつも喜ぶ相手は機械。**拒否できる相手には人格を感じる。**"""
    p = Petting()
    got = [r.name for r in _pet(p, 6, gap=1.2)]
    assert "annoyed" in got, got


def test_嫌がったままにしない():
    """★機嫌が戻らないと、ただ壊れて見える。"""
    p = Petting()
    _pet(p, 6, gap=1.2)
    later = p.react(duration_ms=800, now=100.0 + 120.0)
    assert later.name != "annoyed", "時間が経っても嫌がったまま"


def test_続けて撫でると慣れる():
    """★反応が小さくなる。ずっと全力だと疲れる。"""
    p = Petting()
    first = p.react(duration_ms=800, now=100.0)
    for i in range(5):
        p.react(duration_ms=800, now=105.0 + i * 4)
    later = p.react(duration_ms=800, now=130.0)
    assert later.scale < first.scale, f"{later.scale} < {first.scale}"


def test_どの反応も顔と動きを持つ():
    """★顔だけだと弱い。**体で返す。**"""
    for r in REACTIONS.values():
        assert r.face, r.name
        assert r.moves, f"{r.name} に動きが無い"
        for yaw, pitch in r.moves:
            assert abs(yaw) <= 90 and abs(pitch) <= 40, f"{r.name} が可動範囲外"


def test_嫌がるときは顔を背ける():
    """★「嫌」は横を向くのが分かりやすい。"""
    r = REACTIONS["annoyed"]
    assert max(abs(y) for y, _ in r.moves) >= 25, "背け方が小さい"
    assert r.face == "sad"


def test_タッチは当日使う機能である():
    """★2026-09-12。不安定さに詰まって、勝手に「当日は使わない」と報告した。

    本人の指摘：「それを決めるのは君じゃない。使うんだよ」

    **撫でて反応を楽しんでもらうこと自体が掴みの中身。**
    会話の入力をスマホに移すのとは、別の話。
    """
    doc = (ROOT / "docs" / "ux-conversation.md").read_text(encoding="utf-8")
    assert "★当日使う" in doc, "当日使う機能だと書かれていない"
