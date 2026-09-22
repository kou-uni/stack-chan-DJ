#!/usr/bin/env python3
"""「この機械で直したものは、もう1台に伝わるか」を見る。

    ./.venv/bin/python scripts/sync_check.py

## なぜ要るか（2026-09-23）

当日は **MacBook**、家では **Mac Studio**。同じものを2回直すと、片方が必ず古くなる。
方針は最初から1つ ── **コードは1本。機械ごとに変えるのは設定だけ。**

問題は、**方針を守れているかが目で見えないこと。**
伝わらないのは「git に入っていないもの」だけなので、そこだけを数える。

★**生成できるものは、持ち運ばない。**表情の画像は `make_faces.py` から作り直せるので
  git に無くてよい。**作り直せないのに git に無いものだけが、二度手間になる。**
"""
from __future__ import annotations

import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

# ★追跡外でよいもの。**作り直せる／その機械のもの／人の声**
REGENERABLE = (
    "app/avatar/",        # make_faces.py + pack_avatar.py で作る
    "build/",             # ファームのビルド作業場
    "vendor/",            # clone し直して vendor-patches/ を当てる
    "firmware/", "backup/",
    ".venv/", "__pycache__/", ".pytest_cache/", ".coverage", ".DS_Store",
    "event/rec/",         # ★人の声。入れてはいけない
    ".env", "server/.env",
)


def sh(*args: str, cwd: Path | None = None) -> str:
    return subprocess.run(args, cwd=cwd or ROOT,
                          capture_output=True, text=True).stdout


def _kv(path: Path) -> dict[str, str]:
    out: dict[str, str] = {}
    if not path.exists():
        return out
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if line and not line.startswith("#") and "=" in line:
            k, v = line.split("=", 1)
            out[k.strip()] = v.strip()
    return out


def env_drift() -> list[str]:
    """調整した値が、その機械の中だけに残っていないか。

    ★`.env.gateway` は git に入らない。**ここで調整すると、もう1台には伝わらない。**
      秘密は入っていないので、**調整は見本（git）の側に書く。**
    """
    real, ex = _kv(ROOT / ".env.gateway"), _kv(ROOT / ".env.gateway.example")
    bad = [f"{k} が実物にだけある（見本に書けば、もう1台にも伝わります）"
           for k in sorted(set(real) - set(ex))]
    bad += [f"{k} の値が見本と違う（見本={ex[k]} 実物={real[k]}）"
            for k in sorted(set(real) & set(ex)) if real[k] != ex[k]]
    return bad


def vendor_drift() -> list[str]:
    """他人のコードへの改変が、差分として取り出してあるか。

    ★改変を `vendor/` に置いたままだと、**別の機械で復元できない。**
    """
    bad = []
    for d in sorted((ROOT / "vendor").glob("*")):
        if not (d / ".git").is_dir():
            continue
        cur = sh("git", "diff", cwd=d)
        patch = ROOT / "vendor-patches" / f"{d.name}.patch"
        saved = ""
        if patch.exists():
            text = patch.read_text(encoding="utf-8")
            i = text.find("diff --git")
            saved = text[i:] if i >= 0 else text
        if cur.strip() != saved.strip():
            bad.append(f"{d.name} の改変がパッチと違う"
                       "（./scripts/pack-patches.sh を走らせてください）")
    return bad


def stray_files() -> list[str]:
    """作り直せないのに、git に入っていないもの。"""
    out = sh("git", "status", "--porcelain", "--ignored")
    bad = []
    for line in out.splitlines():
        if not line.startswith(("!!", "??")):
            continue
        rel = line[3:].strip()
        if any(rel.startswith(p) or p in rel for p in REGENERABLE):
            continue
        bad.append(f"{rel} が git に入っていません")
    return bad


def main() -> int:
    groups = [("設定（.env.gateway）", env_drift()),
              ("他人のコードへの改変", vendor_drift()),
              ("置き去りのファイル", stray_files())]
    bad = 0
    for name, items in groups:
        if items:
            bad += len(items)
            print(f"\n★ {name}")
            for x in items:
                print(f"   {x}")
        else:
            print(f"  ○ {name} — もう1台にも伝わります")
    if bad:
        print(f"\n★{bad} 件。**このままだと、同じものを2回直すことになります。**")
        return 1
    print("\nこの機械で直したものは、bootstrap.sh だけでもう1台に載ります。")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
