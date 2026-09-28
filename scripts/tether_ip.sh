#!/usr/bin/env bash
# テザリングに繋いだこの Mac の IP と、実機の設定画面に打ち込む2つの URL を出す。
#   ./scripts/tether_ip.sh              いまの IP と URL
#   ./scripts/tether_ip.sh --alias IP   当日 IP が変わっていたとき、前に実機へ教えた IP をこの Mac に足す（sudo）
# 手順の全文: docs/tethering.md
set -uo pipefail
DEV=$(route -n get default 2>/dev/null | awk '/interface:/{print $2}')
IP=$(ipconfig getifaddr "$DEV" 2>/dev/null || true)
MASK=$(ipconfig getoption "$DEV" subnet_mask 2>/dev/null || echo 255.255.255.0)
SSID=$(ipconfig getsummary "$DEV" 2>/dev/null | awk -F': ' '/ SSID/{print $2; exit}')
if [ "${1:-}" = "--alias" ]; then
  WANT="${2:-}"; [ -z "$WANT" ] && { echo "使い方: $0 --alias 172.20.10.2"; exit 2; }
  [ "$WANT" = "$IP" ] && { echo "  ○ もう $WANT を持っています。何もしません"; exit 0; }
  ping -c1 -W1 "$WANT" >/dev/null 2>&1 && { echo "★ $WANT は LAN 上の別の機械が使っています。別名にできません"; exit 1; }
  echo "  $DEV に別名 $WANT（$MASK）を足します（パスワードを聞かれます）"
  sudo ifconfig "$DEV" alias "$WANT" "$MASK" && echo "  ○ 足しました。実機を再起動すれば来ます" ; exit $?
fi
[ -z "$IP" ] && { echo "★ $DEV に IP がありません。テザリングに繋いでから"; exit 1; }
echo "  この Mac:  $IP  （$DEV / mask $MASK${SSID:+ / SSID $SSID}）"
case "$IP" in 172.20.10.*) echo "  ○ iPhone テザリングの番地帯です";; 192.168.0.*) echo "  ★ 家の LAN の番地帯です。テザリングに繋がっていません";; *) echo "  （番地帯: ${IP%.*}.x）";; esac
echo
echo "  実機の設定画面（http://192.168.4.1 → Advanced）に、この2行をそのまま:"
echo "    OTA URL        http://$IP:8778/"
echo "    WebSocket URL  ws://$IP:8775/"
echo
echo "  当日 IP が変わっていたら:  ./scripts/tether_ip.sh --alias <前に実機へ教えた IP>"
