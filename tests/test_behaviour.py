"""いまの振る舞いを数値で固定する（リファクタ前の基準）。

★これは「正しさ」ではなく「変わっていないこと」を守るテスト。
  Arbiter を差し込んだあとも同じ値が出れば、動作は落ちていない。
"""
import importlib.util, math, sys
from pathlib import Path
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "app" / "dj"))

spec = importlib.util.spec_from_file_location("console", ROOT / "app" / "dj" / "console.py")
console = importlib.util.module_from_spec(spec); spec.loader.exec_module(console)
PoseState, LedState = console.PoseState, console.LedState


def _pose(bpm=120.0, groove=1.0, sway=42.0, nod=9.0):
    p = PoseState(); p.bpm = bpm; p.beat0 = 0.0
    p.sway_deg, p.nod_deg = sway, nod
    p.groove = p._groove_now = groove
    return p


def test_全フレーズが可動範囲に収まる():
    """★どのフレーズでも yaw±90 / pitch差±40 を超えてはいけない。"""
    for ph in PoseState.PHRASES:
        p = _pose(); p._phrase = ph; p._phrase_end = 1e9; p._phrase_span = 8.0
        for i in range(200):
            p.beat0 = -i * 0.05
            y, d = p.dance_angles()
            assert -90 <= y <= 90, f"{ph}: yaw={y}"
            assert -40 <= d <= 40, f"{ph}: pitch差={d}"


def test_縦より横が大きい():
    """客は左右にいる。どのフレーズでも横の振れ幅が縦を上回ること。"""
    for ph in PoseState.PHRASES:
        p = _pose(); p._phrase = ph; p._phrase_end = 1e9; p._phrase_span = 8.0
        ys, ds = [], []
        for i in range(200):
            p.beat0 = -i * 0.05
            y, d = p.dance_angles(); ys.append(y); ds.append(d)
        assert max(ys) - min(ys) >= max(ds) - min(ds), f"{ph} は縦の方が大きい"


def test_ノリが0なら動かない():
    p = _pose(groove=0.0)
    assert p.dance_angles() == (0.0, 0.0)


def test_ノリが大きいほど振り幅も大きい():
    amp = []
    for g in (0.3, 0.6, 1.0):
        p = _pose(groove=g); p._phrase = "sway"; p._phrase_end = 1e9; p._phrase_span = 8.0
        ys = []
        for i in range(80):
            p.beat0 = -i * 0.05
            ys.append(p.dance_angles()[0])
        amp.append(max(ys) - min(ys))
    assert amp[0] < amp[1] < amp[2], f"単調増加でない: {amp}"


def test_助走は目標へ滑らかに寄る():
    p = _pose(groove=1.0); p._groove_now = 0.0
    p.ramp_per_s = 1.0 / 1.2
    for _ in range(20):
        p.step_groove(0.05)
    assert 0.5 < p._groove_now < 0.95, f"1秒後に {p._groove_now}"


def test_LEDは常に12色を返す():
    for pat in LedState.PATTERNS:
        led = LedState(pattern=pat); led.bpm = 120; led.beat0 = 0.0; led.enabled = True
        cols = json_colors(led)
        assert len(cols) == 12, f"{pat}: {len(cols)}色"
        for c in cols:
            assert len(c) == 3 and all(0 <= v <= 255 for v in c), f"{pat}: {c}"


def json_colors(led):
    import json
    return json.loads(led.frame())["colors"]


def test_LEDは消えているとき全部黒():
    led = LedState(); led.enabled = False
    assert all(c == [0, 0, 0] for c in json_colors(led))


def test_ノリが小さいとLEDも暗い():
    bright = []
    for g in (0.2, 1.0):
        led = LedState(pattern="wave", max_brightness=1.0)
        led.bpm = 120; led.beat0 = 0.0; led.enabled = True; led.groove = g
        bright.append(max(max(c) for c in json_colors(led)))
    assert bright[0] < bright[1], f"暗くなっていない: {bright}"
