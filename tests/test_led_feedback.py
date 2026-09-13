"""入力への返事。**触ったら、必ず身体のどこかが応える。**

docs/ideas.md ①〜④。ハンズオンで人が触るのだから、
撫でてもこすっても無反応、というのがいちばん痛い（2026-09-13）。
"""
import sys
import pathlib

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent / "app" / "dj"))

import pytest                                        # noqa: E402
from led import LedState                             # noqa: E402


def _led():
    return LedState(count=12, target="base_ring", max_brightness=0.35)


def test_知らない返事は作れない():
    """★期限を決めていない返事を足させない。消し忘れが起きる。"""
    with pytest.raises(ValueError):
        _led().poke("しらない", now=0.0)


def test_撫でたら光る():
    led = _led()
    led.enabled = False
    led.poke("touch", now=100.0)
    led.now = lambda: 100.5
    assert any(any(c) for c in led.colors())


def test_撫での返事は期限で消える():
    led = _led()
    led.poke("touch", now=100.0)
    led.now = lambda: 100.0 + LedState.POKE_S["touch"] + 0.1
    assert led.poke_kind is None or True     # colors() が片付ける
    led.colors()
    assert led.poke_kind is None


def test_撫での色は七色で一様でない():
    led = _led()
    led.poke("touch", now=0.0)
    led.now = lambda: 0.2
    cols = led.colors()
    assert len({tuple(c) for c in cols}) >= 6, cols


def test_こすりは撫でを追い出さない():
    """★撫でている最中にレコードが動いても、撫での返事を殺さない。"""
    led = _led()
    led.poke("touch", now=100.0)
    led.poke("scratch", now=100.3)
    assert led.poke_kind == "touch"


def test_会話の色は入力より強い():
    """★配布物に「緑=聞く／青=喋る」と書いてある。撫でた瞬間に変わると嘘になる。"""
    led = _led()
    led.talk = "listening"
    led.poke("touch", now=0.0)
    led.now = lambda: 0.2
    cols = led.colors()
    assert len({tuple(c) for c in cols}) == 1        # 会話の色は一様
    assert cols[0][1] > cols[0][0]                   # 緑が強い


def test_バーストは入力より強い():
    led = _led()
    led.burst = 1.0
    led.poke("touch", now=0.0)
    led.now = lambda: 0.2
    cols = led.colors()
    assert sum(1 for c in cols if c[0] >= c[2]) >= 10, cols


def test_つまみは点灯本数で出る():
    led = _led()
    led._meter_now = 0.5                      # 追いつきを飛ばして見る
    led.show_meter(0.5, now=0.0)
    led.now = lambda: 0.2
    cols = led.colors()
    # 先端の1つは半端、その先に薄い尾が1つ残る
    bright = sum(1 for c in cols if max(c) > 40)
    assert 5 <= bright <= 7, [max(c) for c in cols]
    assert not any(cols[-1])                  # 上のほうは消えている


def test_つまみのバーは滑らかに追いつく():
    """★12個しかないので、そのまま出すとカクカク動く（2026-09-13 本人の指摘）。"""
    led = _led()
    led._meter_now = 0.0
    led.show_meter(1.0, now=0.0)
    led.now = lambda: 0.05
    seen = []
    for _ in range(4):
        led.colors()
        seen.append(led._meter_now)
    assert seen == sorted(seen), seen          # 単調に近づく
    assert seen[0] < 1.0, seen                 # 一足飛びにならない
    assert seen[-1] > seen[0], seen


def _bar(v):
    led = _led()
    led._meter_now = v                        # 追いつきを飛ばして目盛りだけ見る
    led.show_meter(v, now=0.0)
    led.now = lambda: 0.01
    return [max(c) for c in led.colors()]


def test_目盛りは0で全消灯_1で全点灯():
    """★100%になる前に100%に見えてはいけない（2026-09-13 本人の指摘）。

    以前は先の粒にも薄い尾を出していたので、**0%で1個光り、83%で全部光って**
    見えていた。メーターは値を読む道具なので、目盛りの正しさが先。
    """
    assert all(v == 0 for v in _bar(0.0))
    full = _bar(1.0)
    assert all(v > 0 for v in full)
    # 99% と 100% が見分けられること（＝手前で振り切れない）
    assert _bar(0.99)[-1] < full[-1]


def test_目盛りは値どおりの本数():
    for v, n in ((0.25, 3), (0.5, 6), (0.75, 9)):
        lit = sum(1 for x in _bar(v) if x > 0)
        assert lit == n, (v, lit)


def test_先端は明るさで半端を表す():
    """★12個しかないので、間は先端の明るさで埋める。"""
    b = _bar(0.5 + 1/24)                      # ちょうど半目盛りぶん上
    assert 0 < b[6] < b[5], b


def test_つまみを回しきると全部点く():
    led = _led()
    led.show_meter(1.0, now=0.0)
    led.now = lambda: 0.2
    assert all(any(c) for c in led.colors())


def test_つまみのメーターも期限で消える():
    led = _led()
    led.show_meter(0.5, now=0.0)
    led.now = lambda: 5.0
    led.colors()
    assert led.meter is None


def test_消えていても入力には返事する():
    """★OFFでも、触った人には返さないと「壊れている」に見える。"""
    import json
    led = _led()
    led.enabled = False
    led.poke("touch", now=100.0)
    led.now = lambda: 100.2
    assert any(any(c) for c in json.loads(led.frame())["colors"])


def test_触っていなければ消えたまま():
    import json
    led = _led()
    led.enabled = False
    assert all(c == [0, 0, 0] for c in json.loads(led.frame())["colors"])


def test_バーの明るさは端から端まで均一():
    """★RGBを直に混ぜると明るさが波打ち、点いているのに凹んで見える。

    2026-09-13：真ん中が 162 まで落ちて、端が 248。
    「もう振り切れている」ように見える原因になっていた。
    """
    led = LedState(count=30, target="port_b", max_brightness=0.35)
    led._meter_now = 1.0
    led.show_meter(1.0, now=0.0)
    led.now = lambda: 0.01
    peaks = [max(c) for c in led.colors()]
    assert max(peaks) - min(peaks) <= 2, peaks


def test_30粒でも0で全消灯_1で全点灯():
    """★実機は30粒（config.toml）。12粒でしか試していないと気づけない。"""
    led = LedState(count=30, target="port_b", max_brightness=0.35)
    led._meter_now = 0.0
    led.show_meter(0.0, now=0.0)
    led.now = lambda: 0.01
    assert all(max(c) == 0 for c in led.colors())
    led._meter_now = 1.0
    led.show_meter(1.0, now=0.0)
    assert all(max(c) > 0 for c in led.colors())
