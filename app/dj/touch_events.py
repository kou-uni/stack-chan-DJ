#!/usr/bin/env python3
"""頭なでの受け取り。**押し出し型で来るものを、押し出し型で受ける。**

## なぜこれが要るか（2026-09-12 の切り分け）

実機は撫でられると**通知を送っている**。

    {"event_type":"touch","subtype":"stroke","duration_ms":6500}

ところが `get_touch_state` は**その通知を保存しない**ので、いくら問い合わせても
`idle` が返る。**「問い合わせて読む」と思い込んでポーリングしていた。**

> **押し出されるものを、引きに行っても取れない。**
> 取れないときは「壊れている」ではなく「窓が違う」を先に疑う。

しかも通知の届け先は**既定で全部 false**（`~/.config/stackchan-mcp/notify.yml`）。
開けないとどこにも届かない。**沈黙は故障と見分けがつかない。**

## 届くタイミング（2026-09-12 実測）

**撫でている間は届かない。指を離した瞬間に、長さつきで1件届く。**

    stroke  250899ms   ← 4分11秒ずっと1件
    stroke   75999ms   ← 1分16秒
    stroke     900ms   ← ふつうの撫で

だから「撫でながら待つ」と、**永遠に来ないように見える**。
私はこれで「センサが壊れた」と判断しかけた。**離すまで来ないだけだった。**

> **押し出し型の通知は、いつ押し出されるのかまで確かめる。**

## なぜ JSONL か

- **ファイルなので確実**。gateway の再起動をまたげる
- console と gateway が別プロセスでも読める
- あとから当日のログとして見返せる（データループ P9）
"""
from __future__ import annotations

import json
import os
import time
from pathlib import Path

DEFAULT_PATH = Path.home() / ".claude" / "stackchan-events.jsonl"
CONFIG_PATH = Path.home() / ".config" / "stackchan-mcp" / "notify.yml"


def notify_config_ok(path: Path = CONFIG_PATH) -> tuple[bool, str]:
    """通知の届け先が開いているか。**既定は全部 false。**

    ★開いていないと永遠に何も来ない。**起動時に気づけるようにする。**
    """
    if not path.exists():
        return False, f"{path} が無い（通知の届け先が全部閉じている）"
    try:
        body = path.read_text(encoding="utf-8")
    except OSError as exc:
        return False, f"{path} が読めない（{exc}）"
    # yaml を読まずに済ませる（依存を増やさない）。jsonl セクションだけ見る
    in_jsonl = False
    for line in body.splitlines():
        s = line.strip()
        if s.startswith("jsonl:"):
            in_jsonl = True
            continue
        if in_jsonl:
            if s.startswith("enabled:"):
                return ("true" in s.lower(),
                        "jsonl が有効" if "true" in s.lower()
                        else "jsonl が false のまま（撫でても届かない）")
            if s and not s.startswith(("-", "#")) and not line.startswith((" ", "\t")):
                break
    return False, "notify.yml に jsonl の設定が無い"


class TouchEvents:
    """撫でられた通知を、追記ファイルから拾う。

    ★同じ撫でを二度返さない（会話が二回起動する）。
    ★起動前の古い記録は無視する（起動した瞬間に過去の撫でで動き出すと事故）。
    """

    def __init__(self, path: Path | None = None, max_age_s: float = 20.0,
                 max_stroke_ms: int = 8000):
        self.path = Path(path) if path else DEFAULT_PATH
        self.max_age_s = max_age_s
        # ★長すぎる撫では「置きっぱなし」。合図にしない
        self.max_stroke_ms = max_stroke_ms
        self._offset = 0
        self._pending: list[dict] = []

    def catch_up(self) -> None:
        """いまある分は「読んだこと」にする。起動時に一度だけ呼ぶ。"""
        try:
            self._offset = self.path.stat().st_size
        except OSError:
            self._offset = 0

    def poll(self) -> dict | None:
        """新しく増えた撫でを1つ返す。無ければ None。"""
        if not self._pending:
            self._read_new()
        while self._pending:
            ev = self._pending.pop(0)
            age = time.time() - float(ev.get("ts_unix") or 0)
            dur = int(ev.get("duration_ms") or 0)
            # ★長く止まっていた間の撫でを、復帰した瞬間にまとめて処理しない
            if age > self.max_age_s:
                continue
            # ★置きっぱなし（何かが載っている）を会話の合図にしない
            if dur > self.max_stroke_ms:
                continue
            return ev
        return None

    def _read_new(self) -> None:
        try:
            size = self.path.stat().st_size
        except OSError:
            return
        if size < self._offset:          # 切り詰められた（ログ回転など）
            self._offset = 0
        if size == self._offset:
            return
        try:
            with self.path.open("r", encoding="utf-8") as f:
                f.seek(self._offset)
                chunk = f.read()
                self._offset = f.tell()
        except OSError:
            return
        for line in chunk.splitlines():
            line = line.strip()
            if not line:
                continue
            try:
                ev = json.loads(line)
            except ValueError:
                continue                  # 壊れた行は飛ばす
            if ev.get("event_type") == "touch":
                self._pending.append(ev)
