#!/usr/bin/env bash
# 頭なでの通知の受け口（~/.config/stackchan-mcp/notify.yml）を、無ければ雛形から置く。既にあれば触らない。
#   ./scripts/ensure-notify.sh
# ★2026-09-29：この設定は機械ごとのホーム直下にあり、git にも bootstrap にも無かった。
#   無いと gateway の既定は全部 false で、実機は送っているのに**誰も受け取らず、頭なでに顔が反応しない**。
#   新しい MacBook で黙って抜ける穴だったので、雛形を git（config/notify.yml.example）に入れ、ここで置く。
set -uo pipefail
cd "$(dirname "$0")/.."
DST="$HOME/.config/stackchan-mcp/notify.yml"
if [ -f "$DST" ]; then
  if grep -qE "^\s*jsonl:" "$DST" && awk '/^jsonl:/{f=1} f&&/enabled:/{print; exit}' "$DST" | grep -q true; then
    echo "  ○ notify.yml あり（jsonl 有効）"; exit 0
  fi
  echo "  ★ notify.yml はあるが jsonl が有効でない。頭なでが届きません → $DST の jsonl.enabled を true に"; exit 1
fi
mkdir -p "$(dirname "$DST")" && cp config/notify.yml.example "$DST" && echo "  ○ notify.yml を雛形から置きました → $DST（gateway を再起動すると効く）"
