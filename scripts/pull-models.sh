#!/usr/bin/env bash
# 当日に要る Ollama のモデルを全部そろえる（無いものだけ落とす）。
#   ./scripts/pull-models.sh
# ★2026-09-29：bootstrap は think-model（gemma3:4b）しか落としていなかった。質疑応答 bot の
#   qwen2.5:14b（約9GB）が MacBook に無いと、当日 D ブロックで bot が黙る。ここで両方そろえる。
set -uo pipefail
cd "$(dirname "$0")/.."
PY=./.venv/bin/python
pgrep -qf "ollama serve" || (nohup ollama serve >/tmp/ollama.log 2>&1 &)
for i in {1..20}; do curl -fsS -m 2 http://127.0.0.1:11434/api/tags >/dev/null 2>&1 && break; sleep 1; done
THINK=$($PY - <<'PY'
import pathlib, tomllib
try:
    print(tomllib.loads(pathlib.Path("app/dj/config.toml").read_text(encoding="utf-8")).get("think", {}).get("think-model", "gemma3:4b"))
except Exception:
    print("gemma3:4b")
PY
)
QA=$($PY -c "import sys; sys.path.insert(0,'app/dj'); import ask; print(ask.DEFAULT_MODEL)")
rc=0
for M in "$THINK" "$QA"; do
  if ollama list 2>/dev/null | awk '{print $1}' | grep -qx "$M"; then echo "  ○ $M あり"
  else echo "  … $M を落とします"; ollama pull "$M" && echo "  ○ $M を入れました" || { echo "  ★ $M を落とせませんでした"; rc=1; }; fi
done
exit $rc
