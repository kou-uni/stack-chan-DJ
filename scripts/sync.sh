#!/usr/bin/env bash
# この機械を、いまの最新に合わせる。**機能追加のたびに、これだけ打つ。**
#
#   ./scripts/sync.sh              取り込んで、要る分だけ入れ直して、検査する
#   ./scripts/sync.sh --no-service 常駐を触らない（開発中）
#
# ★一から立ち上げるのは bootstrap.sh。**2回目以降はこちら。**
#   bootstrap は「既にあるものは触らない」作りなので、更新には使えない。
#
# ★運ぶのは git。**同じ LAN でなくても、コードは揃う。**
#   同じ LAN が要るのは「実機が gateway を見つける」ときだけ。
set -uo pipefail
ROOT=$(cd "$(dirname "$0")/.." && pwd); cd "$ROOT"
NO_SERVICE=0
[ "${1:-}" = "--no-service" ] && NO_SERVICE=1

ok(){   printf "  \033[32m○\033[0m %s\n" "$1"; }
warn(){ printf "  \033[33m▲\033[0m %s\n" "$1"; }
die(){  printf "\n\033[31m★ %s\033[0m\n" "$1"; exit 1; }
step(){ printf "\n\033[1m%s\033[0m\n" "$1"; }

# ── 1. 取り込む ────────────────────────────────
step "1. 変更を取り込む"
if [ -n "$(git status --porcelain)" ]; then
  git status --short | sed 's/^/     /'
  die "この機械に、まだ commit していない変更があります。
   先に片付けてください（消さずに止めています）。"
fi
BEFORE=$(git rev-parse HEAD)
git pull --ff-only --quiet || die "取り込めませんでした（枝が分かれている可能性）"
AFTER=$(git rev-parse HEAD)
if [ "$BEFORE" = "$AFTER" ]; then
  ok "すでに最新です"
else
  ok "$(git rev-list --count "$BEFORE..$AFTER") 件の変更を取り込みました"
  git log --oneline "$BEFORE..$AFTER" | head -8 | sed 's/^/     /'
fi
CHANGED=$(git diff --name-only "$BEFORE" "$AFTER")

# ── 2. 変わったものだけ入れ直す ──────────────────
step "2. 要るものだけ入れ直す"
changed(){ echo "$CHANGED" | grep -q "$1"; }

if changed "requirements.*txt\|pyproject"; then
  ./.venv/bin/pip install -q -r requirements.txt 2>/dev/null \
    && ok "依存を入れ直しました" || warn "依存の入れ直しに失敗（手で確認）"
else ok "依存は変わっていません"; fi

if changed "vendor-patches/"; then
  warn "vendor の改変が変わりました。**bootstrap.sh を1回走らせてください**"
else ok "vendor は変わっていません"; fi

if changed "app/avatar/"; then
  ./.venv/bin/python app/avatar/make_faces.py  >/dev/null 2>&1 &&
  ./.venv/bin/python app/avatar/pack_avatar.py >/dev/null 2>&1 \
    && ok "顔を作り直しました（★実機へは reload_avatar.py で入れ直す）" \
    || warn "顔を作り直せませんでした"
else ok "顔は変わっていません"; fi

if changed "docs/pages/src/"; then
  ./.venv/bin/python scripts/pack-page.py >/dev/null 2>&1 \
    && ok "配布物を固め直しました" || warn "配布物を固め直せませんでした"
else ok "配布物は変わっていません"; fi

# ── 3. 検査 ────────────────────────────────────
step "3. 検査"
./.venv/bin/python -m pytest tests/ -q >/tmp/sync-test.log 2>&1 \
  && ok "$(grep -oE '[0-9]+ passed' /tmp/sync-test.log) " \
  || { tail -12 /tmp/sync-test.log | sed 's/^/     /'; die "試験が落ちました。**この状態で当日に持っていかない。**"; }
./.venv/bin/python scripts/sync_check.py | sed 's/^/  /'

# ── 4. 常駐 ────────────────────────────────────
step "4. 動かす"
if [ "$NO_SERVICE" = "1" ]; then
  warn "--no-service なので、常駐は触りません"
else
  launchctl kickstart -k "gui/$(id -u)/com.uni.stackchan.console" >/dev/null 2>&1 \
    && ok "console を入れ直しました" || warn "console の入れ直しに失敗（未導入かも）"
fi

# ── 5. ★同じ LAN に gateway が2台いないか ───────────
step "5. 実機は、どの Mac を見るか"
echo "     ★この実機のファームには mDNS 探索が**入っていない**（gateway_config_get: discovery_compiled_in=false）。"
echo "       実機は **ws://192.168.0.123:8775/ と http://192.168.0.123:8778/ を固定で**見に来る。"
echo "       別の Mac で受けるなら、その Mac が 192.168.0.123 を持つか、実機の設定を変える（scripts/nfc_enroll.py --scan で疎通確認）。"
OTHERS=$(dns-sd -t 2 -B _stackchan._tcp 2>/dev/null | tail -n +5 | awk '{print $NF}' | sort -u | grep -v '^$')
N=$(printf "%s" "$OTHERS" | grep -c . || true)
if [ "${N:-0}" -gt 1 ]; then
  printf "\n\033[31m★ この LAN に gateway が %s 台います\033[0m\n" "$N"
  printf "%s\n" "$OTHERS" | sed 's/^/     /'
  echo "   **実機がどちらに付くかは決まりません。**開発するほうだけ残してください："
  echo "     もう一方で  ./scripts/stop.sh"
else
  ok "この LAN の gateway は1台です（$(hostname -s)）"
fi

printf "\n\033[1m物理で触るのは DJ機材の USB だけです。\033[0m\n"
echo "  実機は電源が入っていれば、同じ LAN の gateway に自分で付きます。"
