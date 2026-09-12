#!/usr/bin/env bash
# Mac Studio をスリープさせない。出発前に走らせて、そのまま置いていく。
# 止めるときは Ctrl-C か kill。
set -euo pipefail
echo "スリープ抑止を開始します（Ctrl-C で解除）"
echo "  -d ディスプレイ / -i アイドル / -m ディスク / -s AC接続時"
exec caffeinate -dims
