#!/usr/bin/env python3
"""設定ファイル（config.toml）を読んで、CLI の既定値に流し込む。

## なぜ入れたか

引数が47個ある。会場でその場のノリを詰めるとき、
**47個を毎回打ち直すのは無理**だし、前回どう詰めたかも残らない。

## 優先順位

    CLI 引数  >  config.toml  >  コードの既定値

**CLI が一番強い。** これは変えない。
現場で1個だけ試したいときに、ファイルを開かずに済むため。

## 書き方

セクション名は読みやすさのためだけのもの。**どこに書いても動く。**

    [groove]
    full-level = 0.005
    stop-ratio = 0.7

キーは CLI と同じ綴り。`--full-level` なら `full-level`（`full_level` でも可）。
**綴りを間違えたら起動時に止まる。** 黙って無視されるのが一番こわい。
"""
from __future__ import annotations

import sys
import tomllib
from pathlib import Path

DEFAULT_PATH = Path(__file__).resolve().parent / "config.toml"


def load(parser, path: Path | None = None) -> Path | None:
    """config.toml を読んで parser の既定値を差し替える。読んだファイルを返す。"""
    path = path or DEFAULT_PATH
    if not path.exists():
        return None

    try:
        raw = tomllib.loads(path.read_text(encoding="utf-8"))
    except tomllib.TOMLDecodeError as exc:
        raise SystemExit(f"{path} が読めない: {exc}")

    flat = {}
    for key, val in raw.items():
        if isinstance(val, dict):                     # [section] の中身を平らにする
            for k, v in val.items():
                flat[k] = v
        else:
            flat[key] = val

    known = {a.dest for a in parser._actions if a.dest != "help"}
    out = {}
    for k, v in flat.items():
        dest = k.replace("-", "_")
        if dest not in known:
            near = sorted(n for n in known if n.startswith(dest[:4]))
            raise SystemExit(f"{path}: 知らない設定 '{k}'"
                             + (f"（もしかして: {', '.join(near)}）" if near else ""))
        out[dest] = tuple(v) if isinstance(v, list) else v

    parser.set_defaults(**out)
    return path
