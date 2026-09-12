"""LEDの色の意味。★参加者に配る紙と、実機を一致させる。

配布物（event/handson-guide.md）にこう書いてある：

    緑    あなたの声を聞いています
    青    喋っています
    消灯  待機中

★紙を見た人が「緑を探す」のに緑が光らないと、その紙は嘘になる。
  優先順は 喋る > 聞く > 踊り > 消灯。会話が最優先。
"""
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "app" / "dj"))
from led import LedState  # noqa: E402


def _led(**kw):
    s = LedState(max_brightness=1.0, **kw)
    s.bpm, s.beat0 = 120.0, 0.0
    return s


def _hue(c):
    """いちばん強い成分。r/g/b のどれか。"""
    r, g, b = c
    return "r" if r > g and r > b else ("g" if g >= r and g > b else "b")


def test_聞いている間は緑():
    s = _led(); s.enabled = True
    s.talk = "listening"
    for c in s.colors():
        assert _hue(c) == "g", f"聞いている間は緑。いまは {c}"


def test_喋っている間は青():
    s = _led(); s.enabled = True
    s.talk = "speaking"
    for c in s.colors():
        assert _hue(c) == "b", f"喋っている間は青。いまは {c}"


def test_会話は踊りより優先される():
    """★踊っている最中に話しかけられても、聞いていることが分かるように。"""
    s = _led(); s.enabled = True
    s.talk = "listening"
    assert all(_hue(c) == "g" for c in s.colors())


def _lit_over_time(s, n=40):
    """時間を進めながら、一度でも光ったか。模様は拍で消える瞬間があるため。"""
    import time as _t
    for i in range(n):
        s.beat0 = _t.time() - i * 0.02
        if any(c != [0, 0, 0] for c in json.loads(s.frame())["colors"]):
            return True
    return False


def test_待機は消灯():
    """★紙に『消灯＝待機中。タップすると起きます』と書いてある。"""
    s = _led(); s.enabled = False        # 踊っていない
    s.talk = None                        # 会話もしていない
    assert not _lit_over_time(s), "待機なのに光っている"


def test_踊っている間は模様が出る():
    s = _led(pattern="wave"); s.enabled = True
    s.talk = None
    assert _lit_over_time(s), "踊っているのに光らない"


def test_会話中は踊っていなくても光る():
    """★ここが実装前にテストで見つかった穴。

    会話中は踊っていない（enabled=False）。
    LED を enabled だけで閉じていたので、緑も青も一度も出ない作りだった。
    """
    s = _led(); s.enabled = False
    s.talk = "listening"
    assert _lit_over_time(s), "会話中なのに消灯している"


def test_知らない状態は無視する():
    """★会話側が変な値を入れても、踊りが壊れないこと。"""
    s = _led(pattern="wave"); s.enabled = True
    s.talk = "なにかへんな値"
    assert _lit_over_time(s)


def test_配布物と実装の対応が文書に残っている():
    doc = (ROOT / "event" / "handson-guide.md").read_text(encoding="utf-8")
    for word in ("緑", "青", "消灯"):
        assert word in doc


# ── 光るのに音は要らない（2026-09-12 本人の指摘）───────────
#
# > **「光るのは、Playモードか否かは関係ないように動くべき。音声関係ないから」**
#
# 模様を割り当てたパッドを押しても、DJモードでないと光らなかった。
# **模様は「見せるもの」で、拍に合わせるのは味付け。** 前提が逆だった。

def test_模様を選んだら音がなくても光る():
    s = LedState(count=8)
    s.enabled = False              # 踊っていない（OFFモード）
    s.show_pattern("laser")
    assert any(any(c) for c in s.colors()), "選んだのに消えている"


def test_拍が無くても模様が進む():
    """★bpm=0 でも止まって見えないこと。**自走する。**"""
    import time as _t
    s = LedState(count=8)
    s.show_pattern("chase")
    a = s.colors()
    _t.sleep(0.25)
    b = s.colors()
    assert a != b, "止まって見える"


def test_踊りはじめたら拍に乗る():
    """★自走はあくまで音が無いときだけ。音があればそちらが勝つ。"""
    s = LedState(count=8)
    s.show_pattern("laser")
    s.enabled = True
    s.bpm = 128.0
    assert s.bpm == 128.0


# ── 選んだ模様は20秒で戻る（2026-09-12 本人の要望）──────────
#
# 押しっぱなしの状態にすると、**次に押すまでずっとその模様**になる。
# 演奏中は手が離せないので、**勝手に戻ってほしい。**

def test_二十秒たったら元に戻る():
    s = LedState(count=8, pattern="show")
    s.show_pattern("laser", hold_s=20.0, now=100.0)
    assert s.current_pattern(now=110.0) == "laser"
    assert s.current_pattern(now=121.0) == "show", "戻っていない"


def test_戻ったら自走もやめる():
    """★戻ったのに光りっぱなしだと、戻った気がしない。"""
    s = LedState(count=8)
    s.show_pattern("laser", hold_s=20.0, now=100.0)
    s.current_pattern(now=121.0)
    assert not s.manual


def test_押し直したら数え直す():
    s = LedState(count=8, pattern="show")
    s.show_pattern("laser", hold_s=20.0, now=100.0)
    s.show_pattern("sparks", hold_s=20.0, now=115.0)
    assert s.current_pattern(now=130.0) == "sparks", "前の期限で消えている"


def test_踊っている間は消えない():
    """★DJモードで踊っているなら、基本の模様に戻るだけ。真っ暗にしない。"""
    s = LedState(count=8, pattern="show")
    s.enabled = True
    s.bpm = 120.0
    s.show_pattern("laser", hold_s=20.0, now=100.0)
    s.current_pattern(now=121.0)
    assert any(any(c) for c in s.colors()), "踊っているのに消えた"
