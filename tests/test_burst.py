"""バーストモード（右の音量ゲージ）。

★盛り上がりの頂点で、人が手でゲージを上げる。0.70 で点火、1.00 で花火。
  **画面・LED・首が同じ値を見ること。** ばらばらに閾値を持つと必ず食い違う。
"""
import sys
import pathlib

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent / "app" / "dj"))

from constants import BURST_ON, burst_amount     # noqa: E402
from led import LedState                          # noqa: E402
from motion.pose import PoseState                 # noqa: E402
from presence import Presence                     # noqa: E402
from stage import stage_state                     # noqa: E402


def test_閾値の下では何も起きない():
    assert burst_amount(0.0) == 0
    assert burst_amount(BURST_ON - 0.001) == 0


def test_閾値ちょうどは0から始まる():
    """★段差を作らない。0.70 でいきなり全開だと事故に見える。"""
    assert burst_amount(BURST_ON) == 0


def test_満で1になり途中は連続():
    assert burst_amount(1.0) == 1.0
    assert abs(burst_amount(0.85) - 0.5) < 1e-9


def test_LEDは赤が主になる():
    led = LedState(count=12, target="base_ring", max_brightness=0.35)
    led.burst = 0.9
    cols = led.colors()
    assert len(cols) == 12
    # ★赤が青より強い粒が大多数。桃色や紫にならないこと
    reddish = sum(1 for c in cols if c[0] >= c[2])
    assert reddish >= 10, cols


def test_LEDは消えていても点く():
    """★人が意図してゲージを上げている。enabled を見て黙らない。"""
    led = LedState(count=12, target="base_ring")
    led.enabled = False
    led.burst = 0.95
    import json
    assert any(any(c) for c in json.loads(led.frame())["colors"])


def test_首は曲が無くても揺れる():
    pose = PoseState()
    pose.bpm = 0
    pose.burst = 0.95
    yaw, dip = pose.dance_angles()
    assert abs(yaw) > 5 or abs(dip) > 2, (yaw, dip)


def test_首はバースト中に踊りの経路を開ける():
    pose = PoseState()
    pose.dance = False
    pose.burst = 0.95
    assert pose._sync_arbiter().dancing


def test_閾値の下では首は静か():
    pose = PoseState()
    pose.bpm = 0
    pose.burst = 0.5
    assert pose.dance_angles() == (0.0, 0.0)


def test_画面にも同じ値が届く():
    led = LedState(count=12, target="base_ring")
    pres = Presence()
    pres.burst = 0.83
    s = stage_state(led, pres, now=0.0)
    assert abs(s["burst"] - 0.83) < 1e-9


def test_画面とPythonで閾値が同じ():
    """★2箇所に閾値があると、片方だけ直して食い違う。"""
    html = (pathlib.Path(__file__).resolve().parent.parent
            / "app" / "dj" / "stage.html").read_text(encoding="utf-8")
    import re
    m = re.search(r"const BURST_ON = ([0-9.]+)", html)
    assert m, "stage.html に BURST_ON が無い"
    assert float(m.group(1)) == BURST_ON
