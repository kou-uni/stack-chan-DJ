#!/bin/zsh
# 新しい Mac を、一から当日の形にする。
#
# ★これ1本で終わるようにしてある（2026-09-15）。
#   手で運ぶものは無い。足りないものは取ってくるか、その場で作る。
#
#   使い方:
#       git clone https://github.com/kou-uni/stack-chan-DJ.git
#       cd stack-chan-DJ && ./scripts/bootstrap.sh
#
#   途中で止まったら、**そこだけ直してもう一度走らせる**。
#   何度走らせても同じ結果になるように書いてある（冪等）。
#
# ★設計の考え方
#   - **止まるときは日本語で理由を言う。** 「失敗しました」で終わらせない
#   - **既にあるものは触らない。** 取り直して壊すより、あるものを使う
#   - 最後は必ず doctor.py。**「入った」ではなく「動く」で判定する**
set -uo pipefail
cd "$(dirname "$0")/.."
ROOT=$(pwd)

SKIP_MODEL=0
SKIP_VOICEVOX=0
SKIP_SERVICE=0
for a in "$@"; do
  case "$a" in
    --skip-model)    SKIP_MODEL=1 ;;
    --skip-voicevox) SKIP_VOICEVOX=1 ;;
    --skip-service)  SKIP_SERVICE=1 ;;   # ★検証用。常駐を触らない
    -h|--help)
      echo "使い方: ./scripts/bootstrap.sh [--skip-model] [--skip-voicevox] [--skip-service]"; exit 0 ;;
  esac
done

ok(){    print -P "%F{green}  ○%f $1" }
warn(){  print -P "%F{yellow}  △%f $1" }
die(){   print -P "%F{red}  ×%f $1"; echo; print -P "%F{red}ここで止めます。上の理由を直して、もう一度走らせてください。%f"; exit 1 }
step(){  echo; print -P "%F{cyan}── $1%f" }

# ── 0. 前提 ─────────────────────────────────
step "0. 前提を確かめる"

[ "$(uname)" = "Darwin" ] || die "macOS でしか動きません（uname=$(uname)）"
[ "$(uname -m)" = "arm64" ] || warn "Apple Silicon ではありません。VOICEVOX の取得先が違います"

if ! command -v git >/dev/null; then
  die "git がありません。'xcode-select --install' を先に実行してください"
fi
ok "git $(git --version | awk '{print $3}')"

if ! command -v brew >/dev/null; then
  die "Homebrew がありません。https://brew.sh の1行を実行してから、もう一度"
fi
ok "Homebrew あり"

PY=$(command -v python3.14 || command -v python3 || true)
[ -n "$PY" ] || die "python3 がありません。'brew install python@3.14' を実行してください"
PYV=$("$PY" -c 'import sys;print("%d.%d"%sys.version_info[:2])')
ok "Python $PYV  ($PY)"

# 空き容量。VOICEVOX 2GB + モデル 3.3GB + 依存で 8GB は見ておく
FREE=$(df -g . | tail -1 | awk '{print $4}')
[ "$FREE" -ge 8 ] || die "空き容量が ${FREE}GB しかありません。8GB 以上あけてください"
ok "空き ${FREE}GB"

# ── 1. Python の環境 ───────────────────────────
step "1. Python の環境を作る"
if [ ! -d .venv ]; then
  "$PY" -m venv .venv || die "venv を作れませんでした"
fi
./.venv/bin/pip install -q --upgrade pip
./.venv/bin/pip install -q -r requirements-dev.txt \
  || die "依存を入れられませんでした（requirements-dev.txt）"
ok "依存を入れました"

# ── 2. vendor ─────────────────────────────────
step "2. vendor を取ってくる"
mkdir -p vendor

clone_pinned(){   # 名前 URL
  local name=$1 url=$2 dir="vendor/$1" pin="vendor-patches/$1.pin"
  local rev=""
  [ -f "$pin" ] && rev=$(cut -d' ' -f2 "$pin")
  if [ -d "$dir/.git" ]; then
    ok "$name は既にあります（触りません）"
    return 0
  fi
  git clone -q "$url" "$dir" || die "$name を clone できませんでした（$url）"
  if [ -n "$rev" ]; then
    git -C "$dir" checkout -q "$rev" \
      || die "$name の版 $rev が見つかりません。vendor-patches/$name.pin を確かめてください"
    ok "$name  版 ${rev:0:7} に固定"
  else
    warn "$name  版の固定がありません（最新を取りました）"
  fi
  # ★改変を当て直す。**文章からは復元できないので patch で運んでいる**
  if [ -f "vendor-patches/$name.patch" ]; then
    git -C "$dir" apply --check "$ROOT/vendor-patches/$name.patch" \
      || die "$name の改変が当たりません。版がずれています（docs/vendor-patches.md）"
    git -C "$dir" apply "$ROOT/vendor-patches/$name.patch"
    ok "$name  改変を当てました"
  fi
}

clone_pinned stackchan-mcp  https://github.com/kisaragi-mochi/stackchan-mcp.git
clone_pinned m5stack-avatar https://github.com/meganetaaan/m5stack-avatar.git

./.venv/bin/pip install -q -e './vendor/stackchan-mcp/gateway[stt-faster-whisper,tts]' \
  || die "gateway を入れられませんでした"
ok "gateway を入れました"

# ── 3. VOICEVOX ───────────────────────────────
step "3. VOICEVOX（声）"
VV_VER=0.25.2
VV_DIR=vendor/voicevox/macos-arm64
if [ "$SKIP_VOICEVOX" = "1" ]; then
  warn "--skip-voicevox が指定されたので飛ばします"
elif [ -x "$VV_DIR/run" ]; then
  ok "VOICEVOX は既にあります"
else
  echo "    2GB ほど落とします。回線によっては数分かかります…"
  mkdir -p vendor/voicevox
  T=$(mktemp -d)
  BASE="https://github.com/VOICEVOX/voicevox_engine/releases/download/$VV_VER"
  ARCH=$(uname -m)
  # ★名前は版で変わる。**決め打ちしてから、外れたら一覧に聞きに行く**
  ASSET="voicevox_engine-macos-${ARCH}-${VV_VER}.7z.001"
  if ! curl -fsIL -o /dev/null "$BASE/$ASSET" 2>/dev/null; then
    ASSET=$(curl -fsSL "https://api.github.com/repos/VOICEVOX/voicevox_engine/releases/tags/$VV_VER" 2>/dev/null \
      | "$ROOT/.venv/bin/python" -c "
import sys, json
try: d = json.load(sys.stdin)
except Exception: sys.exit(0)
for a in d.get('assets', []):
    n = a['name']
    if 'macos' in n and '$ARCH' in n and n.endswith('.7z.001'):
        print(n); break
")
  fi
  if [ -n "$ASSET" ] && curl -fL --retry 3 -o "$T/vv.7z.001" "$BASE/$ASSET" 2>/dev/null; then
    command -v 7zz >/dev/null || command -v 7z >/dev/null || brew install -q sevenzip
    (cd "$T" && (7zz x vv.7z.001 >/dev/null 2>&1 || 7z x vv.7z.001 >/dev/null 2>&1)) \
      || die "VOICEVOX を展開できませんでした"
    SRC=$(find "$T" -maxdepth 3 -name run -type f | head -1)
    [ -n "$SRC" ] || die "VOICEVOX の中身が想定と違います（run が見つからない）"
    mkdir -p "$VV_DIR" && cp -R "$(dirname "$SRC")"/* "$VV_DIR"/
    chmod +x "$VV_DIR/run"
    ok "VOICEVOX $VV_VER を入れました"
  else
    warn "自動で落とせませんでした。手で入れてください:"
    echo "      $BASE"
    echo "      展開して vendor/voicevox/macos-arm64/ に置く（run が直下に来るように）"
  fi
  rm -rf "$T"
fi

# ── 4. 頭脳 ───────────────────────────────────
step "4. 頭脳（Ollama）"
if [ "$SKIP_MODEL" = "1" ]; then
  warn "--skip-model が指定されたので飛ばします"
else
  command -v ollama >/dev/null || brew install -q ollama || die "ollama を入れられませんでした"
  ok "ollama あり"
  # ★常駐していないと pull も生成もできない
  pgrep -qf "ollama serve" || (nohup ollama serve >/tmp/ollama.log 2>&1 &)
  for i in {1..20}; do curl -fsS -m 2 http://127.0.0.1:11434/api/tags >/dev/null 2>&1 && break; sleep 1; done
  MODEL=$(./.venv/bin/python - <<'PY'
import pathlib, tomllib
try:
    d = tomllib.loads(pathlib.Path("app/dj/config.toml").read_text(encoding="utf-8"))
    print(d.get("think", {}).get("think-model", "gemma3:4b"))
except Exception:
    print("gemma3:4b")
PY
)
  if ollama list 2>/dev/null | grep -q "^${MODEL%%:*}"; then
    ok "モデル $MODEL は既にあります"
  else
    echo "    $MODEL を落とします（3GB前後）…"
    ollama pull "$MODEL" || die "$MODEL を落とせませんでした"
    ok "$MODEL を入れました"
  fi
fi

# ── 5. 設定 ───────────────────────────────────
step "5. 設定"
if [ -f .env.gateway ]; then
  ok ".env.gateway は既にあります（触りません）"
else
  cp .env.gateway.example .env.gateway || die ".env.gateway を作れませんでした"
  ok ".env.gateway を雛形から作りました"
fi

# ★頭脳の在処。この機械の中を指していることを確かめる
./.venv/bin/python - <<'PY'
import pathlib, tomllib
d = tomllib.loads(pathlib.Path("app/dj/config.toml").read_text(encoding="utf-8"))
url = d.get("think", {}).get("think-url", "")
mark = "  ○" if "127.0.0.1" in url or "localhost" in url else "  △"
print(f"{mark} 頭脳の在処: {url}")
if mark == "  △":
    print("     ★この機械の外を指しています。会場で使うなら 127.0.0.1 に戻すこと")
PY

# ── 6. 表情 ───────────────────────────────────
step "6. 表情のデータ"
if [ -f app/avatar/avatar_layered.raw ]; then
  ok "$(wc -c < app/avatar/avatar_layered.raw | tr -d ' ') バイト（既にあります）"
else
  ./.venv/bin/python app/avatar/make_faces.py  >/dev/null 2>&1 \
    || die "顔を描けませんでした（app/avatar/make_faces.py）"
  ./.venv/bin/python app/avatar/pack_avatar.py >/dev/null 2>&1 \
    || die "顔を固められませんでした（app/avatar/pack_avatar.py）"
  ok "$(wc -c < app/avatar/avatar_layered.raw | tr -d ' ') バイトを生成しました"
fi

# ── 7. 試験 ───────────────────────────────────
step "7. 試験"
./.venv/bin/python -m pytest tests/ -q || die "試験が落ちました。**ここから先へ進まないこと**"

# ── 8. 常駐 ───────────────────────────────────
step "8. 常駐にする"
if [ "$SKIP_SERVICE" = "1" ]; then
  warn "--skip-service が指定されたので飛ばします"
else
  ./scripts/service.sh install || die "常駐にできませんでした（scripts/service.sh）"
  ok "gateway と console をログイン時に上げるようにしました"
fi

echo
print -P "%F{green}── できました ──%f"
cat <<'MSG'

次にやること:

  1. VOICEVOX を上げる（声が要る）
       vendor/voicevox/macos-arm64/run --host 127.0.0.1 --port 50021 &

  2. 全部つながっているか見る
       ./.venv/bin/python scripts/doctor.py

  3. 実機の電源を入れて、同じ Wi-Fi に乗せる
       実機は mDNS で探すので、**本体の設定は触らない**

  4. DJ機材(DDJ-FLX2)を USB で挿す
       MIDI は USB。**console を動かすこの機械に挿すこと**

詰まったら docs/macbook-setup.md を見てください。
MSG
