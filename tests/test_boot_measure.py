"""起動計測（scripts/boot_measure.py）の読み取りが、実機ログの形で壊れないこと。"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
import boot_measure as bm  # noqa: E402

LOG = """
I (5123) wifi:pm start, type: 1
I (11880) wifi:connected with home-2g, aid = 3, channel 6
I (12940) wifi:Got IP: 192.168.0.200
I (14090) Ota: Current is the latest version
I (14560) WS: Connected to websocket server
I (17750) Application: set_avatar: face=idle applied=1
I (17900) Application: set_avatar: face=idle applied=1
""".strip().splitlines()


def test_parse_reads_first_match_and_powersave():
    r = bm.parse(LOG)
    assert r["wifi"] == 11.88 and r["ip"] == 12.94 and r["ota"] == 14.09
    assert r["ws"] == 14.56 and r["face"] == 17.75          # 2行目の顔は取らない
    assert r["pm"] == "MIN_MODEM"


def test_parse_powersave_type_0_is_none_and_missing_is_unknown():
    r = bm.parse(["I (11985) wifi:pm start, type: 0"] + LOG[1:])
    assert r["pm"] == "none"                                 # 新ファーム（WIFI_PS_NONE）の出方
    assert bm.parse([l for l in LOG if "pm start" not in l])["pm"] == "unknown"


def test_parse_tolerates_missing_marks():
    r = bm.parse(LOG[:2])
    assert "face" not in r and "ota" not in r and r["wifi"] == 11.88
    assert "--" in bm.show(r)                                # 欠けは -- で出る。落ちない


def test_parse_strips_ansi_via_one_boot_path():
    assert bm.ANSI.sub("", "\x1b[0;32mI (1) x\x1b[0m") == "I (1) x"
