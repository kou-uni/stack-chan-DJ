#!/usr/bin/env bash
# 実機が gateway に来ないとき。**止まっている場所を機械が言う。** 手順は docs/rescue.md。
#
#   ./scripts/rescue.sh            上から順に見て、止まっている場所と次の一手を出す
#   ./scripts/rescue.sh --serial   USB で繋いだ実機をリセットして、起動ログの要点を出す
#   ./scripts/rescue.sh --reset    実機をリセットするだけ（USB 経由）
#
# ★2026-09-26：Mac 側の推理に2時間、シリアルを読んだら30秒で確定。
#   **沈黙している側の言い分を聞かずに、こちら側で推理していた。** だから --serial を最初に勧める。
set -uo pipefail
cd "$(dirname "$0")/.."
ok(){   printf "  \033[32m○\033[0m %s\n" "$1"; }
ng(){   printf "  \033[31m×\033[0m %s\n" "$1"; }
hint(){ printf "     → %s\n" "$1"; }
PY=./.venv/bin/python

serial_port(){ $PY - <<'EOF'
from serial.tools import list_ports
for p in list_ports.comports():
    if p.vid == 0x303A and p.pid == 0x1001: print(p.device); break
EOF
}

case "${1:-}" in
--reset)
  PORT=$(serial_port); [ -z "$PORT" ] && { ng "実機の USB（JTAG/serial）が見えません。上の箱の USB-C をデータ線で挿す"; exit 1; }
  $PY - "$PORT" <<'EOF'
import serial, sys, time
s = serial.Serial(sys.argv[1], 115200, timeout=1); s.dtr=False; s.rts=True; time.sleep(0.1); s.rts=False; s.close()
print("  ○ リセットしました")
EOF
  exit 0;;
--serial)
  PORT=$(serial_port); [ -z "$PORT" ] && { ng "実機の USB（JTAG/serial）が見えません。上の箱の USB-C をデータ線で挿す（台側は給電だけ）"; exit 1; }
  echo "  $PORT をリセットして 45 秒読みます…"
  $PY - "$PORT" <<'EOF'
import serial, sys, time, re
s = serial.Serial(sys.argv[1], 115200, timeout=1); s.dtr=False; s.rts=True; time.sleep(0.1); s.rts=False
t0=time.time(); lines=[]
while time.time()-t0 < 45:
    l = s.readline().decode("utf-8","replace").rstrip()
    if l: lines.append(re.sub(r"\x1b\[[0-9;]*m","",l))
s.close()
key = re.compile(r"Got IP|Connected to WiFi|WiFi connecting|Failed to connect|Check new version|Alert|activation|websocket|WebSocket|candidate|gateway|OTA|Ota:|E \(", re.I)
hit = [l for l in lines if key.search(l) and "Add tool" not in l]
print(f"  {len(lines)}行のうち要点 {len(hit)}行")
for l in hit[:40]: print("   ", l[:170])
txt = "\n".join(lines)
print()
if "Failed to connect" in txt and ":8778" in txt:
    m = re.search(r"Failed to connect to ([0-9.]+):8778", txt)
    print(f"  ★ 止まっている場所: OTA 確認。実機は http://{m.group(1) if m else '?'}:8778/ を見に来ている")
    print("     → その IP でこの Mac の OTA スタブが待っているか（status.py の1行目）。IP が違うなら docs/rescue.md §3")
elif "Failed to connect" in txt and ":8775" in txt:
    m = re.search(r"Failed to connect to ([0-9.]+):8775", txt)
    print(f"  ★ 止まっている場所: gateway。実機は ws://{m.group(1) if m else '?'}:8775/ を見に来ている")
    print("     → gateway が上がっているか。IP が違うなら docs/rescue.md §3")
elif "activation" in txt.lower() or "6" in txt and "code" in txt.lower():
    print("  ★ 止まっている場所: OTA が本物のクラウドを向いている（6桁コード）→ ota_url をスタブへ")
elif "Got IP" not in txt:
    print("  ★ 止まっている場所: Wi-Fi。2.4GHz の SSID に繋がっていない → 設定モードに入れ直す")
else:
    print("  Wi-Fi は繋がっている。gateway 側のログも見る: docs/rescue.md §1")
EOF
  exit 0;;
esac

echo "実機が来ないときの切り分け（上から）"
echo
# 1. OTA スタブ
if lsof -nP -iTCP:8778 -sTCP:LISTEN -t >/dev/null 2>&1; then ok "OTA スタブ（:8778）が待っている"
else ng "OTA スタブ（:8778）が止まっている ★ここが9割"; hint "./scripts/service.sh install → 実機を再起動"; fi
# 2. gateway
if curl -sf -m 3 -o /dev/null http://127.0.0.1:8767/mcp -X POST -H 'content-type: application/json' -d '{}' 2>/dev/null || lsof -nP -iTCP:8767 -sTCP:LISTEN -t >/dev/null 2>&1; then ok "gateway（:8767 / :8775）が動いている"
else ng "gateway が動いていない"; hint "launchctl kickstart -k gui/\$(id -u)/com.uni.stackchan.gateway"; fi
# 3. console
pgrep -f "app/dj/console.py" >/dev/null 2>&1 && ok "console が動いている" || { ng "console が止まっている"; hint "launchctl kickstart -k gui/\$(id -u)/com.uni.stackchan.console"; }
# 4. 実機
ST=$($PY scripts/status.py 2>/dev/null)
if echo "$ST" | grep -q "○ 実機"; then ok "実機が gateway に繋がっている"; echo "$ST" | grep "向き先" | sed 's/^/  /'
else
  ng "実機が gateway に来ていない"
  LAST=$(grep -E "ESP32 ready|disconnected" ~/Library/Logs/stackchan/com.uni.stackchan.gateway.log 2>/dev/null | tail -1 | cut -c1-19)
  [ -n "$LAST" ] && hint "最後の記録: $LAST（この後に Mac で何をしたか）"
  hint "★次は実機の言い分を聞く:  ./scripts/rescue.sh --serial （上の箱の USB-C をデータ線で）"
fi
# 5. この Mac の IP と、実機の向き先
IPS=$(ifconfig 2>/dev/null | awk '/inet /&&!/127.0.0.1/{print $2}' | tr '\n' ' ')
echo "  この Mac の IP: $IPS"
echo
echo "手順の全文: docs/rescue.md"
