"""首の主導権が仕様どおりか。

★これは「リファクタで壊れていないこと」を守るための基準。
  実機がなくても走る。CI に載せられる。
"""
import sys, time
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "app" / "dj"))
from motion.arbiter import HeadArbiter, YAW_MIN, YAW_MAX, PITCH_OFFSET_MIN, PITCH_OFFSET_MAX


def test_優先順位はつまみが最上位():
    a = HeadArbiter(); a.dancing = True
    a.set_dance(10, 0); a.set_pose(-38, 0); a.set_knob(60, 10)
    assert a.owner == "knob" and a.angles() == (60, 10)


def test_つまみを離すと主導権が戻る():
    a = HeadArbiter(knob_hold_s=0.05); a.dancing = True
    a.set_dance(10, -3); a.set_knob(60, 10)
    assert a.owner == "knob"
    time.sleep(0.06)
    assert a.owner == "dance" and a.angles() == (10, -3)


def test_キメは踊りより強い():
    a = HeadArbiter(); a.dancing = True
    a.set_dance(10, 0); a.set_pose(-38, 2)
    assert a.owner == "pose" and a.angles() == (-38, 2)
    a.set_pose(None)
    assert a.owner == "dance"


def test_誰もいないときは送らない():
    """★送り続けると gateway 側の踊りを潰す。実際それで一度壊した。"""
    a = HeadArbiter()
    assert a.owner is None and a.should_emit() is False


def test_踊りを止めたら送らない():
    a = HeadArbiter(); a.set_dance(30, 0); a.dancing = False
    assert a.should_emit() is False


def test_範囲外は必ず丸める():
    """★pitch を絶対角度で送って 90→85 にクランプされ真下に張り付いた事故の再発防止。"""
    a = HeadArbiter(); a.dancing = True
    a.set_dance(999, 999)
    y, p = a.angles()
    assert (y, p) == (YAW_MAX, PITCH_OFFSET_MAX)
    a.set_dance(-999, -999)
    assert a.angles() == (YAW_MIN, PITCH_OFFSET_MIN)


def test_pitchは45からの差である():
    """gateway が pitch_center_deg(45) を足す。ここで返すのは差でなければならない。"""
    a = HeadArbiter(); a.dancing = True
    a.set_dance(0, 0)
    assert a.angles()[1] == 0            # 正面は 0（45ではない）
    assert PITCH_OFFSET_MAX <= 40        # 45+40=85 が実機の下限を超えない
