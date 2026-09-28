#!/usr/bin/env bash
# 会場で Mac の IP が変わったら、これ1本。**実機を USB で挿してから走らせる。**
#
#   ./scripts/new_ip.sh
#   ./scripts/new_ip.sh --wifi 会場のSSID     # 実機に会場の Wi-Fi も教える（パスワードを聞く）
#
#   1. この Mac のいまの IP を拾う
#   2. gateway を入れ直す（写真の受け口などは起動時の IP を覚えているため）
#   3. 実機の向き先2つ（ota_url / websocket.url）を USB からその IP に書き換える
#   4. 実機が繋がるまで待って、繋がったかを言う
#
# ★設定画面（タップ → 192.168.4.1）は使わない。NVS は消さない。
# ★Wi-Fi の名前（SSID）が変わった場合は --wifi で実機に教える（家の分は残る。最大10件）。
#   実機は 2.4GHz のみ・ログイン画面のある Wi-Fi には乗れない。
set -uo pipefail
cd "$(dirname "$0")/.."
ok(){   printf "  \033[32m○\033[0m %s\n" "$1"; }
die(){  printf "  \033[31m×\033[0m %s\n\nここで止めます。上の理由を直して、もう一度走らせてください。\n" "$1"; exit 1; }
step(){ printf "\n\033[36m── %s\033[0m\n" "$1"; }

step "1. この Mac の IP"
DEV=$(route -n get default 2>/dev/null | awk '/interface:/{print $2}')
[ -n "$DEV" ] || die "ネットワークに繋がっていません（既定の経路がない）"
IP=$(ipconfig getifaddr "$DEV" 2>/dev/null || true)
case "$IP" in
  "")        die "IPv4 がありません。実機と同じ Wi-Fi に繋いでから" ;;
  192.0.0.*) die "IPv6 だけのネットワークです（iPhone テザリングで起きた）。実機は乗れません" ;;
esac
ok "${IP}  （${DEV}）"

step "2. gateway を入れ直す"
./scripts/service.sh restart >/dev/null || die "入れ直せませんでした（scripts/service.sh）"
for i in {1..20}; do
  nc -z 127.0.0.1 8775 2>/dev/null && nc -z 127.0.0.1 8778 2>/dev/null && break; sleep 1
done
nc -z 127.0.0.1 8775 2>/dev/null || die "gateway（8775）が上がりません。~/Library/Logs/stackchan/ を見る"
nc -z 127.0.0.1 8778 2>/dev/null || die "OTA スタブ（8778）が上がりません。~/Library/Logs/stackchan/ を見る"
ok "gateway と OTA スタブが待っています"

step "3. 実機の向き先を書き換える"
./.venv/bin/python scripts/set_target.py "$IP" "$@" || exit 1

step "4. 実機が繋がるのを待つ"
for i in {1..12}; do
  sleep 5
  if ./.venv/bin/python scripts/status.py 2>/dev/null | grep -q "○ 実機"; then
    ok "繋がりました（向き先 ${IP}）"
    exit 0
  fi
  printf "    待っています… %d秒\n" $((i * 5))
done
die "60秒待っても来ません。'./scripts/rescue.sh --serial' で実機の言い分を聞く"
