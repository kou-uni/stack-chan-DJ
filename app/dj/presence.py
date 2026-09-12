#!/usr/bin/env python3
"""あるべき姿。**状態を持つのはここだけ。実機には書かない。**

設計は docs/architecture.md。この実装がそちらに従う。

## なぜ要るか

表情を19箇所・瞬きを12箇所から直接叩いていた。持ち主がいないので、
誰かが割り込むたびに壊れた（2026-09-09、踊りが止まらない／瞬きが消える）。

**命令をやめて、宣言にする。** ここに「いまどうあるべきか」を置き、
`reconcile.py` が差分だけを実機へ送る。順番の事故が構造的に起きなくなる。

## 3層（混ぜない）

    ① モード   人が決める      OFF / DJ
    ② 活動     音が決める      待機 / 計測中 / 踊り
    ③ 出来事   一時的な上書き  つまみ・撫で・サビ・歓声・顔検出

★③ は**必ず期限を持つ**。期限のない上書きは消し忘れが起きる。
"""
from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import Callable

MODE_IDLE = "off"
MODE_DJ = "dj"

MODE_LABEL = {MODE_IDLE: "OFF（音に反応しない）", MODE_DJ: "DJ（音に反応する）"}
MODE_FACE = {MODE_IDLE: "idle", MODE_DJ: "happy"}
MODE_ORDER = (MODE_IDLE, MODE_DJ)
MODE_LED = {MODE_IDLE: (0, 30, 70), MODE_DJ: (130, 0, 70)}

# ★会話中の顔。**聞いている姿が見えると、話しかけやすい。**
#   LED（緑＝聞く／青＝喋る）と対になる。顔でも分かるようにする。
TALK_FACE = {"listening": "thinking", "speaking": "happy"}

# 出来事の優先順。小さいほど強い。docs/architecture.md §2③ と同じ順。
PRIORITY = ("knob", "touch", "listen", "drop", "cheer", "face")


@dataclass
class Overlay:
    face: str
    until: float
    priority: int


@dataclass
class Presence:
    """いまどうあるべきか。**実機を触らない。計算するだけ。**"""

    mode: str = MODE_IDLE
    dancing: bool = False                          # ② 活動：踊っている
    talk: str | None = None                        # ② 活動："listening" / "speaking"
    dance_face: str = "happy"                      # 踊っている間の顔
    now: Callable[[], float] = time.time
    _overlays: dict[str, Overlay] = field(default_factory=dict)

    # ── ③ 出来事 ────────────────────────────────────
    def overlay(self, kind: str, face: str, seconds: float) -> None:
        """一時的に顔を上書きする。**期限は必須。**"""
        if kind not in PRIORITY:
            raise ValueError(f"知らない出来事: {kind}（PRIORITY に足すこと）")
        if seconds <= 0:
            raise ValueError("期限のない上書きは作らない")
        self._overlays[kind] = Overlay(face, self.now() + seconds,
                                       PRIORITY.index(kind))

    def clear(self, kind: str) -> None:
        self._overlays.pop(kind, None)

    def _live(self) -> Overlay | None:
        t = self.now()
        for k in [k for k, o in self._overlays.items() if o.until <= t]:
            del self._overlays[k]                  # 期限切れは消す
        return min(self._overlays.values(), key=lambda o: o.priority,
                   default=None)

    # ── あるべき姿 ──────────────────────────────────
    def desired(self) -> dict:
        """実機がこうあるべき、という一式。docs/architecture.md §3 の表。"""
        top = self._live()

        if top is not None:
            face = top.face
        elif self.talk in TALK_FACE:
            # ★つまみや撫でには負ける（直接触られている方が強い）。
            #   だが踊りよりは強い。会話中は会話の顔を出す
            face = TALK_FACE[self.talk]
        elif self.mode == MODE_DJ and self.dancing:
            face = self.dance_face
        else:
            face = MODE_FACE[self.mode]

        # ★瞬きを止めるのは「顔を作っているとき」だけ。それ以外は必ず ON。
        blink = not (top is not None
                     or self.talk in TALK_FACE          # 会話中は顔を作っている
                     or (self.mode == MODE_DJ and self.dancing))

        return {
            "talk": self.talk,
            "face": face,
            "blink": blink,
            # ★gateway 側の踊りは**常に切る**。
            #   首とLEDを動かす人が2人いてはいけない（設計 I2）。
            #   実機を動かすのは console のストリームだけ。
            #   `beat_mode_start` はこれを有効にして始まるので、毎回切り直す。
            #   （2026-09-09、診断ツールがここを有効にして暴走した）
            "beat_motion": False,
            "led_rgb": MODE_LED[self.mode],
        }

    # ── 見せる用 ────────────────────────────────────
    def describe(self) -> str:
        d = self.desired()
        top = self._live()
        return (f"モード={self.mode} 踊り={self.dancing} "
                f"出来事={top and [k for k, o in self._overlays.items() if o is top][0]} "
                f"→ 顔={d['face']} 瞬き={d['blink']} 踊らせる={d['beat_motion']}")
