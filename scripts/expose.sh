#!/usr/bin/env bash
# 操作パネルを外に出す。ROADMAP Phase 2。
#
# ★Tailscale は入れるのに sudo が要る（実機の前に居ないと無理）。
#   cloudflared は管理者権限なしで通せるので、外出先から先に進める手として使う。
#
# ★他のトンネルを止めない。この Mac では Obsidian RSI が別のトンネルを持っている。
#   ポート指定で新しく1本足すだけ。**探して殺す、をやらない。**
set -uo pipefail
PORT="${1:-8779}"
LOG=$(mktemp -t stackchan-expose)

command -v cloudflared >/dev/null || { echo "cloudflared がありません"; exit 1; }

if ! lsof -nP -iTCP:$PORT -sTCP:LISTEN >/dev/null 2>&1; then
  echo "★ ポート $PORT が空です。console が動いていません"
  echo "   launchctl kickstart gui/\$(id -u)/com.uni.stackchan.console"
  exit 1
fi

TOKEN=$(cat ~/.config/stackchan/panel-token 2>/dev/null)
[ -z "$TOKEN" ] && { echo "★ 鍵がありません（console を一度起動すると作られます）"; exit 1; }

echo "トンネルを張ります（Ctrl-C で閉じる）…"
cloudflared tunnel --url "http://127.0.0.1:$PORT" >"$LOG" 2>&1 &
PID=$!
trap 'kill $PID 2>/dev/null' EXIT

for i in $(seq 1 40); do
  URL=$(grep -om1 'https://[a-z0-9-]*\.trycloudflare\.com' "$LOG" | head -1)
  [ -n "$URL" ] && break
  sleep 0.5
done
[ -z "$URL" ] && { echo "★ URL が取れませんでした"; tail -5 "$LOG"; exit 1; }

echo
echo "════════════════════════════════════════"
echo "  操作パネル:"
echo "  $URL/panel?k=$TOKEN"
echo "════════════════════════════════════════"
echo "  ★このURLは鍵つき。**そのまま人に送らない**"
echo "  ★Ctrl-C で閉じる。閉じたらURLは消える"
echo
wait $PID
