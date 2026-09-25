#!/usr/bin/env bash
# 当日の台本を、1枚ずつ送れる形にする（紙芝居）。
#
#   ./scripts/build-text.sh        →  event/text.html
#
# ★参加者には渡さない。**F の回収（伏線）が割れる。**
#   だから docs/pages/ には置かない（あそこは配る場所）。
#
# ★道具は kou-uni/kamishibai。**vendor/ に固定して取り込む**（bootstrap と同じ型）。
set -uo pipefail
ROOT=$(cd "$(dirname "$0")/.." && pwd); cd "$ROOT"
K=vendor/kamishibai
PIN=$(cat vendor-patches/kamishibai.pin 2>/dev/null || echo "")

command -v node >/dev/null || { echo "★ node がありません"; exit 1; }

if [ ! -d "$K/.git" ]; then
  echo "  紙芝居の道具を取ってきます…"
  git clone --quiet https://github.com/kou-uni/kamishibai.git "$K" || { echo "★ clone できません"; exit 1; }
  [ -n "$PIN" ] && git -C "$K" checkout --quiet "$PIN"
  echo "  取ってきました（$(git -C "$K" rev-parse --short HEAD)）"
else
  echo "  紙芝居の道具は既にあります（$(git -C "$K" rev-parse --short HEAD)）"
fi

# ★台本とアセットは、こちらが持っている。道具側には置かない
# ★置いたものを「道具側の改変」と誤認させない（pack-patches.sh が拾ってしまう）
EX="$K/.git/info/exclude"
grep -q "stackchan-text" "$EX" 2>/dev/null || cat >> "$EX" <<'EOF'
# stackchan-lab が置いていくもの（道具側の改変ではない）
content/stackchan-text.js
assets/stackchan*.png
dist/
EOF

cp event/kamishibai/text.js "$K/content/stackchan-text.js"
mkdir -p "$K/assets" && cp event/kamishibai/assets/*.png "$K/assets/"

( cd "$K" && node build.mjs content/stackchan-text.js -o dist/stackchan-text.html ) \
  || { echo "★ 組み立てに失敗しました"; exit 1; }

cp "$K/dist/stackchan-text.html" event/text.html
SIZE=$(du -h event/text.html | cut -f1 | tr -d ' ')
echo
echo "  ○ event/text.html  ($SIZE)  ← 1枚のHTML。そのまま開ける"
echo "    ★これは進行役だけのもの。配布物（docs/pages/）には置いていません。"
