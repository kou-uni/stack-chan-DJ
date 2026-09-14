"""受け入れテストの読み上げ台本。

★台本を2箇所に書かない。`event/acceptance.md` の表をそのまま読む。
  表の形が変わると黙って項目が落ちるので、ここで見張る（2026-09-15）。
"""
import importlib.util
import pathlib
import sys

ROOT = pathlib.Path(__file__).resolve().parents[1]
_spec = importlib.util.spec_from_file_location("acc", ROOT / "scripts" / "acceptance.py")
acc = importlib.util.module_from_spec(_spec)
sys.modules["acc"] = acc
_spec.loader.exec_module(acc)

ITEMS = acc.load_items(ROOT / "event" / "acceptance.md")


def test_全部のブロックが拾えている():
    """★E・F の表だけ列が3つで、黙って落ちていた（2026-09-15）。"""
    blocks = {i["id"].split("-")[0] for i in ITEMS}
    assert blocks == {"0", "A", "B", "C", "D", "E", "F"}, sorted(blocks)


def test_項目が減っていない():
    assert len(ITEMS) >= 28, len(ITEMS)


def test_読み上げ文に記号が混ざらない():
    """★★ や ` をそのまま読ませない。**耳で聞くものなので。**"""
    for i in ITEMS:
        line = acc.line_for(i)
        for bad in ("**", "`", "★", "⚠️", "|"):
            assert bad not in line, (i["id"], bad, line)


def test_読み上げ文が長すぎない():
    """★長い読み上げは聞けない。**やることと合格だけ。**"""
    for i in ITEMS:
        assert len(acc.line_for(i)) <= 120, (i["id"], acc.line_for(i))


def test_重要な項目に代替がある():
    """★落ちたら当日が無いものは、**代替を先に決めてある**こと。"""
    for i in ITEMS:
        if i["critical"]:
            assert i["alt"] and i["alt"] != "—", i["id"]


def test_IDが重複しない():
    ids = [i["id"] for i in ITEMS]
    assert len(ids) == len(set(ids)), [x for x in ids if ids.count(x) > 1]
