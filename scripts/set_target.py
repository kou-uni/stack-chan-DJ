#!/usr/bin/env python3
"""実機の向き先（OTA と WebSocket の IP）を、設定画面なしで USB から書き換える。

    ./.venv/bin/python scripts/set_target.py <新しいIP>            # 実機に書く（退避→検算→置換→書き込み→読み戻し）
    ./.venv/bin/python scripts/set_target.py <新しいIP> --dry-run  # 読むだけ。何が何に変わるかを出す
    ./.venv/bin/python scripts/set_target.py <新しいIP> --file nvs.bin --out nvs_new.bin   # ファイルに対して（試験用）

★NVS 全体は消さない。Wi-Fi・画面・LED・音の設定はそのまま。書き換えるのは
  wifi/ota_url, websocket/url, websocket/fallback_url の3つの文字列の**ホスト部だけ**。
★退避は event/rec/nvs/ に置く（Wi-Fi のパスワードが入っているので git に入れない）。
★書く前に、書かれている全項目の CRC が合っていることを確かめる。1つでも合わなければ何もしない。
★esptool を使うので実機は再起動する。

NVS の形（ESP-IDF）: 4096B のページ = 32B ヘッダ + 32B 状態ビットマップ + 126 × 32B 項目。
文字列は「見出し項目（size, data crc）」＋続く項目に本体。CRC は crc32(0xFFFFFFFF 始まり)。
2026-09-29、MacBook 側が手作業でやった手順（issue #2）を、そのまま道具にした。
"""
from __future__ import annotations

import argparse
import re
import struct
import subprocess
import sys
import time
import zlib
from dataclasses import dataclass
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
NVS_OFFSET, NVS_SIZE = 0x9000, 0x6000
PAGE, ENTRY = 4096, 32
TYPE_SZ, TYPE_U8 = 0x21, 0x01
TARGET_KEYS = {("wifi", "ota_url"), ("websocket", "url"), ("websocket", "fallback_url")}
HOST_RE = re.compile(r"^(?P<scheme>[a-z]+://)(?P<host>[^/:]+)(?P<rest>(:\d+)?/.*)?$")
BACKUP_DIR = ROOT / "event" / "rec" / "nvs"


def crc32(data: bytes) -> int:
    return zlib.crc32(data, 0xFFFFFFFF) & 0xFFFFFFFF


def entry_crc(raw: bytes) -> int:
    """見出し項目の CRC。crc フィールド（4..8）を除いた 28 バイト。"""
    return crc32(raw[0:4] + raw[8:32])


@dataclass
class Item:
    page: int
    index: int          # ページ内の項目番号
    state: int          # 0b11 空 / 0b10 書かれている / 0b00 消された
    ns: int
    type: int
    span: int
    key: str
    raw: bytes          # 見出し 32B

    @property
    def offset(self) -> int:
        return self.page * PAGE + 64 + self.index * ENTRY

    @property
    def written(self) -> bool:
        return self.state == 0b10


def parse(img: bytes) -> list[Item]:
    items: list[Item] = []
    for p in range(len(img) // PAGE):
        base = p * PAGE
        bitmap = img[base + 32: base + 64]
        i = 0
        while i < 126:
            raw = img[base + 64 + i * ENTRY: base + 64 + (i + 1) * ENTRY]
            state = (bitmap[i // 4] >> ((i % 4) * 2)) & 0b11
            if state == 0b11:                       # 空
                i += 1; continue
            ns, typ, span = raw[0], raw[1], raw[2]
            key = raw[8:24].split(b"\0", 1)[0].decode("ascii", "replace")
            items.append(Item(p, i, state, ns, typ, span, key, raw))
            i += span if 1 <= span <= 126 - i else 1
    return items


def namespaces(items: list[Item]) -> dict[int, str]:
    return {it.raw[24]: it.key for it in items if it.written and it.ns == 0 and it.type == TYPE_U8}


def string_value(img: bytes, it: Item) -> bytes:
    size = struct.unpack_from("<H", it.raw, 24)[0]
    start = it.offset + ENTRY
    return img[start: start + size]


def verify_all(img: bytes, items: list[Item]) -> list[str]:
    """書かれている全項目の CRC を検算する。合わないものを返す（空なら健全）。"""
    bad = []
    for it in items:
        if not it.written:
            continue
        got = struct.unpack_from("<I", it.raw, 4)[0]
        if entry_crc(it.raw) != got:
            bad.append(f"p{it.page} e{it.index} {it.key}: 見出し CRC")
        if it.type == TYPE_SZ:
            want = struct.unpack_from("<I", it.raw, 28)[0]
            if crc32(string_value(img, it)) != want:
                bad.append(f"p{it.page} e{it.index} {it.key}: 本体 CRC")
    return bad


def targets(img: bytes, items: list[Item]) -> list[tuple[Item, str, str]]:
    """書き換え対象（項目, 名前空間, いまの値）。書かれているものだけ。"""
    ns = namespaces(items)
    out = []
    for it in items:
        if it.written and it.type == TYPE_SZ and (ns.get(it.ns, ""), it.key) in TARGET_KEYS:
            out.append((it, ns[it.ns], string_value(img, it).rstrip(b"\0").decode("utf-8", "replace")))
    return out


def replace_host(url: str, new_host: str) -> str:
    m = HOST_RE.match(url)
    if not m:
        return url                                   # 空や URL でないものは触らない
    return f"{m['scheme']}{new_host}{m['rest'] or ''}"


def rewrite(img: bytes, new_host: str) -> tuple[bytes, list[str]]:
    """新しい像と、変更の説明を返す。入らない・壊れている場合は例外。"""
    items = parse(img)
    bad = verify_all(img, items)
    if bad:
        raise ValueError("書き込む前の検算で CRC が合わない項目がある。何もしない:\n  " + "\n  ".join(bad))
    tg = targets(img, items)
    if not tg:
        raise ValueError("向き先の項目（wifi/ota_url, websocket/url）が見つからない")
    out = bytearray(img); notes = []
    for it, nsname, old in tg:
        new = replace_host(old, new_host)
        if new == old:
            notes.append(f"{nsname}/{it.key}: {old or '（空）'} のまま"); continue
        data = new.encode("utf-8") + b"\0"
        capacity = (it.span - 1) * ENTRY
        if len(data) > capacity:
            raise ValueError(f"{nsname}/{it.key}: 新しい値 {len(data)}B が枠 {capacity}B に入らない（{new}）")
        start = it.offset + ENTRY
        out[start: start + capacity] = data + b"\xff" * (capacity - len(data))
        head = bytearray(it.raw)
        struct.pack_into("<H", head, 24, len(data))
        struct.pack_into("<I", head, 28, crc32(data))
        struct.pack_into("<I", head, 4, entry_crc(bytes(head)))
        out[it.offset: it.offset + ENTRY] = head
        notes.append(f"{nsname}/{it.key}: {old} → {new}")
    new_img = bytes(out)
    bad = verify_all(new_img, parse(new_img))
    if bad:
        raise ValueError("書き換え後の検算で CRC が合わない。書き込まない:\n  " + "\n  ".join(bad))
    return new_img, notes


# ---- 実機 ---------------------------------------------------------------

def find_port() -> str | None:
    from serial.tools import list_ports
    for p in list_ports.comports():
        if p.vid == 0x303A and p.pid == 0x1001:
            return p.device
    return None


def esptool(*args: str) -> None:
    cmd = [sys.executable, "-m", "esptool", *args]
    r = subprocess.run(cmd, capture_output=True, text=True)
    if r.returncode != 0:
        raise RuntimeError("esptool が失敗:\n" + (r.stderr or r.stdout)[-800:])


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("host", help="新しい向き先の IP（MacBook がその網で持つ番地）")
    ap.add_argument("--dry-run", action="store_true", help="読んで、何が変わるかを出すだけ")
    ap.add_argument("--file", type=Path, help="実機ではなくこのファイル（NVS の像）に対して")
    ap.add_argument("--out", type=Path, help="--file のとき、書き出す先")
    ap.add_argument("--port")
    a = ap.parse_args()
    if not re.fullmatch(r"\d{1,3}(\.\d{1,3}){3}", a.host):
        print(f"★ IP の形ではない: {a.host}"); return 2

    if a.file:
        img = a.file.read_bytes()
    else:
        port = a.port or find_port()
        if not port:
            print("★ 実機の USB が見えません（上の箱の USB-C をデータ線で）"); return 1
        BACKUP_DIR.mkdir(parents=True, exist_ok=True)
        bk = BACKUP_DIR / f"nvs-{time.strftime('%Y%m%d-%H%M%S')}.bin"
        print(f"  読み出し → 退避 {bk.relative_to(ROOT)}（git に入らない場所）")
        esptool("--port", port, "read-flash", hex(NVS_OFFSET), hex(NVS_SIZE), str(bk))
        img = bk.read_bytes()

    try:
        new_img, notes = rewrite(img, a.host)
    except ValueError as exc:
        print(f"★ {exc}"); return 1
    for n in notes:
        print("  " + n)
    if all(n.endswith("のまま") for n in notes):
        print("  変えるものがありません"); return 0
    if a.dry_run:
        print("  （--dry-run なので書きません）"); return 0

    if a.file:
        out = a.out or a.file.with_name(a.file.stem + "_new.bin")
        out.write_bytes(new_img); print(f"  書き出し: {out}"); return 0

    tmp = BACKUP_DIR / "nvs-new.bin"; tmp.write_bytes(new_img)
    print("  書き込み中（実機は再起動します）")
    esptool("--port", port, "write-flash", hex(NVS_OFFSET), str(tmp))
    back = BACKUP_DIR / "nvs-readback.bin"
    esptool("--port", port, "read-flash", hex(NVS_OFFSET), hex(NVS_SIZE), str(back))
    if back.read_bytes() != new_img:
        print("★ 読み戻しが一致しない。退避から戻す: esptool write-flash 0x9000 " + str(bk)); return 1
    print(f"  ○ 読み戻し一致。実機は http://{a.host}:8778/ と ws://{a.host}:8775/ を見に来ます（30 秒待つ）")
    print("  戻すとき:  ./.venv/bin/python -m esptool write-flash 0x9000 " + str(bk.relative_to(ROOT)))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
