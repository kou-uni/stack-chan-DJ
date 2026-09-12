#!/usr/bin/env python3
"""どちらの app から起動するかを切り替える。

    ./.venv/bin/python scripts/ota_select.py 1     # ota_1 から起動
    ./.venv/bin/python scripts/ota_select.py 0     # ota_0 に戻す

★app は上書きしない。**切り替えるだけなので、いつでも戻せる。**
★crc の計算式は変種が多い。実機の entry0 で検算した式を使っている。
"""
import struct
import subprocess
import sys
import tempfile
import zlib
from pathlib import Path

PORT = "/dev/cu.usbmodem201101"
OTADATA_ENTRY1 = 0xE000        # entry0(0xd000) は触らない。戻り先として残す


def main(slot: int) -> int:
    if slot not in (0, 1):
        print("スロットは 0 か 1"); return 2
    with tempfile.NamedTemporaryFile(suffix=".bin", delete=False) as f:
        if slot == 0:
            # ★entry1 を消すと entry0 の seq=1 が最大になり ota_0 に戻る
            f.write(b"\xff" * 4096)
            what = "ota_0（entry1 を消す）"
        else:
            seq = 2                                   # (2-1) % 2 = 1
            raw = struct.pack("<I", seq)
            crc = zlib.crc32(raw, 0xFFFFFFFF) & 0xFFFFFFFF
            f.write(raw + b"\xff" * 20 + struct.pack("<II", 2, crc)
                    + b"\xff" * (4096 - 32))
            what = f"ota_1（seq={seq} state=VALID crc={crc:#010x}）"
        path = f.name
    print(f"  → {what}")
    r = subprocess.run([sys.executable, "-m", "esptool", "--port", PORT,
                        "--baud", "921600", "write-flash",
                        hex(OTADATA_ENTRY1), path])
    Path(path).unlink(missing_ok=True)
    return r.returncode


if __name__ == "__main__":
    raise SystemExit(main(int(sys.argv[1]) if len(sys.argv) > 1 else -1))
