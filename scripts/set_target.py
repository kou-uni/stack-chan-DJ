#!/usr/bin/env python3
"""実機の向き先（ota_url / websocket.url）を、USB からこの Mac の IP に書き換える。

    ./.venv/bin/python scripts/set_target.py            # いまの IP に向ける
    ./.venv/bin/python scripts/set_target.py 172.20.10.2
    ./.venv/bin/python scripts/set_target.py --show     # 向き先を見るだけ
    ./.venv/bin/python scripts/set_target.py --wifi 会場のSSID   # 会場の Wi-Fi も教える
    ./.venv/bin/python scripts/set_target.py --usb on     # USB ケーブルを有線 LAN にする（要 USB 版ファーム）

★会場で IP が変わったときの復旧用。**設定画面（タップ → 192.168.4.1）は要らない。**
  実機を USB で挿して、これ1本。

★NVS は消さない。Wi-Fi・画面・LED・音の設定はそのまま残す。
  生きている項目を全部読み、向き先2つだけ差し替えて、ページを詰め直して書く。
  書く前に「向き先2つ以外は1バイトも変わっていない」ことを突き合わせる。
  元の NVS は backup/ に退避する。

★シリアルを開くと実機は再起動する。書いた後も再起動する（それで新しい向き先に行く）。
"""
import argparse
import datetime
import glob
import struct
import subprocess
import sys
import tempfile
import zlib
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
ESPTOOL = str(ROOT / ".venv" / "bin" / "esptool")
PAGE, ENTRIES = 4096, 126
ACTIVE, FULL = 0xFFFFFFFE, 0xFFFFFFFC
TYPE_STR = 0x21
# (名前空間, キー) → 値の雛形
TARGETS = {("wifi", "ota_url"): "http://{ip}:8778/",
           ("websocket", "url"): "ws://{ip}:8775/"}


def crc(d: bytes) -> int:
    return zlib.crc32(bytes(d), 0xFFFFFFFF) & 0xFFFFFFFF


def die(msg: str) -> None:
    print(f"  × {msg}")
    print("ここで止めます。上の理由を直して、もう一度走らせてください。")
    sys.exit(1)


# ── NVS を読む ─────────────────────────────────
def parse(img: bytes):
    """生きている項目を、ページ順・書かれた順に返す。[(ns, type, key, entries_bytes)]"""
    pages = []
    for p in range(len(img) // PAGE):
        pg = img[p * PAGE:(p + 1) * PAGE]
        state, seq = struct.unpack("<II", pg[0:8])
        if state not in (ACTIVE, FULL):
            continue
        if struct.unpack("<I", pg[28:32])[0] != crc(pg[4:28]):
            die(f"NVS のページ{p}のヘッダが壊れています。書き換えません")
        pages.append((seq, pg))
    if not pages:
        die("NVS に中身がありません（消えている？）。設定画面から入れ直してください")
    items, version = [], pages[0][1][8]
    for _, pg in sorted(pages):
        bm = pg[32:64]
        st = [(bm[i // 4] >> ((i % 4) * 2)) & 3 for i in range(ENTRIES)]
        i = 0
        while i < ENTRIES:
            if st[i] != 2:
                i += 1
                continue
            e = pg[64 + i * 32:96 + i * 32]
            if struct.unpack("<I", e[4:8])[0] != crc(e[0:4] + e[8:32]):
                die(f"NVS の項目が壊れています（CRC 不一致）。書き換えません")
            span = e[2] if e[1] in (0x21, 0x41, 0x42) else 1
            items.append((e[0], e[1], e[8:24].split(b"\0")[0].decode(),
                          bytes(pg[64 + i * 32:64 + (i + span) * 32])))
            i += span
    return items, version


def namespaces(items) -> dict:
    return {k: e[24] for ns, t, k, e in items if ns == 0 and t == 0x01}


def read_str(entries: bytes) -> str:
    size = struct.unpack("<H", entries[24:26])[0]
    return entries[32:32 + size].rstrip(b"\0").decode()


def make_str(ns: int, key: str, value: str) -> bytes:
    data = value.encode() + b"\0"
    span = 1 + (len(data) + 31) // 32
    head = bytearray(b"\xff" * 32)
    head[0], head[1], head[2], head[3] = ns, TYPE_STR, span, 0xFF
    head[8:24] = key.encode().ljust(16, b"\0")
    head[24:32] = struct.pack("<HHI", len(data), 0xFFFF, crc(data))
    head[4:8] = struct.pack("<I", crc(head[0:4] + head[8:32]))
    return bytes(head) + data.ljust((span - 1) * 32, b"\xff")


# ── NVS を作り直す ─────────────────────────────
def build(items, version: int, size: int) -> bytes:
    """項目を先頭ページから詰める。最後のページは必ず空けておく（NVS の掃除用）"""
    img = bytearray(b"\xff" * size)
    npages, p, slot = size // PAGE, 0, 0
    used = [[] for _ in range(npages)]
    for it in items:
        span = len(it[3]) // 32
        if slot + span > ENTRIES:
            p, slot = p + 1, 0
        if p >= npages - 1:
            die("NVS に空きが足りません")
        used[p].append((slot, it[3]))
        slot += span
    last = max(i for i, u in enumerate(used) if u)
    for i in range(last + 1):
        pg = bytearray(b"\xff" * PAGE)
        hdr = bytearray(b"\xff" * 32)
        hdr[0:4] = struct.pack("<I", ACTIVE if i == last else FULL)
        hdr[4:8] = struct.pack("<I", i)
        hdr[8] = version
        hdr[28:32] = struct.pack("<I", crc(hdr[4:28]))
        pg[0:32] = hdr
        bm = bytearray(b"\xff" * 32)
        for slot, data in used[i]:
            pg[64 + slot * 32:64 + slot * 32 + len(data)] = data
            for j in range(slot, slot + len(data) // 32):
                bm[j // 4] &= ~(1 << ((j % 4) * 2)) & 0xFF   # 11 → 10 = 書いた
        pg[32:64] = bm
        img[i * PAGE:(i + 1) * PAGE] = pg
    return bytes(img)


def retarget(items, ip: str):
    nsid = namespaces(items)
    want = {(nsid[n], k): v.format(ip=ip) for (n, k), v in TARGETS.items() if n in nsid}
    if len(want) != len(TARGETS):
        die("NVS に wifi / websocket の名前空間がありません。設定画面から一度入れてください")
    out, seen = [], set()
    for ns, t, key, e in items:
        if (ns, key) in want:
            if t != TYPE_STR:
                die(f"{key} が文字列ではありません。書き換えません")
            out.append((ns, t, key, make_str(ns, key, want[(ns, key)])))
            seen.add((ns, key))
        else:
            out.append((ns, t, key, e))
    if seen != set(want):
        die("向き先の項目が NVS に見つかりません。設定画面から一度入れてください")
    return out


def targets_of(items) -> dict:
    nsid = namespaces(items)
    rev = {v: k for k, v in nsid.items()}
    return {f"{rev.get(ns)}.{key}": read_str(e) for ns, t, key, e in items
            if (rev.get(ns), key) in TARGETS}


WIFI_KEYS = {("wifi", f"{k}{i or ''}") for i in range(10) for k in ("ssid", "password")}


def add_wifi(items, ssid: str, password: str):
    """会場の Wi-Fi を足す。家の分は残す（ファームは見つかったものに繋ぐ）。
    ★ファームの形: wifi 名前空間に ssid/password、2件目から ssid1/password1 … 最大10件"""
    ns = namespaces(items)["wifi"]
    have = {k: read_str(e) for n, t, k, e in items if n == ns and ("wifi", k) in WIFI_KEYS}
    slots = [i for i in range(10) if f"ssid{i or ''}" in have]
    hit = [i for i in slots if have[f"ssid{i or ''}"] == ssid]
    i = hit[0] if hit else next((j for j in range(10) if j not in slots), None)
    if i is None:
        die("実機に保存できる Wi-Fi が10件埋まっています")
    want = {f"ssid{i or ''}": ssid, f"password{i or ''}": password}
    out = [(n, t, k, make_str(n, k, want.pop(k)) if n == ns and k in want else e)
           for n, t, k, e in items]
    out += [(ns, TYPE_STR, k, make_str(ns, k, v)) for k, v in want.items()]
    return out, i


def make_i32(ns: int, key: str, value: int) -> bytes:
    e = bytearray(b"\xff" * 32)
    e[0], e[1], e[2], e[3] = ns, 0x14, 1, 0xFF
    e[8:24] = key.encode().ljust(16, b"\0")
    e[24:28] = struct.pack("<i", value)
    e[4:8] = struct.pack("<I", crc(e[0:4] + e[8:32]))
    return bytes(e)


def make_ns(name: str, index: int) -> bytes:
    e = bytearray(b"\xff" * 32)
    e[0], e[1], e[2], e[3] = 0, 0x01, 1, 0xFF
    e[8:24] = name.encode().ljust(16, b"\0")
    e[24] = index
    e[4:8] = struct.pack("<I", crc(e[0:4] + e[8:32]))
    return bytes(e)


def set_usb(items, on: bool):
    """network.usb（USB を有線 LAN にする。ファームの usb_wired.h）を 1/0 にする"""
    nsid = namespaces(items)
    out = list(items)
    if "network" not in nsid:
        idx = max(nsid.values()) + 1
        out.append((0, 0x01, "network", make_ns("network", idx)))
        nsid["network"] = idx
    ns = nsid["network"]
    entry = make_i32(ns, "usb", 1 if on else 0)
    for i, (n, t, k, e) in enumerate(out):
        if n == ns and k == "usb":
            out[i] = (n, 0x14, k, entry)
            return out
    out.append((ns, 0x14, "usb", entry))
    return out


def usb_of(items):
    ns = namespaces(items).get("network")
    for n, t, k, e in items:
        if ns is not None and n == ns and k == "usb":
            return struct.unpack("<i", e[24:28])[0]
    return None


def same_except_targets(a, b) -> bool:
    rev = {v: k for k, v in {**namespaces(a), **namespaces(b)}.items()}
    allowed = set(TARGETS) | WIFI_KEYS | {("network", "usb"), (None, "network")}
    strip = lambda its: [(ns, t, k, e) for ns, t, k, e in its
                         if (rev.get(ns) if ns else None, k) not in allowed]
    return strip(a) == strip(b)


# ── 実機とのやりとり ───────────────────────────
def esptool(port: str, *args: str) -> None:
    r = subprocess.run([ESPTOOL, "--port", port, *args], capture_output=True, text=True)
    if r.returncode != 0:
        print(r.stdout[-800:], r.stderr[-800:])
        die(f"esptool が失敗しました（{' '.join(args[:1])}）")


def read(port: str, off: int, size: int) -> bytes:
    with tempfile.NamedTemporaryFile(suffix=".bin") as f:
        esptool(port, "read-flash", hex(off), hex(size), f.name)
        return Path(f.name).read_bytes()


def nvs_partition(port: str):
    pt = read(port, 0x8000, 0xC00)
    for i in range(0, len(pt), 32):
        e = pt[i:i + 32]
        if e[:2] == b"\xaa\x50" and e[2] == 1 and e[3] == 2:   # data / nvs
            return struct.unpack("<II", e[4:12])
    die("パーティション表に nvs が見つかりません")


def mac_ip() -> str:
    dev = subprocess.run("route -n get default 2>/dev/null | awk '/interface:/{print $2}'",
                         shell=True, capture_output=True, text=True).stdout.strip()
    if not dev:
        die("ネットワークに繋がっていません（既定の経路がない）")
    ip = subprocess.run(["ipconfig", "getifaddr", dev],
                        capture_output=True, text=True).stdout.strip()
    if not ip or ip.startswith("192.0.0."):
        die("この Mac に IPv4 がありません（Wi-Fi に繋がっていない / IPv6 だけのテザリング）")
    return ip


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("ip", nargs="?", help="向ける IP（省略時はこの Mac の IP）")
    ap.add_argument("--show", action="store_true", help="向き先を見るだけ")
    ap.add_argument("--force", action="store_true", help="同じでも書き直す")
    ap.add_argument("--usb", choices=["on", "off"], help="USB ケーブルを有線 LAN にする（on）／しない（off）")
    ap.add_argument("--wifi", metavar="SSID", help="会場の Wi-Fi を足す（家の分は残る）。パスワードは聞く")
    ap.add_argument("--port", help="シリアルポート（省略時は自動）")
    ap.add_argument("--image", help="実機の代わりに NVS のファイルで試す（書き込まない）")
    a = ap.parse_args()

    if a.image:
        port, img = None, Path(a.image).read_bytes()
    else:
        ports = [a.port] if a.port else sorted(glob.glob("/dev/cu.usbmodem*"))
        if not ports:
            die("実機が USB で見えません。USB-C で Mac に挿してください")
        port = ports[0]
        print(f"  ○ 実機  {port}（開くと再起動します）")
        off, size = nvs_partition(port)
        img = read(port, off, size)
    items, version = parse(img)
    now = targets_of(items)
    for k, v in now.items():
        print(f"    いまの {k:<14} {v}")
    print(f"    いまの {'network.usb':<14} {({1: 'on（USB を有線 LAN に）', 0: 'off'}).get(usb_of(items), '未設定（off）')}")
    if a.show:
        return 0

    ip = a.ip or mac_ip()
    print(f"  ○ 向ける先  {ip}")
    new_items = retarget(items, ip)
    if a.wifi:
        import getpass
        import os
        pw = os.environ.get("STACKCHAN_WIFI_PASSWORD") or getpass.getpass(f"    {a.wifi} のパスワード: ")
        if len(pw) < 8:
            die("パスワードが8文字未満です（WPA2 は8文字以上）")
        new_items, slot = add_wifi(new_items, a.wifi, pw)
        print(f"  ○ Wi-Fi  {a.wifi} を {slot + 1} 件目に入れます")
    if a.usb:
        new_items = set_usb(new_items, a.usb == "on")
        print(f"  ○ USB の有線 LAN  {a.usb}")
    if targets_of(new_items) == now and not a.force and not a.wifi and usb_of(new_items) == usb_of(items):
        print("  ○ もう向いています。何もしません")
        return 0
    if not same_except_targets(items, new_items):
        die("向き先以外が変わってしまう。書き換えません（バグ）")
    new = build(new_items, version, len(img))
    again, _ = parse(new)
    if again != new_items:
        die("作り直した NVS を読み直したら中身が違う。書き換えません（バグ）")

    if a.image:
        out = Path(a.image).with_suffix(".new.bin")
        out.write_bytes(new)
        print(f"  ○ 試し書き {out}")
        return 0

    bk = ROOT / "backup" / f"nvs-{datetime.datetime.now():%Y%m%d-%H%M%S}.bin"
    bk.parent.mkdir(exist_ok=True)
    bk.write_bytes(img)
    print(f"  ○ 退避  {bk.relative_to(ROOT)}")
    with tempfile.NamedTemporaryFile(suffix=".bin") as f:
        Path(f.name).write_bytes(new)
        esptool(port, "write-flash", hex(off), f.name)
    if read(port, off, size) != new:
        die(f"書いたものと読み戻したものが違います。退避から戻すには:\n"
            f"     {ESPTOOL} --port {port} write-flash {hex(off)} {bk}")
    for k, v in targets_of(parse(new)[0]).items():
        print(f"  ○ 書いた {k:<14} {v}")
    print("  実機が再起動します。30秒ほどで繋がるはず")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
