#!/usr/bin/env python3
"""当日の音声を録って、文字起こしして、締めの素材にする。仕様は tests/test_meeting.py。

## 何のため（2026-09-12 本人の要望）

**その日に起きたこと・頑張ったことを、締めの挨拶に織り込む。**
台本を前もって書くのではなく、**その場で起きたことを喋る。** ライブ感。

## ゆずれないこと

**音声は部屋の外に出さない。** 当日のメッセージそのもの。
録音（ffmpeg）も文字起こし（faster-whisper）も、この Mac の中だけで終わる。

**録るのは Mac のマイク。** スタックチャンのマイクは会話に専念させる（本人の指示）。

## 作り

    ffmpeg が60秒ごとに wav を吐く
      → 書き終わったものだけ拾う
        → faster-whisper で起こす
          → transcript.jsonl に積む

**録りながら起こす。** 終わってから30分待つと、締めに間に合わない。
"""
from __future__ import annotations

import json
import re
import time
from pathlib import Path

# ★ffmpeg が書いている途中のファイルを掴まない。
#
#   2026-09-12 実地：更新時刻だけで判定したら**空のヘッダだけを掴んだ。**
#   ffmpeg は wav のヘッダを先に書いて、中身を後から流し込む。だから
#   作った直後のファイルが「3秒なにも書かれていない」ように見える。
#
#   **確実なのは「次の塊が出来ているか」。** 出来ていれば ffmpeg は先へ進んでいる。
#   最後の1つだけは次が来ないので、録音が閉じたと分かってから拾う。
QUIET_S = 3.0
MIN_BYTES = 4096          # ★止めた瞬間にできる殻。失敗として数えない

# whisper が無音で吐く定型。★素材に混ざると邪魔
NOISE = ("ご視聴ありがとうございました", "ありがとうございました",
         "おやすみなさい", "チャンネル登録", "字幕", "Thank you", "you")


def finished_chunks(d: Path, quiet_s: float = QUIET_S,
                    closed: bool = False) -> list[Path]:
    """書き終わった塊を、順番に返す。

    closed : 録音が終わっているか。**最後の1つは次が来ないので、これで拾う。**
    """
    now = time.time()
    files = []
    for p in sorted(d.glob("*.wav")):
        try:
            st = p.stat()
        except OSError:
            continue
        if st.st_size < MIN_BYTES:
            continue                      # ★殻は拾わない
        files.append((p, st))

    out = []
    for i, (p, st) in enumerate(files):
        is_last = i == len(files) - 1
        if not is_last:
            out.append(p)                 # ★次がある＝ffmpeg は先へ進んだ
        elif closed and now - st.st_mtime >= quiet_s:
            out.append(p)
    return out


class Transcript:
    """文字起こしの積み上げ。**同じ塊を二度処理しない。**

    ★途中で落ちて再開しても重複しない。3時間の録音では必ず何か起きる。
    """

    def __init__(self, path: Path):
        self.path = Path(path)
        self._done: set[str] = set()
        self._rows: list[dict] = []
        self._load()

    def _load(self) -> None:
        try:
            body = self.path.read_text(encoding="utf-8")
        except OSError:
            return
        for line in body.splitlines():
            if not line.strip():
                continue
            try:
                r = json.loads(line)
            except ValueError:
                continue                      # ★壊れた行は飛ばす。全体を捨てない
            self._done.add(r.get("chunk", ""))
            if (r.get("text") or "").strip():
                self._rows.append(r)

    def done(self, chunk: str) -> bool:
        return chunk in self._done

    def add(self, chunk: str, at_s: float, text: str) -> None:
        """1塊ぶん積む。**空でも「処理済み」の印は残す**（二度やらないため）。"""
        r = {"chunk": chunk, "at": round(at_s, 1), "text": (text or "").strip()}
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self.path.open("a", encoding="utf-8") as f:
            f.write(json.dumps(r, ensure_ascii=False) + "\n")
        self._done.add(chunk)
        if r["text"]:
            self._rows.append(r)

    def lines(self) -> list[dict]:
        return list(self._rows)


def _clock(s: float) -> str:
    return f"{int(s) // 60}:{int(s) % 60:02d}"


def highlights(rows: list[dict], drop_repeats: bool = True) -> str:
    """締めの素材にする。**読むのは人（とわたし）。機械向けに整えない。**

    ★whisper は無音で同じ定型を繰り返す。**畳まないと素材が汚れる。**
    """
    out: list[str] = []
    seen: set[str] = set()
    for r in rows:
        t = re.sub(r"\s+", " ", (r.get("text") or "")).strip()
        if not t:
            continue
        if drop_repeats:
            key = t[:24]
            if key in seen:
                continue
            if any(n in t for n in NOISE) and len(t) < 30:
                if key in seen:
                    continue
            seen.add(key)
        out.append(f"[{_clock(r.get('at', 0))}] {t}")
    return "\n".join(out)
