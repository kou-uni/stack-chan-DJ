#!/bin/zsh
# vendor/ に当てた改変を、**リポジトリで運べる形**（.patch）に書き出す。
#
# ★なぜ要るか（2026-09-15）
#   vendor/ は大きいので git 管理外にしてある。**だが改変が入っている。**
#   改変は `docs/vendor-patches.md` に文章で残してあるが、
#   **文章からは復元できない。** 別の Mac で取り直したら、手で当て直すことになる。
#   当日それをやるのは事故。**機械が当てられる形にしておく。**
#
#   使い方（改変を足したら、そのつど）:
#       ./scripts/pack-patches.sh
#       git add vendor-patches && git commit
set -euo pipefail
cd "$(dirname "$0")/.."
OUT=vendor-patches
mkdir -p "$OUT"

for d in vendor/*/; do
  name=$(basename "$d")
  [ -d "$d/.git" ] || continue
  url=$(git -C "$d" remote get-url origin 2>/dev/null || true)
  # ★このリポジトリ自身を指しているもの（= ただの置き場）は対象外
  case "$url" in *stack-chan-DJ*|"") echo "  － $name（取り直す対象ではない）"; continue;; esac

  rev=$(git -C "$d" rev-parse HEAD)
  if git -C "$d" diff --quiet && [ -z "$(git -C "$d" ls-files --others --exclude-standard)" ]; then
    echo "  ○ $name  改変なし（$rev）"
    printf '%s %s\n' "$name" "$rev" > "$OUT/$name.pin"
    rm -f "$OUT/$name.patch"
    continue
  fi
  git -C "$d" diff > "$OUT/$name.patch"
  printf '%s %s\n' "$name" "$rev" > "$OUT/$name.pin"
  n=$(grep -c '^+++' "$OUT/$name.patch" || true)
  echo "  ✓ $name  ${n}ファイルぶんを $OUT/$name.patch に（版 $rev）"

  # ★未追跡ファイルは diff に出ない。**黙って落ちるので、必ず言う**
  un=$(git -C "$d" ls-files --others --exclude-standard)
  if [ -n "$un" ]; then
    echo "    ★ 追跡外のファイルがあります。patch には入りません:"
    echo "$un" | sed 's/^/      /'
  fi
done

echo
echo "書き出しました。git add vendor-patches && git commit してください。"
