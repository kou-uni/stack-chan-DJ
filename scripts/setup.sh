#!/usr/bin/env bash
# 別の Mac で一から立ち上げる。**これ1本で済むようにする。**
#
#   git clone ... && cd stackchan-lab && ./scripts/setup.sh
#
# ★2026-09-09、MacBook で動かす段になって「依存が書いてない」ことに気づいた。
#   自分の機械でだけ動くものは、作ったうちに入らない。
set -euo pipefail
cd "$(dirname "$0")/.."

echo "── Python ──"
PY=$(command -v python3.14 || command -v python3)
echo "  $($PY --version)  ($PY)"

echo "── 仮想環境 ──"
[ -d .venv ] || "$PY" -m venv .venv
./.venv/bin/pip install -q --upgrade pip
./.venv/bin/pip install -q -r requirements-dev.txt
echo "  依存を入れました"

echo "── 設定 ──"
if [ ! -f .env.gateway ]; then
  cp .env.gateway.example .env.gateway 2>/dev/null || {
    echo "  ★ .env.gateway がありません。Mac Studio からコピーしてください"; exit 1; }
fi
echo "  .env.gateway  OK"

echo "── 表情のデータ ──"
if [ ! -f app/avatar/avatar_layered.raw ]; then
  echo "  ★ app/avatar/avatar_layered.raw がありません"
  echo "     ./.venv/bin/python app/avatar/pack_avatar.py で作るか、もう一方の Mac からコピー"
else
  echo "  $(wc -c < app/avatar/avatar_layered.raw | tr -d ' ') バイト  OK"
fi

echo "── 試験 ──"
./.venv/bin/python -m pytest tests/ -q

cat <<'MSG'

次にやること:

  ./scripts/service.sh install          常駐にする（ログイン時に自動で上がる）
  ./.venv/bin/python scripts/doctor.py  全部 ○ になるか見る

DJ機材(DDJ-FLX2)は、console を動かす Mac に挿すこと。MIDI は USB なので。
MSG
