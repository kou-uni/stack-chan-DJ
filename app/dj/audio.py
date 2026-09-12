#!/usr/bin/env python3
"""音を聴いて踊る。BPM・ノリ・盛り上がり・自己ノイズ対策。

console.py の Console から切り出した mixin。**中身は1行も変えていない。**
Console がこれらを継承して1つのクラスになる。
"""
from __future__ import annotations

import asyncio
import json
import math
import random
import time

from constants import (ROOT, MAPPING, YAW_MIN, YAW_MAX, PITCH_REL_MIN,
                       PITCH_REL_MAX, MODE_IDLE, MODE_DJ, MODE_LABEL,
                       MODE_FACE, MODE_ORDER, _scale)  # noqa: F401


class AudioMixin:
    @staticmethod
    def _extract_bpm(result) -> float | None:
        if result is None:
            return None
        try:
            for block in getattr(result, "content", []) or []:
                text = getattr(block, "text", None)
                if not text:
                    continue
                data = json.loads(text)
                bpm = data.get("bpm")
                if isinstance(bpm, (int, float)) and bpm > 0:
                    return float(bpm)
        except Exception:
            pass
        return None
    # ── 踊りの監督。踊っている間の観測は信用しない
    async def beat_supervisor(self):
        """止める判断と、始める判断で、見るものを分ける。

        ★踊っている間、マイクはサーボの音で埋まっている（実測40倍）。
          だから**踊っている間の音量は、停止の判断に使えない。**
          最初これを混ぜて書いたら、「耳を澄ます」で正しく静かと出ているのに、
          その間の汚れた観測がカウンタをリセットして、永久に止まらなかった。

            止まっている間 → 観測はきれい。音量と拍で「始めるか」を決める
            踊っている間   → 観測は汚い。**耳を澄ました結果だけ**で「止めるか」を決める
        """
        dancing = False
        while True:
            await asyncio.sleep(self.args.beat_poll_s)
            d = self._as_json(await self.gw.call("beat_meta_snapshot")) or {}
            if self.mode != MODE_DJ:
                if dancing:                      # モードが外れたら畳む
                    dancing = False
                    await self._stop_dancing(0.0)
                continue
            if d.get("capture_state") != "listening" or not d.get("capture_healthy"):
                continue      # 実機の listen は30秒ごとに約3秒切れる。その間は判定しない

            bpm, age = d.get("bpm"), d.get("last_beat_age_ms")
            self.led.sync(bpm, age)
            self.pose.sync(bpm, age)

            if not dancing:
                # ── 首は止まっているので、この観測は信用できる
                level = d.get("level") or 0.0
                conf = d.get("confidence") or 0.0
                self.pose.groove = self.groove_from(level, conf, self.args.quiet_level)
                if level >= self.args.quiet_level and age is not None \
                        and age <= self.args.beat_timeout_ms:
                    dancing = True
                    self._silent_since = None
                    await self._start_dancing(d)
                    continue
                # 曲が来ない時間が続いたら、自分でOFFに戻る
                if self.args.dj_timeout_min > 0:
                    if self._silent_since is None:
                        self._silent_since = time.time()
                    elif time.time() - self._silent_since >= self.args.dj_timeout_min * 60:
                        await self.set_mode(
                            MODE_IDLE, why=f"{self.args.dj_timeout_min:g}分 曲が来なかった")
                continue

            # ── 踊っている間。決めるのは「耳を澄ました結果」だけ
            if self.args.listen_check_s <= 0:
                continue
            if time.time() - self._last_check < self.args.listen_check_s:
                # つまみの主導権だけは即座に反映する
                knob = self.pose.active()
                if knob != self._knob_was:
                    self._knob_was = knob
                continue

            level = await self._listen_check()
            # ★止める閾値は、始める閾値より低くする（ヒステリシス）。
            #   同じ値だと、音量が境界を跨ぐたびに開始と停止を往復する。
            #   実際それで「踊りだした／曲が終わった」が数秒おきに繰り返された。
            if level < self.args.quiet_level * self.args.stop_ratio:
                dancing = False
                self._silent_since = time.time()
                await self._stop_dancing(level)
    async def groove_loop(self):
        """ノリを目標へ滑らかに寄せ続ける。首の波を作る側と同じ周期で回す。"""
        last = time.time()
        while True:
            await asyncio.sleep(0.03)
            now = time.time()
            self.pose.step_groove(now - last)
            last = now
            self.led.groove = self.pose._groove_now

    def groove_from(self, level: float, confidence: float, quiet: float) -> float:
        """音の性質から「どれくらい乗るか」を出す。★閾値で切らない。

        曲     ＝ 大きい ＋ 拍がはっきり → 全力で踊る
        話し声 ＝ 小さい ＋ 拍が曖昧     → 軽くうなずく（会話の邪魔をしない）
        無音   ＝                        → 止まる

        話し声で踊るのは**バグではなく良い挙動**。喋っている横で乗ってくるのは可愛い。
        消すのではなく、**強さを変える**のが正しい扱いだった。
        """
        if level < quiet:
            return 0.0
        # ★満点の基準を実測に合わせる。
        #   最初「しっかり鳴っている曲=0.026」を基準にしたが、
        #   実際のDJの音量は 0.005〜0.010 だった。
        #   結果、振り幅が 0.9°〜1.3° にしかならず「動いていない」ように見えた。
        #   **基準は理想値ではなく、実際に来る値に置く。**
        vol = min(1.0, (level - quiet) / max(1e-6, self.args.full_level - quiet))
        # 拍のはっきりさ。実機のマイクでは 0.3 も出れば十分よく取れている
        beat = min(1.0, confidence / self.args.full_confidence)
        # 音量だけでもそこそこ乗る。拍がはっきりすれば全開になる
        g = 0.45 * vol + 0.30 * beat + 0.25 * (vol * beat)
        return max(self.args.min_groove, min(1.0, g))
    async def spike_loop(self):
        """② サビ（ドロップ）と ⑤ 歓声・拍手に反応する。

        どちらも「音量が急に跳ねた」で検出できるが、**意味が違うので反応も変える**。

          踊っている最中の跳ね  → 曲が盛り上がった → **全力で振る＋白フラッシュ**
          止まっている時の跳ね  → 客が沸いた       → **そっちを向いて頷き返す**

        音量の履歴を持ち、直近の中央値の何倍かで判定する。
        絶対値だと会場ごとに調整が要るが、比なら要らない。
        """
        hist: list[float] = []
        last = 0.0
        while True:
            await asyncio.sleep(0.25)
            if self.mode != MODE_DJ:
                continue
            d = self._as_json(await self.gw.call("beat_meta_snapshot")) or {}
            lv = d.get("level") or 0.0
            hist.append(lv)
            if len(hist) > 24:                       # 直近6秒
                hist.pop(0)
            if len(hist) < 8 or time.time() - last < self.args.spike_cooldown_s:
                continue
            base = sorted(hist[:-2])[len(hist[:-2]) // 2]     # 中央値
            if base <= 0 or lv < base * self.args.spike_ratio:
                continue
            last = time.time()

            if self.pose.dance:
                await self._drop()                   # ② サビ
            else:
                await self._cheer(lv)                # ⑤ 歓声

    async def _drop(self):
        """② サビ。全力で振って、白くフラッシュさせる。"""
        print("  ▲ サビ！")
        keep_g, keep_s = self.pose.groove, self.pose.sway_deg
        self.led.flash_white = True
        self.pose.groove = 1.0
        self.pose.sway_deg = keep_s * 1.35           # 一段大きく振る
        self.presence.overlay("drop", "surprised", seconds=self.args.spike_hold_s)
        await asyncio.sleep(self.args.spike_hold_s)
        self.pose.sway_deg = keep_s
        self.pose.groove = keep_g
        self.led.flash_white = False

    async def _cheer(self, level: float):
        """⑤ 歓声・拍手。そっちを向いて頷き返す。

        方向は分からないので、**正面〜少し左右に振って探すように**向く。
        「反応してくれた」が伝わればよく、正確さは要らない。
        """
        print(f"  ♡ 歓声に反応（音量={level:.4f}）")
        side = 1 if int(time.time()) % 2 else -1
        self.presence.overlay("cheer", "happy", seconds=1.5)
        for yaw, pit in ((22 * side, 0), (22 * side, 22), (22 * side, 0),
                         (22 * side, 20), (0, 0)):
            self.pose.hold = (yaw, pit)
            await asyncio.sleep(0.11)
        self.pose.hold = None

    async def _start_dancing(self, d) -> None:
        # ★gateway 側の踊りは反映役が常に切っている（設計 I3）。ここで触らない。
        self.led.enabled = True
        self.set_dancing(True)
        self._last_check = time.time()
        print(f"  ♪ 曲がきた  BPM={d.get('bpm')}  確信度={d.get('confidence',0):.2f}  "
              f"音量={d.get('level'):.4f}")

    async def _stop_dancing(self, level: float) -> None:
        self.pose.groove = 0.0
        self.led.enabled = False
        self.led.swoon = False
        self.set_dancing(False)
        await self.home_head()          # 正面へ。首の出所は Arbiter だけ（設計 I2）
        print(f"  ♪ 曲が終わった（耳を澄まして 音量={level:.5f}）→ 正面に戻ってまばたき")

    # ★測定のための停止を、キメのポーズに見せる。
    #   サーボ音で自分の耳が塞がるので止めるしかない ── ならば「振り付けの一部」にする。
    #   毎回同じ止まり方だと「測定している」のがバレる。4種を順不同で回す。
    # ★止まるときも客の方を向く。真上には誰もいない。
    HOLDS = (
        ("左を見る",   (-38,   0), "embarrassed", "swoon"),
        ("右を見る",   ( 38,   0), "embarrassed", "swoon"),
        ("正面でキメる", (  0,   0), "surprised",   "flash"),
        ("首をかしげる", ( 24,  -4), "thinking",    "hold"),
    )

    async def _listen_check(self) -> float:
        """首を止めて、外の音だけを測る。

        ★踊っている間の観測は自分のサーボ音で埋まる（音楽の13倍）。
          動いている間は一切測らない。**測るのは止まっている間だけ。**
          そのうえで、止まっている姿を演出として成立させる。
        """
        name, (yaw, pitch), face, led = self.HOLDS[self._hold_i % len(self.HOLDS)]
        self._hold_i += 1

        self.set_dancing(False)
        self.pose.hold = (yaw, pitch)   # pitch は45からの差。gatewayが足す
        self.led.swoon = (led in ("swoon", "dim"))
        self.led.groove = 0.15 if led == "dim" else (1.0 if led == "flash" else 0.5)
        # 測っている間ずっと。頷きぶんの余裕を足す（期限で自然に戻る）
        self.presence.overlay("listen", face,
                              seconds=self.args.listen_check_ms / 1000.0 + 1.6)

        await asyncio.sleep(self.args.listen_check_ms / 1000.0)
        levels = []
        for _ in range(2):
            d = self._as_json(await self.gw.call("beat_meta_snapshot")) or {}
            levels.append(d.get("level") or 0.0)
            if d.get("bpm") and (d.get("confidence") or 0) >= 0.10:
                self.locked_bpm = d["bpm"]              # きれいな窓でだけテンポを更新
            await asyncio.sleep(0.35)
        level = min(levels)

        # ★キメのあと、たまに「うんうん！」と頷いてから踊りに戻る。
        #   止まる → 動き出す の間に一拍あると、生き物っぽくなる。
        if level >= self.args.quiet_level * self.args.stop_ratio:
            for d_ in (26, 0, 24, 0, 20, 0):         # 速く3回。うんうんうん！
                self.pose.hold = (yaw * 0.35, d_)
                await asyncio.sleep(0.09)
        self.pose.hold = None
        self.led.swoon = False
        self._last_check = time.time()
        if level >= self.args.quiet_level * self.args.stop_ratio:
            self.set_dancing(True)
            if self.locked_bpm:
                self.pose.bpm = self.locked_bpm
                self.led.bpm = self.locked_bpm
            # ★ノリは、このきれいな窓で測った音量だけで決める。
            #   確信度は踊っている間 構造的に取得できないので使わない。
            self.pose.groove = self.groove_from(level, 1.0, self.args.quiet_level)
            self.presence.clear("listen")          # 踊りに戻る。上書きを畳む
            if not self.args.quiet:
                print(f"    ♪ {name}（音量={level:.4f} BPM={self.locked_bpm}）")
        return level
