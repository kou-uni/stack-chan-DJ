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
import secrets
from pathlib import Path

from led import LedState

TOKEN_PATH = Path.home() / ".config" / "stackchan" / "panel-token"

# ★可動域。超えるとサーボが潰れる（yaw ±90 / pitch は45からの差 ±40）
HEAD = {
    "left":   (-55, 0),
    "right":  (55, 0),
    "up":     (0, -25),
    "down":   (0, 25),
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
        con.pose.hold = HEAD[value]
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
        con.led.pattern = value
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
