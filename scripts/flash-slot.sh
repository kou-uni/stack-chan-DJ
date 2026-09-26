#!/usr/bin/env bash
# 新しい app を「空いている面」に置いて、そこから起動する。**焼き直しではない。いつでも戻せる。**
#
#   ./scripts/flash-slot.sh <xiaozhi.bin>        ota_0 に書いて、ota_0 から起動（いまは ota_1 で動いている前提）
#   ./scripts/flash-slot.sh --back                ota_1（今までの面）に戻す
#   ./scripts/flash-slot.sh --measure [--n 14]    起動から顔が出るまでを測る（scripts/boot_measure.py）
#
# ★2026-09-26：起動が 33 秒かかる原因（起動直後の Wi-Fi 省電力）を1行直したファームを、
#   3日前に入れるために作った。**上書きせず隣の面に置く**ので、ダメなら --back で 10 秒で戻る。
#
# 面の位置は partitions（16m）:  ota_0 = 0x20000 / ota_1 = 0x410000 / otadata = 0xd000
set -uo pipefail
cd "$(dirname "$0")/.."
PY=./.venv/bin/python
OTA0=0x20000
MAXSZ=$((0x3f0000))

port(){ $PY - <<'EOF'
from serial.tools import list_ports
for p in list_ports.comports():
    if p.vid == 0x303A and p.pid == 0x1001: print(p.device); break
EOF
}

measure(){ $PY scripts/boot_measure.py "$@"; }

case "${1:-}" in
--measure) shift; measure "$@"; exit $?;;   # 例: --measure --n 14
--back)
  echo "  ota_1（今までの面）に戻します"; $PY scripts/ota_select.py 1 && sleep 6 && measure; exit $?;;
"" ) echo "使い方: $0 <xiaozhi.bin> | --back | --measure"; exit 2;;
esac

BIN="$1"
[ -f "$BIN" ] || { echo "★ 無い: $BIN"; exit 1; }
SZ=$(stat -f%z "$BIN"); [ "$SZ" -le "$MAXSZ" ] || { echo "★ 大きすぎる: $SZ > $MAXSZ"; exit 1; }
head -c 1 "$BIN" | od -An -tx1 | grep -q e9 || { echo "★ app の形をしていない（先頭が 0xE9 ではない）"; exit 1; }
PORT=$(port); [ -z "$PORT" ] && { echo "★ 実機の USB が見えません（上の箱の USB-C をデータ線で）"; exit 1; }

echo "  いまの面:"; grep -o "Running partition: ota_[01]" ~/Library/Logs/stackchan/com.uni.stackchan.console.log 2>/dev/null | tail -1 || echo "   （不明。ota_1 前提で進めます）"
echo "  ${BIN}（${SZ} バイト）を ota_0 (${OTA0}) に書きます → ${PORT}"
$PY -m esptool --port "$PORT" --baud 921600 write-flash "$OTA0" "$BIN" || { echo "★ 書き込みに失敗。実機は今までの面のまま"; exit 1; }
echo "  ota_0 から起動するよう切り替えます"
$PY scripts/ota_select.py 0 || { echo "★ 切り替えに失敗。実機は今までの面のまま"; exit 1; }
sleep 6
echo "  起動を測ります"; measure
echo
echo "  戻すとき:  ./scripts/flash-slot.sh --back"
