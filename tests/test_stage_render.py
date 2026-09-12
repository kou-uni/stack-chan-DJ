"""背景が本当に描けるかを、毎回確かめる。

## なぜ（2026-09-12 本人の指摘）

> **「サイトが見えない。真っ暗。検証していってるか？この指摘何回め？」**

`HTTP 200` だけ見て「動いた」と報告していた。**配れたことと、描けたことは別。**
実際には `stepHeads is not defined` で描画ループが即死していた。

★**目で見るしかない部分（きれいかどうか）と、機械で分かる部分（描けたか）を分ける。**
  描けたかは機械で分かる。人に「真っ暗だ」と言わせない。
"""
import json
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
CHECK = ROOT / "tests" / "js" / "render_check.js"
PAGE = ROOT / "app" / "dj" / "stage.html"

node = shutil.which("node") or str(Path.home() / ".local/bin/node")


@pytest.mark.skipif(not Path(node).exists(), reason="node が無い")
def test_背景が落ちずに描ける():
    r = subprocess.run([node, str(CHECK), str(PAGE)],
                       capture_output=True, text=True, timeout=90)
    assert r.returncode == 0, r.stdout + r.stderr


@pytest.mark.skipif(not Path(node).exists(), reason="node が無い")
def test_背景の幾何が壊れていない():
    """★目で見るだけでは幾何は守れない。

    遠近が線形に戻る／パネルの左右が非対称になる／灯体が増えすぎる、は
    どれも**画面を見ても気づきにくい**。数字で見張る。
    """
    r = subprocess.run([node, str(ROOT / "tests" / "js" / "geom_check.js"),
                        str(PAGE)], capture_output=True, text=True, timeout=60)
    assert r.returncode == 0, r.stdout + r.stderr


@pytest.mark.skipif(not Path(node).exists(), reason="node が無い")
def test_操作パネルも落ちない():
    """★パネルは <script> の中で DOM を触る。同じ穴を踏みうる。"""
    js = (ROOT / "app" / "dj" / "panel.html").read_text(encoding="utf-8")
    assert "<script>" in js
    r = subprocess.run([node, "--check", "/dev/stdin"],
                       input=js.split("<script>")[1].split("</script>")[0],
                       capture_output=True, text=True, timeout=30)
    assert r.returncode == 0, r.stderr
