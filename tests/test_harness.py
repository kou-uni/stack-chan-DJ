"""受け入れ試験を「単独で」走らせる土台の仕様。

## なぜ要るか（2026-09-12）

`device_check.py` は首とLEDを直接書く。ところが console は
**唯一の書き手**（architecture.md I2）で、20秒ごとに全部を書き直す。
**二人が書けば、測った値が誰のものか分からない。**

しかもストリーム試験は console の 8770/8771 に繋ぎに行くので、
console を止めるだけだと**偽の×**が出る。**それを基準にしたら比較が全部狂う。**

> 焼く前と後で条件が違う測定は、測らないより悪い。
> （[[insights/20260908-incomplete-measurement-is-worse-than-guessing]]）

だから試験台が、**console を止め、自分のサーバを立て、終わったら必ず戻す。**
"""
import asyncio
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "app" / "dj"))
from harness import ConsolePause, throwaway_ws, port_busy   # noqa: E402


class FakeCtl:
    """launchctl の代わり。呼ばれた順に記録する。"""

    def __init__(self, running=True):
        self.calls, self._running = [], running

    def is_running(self, label):
        return self._running

    def stop(self, label):
        self.calls.append(("stop", label))
        self._running = False

    def start(self, label):
        self.calls.append(("start", label))
        self._running = True


def test_console_is_stopped_then_restored():
    """★動いていたなら、止めて、必ず戻す。"""
    ctl = FakeCtl(running=True)
    with ConsolePause("com.uni.stackchan.console", ctl):
        assert ctl.calls == [("stop", "com.uni.stackchan.console")]
    assert ctl.calls[-1] == ("start", "com.uni.stackchan.console")


def test_console_restored_even_when_test_blows_up():
    """★試験が落ちても戻す。戻し忘れると実機が沈黙したままになる。"""
    ctl = FakeCtl(running=True)
    with pytest.raises(RuntimeError):
        with ConsolePause("x", ctl):
            raise RuntimeError("試験が落ちた")
    assert ("start", "x") in ctl.calls


def test_not_running_console_is_left_alone():
    """★もともと止まっていたなら、勝手に起動しない。"""
    ctl = FakeCtl(running=False)
    with ConsolePause("x", ctl):
        pass
    assert ctl.calls == []


def test_throwaway_ws_binds_and_releases():
    """★立てたサーバは必ず閉じる。

    以前 `async with websockets.serve()` で --verify が終わらなくなった。
    **開いた接続を待ち続けるから。** 同じ穴を踏まない。
    """
    async def go():
        port = 8899
        assert not port_busy(port)
        async with throwaway_ws(port):
            assert port_busy(port)
        for _ in range(20):                 # 解放は非同期。少し待つ
            if not port_busy(port):
                return
            await asyncio.sleep(0.05)
        raise AssertionError("ポートが解放されていない")

    asyncio.run(asyncio.wait_for(go(), timeout=10))


# ── 戻し方が間違っていた（2026-09-12 実地）──────────────
#
# `bootout` で止めたあと `kickstart` で戻していた。
# **bootout すると読み込み自体が消えるので、kickstart は何もしない。**
#
# 結果、console が落ちたまま放置され、**実機が全部無反応になった。**
# 本人の言葉：**「何も反応しない。というか今までのも反応しなくなった」**
#
# ★止める手段と戻す手段は、**対になっていないといけない。**

class RecordCtl:
    """launchctl の代わり。**読み込み状態まで真似る。**"""

    def __init__(self, loaded=True, running=True):
        self.loaded, self.running, self.calls = loaded, running, []

    def is_running(self, label):
        return self.loaded and self.running

    def stop(self, label):
        self.calls.append("stop")
        self.loaded = self.running = False      # ★bootout は読み込みごと消す

    def start(self, label):
        self.calls.append("start")
        self.loaded = self.running = True


def test_止めたあと本当に動いている状態に戻る():
    ctl = RecordCtl()
    with ConsolePause("x", ctl):
        assert not ctl.is_running("x")
    assert ctl.is_running("x"), "止めたまま戻っていない"


def test_落ちても戻る():
    ctl = RecordCtl()
    try:
        with ConsolePause("x", ctl):
            raise RuntimeError("試験が落ちた")
    except RuntimeError:
        pass
    assert ctl.is_running("x")
