"""DJのキーで LEDの模様を切り替える仕様。

## なぜ（2026-09-12）

模様を13個つくったが、**スマホからしか出せなかった。**
当日、演者は DJ機材に手を置いている。**画面を触りに行く隙は無い。**

割り当ては `mapping.json` の `led_pattern`。実機で1つずつ押して決めた
（`scripts/assign_led.py`）。

★**顔のボタンと同じ経路に乗せない。** 顔は一時的な上書き、模様は続く状態。
"""
import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "app" / "dj"))
from midi_in import MidiMixin      # noqa: E402


class Msg:
    def __init__(self, ch, note):
        self.type, self.channel, self.note, self.velocity = "note_on", ch, note, 100


class FakeLed:
    def __init__(self): self.pattern, self.manual = "show", False

    def show_pattern(self, name):
        self.pattern, self.manual = name, True


class Fake(MidiMixin):
    def __init__(self, ctl):
        self.ctl = ctl
        self.note = {(v["ch"], v["num"]): k for k, v in ctl.items()
                     if v.get("kind") == "note"}
        self.cc = {}
        self.led = FakeLed()
        self.faces = []
        self.mode = "off"
        self.args = type("A", (), {"off_ch": 6, "off_note": 99,
                                   "play_ch": 0, "play_note": 11})()

    async def show_face(self, face, slot=None): self.faces.append(face)
    async def set_mode(self, m, why=""): self.mode = m
    async def wake_servos(self): pass
    def _show_pose(self, *_): pass


CTL = {
    "led_laser": {"kind": "note", "ch": 9, "num": 5, "label": "LED laser",
                  "led_pattern": "laser"},
    "btn_happy": {"kind": "note", "ch": 7, "num": 4, "label": "笑う",
                  "avatar": "happy"},
}


def run(c): return asyncio.run(c)


def test_割り当てたキーで模様が変わる():
    f = Fake(CTL)
    run(f._handle(Msg(9, 5)))
    assert f.led.pattern == "laser"


def test_モードに関係なく光る():
    """★本人「光るのは Playモードか否かは関係ないように動くべき」。"""
    f = Fake(CTL)
    f.mode = "off"
    run(f._handle(Msg(9, 5)))
    assert f.led.manual, "OFFモードだと光らない作りのまま"


def test_模様のキーで顔を変えない():
    """★顔は一時的な上書き、模様は続く状態。**混ぜない。**"""
    f = Fake(CTL)
    run(f._handle(Msg(9, 5)))
    assert f.faces == [], f.faces


def test_顔のボタンは今までどおり():
    f = Fake(CTL)
    run(f._handle(Msg(7, 4)))
    assert f.faces == ["happy"]
    assert f.led.pattern == "show"


def test_知らない模様なら何もしない():
    """★mapping を手で書き換えて壊れた名前が入ることがある。"""
    f = Fake({"led_x": {"kind": "note", "ch": 9, "num": 1,
                        "label": "x", "led_pattern": "そんな模様はない"}})
    run(f._handle(Msg(9, 1)))
    assert f.led.pattern == "show"
