#!/usr/bin/env bash
# console を止める。**片付けを走らせてから**終わる。
#
#   beat mode の停止 / ストリームの購読解除 / 首を正面 / 待機の顔
#
# ★ kill -9 は使わないこと。片付けが1つも走らず、
#   実機は踊ったまま、gateway は購読したままになる。
set -uo pipefail

PIDS=$(pgrep -f "app/dj/console.py" || true)
if [ -z "$PIDS" ]; then
  echo "console は動いていません"
  exit 0
fi

echo "止めます: PID $PIDS"
kill -TERM $PIDS 2>/dev/null || true

for i in $(seq 1 15); do
  pgrep -f "app/dj/console.py" >/dev/null || { echo "止まりました（${i}秒）"; exit 0; }
  sleep 1
done

echo "★ 15秒で止まりませんでした。強制的に終了します（片付けは走りません）"
pkill -9 -f "app/dj/console.py" || true
echo "  gateway 側に残っていないか確認してください:"
echo "    ./.venv/bin/python scripts/status.py"
exit 1
