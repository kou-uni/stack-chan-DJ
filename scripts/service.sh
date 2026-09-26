#!/usr/bin/env bash
# gateway と console を macOS の常駐サービスにする。
#
#   ./scripts/service.sh install     常駐化する（ログイン時に自動で上がる）
#   ./scripts/service.sh status      いまの状態
#   ./scripts/service.sh restart     入れ直す
#   ./scripts/service.sh stop        止める（次のログインでまた上がる）
#   ./scripts/service.sh uninstall   常駐をやめる
#   ./scripts/service.sh logs        ログを追う
#
# ★常駐にすると「起動する」作業が無くなる。
#   実機の電源を入れれば、console が待っているのでそのまま繋がる。
set -uo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
LA="$HOME/Library/LaunchAgents"
LOGDIR="$HOME/Library/Logs/stackchan"
GW="com.uni.stackchan.gateway"
CON="com.uni.stackchan.console"
# ★OTA スタブ。実機は起動時に ota_url（:8778）へ問い合わせ、通るまで WebSocket に来ない。
#   2026-09-26：手で `&` 起動していたスタブが死んでいて、実機が半日戻ってこなかった。
OTA="com.uni.stackchan.ota"
DOMAIN="gui/$(id -u)"

mkdir -p "$LA" "$LOGDIR"

plist() {  # $1=ラベル $2=実行するもの... （残りは引数）
  local label="$1"; shift
  cat <<XML
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0"><dict>
  <key>Label</key><string>${label}</string>
  <key>ProgramArguments</key><array>
$(for a in "$@"; do echo "    <string>${a}</string>"; done)
  </array>
  <key>WorkingDirectory</key><string>${ROOT}</string>
  <key>RunAtLoad</key><true/>
  <key>KeepAlive</key><true/>
  <key>ThrottleInterval</key><integer>20</integer>
  <key>ProcessType</key><string>Interactive</string>
  <key>StandardOutPath</key><string>${LOGDIR}/${label}.log</string>
  <key>StandardErrorPath</key><string>${LOGDIR}/${label}.log</string>
</dict></plist>
XML
}

case "${1:-}" in

install)
  echo "手で動かしているものを止めます …"
  "$ROOT/scripts/stop.sh" >/dev/null 2>&1 || true

  # ★gateway は「名前」では見つからない（ただの Python として見える）。
  #   MCP のポートを持っている相手を探して止める。
  #   ★ポート番号で探すこと。他の Python（8765 の別プロジェクト）を巻き込まない。
  MCP_PORT="$(awk -F= '/^MCP_HTTP_PORT=/{gsub(/[^0-9]/,"",$2); print $2}' "$ROOT/.env.gateway")"
  OLD="$(lsof -nP -iTCP:"${MCP_PORT:-8767}" -sTCP:LISTEN -t 2>/dev/null || true)"
  if [ -n "$OLD" ]; then
    echo "  古い gateway を止めます (PID $OLD, ポート ${MCP_PORT:-8767})"
    kill -TERM $OLD 2>/dev/null || true
    for i in $(seq 1 10); do
      lsof -nP -iTCP:"${MCP_PORT:-8767}" -sTCP:LISTEN -t >/dev/null 2>&1 || break
      sleep 1
    done
  fi
  sleep 2

  plist "$OTA" "$ROOT/.venv/bin/python" "$ROOT/scripts/ota_stub.py" "--port" "8778" > "$LA/$OTA.plist"
  plist "$GW"  "/bin/bash" "$ROOT/scripts/gateway.sh"                > "$LA/$GW.plist"
  # ★実機を待ち続ける（--wait-device 0）。電源を入れた瞬間に繋がる
  plist "$CON" "$ROOT/.venv/bin/python" "-u" "$ROOT/app/dj/console.py" \
        "--wait-device" "0" "--quiet"                                 > "$LA/$CON.plist"

  for L in "$OTA" "$GW" "$CON"; do
    launchctl bootout  "$DOMAIN/$L" 2>/dev/null || true
    launchctl bootstrap "$DOMAIN" "$LA/$L.plist" || { echo "★ $L の登録に失敗"; exit 1; }
  done
  # gateway が立ってから console、の順にしたいので console だけ入れ直す
  sleep 6
  launchctl kickstart -k "$DOMAIN/$CON" 2>/dev/null || true

  echo "常駐にしました。ログイン時に自動で上がります"
  echo "  ログ: $LOGDIR/"
  ;;

uninstall)
  for L in "$CON" "$GW"; do
    launchctl bootout "$DOMAIN/$L" 2>/dev/null || true
    rm -f "$LA/$L.plist"
  done
  echo "常駐をやめました（いま動いているものも止まります）"
  ;;

start)   for L in "$GW" "$CON"; do launchctl kickstart "$DOMAIN/$L" 2>/dev/null || true; done; echo "起動しました" ;;
stop)    for L in "$CON" "$GW"; do launchctl kill TERM "$DOMAIN/$L" 2>/dev/null || true; done; echo "止めました（次のログインでまた上がります）" ;;
restart) launchctl kickstart -k "$DOMAIN/$GW" 2>/dev/null; sleep 5
         launchctl kickstart -k "$DOMAIN/$CON" 2>/dev/null; echo "入れ直しました" ;;

status)
  for L in "$GW" "$CON"; do
    if launchctl print "$DOMAIN/$L" >/dev/null 2>&1; then
      PID=$(launchctl print "$DOMAIN/$L" 2>/dev/null \
            | awk -F'= ' '/^[[:space:]]*pid = /{gsub(/[^0-9]/,"",$2); print $2; exit}')
      if [ -n "$PID" ]; then
        printf "%s %-28s PID %s\n" "○" "$L" "$PID"
      else
        printf "%s %-28s %s\n" "△" "$L" "登録済み・いま停止中"
      fi
    else
      printf "%s %-28s %s\n" "×" "$L" "未登録"
    fi
  done
  echo
  "$ROOT/.venv/bin/python" "$ROOT/scripts/status.py" 2>/dev/null | grep -v "gateway に接続"
  ;;

logs)
  tail -f "$LOGDIR"/*.log
  ;;

*)
  sed -n '2,12p' "$0" | sed 's/^# \{0,1\}//'
  exit 1 ;;
esac
