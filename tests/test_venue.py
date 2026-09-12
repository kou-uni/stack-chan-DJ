"""会場で動くこと。★家と会場でネットワークが違う。

会場の条件（docs/requirements.md）:
  - 会場Wi-Fiに繋がない。**iPhone のテザリング**
  - 母艦は **MacBook**（家は Mac Studio）
  - つまり **IP も機械名も変わる**

★変わらないものを1つ作って、そこに全部ぶら下げる。
"""
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "app" / "dj"))


def _src(name):
    return (ROOT / "app" / "dj" / name).read_text(encoding="utf-8")


def test_画面サーバは実機を待つ前に立つ():
    """★会場では、ロボットの電源より先に画面を出したい。

    実機待ちのあとに置くと、ロボットを繋ぐまで iPad が真っ暗になる。
    設営中こそ画面が出ていてほしい。
    """
    s = _src("console.py")
    i_stage = s.index("run_stage(")
    i_wait = s.index("await wait_for_device(")
    assert i_stage < i_wait, "画面サーバが実機待ちより後ろにある"


def test_URLは機械名に依存しない():
    """★家は Mac Studio、会場は MacBook。機械名を URL に使わない。"""
    s = _src("stage.py")
    assert "STAGE_HOST" in s, "固定の名前が定義されていない"
    from stage import STAGE_HOST
    assert STAGE_HOST.endswith(".local"), STAGE_HOST
    assert "mac" not in STAGE_HOST.lower() and "studio" not in STAGE_HOST.lower()


def test_名前をmDNSで配る仕組みがある():
    """★IP は毎回変わる。名前で引けるようにする。"""
    s = _src("stage.py")
    assert "zeroconf" in s.lower(), "mDNS で名乗る仕組みが無い"
    assert "async def advertise" in s or "def advertise" in s


def test_IPが変わったら名乗り直す():
    """★家 → テザリング で IP が変わる。名乗ったままだと引けなくなる。"""
    s = _src("stage.py")
    assert "def watch_network" in s, "ネットワークの変化を見ていない"


def test_全ての口を0000で開く():
    """★127.0.0.1 で開くと、iPad から届かない。"""
    s = _src("console.py")
    i = s.index("run_stage(")
    assert '"0.0.0.0"' in s[i:i + 120], "外から届かない口の開き方をしている"


def test_会場の手順が書いてある():
    doc = (ROOT / "docs" / "runbook.md").read_text(encoding="utf-8")
    assert "テザリング" in doc, "会場の手順が runbook に無い"
    assert "stackchan.local" in doc, "iPad で開く名前が書かれていない"
