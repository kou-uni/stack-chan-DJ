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


def test_演奏中かはモードで分かる():
    """★こすると音楽が止まって拍が消える。**モードなら消えない。**"""
    led, pres = _parts()
    assert "mode" in stage_state(led, pres, now=0.0)


def test_使っていない項目を載せない():
    """★毎拍送る。**読まれていない値を運ばない**（2026-09-12 に beat/groove/mode を外した）。"""
    led, pres = _parts()
    s = stage_state(led, pres, now=0.0)
    for gone in ("beat", "groove"):
        assert gone not in s, f"{gone} がまだ載っている"



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
    assert s["bpm"] == 0.0 and s["n"] == 0


def test_送る中身は小さい():
    """★毎拍たくさん送ると、iPad より先にネットワークが詰まる。

    ★項目数ではなく**バイト数**で見る（2026-09-13）。
      leds のように「1項目だが中身が12個」があるので、数えても意味がない。
      20Hz で流すので、1KB を超えたら 20KB/s。会場の Wi-Fi では重い。
    """
    import json
    led, pres = _parts()
    led.enabled, led.bpm = True, 124
    s = stage_state(led, pres, now=0.0)
    size = len(json.dumps(s))
    assert size <= 1024, f"1フレーム {size} バイト。20Hz で {size*20//1024}KB/s"
