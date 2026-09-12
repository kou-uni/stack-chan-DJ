#!/usr/bin/env python3
"""外から操作するパネルの中身。仕様は tests/test_panel.py。ROADMAP Phase 2。

## 誰が、どこで（CLAUDE.md §1.5）

**本人・外出先・スマホ・片手。** 家のロボットは見えない。

- 押すのは**大きなボタン数個**。文字入力は最後の手段
- **動いた証拠を返す**。ロボット自身のカメラで撮って見せる
- **公開されている前提**で作る。URLが短くても、公開は公開

## 書き手を増やさない

パネルは**実機に直接書かない**。console の `presence` / `pose` を動かすだけ。
console が唯一の書き手（architecture.md I2）という前提を、パネルで壊さない。
写真と発話だけは実機を呼ぶ（状態を持たないので、取り合いにならない）。
"""
from __future__ import annotations

import asyncio
import contextlib
import hmac
import json
import re
import secrets
from dataclasses import dataclass
from pathlib import Path

from led import LedState

TOKEN_PATH = Path.home() / ".config" / "stackchan" / "panel-token"

# ★可動域。超えるとサーボが潰れる（yaw ±90 / pitch は45からの差 ±40）
#
# ★pitch は**大きいほど上**。2026-09-12 に実機で撮って確かめた:
#     pitch 10 → 観葉植物・窓・床のあたり ＝ 下
#     pitch 80 → 天井の見切り             ＝ 上
#   コード内のコメント（「45 を送ると真下になる」）を測らずに信じて逆にしていた。
#   **書かれていることではなく、撮って確かめたことを仕様にする。**
# ★1つのボタンは1つの軸だけ動かす。**触っていない軸は保つ。**
#   （2026-09-12：下を向いてから左を押すと、首を上げながら横を向いていた）
#   None = その軸は今のまま
HEAD = {
    "left":   (-55, None),
    "right":  (55, None),
    # ★±35（絶対 10〜80）。可動域は±40 だが、端ちょうどは張り付きやすい。
    #   絶対 10 と 80 は実写で確認済み（2026-09-12）
    "up":     (None, 35),
    "down":   (None, -35),
    # ★「まんなか」は**中央に戻す指示**。固定を外すだけだと、その場に残る
    #   （実測 2026-09-12: center を押しても (53,44) のまま動かなかった）
    "center": (0, 0),
}

FACES = ("happy", "surprised", "embarrassed", "sad", "thinking", "idle", "sleepy")

# ★喋らせる長さの上限。長文を流し込まれると読み上げが終わらない
SAY_MAX = 60


# ── 鍵 ────────────────────────────────────────────
def make_token() -> str:
    return secrets.token_hex(16)


def check_token(given: str | None, real: str) -> bool:
    """★時間差で当てられないように比べる。空は必ず拒否。"""
    if not given or not real:
        return False
    return hmac.compare_digest(str(given), str(real))


def load_token(path: Path = TOKEN_PATH) -> str:
    """鍵を読む。無ければ作る。**リポジトリには置かない。**"""
    try:
        t = path.read_text(encoding="utf-8").strip()
        if t:
            return t
    except OSError:
        pass
    path.parent.mkdir(parents=True, exist_ok=True)
    t = make_token()
    path.write_text(t, encoding="utf-8")
    path.chmod(0o600)
    return t


# ── 操作 ──────────────────────────────────────────
def _ok(con, **kw) -> dict:
    """★状態を必ず一緒に返す。**往復を2回すると、その分だけ遅く感じる。**"""
    return {"ok": True, "state": panel_state(con), **kw}


async def apply_action(con, action: str, value: str) -> dict:
    """1つの操作を実行する。**知らない指示は例外にする。**

    ★黙って無視しない。**沈黙は故障と見分けがつかない。**
    """
    if action == "head":
        if value not in HEAD:
            raise ValueError(f"知らない向き: {value}")
        want = HEAD[value]
        cur = con.pose.hold or (0, 0)
        con.pose.hold = (cur[0] if want[0] is None else want[0],
                         cur[1] if want[1] is None else want[1])
        return _ok(con, head=value)

    if action == "face":
        if value not in FACES:
            raise ValueError(f"知らない顔: {value}")
        con.presence.overlay("knob", value, 6.0)   # ★期限は必須
        return _ok(con, face=value)

    if action == "mode":
        if value not in ("off", "dj"):
            raise ValueError(f"知らないモード: {value}")
        con.presence.mode = value
        if value == "dj":
            # ★踊るなら首を返す。握ったままだと踊れない
            con.pose.hold = None
        return _ok(con, mode=value)

    if action == "led":
        if value not in LedState.PATTERNS:
            raise ValueError(f"知らない模様: {value}")
        con.led.show_pattern(value)             # ★音と関係なく光る
        return _ok(con, led=value)

    if action == "say":
        text = (value or "").strip()[:SAY_MAX]
        if not text:
            raise ValueError("喋る内容が空")
        await con.gw.call("say", text=text, speaker_id=14)
        return _ok(con, said=text)

    if action == "photo":
        r = await con.gw.call("take_photo", question="いま何が見えますか")
        body = r.content[0].text if getattr(r, "content", None) else "{}"
        try:
            d = json.loads(body)
        except ValueError:
            d = {"raw": body[:200]}
        return _ok(con, image_path=d.get("image_path"), answer=d.get("answer"))

    raise ValueError(f"知らない操作: {action}")


def panel_state(con) -> dict:
    """いま何が起きているか。**外から見えないものを、見えるようにする。**"""
    d = con.presence.desired()
    return {
        "mode": con.presence.mode,
        "dancing": bool(con.presence.dancing),
        "talk": con.presence.talk,
        "pattern": con.led.pattern,
        "bpm": float(getattr(con.led, "bpm", 0) or 0),
        "face": d.get("face"),
        "head": list(con.pose.hold) if con.pose.hold else None,
    }


class CameraFeed:
    """カメラ映像を流し続ける。**押さなくても映っている**ための仕組み。

    ## なぜ（2026-09-12、本人の指摘）

    > **「今見るって押したら見れる感じか。それはUXが悪いね」**

    そのとおり。**来た目的そのものを押させていた。**
    外にいる人にはロボットが見えない。**主役は映像で、それは既定で動いているべき。**

    実測: 1枚 0.40〜0.81秒 / 11KB → **1.9コマ/秒**。動画として成立する。

    ## 決めごと

    - **実機は1台。** 見る人が何人でも、撮る輪は1つ
    - **誰も見ていないときは撮らない。** 実機が熱を持つし、無駄
    - **1枚撮り損ねても止まらない。** 沈黙より、少し古い絵のほうがまし
    """

    def __init__(self, capture, interval_s: float = 0.55):
        self._capture = capture
        self.interval_s = interval_s
        self.latest: bytes | None = None
        self.stamp: float = 0.0
        self._viewers = 0
        self._task: asyncio.Task | None = None
        self._tick = asyncio.Event()      # 新しい絵が来たことを知らせる

    @property
    def viewers(self) -> int:
        """いま何人が見ているか。**外から確かめられるようにする。**"""
        return self._viewers

    @contextlib.asynccontextmanager
    async def viewer(self):
        """見ている間だけ撮る。**抜けたら必ず減らす。**"""
        self._viewers += 1
        if self._task is None or self._task.done():
            self._task = asyncio.ensure_future(self._loop())
        try:
            yield self
        finally:
            self._viewers -= 1
            if self._viewers <= 0 and self._task:
                self._task.cancel()
                self._task = None

    async def wait_new(self, timeout: float = 5.0) -> bytes | None:
        """次の絵を待つ。無ければいまある絵を返す。"""
        with contextlib.suppress(asyncio.TimeoutError):
            await asyncio.wait_for(self._tick.wait(), timeout)
        self._tick.clear()
        return self.latest

    async def _loop(self) -> None:
        import time
        while self._viewers > 0:
            t0 = time.time()
            try:
                img = await self._capture()
                if img:
                    self.latest, self.stamp = img, time.time()
                    self._tick.set()
            except asyncio.CancelledError:
                raise
            except Exception:
                pass                       # ★1枚落としても止めない
            rest = self.interval_s - (time.time() - t0)
            if rest > 0:
                await asyncio.sleep(rest)


class AskDesk:
    """パネルから投げられた質問に、声と文字で答える。

    ## 誰が使うか

    **外出先の本人。声は聞こえない。** 当日は「もくもくタイム中の質問受け」になる。

    - **答えは声と文字の両方。** 喋らせて終わりは、外では無反応と同じ
    - **喋るのは短く、画面には全文。** 声と文字で役割が違う
    - Ollama は数秒かかる。**待っていると分かるようにする**

    ★実機は1台。**連打されても順番に捌く。**
    """

    NO_ANSWER = "うーん、それはちょっと分からないです"

    def __init__(self, think=None, keep: int = 12):
        self._think = think
        self._keep = keep
        self._log: list[dict] = []
        self._lock = asyncio.Lock()

    def history(self) -> list[dict]:
        return list(self._log)

    async def ask(self, con, text: str) -> dict:
        import time
        q = (text or "").strip()
        # ★空を投げると、知識をそのまま読み上げる（実測）
        if not q:
            return {"q": q, "full": "", "spoken": "", "ms": 0}

        async with self._lock:                 # ★実機は1台。順番に
            t0 = time.time()
            _talk(con, "speaking")
            try:
                full = await self._answer(q)
                if not full:
                    full = self.NO_ANSWER      # ★無言が一番壊れて見える
                spoken = self._speak_text(full)
                if spoken:
                    await con.gw.call("say", text=spoken, speaker_id=14)
            finally:
                _talk(con, None)
            rec = {"q": q, "full": full, "spoken": spoken,
                   "ms": int((time.time() - t0) * 1000)}
            self._log.append(rec)
            del self._log[:-self._keep]
            return rec

    async def _answer(self, q: str) -> str:
        if self._think is not None:
            return (await self._think(q)) or ""
        from talk import think                 # ★遅延 import（試験で ollama を要求しない）
        return await think(q)

    # ★会場の40字は「人が待っている」から。**パネルは読める。**
    #   同じ制約を持ち込むと、1文目が切れて「続きは…」だけが流れる（2026-09-12 実地）
    SPEAK_MAX = 90

    @classmethod
    def _speak_text(cls, full: str) -> str:
        from talk import _speakable
        t = _speakable(full)
        if not t:
            return ""
        if len(t) <= cls.SPEAK_MAX:
            return t
        # ★文の切れ目でしか切らない。途中で切ると意味が壊れる
        head = ""
        for mark in ("。", "！", "？"):
            i = t.rfind(mark, 0, cls.SPEAK_MAX)
            if i > len(head):
                head = t[:i + 1]
        return head or t[:cls.SPEAK_MAX]


# ── 長いセリフを読ませる ────────────────────────────
#
# Claude Code が書いた文章を、スタックチャンに読ませる（2026-09-12 本人の要望）。
# **Ollama の短い返答とは役割が違う。こちらは長くてよく、質が要る。**

SPEECH_LIMIT = 80        # 1回に読ませる長さ。★長すぎると読み上げが崩れる
FACES_OK = ("happy", "surprised", "embarrassed", "sad", "thinking",
            "idle", "sleepy", "angry", "doubt")

# ★話しているのに固まっていると、読み上げ機に見える（2026-09-12 本人の指摘）。
#   (yaw, pitch差) の列。**pitch は45度からの差。** 大きく振らない ——
#   人は喋りながら首を大きく回さない。**小さく、間を持って動く**
MOVES: dict[str, tuple[tuple[float, float], ...]] = {
    "nod":    ((0, -14), (0, 8), (0, -11), (0, 6), (0, -8), (0, 3)),   # うなずく
    "tilt":   ((16, 6), (22, 10), (14, 5), (20, 9)),                   # かしげる
    "look_l": ((-40, 4), (-34, 8), (-44, 3), (-36, 6)),                # 左を見る
    "look_r": ((40, 4), (34, 8), (44, 3), (36, 6)),                    # 右を見る
    "scan":   ((-38, 5), (-12, 2), (16, 6), (40, 3), (10, 5), (-16, 2)),  # 見回す
    "perk":   ((0, 16), (6, 12), (-5, 15), (0, 11)),                   # 顔を上げる
    # ★はしゃぐ用。**言い切るところで大きく振る**
    "bounce": ((0, 18), (0, -12), (0, 16), (0, -8), (0, 14), (0, -6)),  # 跳ねる
    "shake":  ((-20, 4), (20, 4), (-16, 6), (16, 6), (-11, 3), (11, 3)),  # ぶんぶん
    "swing":  ((-34, 10), (0, -6), (34, 10), (0, -6)),                 # 大きく振る
    # 無指定の行。**止まっている行を作らない**
    "idle":   ((5, 3), (-4, 1), (3, 4), (-5, 2), (2, 3), (-3, 1)),
}
MOVE_STEP_S = 0.30


@dataclass
class Line:
    """読ませる1かたまり。"""

    text: str
    face: str | None = None
    pause_before: float = 0.0
    led: str | None = None
    move: str | None = None


def split_speech(script: str, limit: int = SPEECH_LIMIT) -> list[Line]:
    """台本を、読ませる単位に割る。

    ★**文の途中で切らない。** 切れ目で区切る
    ★**短ければまとめる。** 1文ずつ細切れだと間が空いて不自然
    ★`[happy]` で表情、`[pause=1.5]` で間。**知らない指示は捨てて、言葉は残す**
      （表情は飾り、本体は言葉。セリフが読まれないほうが困る）
    """
    out: list[Line] = []
    buf = ""
    face: str | None = None
    pause = 0.0
    led: str | None = None
    move: str | None = None

    def emit():
        nonlocal buf, face, pause, led, move
        s = buf.strip()
        buf = ""
        if not s:
            return
        # ★無指定でも動かす。止まっている行を作らない
        out.append(Line(s, face, pause, led, move or "idle"))
        face, pause, led, move = None, 0.0, None, None   # ★次の1かたまりにだけ効く

    for tok in re.split(r"(\[[^\]]{0,40}\])", script):
        if not tok:
            continue
        m = re.fullmatch(r"\[([^\]]{0,40})\]", tok)
        if m:
            tag = m.group(1).strip()
            if tag in FACES_OK:
                emit()
                face = tag
            elif tag in MOVES or tag.startswith("move="):
                name = tag.split("=", 1)[1].strip() if "=" in tag else tag
                if name in MOVES:
                    emit()
                    move = name
                # ★知らない動きは捨てる。**言葉は読む**
            elif tag.startswith("led="):
                name = tag.split("=", 1)[1].strip()
                if name in LedState.PATTERNS:
                    emit()
                    led = name
                # ★知らない模様は捨てる。**言葉は読む**
            elif tag.startswith("pause"):
                emit()
                try:
                    pause = float(tag.split("=", 1)[1])
                except (IndexError, ValueError):
                    pause = 1.0
            # ★知らないタグは黙って捨てる。言葉は残す
            continue

        # ★改行は書き手が置いた区切り。**必ずそこで割る**（間の取り方は作者のもの）
        for i, chunk in enumerate(tok.split("\n")):
            if i:
                emit()
            for piece in _sentences(chunk, limit):
                if buf.strip() and len(buf) + len(piece) > limit:
                    emit()
                buf += piece
    emit()
    return out


def _sentences(text: str, limit: int = SPEECH_LIMIT) -> list[str]:
    """文に割る。★切れ目が無い長文は、そこで初めて機械的に切る。"""
    out: list[str] = []
    for p in [x for x in re.split(r"(?<=[。！？\n])", text) if x]:
        while len(p) > limit:
            out.append(p[:limit])
            p = p[limit:]
        if p:
            out.append(p)
    return out


async def _play_move(con, name: str) -> None:
    """喋り終わるまで首を動かし続ける。**必ず離す。**

    ★決め打ちの回数で終わらせない。動きは1秒で終わるのに、
      1行を読むのは3〜5秒ある。**残りが固まって読み上げ機に見えた**
      （2026-09-12 本人の指摘）。
    """
    steps = MOVES.get(name)
    if not steps:
        return
    try:
        i = 0
        while True:                       # ★呼び出し側が止めるまで回り続ける
            yaw, pitch = steps[i % len(steps)]
            con.pose.hold = (yaw, pitch)
            await asyncio.sleep(MOVE_STEP_S)
            i += 1
    except asyncio.CancelledError:
        raise
    finally:
        con.pose.hold = None


def _talk(con, state: str | None) -> None:
    """会話中であることを、presence と LED の両方に伝える。

    ★console は set_talk() で両方に配っている。**片方だけ立てない。**
    """
    fn = getattr(con, "set_talk", None)
    if callable(fn):
        fn(state)
        return
    con.presence.talk = state
    if hasattr(con, "led"):
        con.led.talk = state


async def perform(con, script: str, limit: int = SPEECH_LIMIT) -> dict:
    """台本を、順番に読ませる。**読み終わるまで次を出さない。**

    ★かぶると聞き取れない。`say` は鳴り終わる少し前に返るので、少し待つ。
    """
    lines = split_speech(script, limit)
    for ln in lines:
        if ln.pause_before:
            await asyncio.sleep(min(ln.pause_before, 10.0))
        if ln.face:
            con.presence.overlay("knob", ln.face, 8.0)
        if ln.led:
            con.led.show_pattern(ln.led, hold_s=600.0)
        # ★喋りと同時に動かし、**喋り終わったら止める。**
        mover = asyncio.ensure_future(_play_move(con, ln.move or "idle"))
        # ★LED にも伝わる口を通す。presence だけ立てると背景が真っ暗になる
        #   （2026-09-12 実地：締めの挨拶で LED が消えていた）
        _talk(con, "speaking")
        try:
            await con.gw.call("say", text=ln.text, speaker_id=14)
            await asyncio.sleep(0.35)      # ★鳴り終わる前に返る分
        finally:
            mover.cancel()
            with contextlib.suppress(asyncio.CancelledError, Exception):
                await mover
            _talk(con, None)
    return {"ok": True, "lines": len(lines),
            "chars": sum(len(l.text) for l in lines)}


# ── MIDI を流し込む（試験用）─────────────────────────
#
# 2026-09-12 本人の指摘：**「なんで僕が押すまでわかんないんだ」**
#
# 割り当てが効いているかを、人にパッドを押させて確かめていた。
# **人の手でしか確かめられない作りは、確かめられていないのと同じ。**
#
# ★実機に触る必要がある部分（サーボ・LEDの見え方）と、
#   **合成した入力で確かめられる部分（割り当て・分岐）を分ける。**


class _Msg:
    """mido のメッセージの代わり。**必要な属性だけ持つ。**"""

    def __init__(self, **kw):
        self.__dict__.update(kw)

    def __repr__(self):
        return f"<{self.type} {self.__dict__}>"


def fake_note(ch: int, num: int, velocity: int = 100,
              kind: str = "note", value: int = 0) -> "_Msg":
    if kind == "cc":
        return _Msg(type="control_change", channel=ch, control=num, value=value)
    return _Msg(type="note_on", channel=ch, note=num, velocity=velocity)
