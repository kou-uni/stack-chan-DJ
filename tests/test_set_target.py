"""向き先の書き換え（scripts/set_target.py）。実機の NVS から取った本物の項目で検算する。"""
import base64
import struct
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
import set_target as st  # noqa: E402

# 2026-09-12 の実機 NVS から（ESP-IDF の nvs_tool が出した raw）。秘密は含まない
OTA_HEAD = base64.b64decode("AyEC/9wRCrRvdGFfdXJsAAAAAAAAAAAAGwD//yZO1mU=")
OTA_BODY = base64.b64decode("aHR0cDovLzE5Mi4xNjguMC4xMjM6ODc3OC8A//////8=")
WS_HEAD = base64.b64decode("BCEC/4LVt7h1cmwAAAAAAAAAAAAAAAAAGQD//w/z/Bc=")
WS_BODY = base64.b64decode("d3M6Ly8xOTIuMTY4LjAuMTIzOjg3NzUvAP////////8=")
FB_HEAD = base64.b64decode("BCEC/zEwD2dmYWxsYmFja191cmwAAAAAAQD///////8=")
FB_BODY = base64.b64decode("AP////////////////////////////////////////8=")


def ns_entry(name: str, idx: int) -> bytes:
    raw = bytearray(b"\xff" * 32)
    raw[0], raw[1], raw[2], raw[3] = 0, st.TYPE_U8, 1, 0xFF
    raw[8:24] = name.encode().ljust(16, b"\0")
    raw[24] = idx; raw[25:32] = b"\0" * 7
    struct.pack_into("<I", raw, 4, st.entry_crc(bytes(raw)))
    return bytes(raw)


def make_image(entries: list[bytes], states: list[int] | None = None) -> bytes:
    """1ページの NVS 像。states は項目ごとの状態（既定は全部「書かれている」）。"""
    page = bytearray(b"\xff" * st.PAGE)
    page[0:4] = b"\xfc\xff\xff\xff"                     # 状態 FULL 相当（ヘッダの中身は今回触らない）
    n = len(entries); states = states or [0b10] * n
    bitmap = bytearray(b"\xff" * 32)
    for i, s in enumerate(states):
        bitmap[i // 4] &= ~(0b11 << ((i % 4) * 2)) & 0xFF
        bitmap[i // 4] |= s << ((i % 4) * 2)
    page[32:64] = bitmap
    page[64:64 + 32 * n] = b"".join(entries)
    return bytes(page) + b"\xff" * (st.PAGE * 5)


BASE = [ns_entry("wifi", 3), OTA_HEAD, OTA_BODY, ns_entry("websocket", 4), WS_HEAD, WS_BODY, FB_HEAD, FB_BODY]


def test_crc_formula_matches_the_real_device():
    assert st.entry_crc(OTA_HEAD) == struct.unpack_from("<I", OTA_HEAD, 4)[0] == 0xB40A11DC
    assert st.crc32(OTA_BODY[:27]) == struct.unpack_from("<I", OTA_HEAD, 28)[0]
    assert st.entry_crc(WS_HEAD) == struct.unpack_from("<I", WS_HEAD, 4)[0]
    assert st.crc32(WS_BODY[:25]) == struct.unpack_from("<I", WS_HEAD, 28)[0]


def test_reads_the_two_targets_and_leaves_empty_fallback():
    img = make_image(BASE)
    items = st.parse(img)
    assert st.verify_all(img, items) == []
    vals = {(ns, it.key): v for it, ns, v in st.targets(img, items)}
    assert vals == {("wifi", "ota_url"): "http://192.168.0.123:8778/",
                    ("websocket", "url"): "ws://192.168.0.123:8775/",
                    ("websocket", "fallback_url"): ""}


def test_rewrite_to_a_shorter_ip_updates_size_and_crcs():
    img = make_image(BASE)
    new, notes = st.rewrite(img, "192.168.2.1")
    items = st.parse(new)
    assert st.verify_all(new, items) == []                        # 検算が通る（見出しも本体も）
    vals = {(ns, it.key): v for it, ns, v in st.targets(new, items)}
    assert vals[("wifi", "ota_url")] == "http://192.168.2.1:8778/"
    assert vals[("websocket", "url")] == "ws://192.168.2.1:8775/"
    assert vals[("websocket", "fallback_url")] == ""              # 空は空のまま
    assert any("のまま" in n for n in notes) and sum("→" in n for n in notes) == 2
    ota = next(it for it, ns, _ in st.targets(new, items) if it.key == "ota_url")
    assert struct.unpack_from("<H", ota.raw, 24)[0] == len("http://192.168.2.1:8778/") + 1
    body = new[ota.offset + 32: ota.offset + 64]
    assert body[len("http://192.168.2.1:8778/")] == 0 and body[-1] == 0xFF     # NUL 終端、余りは 0xFF
    # 触っていない項目はバイト単位で同じ
    assert new[:64 + 32] == img[:64 + 32]


def test_rewrite_to_a_longer_ip_fits_in_the_same_span():
    img = make_image(BASE)
    new, _ = st.rewrite(img, "172.20.10.14")
    vals = {(ns, it.key): v for it, ns, v in st.targets(new, st.parse(new))}
    assert vals[("websocket", "url")] == "ws://172.20.10.14:8775/"


def test_refuses_when_a_crc_is_already_broken():
    img = bytearray(make_image(BASE))
    img[64 + 32 * 2 + 3] ^= 0x01                                  # ota_url 本体を1ビット壊す
    with pytest.raises(ValueError, match="CRC"):
        st.rewrite(bytes(img), "192.168.2.1")


def test_erased_duplicates_are_not_touched():
    old_ws = [WS_HEAD, WS_BODY]
    img = make_image(BASE + old_ws, [0b10] * len(BASE) + [0b00, 0b00])
    new, notes = st.rewrite(img, "192.168.2.1")
    off = 64 + 32 * len(BASE)
    assert new[off: off + 64] == WS_HEAD + WS_BODY               # 消された古い項目はそのまま
    assert sum("→" in n for n in notes) == 2


def test_replace_host_keeps_scheme_port_and_path():
    assert st.replace_host("ws://192.168.0.123:8775/", "10.0.0.5") == "ws://10.0.0.5:8775/"
    assert st.replace_host("http://a.example.com/x/y", "10.0.0.5") == "http://10.0.0.5/x/y"
    assert st.replace_host("", "10.0.0.5") == ""
