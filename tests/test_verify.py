"""--verify の判定。★実際に踏んだ事故を、そのまま入力として与える。"""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "app" / "dj"))
from verify import judge


def test_真下を向いていたら捕まえる():
    """2026-09-08 の事故。45 を送って gateway が 45 を足し、真下に張り付いた。"""
    bad = judge([10.0] * 20, [45.0] * 20)
    assert bad, "真下を見逃した。これを見逃すと同じ日をもう一度やることになる"
    assert any("端に張り付いて" in b for b in bad)


def test_可動範囲外の_yaw_を捕まえる():
    assert judge([999.0], [0.0])
    assert judge([-999.0], [0.0])


def test_可動範囲外の_pitch_を捕まえる():
    """★超えた分は gateway が黙って丸める。ログにも何も出ない。"""
    bad = judge([0.0], [49.8])          # sway が実際に返していた値
    assert any("可動範囲外" in b for b in bad)


def test_正常な値は通す():
    ys = [-38.0, -10.0, 0.0, 22.0, 38.0]
    ps = [-4.0, 0.0, 7.0, 14.0, 30.0]
    assert judge(ys, ps) == []


def test_境界ちょうどは通す():
    # ★pitch差 -34 → 絶対 11、+34 → 絶対 79。どちらも安全域の内側
    assert judge([-90.0, 90.0], [-34.0, 34.0]) == []


def test_上の端も捕まえる():
    """★向きが分からないので両端を守る（2026-09-12）。"""
    assert judge([0.0], [40.0]), "上の端を見逃した"


def test_フレームが無ければ問題なし():
    assert judge([], []) == []
