#!/usr/bin/env bash
# スマホで開くための URL を1本出す。**外にいても開ける形で。**
#
#   ./scripts/share.sh text     当日の台本（鍵つき）
#   ./scripts/share.sh qa       参加者の質疑
#   ./scripts/share.sh          一覧
#
# ★なぜ要るか（2026-09-25 の失敗）
#   「スマホから見たい」と言われて、**LANのURL**を出した。外にいたので開けない。
#   次に **QR** を出した。**そのスマホで、そのスマホの画面は読めない。**
#   さらに「ファイルに書きました、cat してください」と言った。**Macの前にいる人の話。**
#
#   ★**相手がどこにいるかを先に決める。**「スマホから」は、たいてい「外から」。
#     出すのは**タップできる https の1本**。QRは Mac の前にいるときだけ。
#     （当日の教材と同じ話 ── 合図は、相手が見ている場所から出す）
set -uo pipefail
cd "$(dirname "$0")/.."
PORT=8779
LOG=/tmp/stackchan-share-$PORT.log

declare -a NAMES=(text panel qa p map guide)
path_of(){ case "$1" in
  text) echo "/text";;  panel) echo "/panel";; qa) echo "/qa";;
  p) echo "/p";;        map) echo "/p/map";;  guide) echo "/guide";; esac; }
keyed_of(){ case "$1" in text|panel) echo 1;; *) echo 0;; esac; }
why_of(){ case "$1" in
  text)  echo "当日の台本（37画面）★進行役だけ";;
  panel) echo "操作パネル ★進行役だけ";;
  qa)    echo "参加者の質疑応答（Dの冒頭で配る）";;
  p)     echo "配布物の一覧（10枚）";;
  map)   echo "地図（Bで指す）";;
  guide) echo "なでかたの案内";; esac; }

NAME="${1:-}"
if [ -z "$NAME" ] || [ -z "$(path_of "$NAME")" ]; then
  echo "どれを出しますか"; echo
  for n in "${NAMES[@]}"; do
    printf "  %-6s %-9s %s %s\n" "$n" "$(path_of $n)" \
      "$([ "$(keyed_of $n)" = 1 ] && echo '鍵つき' || echo '      ')" "$(why_of $n)"
  done
  echo; echo "  ./scripts/share.sh <名前>"
  exit 0
fi

# ── console が動いているか ──
curl -sf -m 3 "http://127.0.0.1:$PORT/p" >/dev/null 2>&1 \
  || { echo "★ console が動いていません"; echo "   launchctl kickstart -k gui/\$(id -u)/com.uni.stackchan.console"; exit 1; }

# ── トンネル。**他人のトンネルは絶対に止めない**（この Mac には別のが居る）──
url_from_log(){ grep -om1 'https://[a-z0-9-]*\.trycloudflare\.com' "$LOG" 2>/dev/null | head -1; }
BASE=$(url_from_log)
if [ -n "$BASE" ] && pgrep -f "cloudflared tunnel --url http://127.0.0.1:$PORT" >/dev/null \
   && curl -sf -o /dev/null -m 20 "$BASE/p"; then
  echo "  いまのトンネルを使います"
else
  command -v cloudflared >/dev/null || { echo "★ cloudflared がありません"; exit 1; }
  echo "  トンネルを張ります（少し待ちます）…"
  nohup cloudflared tunnel --url "http://127.0.0.1:$PORT" > "$LOG" 2>&1 &
  for i in $(seq 1 60); do BASE=$(url_from_log); [ -n "$BASE" ] && break; sleep 1; done
  [ -z "$BASE" ] && { echo "★ URL が取れませんでした"; tail -5 "$LOG"; exit 1; }
  for i in $(seq 1 20); do curl -sf -o /dev/null -m 10 "$BASE/p" && break; sleep 3; done
fi

URL="$BASE$(path_of "$NAME")"
if [ "$(keyed_of "$NAME")" = 1 ]; then
  T=$(cat ~/.config/stackchan/panel-token 2>/dev/null)
  [ -z "$T" ] && { echo "★ 鍵がありません"; exit 1; }
  URL="$URL?k=$T"
fi

CODE=$(curl -s -o /dev/null -w '%{http_code}' -m 25 "$URL")
echo
echo "$URL"
echo
echo "  $(why_of "$NAME")   （応答 $CODE）"
[ "$(keyed_of "$NAME")" = 1 ] && echo "  ★鍵が入っています。**人に送らない。**"
echo "  ★トンネルは張りっぱなしにしない。終わったら:  ./scripts/unshare.sh"
