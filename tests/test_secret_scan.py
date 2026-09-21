"""公開前の秘密走査。**見つけられることと、誤検知しないことの両方**を見る。"""
import importlib.util
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
_spec = importlib.util.spec_from_file_location("secret_scan", ROOT / "scripts" / "secret_scan.py")
ss = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(ss)


@pytest.mark.parametrize("line", [
    "OPENAI_API_KEY = 'sk-abcdefghijklmnopqrstuvwxyz0123'",
    "token: ghp_0123456789012345678901234567890123456",
    "AKIA0123456789ABCDEF",
    "https://x.trycloudflare.com/panel?k=0123456789abcdef0123456789abcdef",
    "-----BEGIN PRIVATE KEY-----",
])
def test_見つける(tmp_path, line):
    """★形で探す。名前（API_KEY=）に頼ると、変数名を変えただけで抜ける。"""
    f = tmp_path / "a.py"
    f.write_text(line, encoding="utf-8")
    assert ss.scan([f]) != [], f"見逃した: {line}"


@pytest.mark.parametrize("line", [
    "TOKEN_PATH = Path.home() / '.config' / 'stackchan' / 'panel-token'",
    "鍵は ~/.config/stackchan/panel-token にあります",
    "url = 'http://127.0.0.1:8779/panel'",
    "sk = 'short'",
])
def test_誤検知しない(tmp_path, line):
    """★誤検知は、検査そのものを使われなくする。"""
    f = tmp_path / "a.py"
    f.write_text(line, encoding="utf-8")
    assert ss.scan([f]) == [], f"誤検知: {line}"


def test_ログの種類はそれだけで止める(tmp_path):
    """★いちばん危ないのは鍵ではなくログ。中身を読む前に止める。"""
    d = tmp_path / "acceptance-log"
    d.mkdir()
    f = d / "2026-09-28.jsonl"
    f.write_text('{"q": "こんにちは"}', encoding="utf-8")
    assert ss.scan([f]) != []


def test_このリポジトリ自身が綺麗である():
    """★これが赤くなったまま配らない。"""
    assert ss.scan(ss.tracked(staged=False)) == []
