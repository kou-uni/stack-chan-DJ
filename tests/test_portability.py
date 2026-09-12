"""どの Mac でも動くこと。

★2026-09-09、目の前の Mac Studio だけを見て作っていて、
  MacBook で動かす前提（設計にあった）を丸ごと忘れた。
  **自分の機械でだけ動くものは、作ったうちに入らない。**

当日の構成:
    自宅  gateway + console = Mac Studio
    会場  gateway + console = MacBook   ← DJ機材が USB なので必然
    実機はどちらを見るかを mDNS で決める（本体に触らず切り替わる）
"""
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

# その機械にしか無いもの。設定ファイル以外に書いてはいけない。
MACHINE_SPECIFIC = re.compile(
    r"/Users/[a-z]+/|192\.168\.\d+\.\d+|/dev/cu\.usbmodem\d+|\ben[0-9]\b")

# 調べる対象。ドキュメントと設定は対象外（そこには書いてよい）
TARGETS = ([p for p in (ROOT / "app").rglob("*.py")]
           + [p for p in (ROOT / "scripts").glob("*.sh")]
           + [p for p in (ROOT / "scripts").glob("*.py")])


def _code_lines(path: Path):
    """コメントと文字列の説明を除いた、実際に効く行。"""
    for i, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
        s = line.strip()
        if not s or s.startswith(("#", "//", '"""', "*", "★")):
            continue
        yield i, line


def test_特定の機械に縛られた値がコードに無い():
    bad = []
    for p in TARGETS:
        for i, line in _code_lines(p):
            m = MACHINE_SPECIFIC.search(line)
            if m:
                bad.append(f"{p.relative_to(ROOT)}:{i}  {m.group()}")
    assert not bad, (
        "その機械にしか無い値がコードに埋まっている:\n  " + "\n  ".join(bad)
        + "\n\n→ config.toml か .env.gateway に出すこと。MacBook で動かなくなる")


def test_依存を書いたファイルがある():
    """★これが無いと、別の Mac で環境を再現できない。"""
    req = ROOT / "requirements.txt"
    assert req.exists(), "requirements.txt が無い"
    body = req.read_text(encoding="utf-8")
    for pkg in ("mcp", "mido", "websockets", "numpy", "opencv", "pyserial"):
        assert re.search(rf"^{pkg}", body, re.M | re.I), f"{pkg} が requirements.txt に無い"


def test_一から立ち上げる手順が1本ある():
    s = (ROOT / "scripts" / "setup.sh")
    assert s.exists(), "別の Mac で立ち上げる手順が無い"
    body = s.read_text(encoding="utf-8")
    assert "venv" in body and "requirements" in body
    assert "pytest" in body, "立ち上げたら試験を通すところまでやること"


def test_常駐の設定は実行時にパスを埋める():
    """★plist に自分の家のパスを固定で書くと、別の Mac で動かない。"""
    body = (ROOT / "scripts" / "service.sh").read_text(encoding="utf-8")
    assert 'ROOT="$(cd "$(dirname "$0")/.." && pwd)"' in body
    assert "${ROOT}" in body, "plist に絶対パスを実行時に埋めていない"


def test_設計文書に2台構成が書いてある():
    doc = (ROOT / "docs" / "architecture.md").read_text(encoding="utf-8")
    assert "MacBook" in doc, "当日の配置（どの Mac が何を動かすか）が設計文書に無い"
    assert "mDNS" in doc
