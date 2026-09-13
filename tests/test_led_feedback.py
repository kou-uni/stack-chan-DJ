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


def test_バーの先には薄い尾が残る():
    """★粒の間を埋めないと、飛び飛びに見える。"""
    led = _led()
    led._meter_now = 0.5
    led.show_meter(0.5, now=0.0)
    led.now = lambda: 0.2
    cols = led.colors()
    tail = [max(c) for c in cols]
    assert 0 < tail[6] < tail[5], tail


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
