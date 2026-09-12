"""反映役。★実機なしで、送るものと送らないものを確かめる。"""
import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "app" / "dj"))
import presence as P          # noqa: E402
from reconcile import Reconciler  # noqa: E402


class FakeGateway:
    """呼ばれたツールを覚えるだけの偽物。"""
    def __init__(self):
        self.calls = []

    async def call(self, name, **args):
        self.calls.append((name, args))

    def names(self):
        return [n for n, _ in self.calls]


def run(coro):
    return asyncio.run(coro)


def _pair():
    gw = FakeGateway()
    p = P.Presence(now=lambda: 0.0)
    return gw, p, Reconciler(gw, p, quiet=True)


def test_最初は全部送る():
    gw, p, r = _pair()
    run(r.apply())
    assert gw.names() == ["set_avatar", "set_blink", "beat_mode_update", "set_all_leds"]


def test_変わらなければ何も送らない():
    """★毎周期ぜんぶ送ると、往復が増えて音声の取り込みを邪魔する。"""
    gw, p, r = _pair()
    run(r.apply())
    n = len(gw.calls)
    run(r.apply()); run(r.apply())
    assert len(gw.calls) == n, "変化が無いのに送っている"


def test_変わったものだけ送る():
    gw, p, r = _pair()
    run(r.apply())
    gw.calls.clear()
    p.overlay("cheer", "happy", seconds=1.0)      # 顔と瞬きだけ変わる
    run(r.apply())
    assert gw.names() == ["set_avatar", "set_blink"]


def test_期限が切れたら元に戻す():
    gw, p, r = _pair()
    p.overlay("cheer", "happy", seconds=1.0)
    run(r.apply())
    gw.calls.clear()
    p.now = lambda: 2.0
    run(r.apply())
    assert ("set_avatar", {"face": "idle"}) in gw.calls, "顔が戻っていない"
    assert ("set_blink", {"enabled": True}) in gw.calls, "瞬きが戻っていない"


def test_乱されても送り直しで戻る():
    """★外から誰かが叩いても、次の全体送信で必ず戻る。"""
    gw, p, r = _pair()
    run(r.apply())
    gw.calls.clear()
    run(r.apply(force=True))
    assert len(gw.calls) == 4, "送り直しで全部やり直していない"


def test_OFF_でも_gateway_には踊らせない():
    """★2026-09-09 の事故。OFF のまま止まらなくなった。"""
    gw, p, r = _pair()
    p.mode, p.dancing = P.MODE_IDLE, True
    run(r.apply())
    assert ("beat_mode_update",
            {"motion_enabled": False, "led_enabled": False}) in gw.calls


def test_DJ_でも_gateway_には踊らせない():
    """★動かす人は console だけ。gateway の踊りは常に切る。"""
    gw, p, r = _pair()
    p.mode, p.dancing = P.MODE_DJ, True
    run(r.apply())
    assert ("beat_mode_update",
            {"motion_enabled": False, "led_enabled": False}) in gw.calls


def test_顔を出してから瞬きを決める():
    """★顔を変えると実機側で瞬きが乱れる。逆順だと瞬きが消える。"""
    gw, p, r = _pair()
    run(r.apply())
    assert gw.names().index("set_avatar") < gw.names().index("set_blink")


def test_実機が入れ替わったら記録を捨てる():
    gw, p, r = _pair()
    run(r.apply())
    gw.calls.clear()
    r.forget()
    run(r.apply())
    assert len(gw.calls) == 4, "実機が変わったのに差分だけ送っている"


def test_実機が応答しなくても止まらない():
    """★片付けや診断の最中に落ちると、そこで全部止まる。"""
    class Broken(FakeGateway):
        async def call(self, name, **args):
            raise OSError("実機が居ない")

    p = P.Presence(now=lambda: 0.0)
    r = Reconciler(Broken(), p, quiet=True)
    run(r.apply())                                # 例外が漏れないこと
    assert r.writes == 0
