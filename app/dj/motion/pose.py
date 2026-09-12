#!/usr/bin/env python3
"""首の状態。つまみ・キメのポーズ・踊りを1つにまとめる。

console.py から切り出した。**振る舞いは1行も変えていない。**
"""
from __future__ import annotations

import json
import time

from .arbiter import HeadArbiter
from . import phrases



class PoseState:
    """つまみの狙い角度、または踊りの首振り。

    ★触っていない間はフレームを送らない。
      送り続けると「正面を向け」を毎秒15〜20回投げることになり、
      beat mode が首を振ろうとしても即座に上書きされて踊れなくなる。
      （実機のログで、6秒間に yaw=0 の指令が90件届いていた）
      つまみを離して数秒たったら、首を踊りに明け渡す。
    """

    def __init__(self, hold_s: float = 2.0):
        self.yaw = 0.0
        self.pitch = 0.0
        self.hold_s = hold_s
        self.touched_at = 0.0
        # ── 踊り。beat mode の首振りは「1拍に1回、±14°に飛ぶ」だけなので、
        #    遅い曲だと間延びする（BPM75 なら0.8秒に1回）。
        #    こちらは同じ拍時計から**連続的な波**を作るので、細かく刻める。
        self.dance = False
        self.bpm = 0.0
        self.beat0 = 0.0
        self.sway_deg = 22.0
        self.nod_deg = 7.0
        self.subdiv = 1.0        # 1=1拍で1往復, 2=半拍で1往復
        # ★ノリの強さ 0..1。閾値で「踊る／踊らない」を切らず、連続量として持つ。
        #   曲＝大きく、話し声＝軽くうなずく、無音＝止まる。
        #   会話の邪魔をせず、でも聞いているのが伝わる。
        self.groove = 0.0        # 目標
        self._groove_now = 0.0   # 実際に出している値（助走のため遅れて追いつく）
        self.ramp_per_s = 0.5
        self.fall_per_s = 0.8
        self.phrase_beats = 8    # 何拍でフレーズを切り替えるか
        self._phrase = "sway"
        self._phrase_n = -1
        self._phrase_end = 0.0
        self._phrase_span = 8.0
        self.arb = HeadArbiter(knob_hold_s=hold_s)
        self.hold = None         # (yaw, pitch) を入れると、そこで固定する

    def touch(self) -> None:
        self.touched_at = time.time()

    def active(self) -> bool:
        return (time.time() - self.touched_at) <= self.hold_s

    def sync(self, bpm, last_beat_age_ms) -> None:
        if bpm and bpm > 0:
            self.bpm = bpm
        if last_beat_age_ms is not None:
            self.beat0 = time.time() - last_beat_age_ms / 1000.0

    def step_groove(self, dt: float) -> None:
        """ノリを目標へ滑らかに寄せる。

        ★突然フルスイングで始めない。人は曲が始まって数拍聴いてから乗り出す。
          立ち上がりは遅く（2秒）、立ち下がりは少し速く（1.2秒）。
          止まるときも急停止せず、振り幅が細くなって消える。
        """
        rate = self.ramp_per_s if self.groove > self._groove_now else self.fall_per_s
        d = self.groove - self._groove_now
        step = rate * dt
        self._groove_now += max(-step, min(step, d))
        self._groove_now = max(0.0, min(1.0, self._groove_now))

    # ★振り付けの本体は motion/phrases.py（純関数）に置いた。
    #   ここは「いま何拍目か」「どのフレーズか」という状態だけを持つ。
    #   実機なしで振り付けを検証できるようにするため（tests/test_phrases.py）。
    YAW_LIM, PITCH_LIM = phrases.YAW_LIM, phrases.PITCH_LIM
    PHRASES = phrases.PHRASES
    PHRASE_LENS = phrases.PHRASE_LENS

    def dance_angles(self):
        """いまの角度。返すのは yaw と「45度からの差」。"""
        g = self._groove_now
        if self.bpm <= 0 or g <= 0.02:
            return 0.0, 0.0
        t = (time.time() - self.beat0) / (60.0 / self.bpm)     # 拍単位の時刻

        if t >= self._phrase_end:                              # フレーズを切り替える
            self._phrase_n += 1
            self._phrase_span = phrases.phrase_len(self._phrase_n)
            self._phrase_end = t + self._phrase_span
            self._phrase = phrases.pick(self._phrase_n, self.bpm, self._phrase)

        span = max(1e-6, self._phrase_span)
        in_phrase = 1.0 - max(0.0, min(1.0, (self._phrase_end - t) / span))

        return phrases.angles(
            self._phrase, t, in_phrase,
            sway=self.sway_deg * (g ** 1.15),                  # ノリで振り幅が伸びる
            nod=self.nod_deg * (0.45 + 0.55 * g),
            dip=self.nod_deg,                                  # 頷きの深さはノリで薄めない
        )

    # ── 主導権の判定は HeadArbiter に委譲する ──────────────
    #   以前はここに散らばっていて、19箇所から首を書いていた。
    def _sync_arbiter(self):
        a = self.arb
        a.knob_hold_s = self.hold_s
        if self.hold is not None:
            a.set_pose(self.hold[0], self.hold[1])
        else:
            a.set_pose(None)
        a.dancing = self.dance
        if self.dance:
            a.set_dance(*self.dance_angles())
        if self.touched_at:
            a._knob, a._knob_at = (self.yaw, self.pitch), self.touched_at
        return a

    def emit(self) -> bool:
        """いまフレームを送るべきか。判断は Arbiter が持つ。"""
        return self._sync_arbiter().should_emit()

    def frame(self) -> str:
        yaw, pitch = self._sync_arbiter().angles()
        return json.dumps({
            "source": "ddj-flx2", "frame": "continuous",
            "yaw": round(yaw, 2), "pitch": round(pitch, 2),
            "ts": int(time.time() * 1000),
        })


