#!/usr/bin/env bash
# 自分が張ったトンネルだけ閉じる。
# ★この Mac には別のトンネルが居る（Obsidian RSI）。**探して殺す、をやらない。**
PORT=8779
PID=$(pgrep -f "cloudflared tunnel --url http://127.0.0.1:$PORT" | head -1)
[ -z "$PID" ] && { echo "  張っていません"; exit 0; }
kill "$PID" && echo "  閉じました（$PORT のぶんだけ）"
