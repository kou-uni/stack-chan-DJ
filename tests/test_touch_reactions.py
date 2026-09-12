"""撫でられたときの反応が、実際に console から出ることの仕様。

## なぜ書くか（2026-09-12）

`petting.py`（6つの反応）と `touch_events.py`（押し出し型の受け取り）は
テストまで揃っていたのに、**console から一度も呼ばれていなかった。**

console は `get_touch_state` を0.8秒ごとに問い合わせる**古いポーリング方式**のまま。
これは**仕様上いつも idle を返す**と切り分け済みの経路だった。
撫でて動いていたのは**ファーム自身の反応**で、こちらの6つは死んでいた。

> **モジュールが在ることと、呼ばれていることは別。**
> テストが緑でも、繋がっていなければ動かない。
"""
import asyncio
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "app" / "dj"))
from petting import REACTIONS                      # noqa: E402
from touch import TouchReactor                     # noqa: E402


class FakePresence:
    def __init__(self):
        self.overlays = []

    def overlay(self, kind, face, seconds):
        self.overlays.append((kind, face, seconds))


class FakePose:
    def __init__(self):
        self.hold = None
        self.holds = []

    def __setattr__(self, k, v):
        object.__setattr__(self, k, v)
        if k == "hold" and hasattr(self, "holds"):
            self.holds.append(v)


def make(**kw):
    return TouchReactor(FakePresence(), FakePose(), face_s=3.0, **kw)


def ev(duration_ms=800, subtype="stroke"):
    return {"event_type": "touch", "subtype": subtype,
            "duration_ms": duration_ms, "ts_unix": time.time()}


def test_a_pet_produces_one_of_the_six_reactions():
    async def _go():
        """★6つの反応のどれかが必ず出る。ファーム任せにしない。"""
        r = make()
        await r.handle(ev(), now=100.0)
        assert r.presence.overlays, "顔が出ていない"
        kind, face, _ = r.presence.overlays[0]
        assert kind == "touch"
        assert face in {x.face for x in REACTIONS.values()}
    asyncio.run(_go())


def test_moves_are_played_and_released():
    async def _go():
        """★首を動かして、**必ず戻す**。戻さないと傾いたままになる。"""
        r = make()
        await r.handle(ev(), now=100.0)
        assert len(r.pose.holds) >= 3, "首が動いていない"
        assert r.pose.holds[-1] is None, "首を戻していない"
    asyncio.run(_go())


def test_same_reaction_never_twice_in_a_row():
    async def _go():
        """★同じ返しを繰り返した瞬間に機械に戻る。"""
        r = make()
        seen = []
        for i in range(6):
            r.presence.overlays.clear()
            await r.handle(ev(), now=100.0 + i * 3)
            seen.append(r.presence.overlays[0][1])
        assert all(a != b for a, b in zip(seen, seen[1:])), seen
    asyncio.run(_go())


def test_something_resting_on_the_head_is_not_a_pet():
    async def _go():
        """★長すぎる「撫で」は置きっぱなし。合図にしない。

        実測で 250899ms / 57100ms が出ている。**手を離すまで1件で来る。**
        """
        r = make(max_stroke_ms=8000)
        await r.handle(ev(duration_ms=57100), now=100.0)
        assert r.presence.overlays == [], "置きっぱなしに反応している"
    asyncio.run(_go())


def test_a_new_pet_interrupts_the_previous_one():
    async def _go():
        """★前の反応が終わる前に触られたら、新しい方を出す。

        待たせると「反応が遅い機械」に見える。
        """
        r = make()
        await r.handle(ev(), now=100.0)
        first = len(r.pose.holds)
        await r.handle(ev(), now=100.5)
        assert len(r.pose.holds) > first
        assert r.pose.holds[-1] is None
    asyncio.run(_go())
