#!/usr/bin/env bash
# gateway をデーモンモードで起動する。
#   MCP  : http://127.0.0.1:8767/mcp   ← console.py と Claude Code が繋ぐ
#   ESP32: ws://<LAN IP>:8775/         ← 実機が繋ぐ
set -euo pipefail
cd "$(dirname "$0")/.."
set -a; . ./.env.gateway; set +a

# ★ LAN IP は「既定経路のインターフェース」から取る。
#    この Mac Studio は有線(en7)と Wi-Fi(en1) の両方が同じサブネットに居るため、
#    列挙順で拾うと日によって変わる。抜き差しで死なない方を選ぶ。
if [ -z "${VISION_HOST:-}" ]; then
  DEV=$(route -n get default 2>/dev/null | awk '/interface:/{print $2}')
  if [ -n "$DEV" ]; then
    VISION_HOST=$(ipconfig getifaddr "$DEV" 2>/dev/null || true)
    export VISION_HOST
  fi
fi

echo "─────────────────────────────────────────────"
echo " ESP32 の接続先 : ws://${VISION_HOST:-<LAN IP>}:${WS_PORT}/"
echo " MCP            : http://${MCP_HTTP_HOST}:${MCP_HTTP_PORT}/mcp"
echo " 写真の受け口   : http://${VISION_HOST:-<LAN IP>}:${CAPTURE_PORT}/"
echo " （経路: ${DEV:-?}）"
echo "─────────────────────────────────────────────"
exec ./.venv/bin/stackchan-mcp serve --transport streamable-http "$@"
