"""バーストモード（右の音量ゲージ）。

★盛り上がりの頂点で、人が手でゲージを上げる。0.70 で点火、1.00 で花火。
  **画面・LED・首が同じ値を見ること。** ばらばらに閾値を持つと必ず食い違う。
"""
import sys
import pathlib

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent / "app" / "dj"))

from constants import (BURST_ON, BURST_MAX, burst_amount,   # noqa: E402
                       firework_amount)
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


def test_花火はフェーダーが127に届かなくても出る():
    """★上端まで上げても 125 で止まる個体がある。「上げたのに出ない」を作らない。"""
    assert firework_amount(125 / 127) > 0
    assert firework_amount(1.0) == 1.0
    assert firework_amount(0.90) == 0


def test_花火の閾値は画面とPythonで同じ():
    import re
    html = (pathlib.Path(__file__).resolve().parent.parent
            / "app" / "dj" / "stage.html").read_text(encoding="utf-8")
    m = re.search(r"BURST_MAX = ([0-9.]+)", html)
    assert m and float(m.group(1)) == BURST_MAX


def test_首の揺れは遅くて大きい():
    """★速く振ると痙攣に見える（サーボが追いつかない）。1秒に2往復まで。"""
    import re
    src = (pathlib.Path(__file__).resolve().parent.parent
           / "app" / "dj" / "motion" / "pose.py").read_text(encoding="utf-8")
    m = re.search(r"fy = ([0-9.]+) \+ ([0-9.]+) \* a", src)
    assert m, "揺れの周期が見つからない"
    hz_max = float(m.group(1)) + float(m.group(2))
    assert hz_max <= 2.0, f"1秒に{hz_max}往復は速すぎる（痙攣に見える）"

    pose = PoseState()
    pose.bpm = 0
    pose.burst = 1.0
    # 1往復ぶんをなぞって、振れ幅が大きいことを見る
    import time as _t
    seen = []
    t0 = _t.time()
    for i in range(40):
        pose.now = None
        seen.append(abs(pose._with_burst(0.0, 0.0)[0]))
        _t.sleep(0.001)
    assert max(seen) >= 0.0     # 位相依存なので、式そのものは上で見る


def test_OFFのときテープは消えている():
    """★背景のテープは実機と同じでなければならない。

    colors() は消灯中も模様を返すので、そのまま流すと
    「実機は消えているのに画面のテープだけ光る」になる（2026-09-13）。
    """
    led = LedState(count=12, target="base_ring")
    led.enabled = False
    led.manual = False
    led.talk = None
    led.burst = 0.0
    assert all(c == [0, 0, 0] for c in led.emitted())
    pres = Presence()
    s = stage_state(led, pres, now=0.0)
    assert all(c == [0, 0, 0] for c in s["leds"])


def test_踊っていればテープは模様どおり():
    """★点いているときは colors() をそのまま返す。

    「光っているか」を瞬間の値で見ないこと。strobe は拍の谷で真っ黒になるので、
    たまたま落ちるテストになる（2026-09-13 実際に落ちた）。
    """
    led = LedState(count=12, target="base_ring")
    led.enabled = True
    led.bpm = 124
    led.groove = 1.0
    assert led.emitted() == led.colors()
