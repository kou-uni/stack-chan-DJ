"""DJの右レコード（ジョグ）でスポットライトを振る仕様。

## なぜ（2026-09-12 本人の要望）

> **「スポットライトは、DJの右レコードのチュクチュクの動きに合わせて若干左右する
> ようにしたい（触ってない時はランダムに戻る）」**

★演者の手の動きが、そのまま照明になる。**触っていないときは自動に返す。**
  ずっと手で持っていないと動かない照明は、演奏の邪魔になる。

## 実測（2026-09-12）

右ジョグは ch1 CC#34。**中心64の相対値**（63〜66 が来る）。
回した向きと速さが差分で分かる。**絶対位置ではない。**
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "app" / "dj"))
from jog import Jog   # noqa: E402


def test_中心では動かない():
    j = Jog()
    j.feed(64, now=0.0)
    assert j.value(now=0.0) == 0.0


def test_回すと振れる():
    j = Jog()
    for _ in range(20):
        j.feed(66, now=0.0)
    assert j.value(now=0.0) > 0.2


def test_逆に回すと逆に振れる():
    j = Jog()
    for _ in range(20):
        j.feed(62, now=0.0)
    assert j.value(now=0.0) < -0.2


def test_振り切れない():
    """★可動域を超えない。振り切れると、ただ端で止まって見える。"""
    j = Jog()
    for _ in range(500):
        j.feed(70, now=0.0)
    assert -1.0 <= j.value(now=0.0) <= 1.0


def test_手を止めればすぐ中心へ戻る():
    """★位置ではなく速度。**止めた瞬間に照明も止まる。**"""
    j = Jog()
    for i in range(20):
        j.feed(66, now=i*0.005)
    assert abs(j.value(now=0.1)) > 0.2
    assert abs(j.value(now=0.45)) < 0.05, "止めたのに振れたまま"


def test_往復すれば照明も往復する():
    """★チュクチュクに追従する。**片側に張り付かない。**"""
    j = Jog()
    t = 0.0
    for _ in range(8):
        j.feed(67, now=t); t += 0.01
    a = j.value(now=t)
    for _ in range(8):
        j.feed(61, now=t); t += 0.01
    b = j.value(now=t)
    assert a > 0.1 and b < -0.1, (a, b)


def test_触っていなければ自動に返る():
    """★ずっと手で持っていないと動かない照明は、演奏の邪魔になる。"""
    j = Jog()
    for _ in range(20):
        j.feed(66, now=0.0)
    assert j.weight(now=0.1) > 0.8, "触った直後は手が勝つ"
    assert j.weight(now=3.0) < 0.05, "離しても自動に戻っていない"


def test_離すと中心へ戻る():
    j = Jog()
    for _ in range(20):
        j.feed(66, now=0.0)
    big = abs(j.value(now=0.0))
    assert abs(j.value(now=2.5)) < big * 0.5, "戻っていない"


def test_跳ねる値を無視する():
    """★64をまたぐ大きな飛びは、回り込み（127→0）。**速度として数えない。**"""
    j = Jog()
    j.feed(64, now=0.0)
    j.feed(127, now=0.0)
    j.feed(0, now=0.0)
    assert abs(j.value(now=0.0)) < 0.2


# ── 静止中もゆらぐ（2026-09-12 実測）────────────────
#
# 触っていないのに **63 と 65 が毎秒190回**流れてくる（エンコーダのゆらぎ）。
# 1つずつ足していたので、**触っていないのに勝手に振れて、戻らなくなった。**
#
# ★行ったり来たりは動きではない。**短い窓の「正味」で見る。**

def test_ゆらぎでは動かない():
    j = Jog()
    for i in range(400):                       # 63/65 が交互に来る
        j.feed(63 if i % 2 else 65, now=i*0.005)
    assert abs(j.value(now=2.0)) < 0.05, "ゆらぎで振れている"
    assert j.weight(now=2.0) < 0.05, "触っていないのに手が勝っている"


def test_本当に回せば動く():
    j = Jog()
    for i in range(40):                        # 一方向に回す
        j.feed(66, now=i*0.005)
    assert j.value(now=0.2) > 0.15


def test_ゆらぎの中でも回せば拾う():
    j = Jog()
    t = 0.0
    for i in range(200):
        j.feed(66 if i % 3 else 63, now=t); t += 0.005
    assert j.value(now=t) > 0.1
