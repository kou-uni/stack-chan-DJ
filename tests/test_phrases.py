"""振り付けの契約。実機なしで全フレーズ・全時刻を検証する。"""
import math, sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "app" / "dj"))
from motion import phrases as P


def sweep(ph, sway=42.0, nod=9.0, n=400):
    """1フレーズを細かく走査して (yaw列, pitch列) を返す。"""
    ys, ds = [], []
    for i in range(n):
        t = i * 0.05
        y, d = P.angles(ph, t, (i % 160) / 160, sway, nod)
        ys.append(y); ds.append(d)
    return ys, ds


def test_全フレーズが可動範囲に収まる():
    for ph in P.PHRASES:
        ys, ds = sweep(ph)
        assert max(map(abs, ys)) <= P.YAW_LIM, ph
        assert max(map(abs, ds)) <= P.PITCH_LIM, ph


def test_全フレーズで横が動く():
    """★客は左右にいる。どのフレーズでも横が止まってはいけない。"""
    for ph in P.PHRASES:
        ys, _ = sweep(ph)
        assert max(ys) - min(ys) >= 10, f"{ph} は横がほぼ止まっている"


def test_縦は横より小さい():
    for ph in P.PHRASES:
        ys, ds = sweep(ph)
        assert (max(ds) - min(ds)) <= (max(ys) - min(ys)), f"{ph} は縦が大きすぎる"


def test_頷き系は下向きに深く入る():
    """うんうん＝下方向。上に振れても頷きには見えない。"""
    for ph in ("nod2", "yes"):
        _, ds = sweep(ph)
        assert max(ds) >= 25, f"{ph} の頷きが浅い（{max(ds):.0f}°）"


def test_頷きは鋭い():
    """sin の緩やかな波では頷きに見えない。下がっている時間が短いこと。"""
    _, ds = sweep("nod2", n=200)
    deep = sum(1 for d in ds if d > 10)
    assert deep / len(ds) < 0.4, "下がっている時間が長すぎる＝鈍い"


def test_片側を向くフレーズは実際に片側へ寄る():
    yl, _ = sweep("point_l"); yr, _ = sweep("point_r")
    assert sum(yl) / len(yl) < -10, "point_l が左に寄っていない"
    assert sum(yr) / len(yr) > 10, "point_r が右に寄っていない"


def test_scanは端から端まで動く():
    ys, _ = sweep("scan")
    assert max(ys) - min(ys) >= 60, "見渡す幅が狭い"


def test_同じフレーズが連続しない():
    prev = "sway"
    for n in range(50):
        cur = P.pick(n, 120.0, prev)
        assert cur != prev
        prev = cur


def test_フレーズの長さが一定でない():
    lens = {P.phrase_len(n) for n in range(20)}
    assert len(lens) >= 3, "長さが一定だと変化が規則になる"


def test_ノリが小さいと振り幅も小さい():
    big = sweep("sway", sway=42.0)[0]
    small = sweep("sway", sway=10.0)[0]
    assert max(big) - min(big) > max(small) - min(small)
