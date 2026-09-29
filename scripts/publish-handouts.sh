#!/usr/bin/env bash
# 配布物（docs/pages の10枚）を、参加者向けの公開リポジトリへ写して push する。
#   ./scripts/publish-handouts.sh
# ★進行表（shinkou.html）と台本（event/text.html）は写さない。伏線が割れる。
# ★公開先: https://kou-uni.github.io/workshop-of-stackchan-at-cryptobar/
set -euo pipefail
cd "$(dirname "$0")/.."
PAGES="tsukutta-mono hajimekata shippai genka firmware sekkeizu haisenzu dj-hajimekata omi map"
REPO="https://github.com/kou-uni/workshop-of-stackchan-at-cryptobar.git"
W=$(mktemp -d)
git clone -q --depth 1 "$REPO" "$W"
./.venv/bin/python scripts/pack-page.py >/dev/null
for p in $PAGES; do cp "docs/pages/$p.html" "$W/"; done
[ -f "$W/shinkou.html" ] && { echo "★ 公開側に shinkou.html がある。消します"; git -C "$W" rm -q shinkou.html; }
# ★見るのは写した配布物だけ。kamishibai/（台本）には設定画面の番地 192.168.4.1 が正当に入っている
if for p in $PAGES; do cat "$W/$p.html"; done | grep -qE "sk-[A-Za-z0-9]{20,}|ghp_[A-Za-z0-9]{30,}|BACKLOG|panel-token|192\.168\.(0|7)\.[0-9]+"; then
  echo "★ 秘密らしきものが配布物に入っている。push しません"; exit 1; fi
if git -C "$W" diff --quiet && [ -z "$(git -C "$W" status --porcelain)" ]; then echo "  変更なし"; exit 0; fi
git -C "$W" add -A
git -C "$W" -c user.name=kou-uni -c user.email=theta.sparkx@gmail.com commit -q -m "配布物を更新 $(date +%Y-%m-%d)"
git -C "$W" push -q origin main
echo "  ○ 公開しました: https://kou-uni.github.io/workshop-of-stackchan-at-cryptobar/（反映まで1分ほど）"
rm -rf "$W"
