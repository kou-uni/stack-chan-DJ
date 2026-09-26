#!/usr/bin/env bash
# 新しい app を「空いている面」に置いて、そこから起動する。**焼き直しではない。いつでも戻せる。**
#
#   ./scripts/flash-slot.sh <xiaozhi.bin>        ota_0 に書いて、ota_0 から起動（いまは ota_1 で動いている前提）
#   ./scripts/flash-slot.sh --back                ota_1（今までの面）に戻す
#   ./scripts/flash-slot.sh --measure             起動から顔が出るまでを測る（USB のログ）
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

measure(){
  PORT=$(port); [ -z "$PORT" ] && { echo "★ 実機の USB が見えません"; return 1; }
  $PY - "$PORT" <<'EOF'
import serial, sys, time, re
s = serial.Serial(sys.argv[1], 115200, timeout=1); s.dtr=False; s.rts=True; time.sleep(0.1); s.rts=False
t0=time.time(); lines=[]
while time.time()-t0 < 45:
    l = s.readline().decode("utf-8","replace").rstrip()
    if l: lines.append(re.sub(r"\x1b\[[0-9;]*m","",l))
    if any("set_avatar: face=idle applied=1" in x for x in lines[-1:]): break
s.close()
def ms(pat):
    for l in lines:
        if re.search(pat, l):
            m = re.search(r"\((\d+)\)", l)
            if m: return int(m.group(1))/1000
    return None
marks=[("Wi-Fi 接続", r"wifi:connected with"),("IP", r"Got IP"),("OTA 応答", r"Ota: Current is the latest|Ota: No mqtt"),
       ("WebSocket", r"WS: Connected to websocket|WebSocket handshake done"),("顔", r"set_avatar: face=idle applied=1")]
pm = next((l for l in lines if "wifi:pm start" in l), None)
print("  省電力:", "MIN_MODEM（旧）" if pm and "type: 1" in pm else ("なし（新）" if not pm else pm[-40:]))
prev=0
for name, pat in marks:
    t = ms(pat)
    print(f"   {t:6.2f}s  (+{t-prev:5.2f})  {name}" if t is not None else f"      --          {name}")
    if t is not None: prev=t
EOF
}

case "${1:-}" in
--measure) measure; exit $?;;
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
echo "  $BIN（$SZ バイト）を ota_0 ($OTA0) に書きます → $PORT"
$PY -m esptool --port "$PORT" --baud 921600 write-flash "$OTA0" "$BIN" || { echo "★ 書き込みに失敗。実機は今までの面のまま"; exit 1; }
echo "  ota_0 から起動するよう切り替えます"
$PY scripts/ota_select.py 0 || { echo "★ 切り替えに失敗。実機は今までの面のまま"; exit 1; }
sleep 6
echo "  起動を測ります"; measure
echo
echo "  戻すとき:  ./scripts/flash-slot.sh --back"
