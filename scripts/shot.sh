#!/bin/zsh
# 背景を**実際に撮って見る**。
#
# ★2026-09-13 の失敗：テストは全部緑なのに、画面はテープの光で真っ白に洗い流されていた。
#   「描画OK」「幾何OK」は**落ちずに描けた**ことしか言っていない。
#   加算合成の合計が1を超えているといった「見れば一発」の壊れ方は、
#   数字の検算をすり抜ける。**出す前に、一度は目で見る。**
#
#   使い方:  scripts/shot.sh out.png [待ち秒]
set -e
OUT=${1:-/tmp/stage.png}; WAIT=${2:-6}
HERE=$(cd $(dirname $0)/.. && pwd)
PORT=9333
if ! curl -s -m 2 http://127.0.0.1:$PORT/json/version >/dev/null 2>&1; then
  nohup "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome" \
    --headless=new --disable-gpu --remote-debugging-port=$PORT \
    --user-data-dir=/tmp/stackchan-cdp --window-size=1600,900 --hide-scrollbars \
    "http://127.0.0.1:8779/" >/dev/null 2>&1 &
  for i in $(seq 1 30); do
    curl -s -m 1 http://127.0.0.1:$PORT/json/version >/dev/null 2>&1 && break; sleep 1
  done
fi
$HERE/.venv/bin/python $HERE/scripts/shot.py "$OUT" \
  "document.getElementById('hud').textContent" "$WAIT"
