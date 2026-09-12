#!/usr/bin/env bash
# 出発前・イベント直前の疎通チェック。全部 OK になってから家を出る。
set -uo pipefail

ok(){ printf "  \033[32mOK\033[0m   %s\n" "$1"; }
ng(){ printf "  \033[31mNG\033[0m   %s\n" "$1"; }

echo "== 1. Ollama =="
curl -sf http://localhost:11434/api/tags >/dev/null && ok "Ollama が応答" || ng "Ollama が落ちている"

echo "== 2. xiaozhi-esp32-server =="
docker ps --format '{{.Names}}' | grep -q xiaozhi-server && ok "コンテナが動いている" || ng "コンテナが止まっている"
curl -sf http://localhost:8002 >/dev/null && ok "管理画面が開く" || ng "管理画面に繋がらない"

echo "== 3. Tailscale =="
if command -v tailscale >/dev/null 2>&1; then
  tailscale status >/dev/null 2>&1 && ok "Tailscale 接続中" || ng "Tailscale が未接続"
  echo "  --- funnel status ---"
  tailscale funnel status 2>&1 | sed 's/^/  /'
else
  ng "Tailscale が未インストール"
fi

echo "== 4. スリープ抑止 =="
pgrep -q caffeinate && ok "caffeinate 実行中" || ng "caffeinate が動いていない（scripts/keep-awake.sh）"

echo
echo "外部URL（PUBLIC_WS_URL）:"
grep -s '^PUBLIC_WS_URL=' ../server/.env 2>/dev/null || echo "  server/.env に未設定"
