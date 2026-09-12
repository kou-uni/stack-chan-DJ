"""背景スクリーン（iPad）へ送る状態。

★「スタックチャンが指令している」を**事実にする**。
  実機のマイクが聴いた音 → gateway → console → 背景が動く。
  演出ではなく、本当にその経路で動いている。

★ここは Phase 2（スマホから触れる）と同じ土台。サーバは1本。
"""
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "app" / "dj"))

import presence as P          # noqa: E402
from led import LedState      # noqa: E402
from stage import stage_state  # noqa: E402


def _parts(bpm=128.0, dancing=False, talk=None, mode=P.MODE_IDLE, now=10.0):
    led = LedState(count=30, max_brightness=1.0)
    led.bpm, led.beat0, led.enabled = bpm, 0.0, dancing
    pres = P.Presence(now=lambda: now)
    pres.mode, pres.dancing, pres.talk = mode, dancing, talk
    return led, pres


def test_拍の位置が0から1で返る():
    """★画面は拍の位置で光る。秒ではなく位相で渡す。"""
    for t in (0.0, 0.11, 0.23, 0.47):
        led, pres = _parts()
        led.beat0 = -t
        s = stage_state(led, pres, now=0.0)
        assert 0.0 <= s["beat"] < 1.0, s["beat"]


def test_BPMをそのまま渡す():
    led, pres = _parts(bpm=140.0)
    assert stage_state(led, pres, now=0.0)["bpm"] == 140.0


def test_色はLEDと同じシリーズを使う():
    """★テープと画面で色が食い違うと、途端に嘘くさくなる。"""
    led, pres = _parts()
    for n in (0, 16, 32, 48, 64):
        led.beat0 = -(n * 60.0 / led.bpm)
        s = stage_state(led, pres, now=0.0)
        assert s["series"] in ("blue", "red")
        assert s["series"] == led._series_name(s["n"])


def test_踊っているかどうかが分かる():
    led, pres = _parts(dancing=True, mode=P.MODE_DJ)
    assert stage_state(led, pres, now=0.0)["dancing"] is True
    led, pres = _parts(dancing=False)
    assert stage_state(led, pres, now=0.0)["dancing"] is False


def test_サビが伝わる():
    led, pres = _parts(dancing=True, mode=P.MODE_DJ)
    led.flash_white = True
    assert stage_state(led, pres, now=0.0)["drop"] is True


def test_会話の状態が伝わる():
    """★聞いている／喋っている。画面もLEDと同じ意味で光らせる。"""
    led, pres = _parts(talk="listening")
    assert stage_state(led, pres, now=0.0)["talk"] == "listening"


def test_曲が止まっていても落ちない():
    """★BPM が無いときに割り算で落ちない。"""
    led, pres = _parts(bpm=0.0)
    s = stage_state(led, pres, now=0.0)
    assert s["bpm"] == 0.0 and s["beat"] == 0.0


def test_送る中身は小さい():
    """★毎拍たくさん送ると、iPad より先にネットワークが詰まる。"""
    led, pres = _parts()
    s = stage_state(led, pres, now=0.0)
    assert len(s) <= 10, f"項目が {len(s)} 個。増やしすぎ"
