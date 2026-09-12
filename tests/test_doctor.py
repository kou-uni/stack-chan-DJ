"""健康診断の作法。★入口が増えても中身が1つであること。"""
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "app" / "dj"))
import doctor  # noqa: E402


def test_直したものは直ったと表示される():
    """★×のまま残すと『まだ壊れている』に見える。当日それで混乱する。"""
    c = doctor.Check("なにか", doctor.NG, "壊れている")
    c.repair("直した")
    assert c.state == doctor.FIXED
    assert doctor.MARK[c.state] == "✓"


def test_全部直れば終了コードは0():
    r = doctor.Report()
    r.add("A", doctor.NG, "壊れている").repair("直した")
    r.add("B", doctor.OK, "問題なし")
    assert r.worst == doctor.OK
    assert r.repaired == 1


def test_直っていなければ終了コードは1():
    r = doctor.Report()
    r.add("A", doctor.NG, "壊れている")
    assert r.worst == doctor.NG


def test_警告は正常より重く_異常より軽い():
    r = doctor.Report()
    r.add("A", doctor.OK, ""); r.add("B", doctor.WARN, "")
    assert r.worst == doctor.WARN


def test_日本語の桁幅を2で数える():
    """★文字数で揃えると桁がずれる。読めない表は読まれない。"""
    assert doctor._width("実機") == 4
    assert doctor._width("gateway") == 7
    assert doctor._width("pose ストリーム") == 4 + 1 + 10   # 半角4 空白1 全角5文字
    assert len(doctor._pad("実機", 10)) == 2 + 6


def test_点検だけのときは表情で警告を出さない():
    """★毎回出る警告は、いずれ誰も読まなくなる。"""
    src = (ROOT / "app" / "dj" / "doctor.py").read_text(encoding="utf-8")
    i = src.index("# 表情は「入っているか」")
    tail = src[i:src.index("except Exception", i)]   # ★ i 以降で探す。手前にも同じ語がある
    assert "r.note" in tail, "点検時は検査項目ではなく補足として出す"
    assert "WARN" not in tail


def test_中身は入口から独立している():
    """★あとでスマホ・撫でる操作からも同じ run() を呼ぶ。"""
    import inspect
    src = inspect.getsource(doctor.run)
    for ui in ("argparse", "input(", "sys.argv"):
        assert ui not in src, f"中身に入口の都合（{ui}）を持ち込まない"
    assert "print(" not in src, "表示は show() の仕事。run() は結果を返すだけ"


def test_診断は勝手に踊らせない():
    """2026-09-09 の事故。

    ★`beat_mode_start` は gateway 側の踊りを**有効にして**始まる。
      モードを持っているのは console。診断ツールがそれを飛び越えると、
      OFF のはずなのに音へ反応し続け、**誰も止める人が居なくなる。**
    """
    src = (ROOT / "app" / "dj" / "doctor.py").read_text(encoding="utf-8")
    i = src.index('gw.call("beat_mode_start"')
    j = src.index("c.repair(", i)
    assert 'beat_mode_update' in src[i:j], \
        "beat_mode_start のあとに motion を切らないと、OFF のまま踊り続ける"
    assert "motion_enabled=False" in src[i:j]
