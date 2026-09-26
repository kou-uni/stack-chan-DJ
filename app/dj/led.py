#!/usr/bin/env python3
"""LED リング。**色に意味を持たせる。**

参加者に配る紙（event/handson-guide.md）にこう書いてある。

    緑    あなたの声を聞いています
    青    喋っています
    消灯  待機中。タップすると起きます

★紙を見た人が「緑を探す」のに緑が光らなければ、その紙は嘘になる。
  実装を紙に合わせる。**会話が最優先**（サブ講師として、
  聞いているのか喋っているのかが分からないと相談できない）。

    優先順:  喋っている(青) > 聞いている(緑) > 踊り(模様) > 消灯
"""
from __future__ import annotations

import colorsys
import json
import math
import time



class LedState:
    """LEDの見た目を作る。beat mode の点滅は止めて、こちらで全部描く。

    ★beat mode も同じ12個を叩くので、両方動かすと取り合いになる。
      向こうは「1色を拍で明滅」しかできないが、こちらは12個を個別に塗れる。
      拍の時刻は BPM から自前で刻む（拍イベントを待たない ＝ 遅れない）。

    模様:
      strobe  拍の瞬間に全灯 → すぐ落ちる。一番激しい
      chase   光の粒が輪を回る。拍ごとに1つ進む
      rainbow 12個に色相を配って回す。拍で回転が跳ねる
      split   半分ずつ違う色。拍ごとに入れ替わる
    """

    PATTERNS = ("wave", "strobe", "chase", "rainbow", "split", "mix",
                "laser", "sweep", "build", "sparks", "strobe_hard",
                "segments", "show")
    # 拍ごとに切り替える色（彩度を上げて暗い箱で見えるように）
    PALETTE = [(255, 0, 80), (0, 140, 255), (0, 255, 120), (255, 180, 0),
               (200, 0, 255), (0, 255, 255), (255, 60, 0)]

    # ★色は「シリーズ」で切り替える（本人の指定・2026-09-10）。
    #   赤と青を**同時に混ぜない**。混ぜると濁る。区間ごとに世界を変える。
    #   基調は青（Alan Walker に忠実に）。赤は差し色として、たまに。
    SERIES = {
        "blue": [(0, 80, 255), (0, 229, 255), (90, 0, 255)],    # 深青・シアン・青紫
        # ★本人が提示した写真（ROG のライブ）の赤。**血のような深い赤。**
        #   ピンクに寄せない。青を混ぜた瞬間に安っぽくなる
        "red":  [(255, 0, 0), (255, 40, 0), (200, 0, 20)],      # 赤・橙赤・暗赤
    }
    # 青3回に対して赤1回。★これ以上赤を増やすと Alan Walker から外れる
    SERIES_ORDER = ("blue", "blue", "blue", "red")
    SERIES_BEATS = 16                   # 色が変わる周期。模様より長くする
    SEG_BLOCKS = 6                      # テープを何ブロックに割るか

    # 旧名。白は共通なのでここに残す
    COLD = [(0, 80, 255), (0, 229, 255), (255, 255, 255), (90, 0, 255)]

    # sweep の向き。★1方向だけだとすぐ見飽きる（本人の指定・2026-09-10）
    #   ltr 左→右 ／ rtl 右→左 ／ in 両端→中央 ／ out 中央→両端
    SWEEP_DIRS = ("ltr", "rtl", "in", "out")
    # ★2026-09-10、実機で見ながら3回調整した記録：
    #     2.0拍 (0.94秒) … 最初
    #     1.5拍 (0.70秒) … 速すぎ。「走っている」ではなく「点滅」に見えた
    #     2.5拍 (1.17秒) … 遅すぎ
    #     2.25拍(1.05秒) … まだ少し遅い
    #     2.1拍 (0.98秒) … まだ
    #     1.95拍(0.91秒) … まだ
    #     1.73拍(0.81秒) … まだ
    #     1.39拍(0.65秒) … まだ
    #     0.96拍(0.45秒) … ★本人の指定。ほぼ1拍で1周＝拍と揃う
    #   **目が線を追えて、かつ止まって見えない**幅は意外と狭い。
    SWEEP_BEATS = 0.96
    BUILD_BEATS = 4                     # 煽りの長さ。短いほど早く効く
    BUILD_HOLD = 0.88                   # ここから先は真っ暗＝爆発前の溜め

    def __init__(self, count=12, target="base_ring", max_brightness=0.35,
                 pattern="strobe", cycle_beats=8):
        self.count = count
        self.target = target
        self.max_brightness = max(0.0, min(1.0, max_brightness))
        self.pattern = pattern
        self.cycle_beats = max(1, cycle_beats)
        self.bpm = 0.0
        self.beat0 = 0.0          # 直近の拍の時刻
        self.enabled = False
        # ★人が模様を選んだ。**音とは関係なく光る**（2026-09-12 本人の指摘）
        #   「模様は見せるもの。拍に合わせるのは味付け」。前提が逆だった
        self.manual = False
        self.free_bpm = 120.0        # 音が無いときの自走テンポ
        # ★選んだ模様は、しばらくしたら元に戻る（2026-09-12 本人の要望）
        #   演奏中は手が離せない。**戻すために押し直させない**
        self.base_pattern = pattern
        self.hold_until = 0.0
        # 「耳を澄ます」間の見え方。強い点滅をやめて、ゆっくり息をする
        self.swoon = False
        self.flash_white = False
        # ノリの強さ。曲なら全開、話し声なら弱く光るだけ
        self.groove = 1.0
        # ★会話の状態。"listening" / "speaking" / None
        #   会話（サブ講師）が入ったらここを動かす。踊りより優先される。
        self.talk: str | None = None
        self.burst = 0.0        # ★右の音量ゲージ 0..1（バーストモード）
        # ★入力への返事。**期限つき**（Presence の overlay と同じ考え方）。
        #   期限のない割り込みは消し忘れが起きる
        self.poke_kind: str | None = None
        self.poke_until = 0.0
        self.meter: float | None = None      # つまみの値 0..1（目標）
        self.meter_until = 0.0
        self._meter_now = 0.0                # 実際に出している値（追いつく）
        self._meter_at = 0.0                 # 最後に計算した時刻
        # ★時計を外から差し替えられるようにする。
        #   サビの点滅は時刻で決まるので、これが無いと試験で測れない
        self.now = time.time

    # ── 拍の時計。ホストが刻むので、拍イベントの往復を待たない
    def sync(self, bpm: float | None, last_beat_age_ms: int | None) -> None:
        if bpm and bpm > 0:
            self.bpm = bpm
        if last_beat_age_ms is not None:
            self.beat0 = time.time() - last_beat_age_ms / 1000.0

    def _phase(self):
        """(拍の通し番号, 拍の中の位置0..1) を返す。

        ★音が無くても、人が模様を選んでいるなら自走する。
          止まって見える模様は、選んだ意味がない。
        """
        bpm = self.bpm
        if bpm <= 0 and self.manual:
            bpm = self.free_bpm
        if bpm <= 0:
            return 0, 0.0
        period = 60.0 / bpm
        elapsed = time.time() - self.beat0
        n = int(elapsed // period)
        return n, (elapsed % period) / period

    @staticmethod
    def _hsv(h, s=1.0, v=1.0):
        i = int(h * 6) % 6
        f = h * 6 - int(h * 6)
        p, q, t = v * (1 - s), v * (1 - f * s), v * (1 - (1 - f) * s)
        r, g, b = [(v, t, p), (q, v, p), (p, v, t),
                   (p, q, v), (t, p, v), (v, p, q)][i]
        return int(r * 255), int(g * 255), int(b * 255)

    # 紙に書いてある色。ここを変えたら配布物も直すこと
    TALK_COLOR = {"listening": (0, 255, 90), "speaking": (0, 120, 255)}

    def _drop_flash(self):
        """サビ。**白の暴力的なストロボ。**

        ★べた塗りの2.5秒は、電流を超えるうえに見た目も弱い。
          切れ目があるほうが強い（Alan Walker のドロップ）。
        """
        t = self.now()
        # 16分相当の高速点滅。たまに1つ飛ばして不規則にする
        beat = 60.0 / self.bpm if self.bpm > 0 else 0.5
        step = beat / 4
        i = int(t / step)
        on = (i % 3 != 2)                      # 3回に1回抜く＝機械的に見えない
        f = 0.0
        if on:
            ph = (t % step) / step
            f = (1.0 - ph) ** 0.6              # 立ち上がりは瞬時、落ちは速い
        v = int(255 * f * self.max_brightness)
        return [[v, v, v]] * self.count

    # ── 入力への返事 ──────────────────────────────
    # ★**入力があったら、必ず身体のどこかが応える。**（docs/ideas.md）
    #   撫でても、こすっても、つまみを回しても、いままでLEDは無反応だった。
    #   ハンズオンで人が触るのだから、ここが空いているのはいちばん痛い。
    #
    # 強さの順（迷ったらここを見る）:
    #   バースト > 会話の色 > 入力への返事 > つまみメーター > うっとり > 模様
    #
    # ★**会話の色は入力より強い。** 配布物に「緑=聞く／青=喋る」と書いてある。
    #   撫でた瞬間だけ色が変わると、その紙が嘘になる（顔と声では返している）
    POKE_S = {"touch": 2.6, "scratch": 0.9, "button": 0.7, "nfc": 2.4}

    def poke(self, kind: str, now: float | None = None) -> None:
        """入力に返事をする。**期限は種類ごとに決め打ち。**

        ★`now` を渡すのは試験のときだけ。**呼ぶ側の時計を渡さない。**
          呼ぶ側が `loop.time()`（起動からの秒）で、こちらが `time.time()` だと、
          期限が桁違いになって点いた瞬間に消える（2026-09-13 実際に起きた）。
        """
        if kind not in self.POKE_S:
            raise ValueError(f"知らない返事: {kind}（POKE_S に足すこと）")
        now = self.now() if now is None else now
        until = now + self.POKE_S[kind]
        # ★強い返事が出ている間は上書きしない。ちらつく
        if self.poke_kind and now < self.poke_until and kind == "scratch" \
           and self.poke_kind == "touch":
            return
        self.poke_kind, self.poke_until = kind, until

    def show_meter(self, v: float, seconds: float = 1.1,
                   now: float | None = None) -> None:
        """つまみの値を、点灯本数で見せる。**手元を見ずに分かるのが本当の価値。**"""
        now = self.now() if now is None else now
        self.meter = max(0.0, min(1.0, float(v)))
        self.meter_until = now + seconds

    def _poke_colors(self, kind: str, left: float):
        """返事の色。**残り時間で細っていく**（ぶつ切りにしない）。"""
        t = time.time()
        f = min(1.0, left / self.POKE_S[kind])         # 1 → 0
        k = self.max_brightness * (0.55 + 1.65 * f)
        out = []
        if kind == "touch":
            # ★七色がぐるぐる回る。**撫でられて照れた勢い**
            spin = t * 2.6
            for i in range(self.count):
                h = (spin + i / self.count) % 1.0
                c = self._hsv(h, 1.0, 1.0)
                # 粒ごとにチカチカさせる（一様だとただの虹）
                g = 0.55 + 0.45 * math.sin((t * 14.0) + i * 1.7)
                out.append([min(255, int(c[0] * k * g)),
                            min(255, int(c[1] * k * g)),
                            min(255, int(c[2] * k * g))])
            return out
        if kind == "nfc":
            # ★受付の「ようこそ」。**中央から両側へ白が広がって、ミントに落ち着く**
            #   （扉が開く形）。虹（撫で）とは別の出来事だと分かるように色を変える
            open_ = 1.0 - f                              # 0 → 1 で広がる
            mid = (self.count - 1) / 2.0
            for i in range(self.count):
                d = abs(i - mid) / max(1.0, mid)         # 中央 0 → 端 1
                lit = 1.0 if d <= open_ else 0.0
                white = max(0.0, 1.0 - open_ * 1.4)      # 最初は白、だんだんミントへ
                r = int((255 * white + 62 * (1 - white)) * k * lit)
                g = int((255 * white + 227 * (1 - white)) * k * lit)
                b = int((255 * white + 155 * (1 - white)) * k * lit)
                out.append([min(255, r), min(255, g), min(255, b)])
            return out
        if kind == "scratch":
            # ★こすりは**速くて白い**。音の解析を待たず、操作そのものに返す
            step = int(t * 26)
            for i in range(self.count):
                on = ((step + i) % 3) == 0
                c = (255, 255, 255) if on else (40, 140, 255)
                g = 1.0 if on else 0.35
                out.append([min(255, int(c[0] * k * g)),
                            min(255, int(c[1] * k * g)),
                            min(255, int(c[2] * k * g))])
            return out
        # button: 端から中央へ一度だけ寄せる
        u = 1.0 - f
        mid = (self.count - 1) / 2.0
        for i in range(self.count):
            d = abs(i - mid) / max(1e-6, mid)
            g = max(0.0, 1.0 - abs(d - u) * 3.0)
            out.append([min(255, int(255 * k * g)),
                        min(255, int(210 * k * g)),
                        min(255, int(90 * k * g))])
        return out

    def _meter_colors(self, v: float):
        """点灯本数で値を出す。★端は赤、真ん中は緑。**音量計と同じ読み方**

        ★12個しかないので、そのまま出すと**カクカク動く**（2026-09-13 本人の指摘）。
          2つ手当てする:
          ① 目標へ**滑らかに追いつく**（つまみを飛ばしてもバーは滑る）
          ② 先端の1個を**半端な明るさ**で出す（＝粒の間を明るさで埋める）

        ★尾（先の粒も薄く光らせる）はやめた。**0%で1個光り、83%で全部光って
          見えてしまう**（2026-09-13 本人の指摘：100%になる前に100%に見える）。
          メーターは値を読む道具なので、**滑らかさより目盛りの正しさが先**。
          滑らかさは①（時間の追いつき）と、先端の明るさで足りる。

        目盛り: v=0 → 全消灯 / v=1 → 全点灯 / 途中は先端の1個が明るさで表す
        """
        n = self.count
        t = time.time()
        dt = min(0.2, max(0.0, t - self._meter_at))
        self._meter_at = t
        # 追いつく速さ。**速すぎるとカクつき、遅すぎると置いていかれる**
        a = 1.0 - math.exp(-dt / 0.055)
        self._meter_now += (v - self._meter_now) * a
        lit = self._meter_now * n
        k = self.max_brightness * 1.5
        out = []
        for i in range(n):
            d = lit - i
            if d >= 1.0:
                f = 1.0
            elif d > 0.0:
                f = d                                   # 先端は半端に光る
            else:
                out.append([0, 0, 0]); continue
            # ★色相だけ動かす（緑→橙→赤）。RGBを直に混ぜると**明るさが波打ち**、
            #   点いているのに凹んで見える（2026-09-13：真ん中が暗かった）
            u = i / max(1, n - 1)
            c = self._hsv((1.0 - u) * 0.33, 1.0, 1.0)
            out.append([min(255, int(c[0] * k * f)),
                        min(255, int(c[1] * k * f)),
                        min(255, int(c[2] * k * f))])
        return out

    # ★バーストは赤を中心に。**白を混ぜて振り切れさせる。**
    #   青を残すと桃色になって、赤の圧が出ない（2026-09-13）
    BURST_HUES = ((255, 20, 10), (255, 90, 0), (255, 0, 60), (255, 255, 255))

    def _burst_colors(self, amt: float):
        """バーストの色。**強さが上がるほど速く、白が増える。**

        amt は 0..1（`constants.burst_amount`）。段差を作らない。
        """
        t = time.time()
        rate = 9.0 + 13.0 * amt                   # 1秒あたりの刻み
        step = int(t * rate)
        ph = (t * rate) % 1.0
        k = min(1.0, self.max_brightness * (1.6 + 1.4 * amt))
        out = []
        for i in range(self.count):
            # ★粒ごとに位相をずらす。全部同時だと「ただの点滅」に見える
            j = (step + i * 3) % len(self.BURST_HUES)
            c = self.BURST_HUES[j]
            # 白は amt が高いときだけ出す（低い間は赤〜橙で押す）
            if c == (255, 255, 255) and amt < 0.45:
                c = self.BURST_HUES[0]
            f = (1.0 - ph) ** (1.4 - 0.9 * amt)   # 強いほど落ちが遅い＝焼き付く
            f = 0.35 + 0.65 * f
            out.append([min(255, int(c[0] * f * k)),
                        min(255, int(c[1] * f * k)),
                        min(255, int(c[2] * f * k))])
        return out

    def colors(self):
        # ★バーストは会話より強い。**頂点で止めない。**
        #   ここだけは人が意図してゲージを上げているので、最優先でよい
        from constants import burst_amount
        amt = burst_amount(self.burst)
        if amt > 0:
            return self._burst_colors(amt)

        # ★会話がいちばん強い。踊っている最中に話しかけられても、
        #   「聞いている」ことが分かるようにする。
        c = self.TALK_COLOR.get(self.talk)
        if c is not None:
            # ゆっくり息をさせる。点滅させると喋りにくい
            f = 0.55 + 0.45 * (1 + math.sin(time.time() * 1.6 * math.tau / 2)) / 2
            k = self.max_brightness * f
            return [[int(c[0] * k), int(c[1] * k), int(c[2] * k)]] * self.count

        # ★入力への返事。会話の色より弱く、模様より強い
        now = self.now()
        if self.poke_kind:
            left = self.poke_until - now
            if left > 0:
                return self._poke_colors(self.poke_kind, left)
            self.poke_kind = None
        if self.meter is not None:
            if now < self.meter_until:
                return self._meter_colors(self.meter)
            self.meter = None

        if self.flash_white:                          # サビ：白で焼く（点滅）
            return self._drop_flash()
        n, ph = self._phase()
        # 弱いノリでは暗く。話し声に全開で光ると邪魔になる
        k = self.max_brightness * (0.18 + 0.82 * self.groove)

        # うっとりしている間：拍を刻むのをやめて、全体がゆっくり明滅する
        if self.swoon:
            t = time.time() * 0.9
            f = 0.35 + 0.35 * (1 + math.sin(t * math.tau)) / 2
            c = (255, 90, 130)                       # ♥に合わせた桃色
            return [[int(c[0] * f * k), int(c[1] * f * k), int(c[2] * f * k)]] * self.count
        # ── 見せ場の模様（寒色・強い落差）────────────────
        if self.pattern in ("laser", "sweep", "build", "show",
                            "sparks", "strobe_hard", "segments"):
            return self._show(n, ph, k)

        base = self.PALETTE[(n // self.cycle_beats) % len(self.PALETTE)]
        out = [[0, 0, 0]] * self.count

        # ★12個並んでいるのに一斉に光らせるのは、もったいない。
        #   左から右へ、サインカーブが流れていくようにする。
        if self.pattern == "wave" or (self.pattern == "mix" and (n // 16) % 3 == 0):
            out = []
            for i in range(self.count):
                # 位置ごとに位相をずらす＝波が流れる
                ph_i = (n + ph) - i / self.count * 1.5
                v = (math.sin(ph_i * math.tau) + 1) / 2
                f = (v ** 2.2) * k                       # 山を鋭く
                out.append([int(base[0]*f), int(base[1]*f), int(base[2]*f)])
            return out

        if self.pattern == "mix":                        # 16拍ごとに模様を替える
            self_pat = ("strobe", "chase", "rainbow")[((n // 16) % 3 + 2) % 3]
        else:
            self_pat = self.pattern

        if self_pat == "strobe":
            # 拍の頭で全灯、25%で消える。一番強い
            f = max(0.0, 1.0 - ph / 0.25)
            c = self.PALETTE[n % len(self.PALETTE)]
            out = [[int(c[0] * f * k), int(c[1] * f * k), int(c[2] * f * k)]] * self.count

        elif self_pat == "chase":
            head = (n + int(ph * 2)) % self.count      # 半拍で1つ進む
            out = []
            for i in range(self.count):
                d = (i - head) % self.count
                f = max(0.0, 1.0 - d / 3.5) ** 2       # 尾を引く
                out.append([int(base[0] * f * k), int(base[1] * f * k), int(base[2] * f * k)])

        elif self_pat == "rainbow":
            spin = (n + ph) * 0.12
            pulse = 0.55 + 0.45 * max(0.0, 1.0 - ph / 0.35)
            out = []
            for i in range(self.count):
                r, g, b = self._hsv((i / self.count + spin) % 1.0)
                out.append([int(r * pulse * k), int(g * pulse * k), int(b * pulse * k)])

        else:  # split
            a = self.PALETTE[n % len(self.PALETTE)]
            b_ = self.PALETTE[(n + 3) % len(self.PALETTE)]
            f = 0.5 + 0.5 * max(0.0, 1.0 - ph / 0.4)
            out = [[int(c[0] * f * k), int(c[1] * f * k), int(c[2] * f * k)]
                   for i in range(self.count)
                   for c in [a if (i + n) % self.count < self.count // 2 else b_]]
        return out

    # ────────────────────────────────────────────────
    #  見せ場。**点きっぱなしにしない。落差で殴る。**
    # ────────────────────────────────────────────────
    def _mul(self, c, f):
        return [int(max(0, min(255, c[0] * f))),
                int(max(0, min(255, c[1] * f))),
                int(max(0, min(255, c[2] * f)))]

    # 混在で使う模様。★「ランダムで混在するのが最高」（本人・2026-09-10）
    SHOW_MIX = ("strobe_hard", "laser", "sparks", "sweep", "build", "segments")
    SHOW_BEATS = 4                      # 何拍ごとに切り替えるか

    def _series_name(self, n: int) -> str:
        """いまの色のシリーズ。★模様より長い周期で変わる。"""
        return self.SERIES_ORDER[(n // self.SERIES_BEATS) % len(self.SERIES_ORDER)]

    def _tone(self, n: int):
        """いま使う色。シリーズの中から、さらに細かく切り替える。"""
        pal = self.SERIES[self._series_name(n)]
        return pal[(n // max(1, self.cycle_beats)) % len(pal)]

    def _pick(self, n: int) -> str:
        """n 拍目に出す模様。**乱数を使わない。**

        ★毎回違う絵だと「演出」ではなく「ノイズ」に見える。
          拍から決まるようにすると、同じ拍で同じ絵になり、
          繰り返すうちにリズムとして認識される。

        ★仕組み：1つ進むごとに 1〜(種類-1) だけ番号をずらす。
          **ずれ幅が0にならない**ので、同じ模様が続くことが原理的に無い。
          ずれ幅自体も周期的に変わるので、並びは固定にならない
          （見ているうちに次が読めてしまうのを防ぐ）。
        """
        m = len(self.SHOW_MIX)
        q = m - 1
        slot = n // self.SHOW_BEATS
        # ずらし幅 step(i) = 1 + (i mod q) の累積和。閉じた式で出す
        full, rem = divmod(slot, q)
        # ★1周ぶんのずれの合計が種類数の倍数だと、周期が短くなって
        #   同じ4つがぐるぐる回るだけになった（実測）。1周ごとに +1 して崩す
        moved = (slot + full * (q * (q - 1) // 2 + 1)
                 + rem * (rem + 1) // 2)
        return self.SHOW_MIX[moved % m]

    def _sweep(self, u: float, direction: str, k: float, tone=None):
        """走る光。u は 0→1 で1周ぶんの進み。

        ★4つの向きを持つ（本人の指定）。
          ltr 左→右 ／ rtl 右→左 ／ in 両端→中央 ／ out 中央→両端
        """
        out = [[0.0, 0.0, 0.0] for _ in range(self.count)]
        span = self.count - 1
        mid = span / 2.0
        white = (255, 255, 255)
        cold = tone if tone is not None else self.SERIES["blue"][1]
        u = max(0.0, min(1.0, u))

        if direction == "ltr":
            heads = [u * (self.count + 6) - 3]
        elif direction == "rtl":
            heads = [(1.0 - u) * (self.count + 6) - 3]
        elif direction == "in":                       # 両端 → 中央
            heads = [-2 + u * (mid + 2), span + 2 - u * (mid + 2)]
        else:                                         # out: 中央 → 両端
            heads = [mid - u * (mid + 3), mid + u * (mid + 3)]

        for head in heads:
            for i in range(self.count):
                d = abs(i - head)
                if d >= 3.5:
                    continue
                f = (1.0 - d / 3.5) ** 1.8 * k
                c = white if d < 1.2 else cold
                for j in range(3):
                    out[i][j] = max(out[i][j], c[j] * f)
        return [[int(max(0, min(255, v))) for v in c] for c in out]

    def _show(self, n, ph, k):
        pat = self.pattern
        if pat == "show":
            pat = self._pick(n)

        cold = self._tone(n)                  # ★シリーズから採る
        white = (255, 255, 255)

        if pat == "laser":
            # ★2本が逆方向に走り、すれ違う。
            #   交差する瞬間がいちばんきれいなので、そこで白く強くする。
            out = [[0.0, 0.0, 0.0] for _ in range(self.count)]
            speed = 2.0                          # 1拍で2往復
            t = (n + ph) * speed
            span = self.count - 1
            a = (math.sin(t * math.tau / 2) + 1) / 2 * span          # →
            b = span - a                                            # ← 逆向き

            for head in (a, b):
                for i in range(self.count):
                    d = abs(i - head)
                    if d >= 2.4:
                        continue
                    f = (1.0 - d / 2.4) ** 2 * k
                    c = white if d < 0.9 else cold
                    # 重なったら足す＝交差の瞬間だけ焼ける
                    for j in range(3):
                        out[i][j] = out[i][j] + c[j] * f

            # 拍の頭だけ、うっすら全体を舐める（線に体をつける）
            if ph < 0.06:
                for i in range(self.count):
                    for j in range(3):
                        out[i][j] = max(out[i][j], cold[j] * 0.25 * k)
            return [[int(max(0, min(255, v))) for v in c] for c in out]

        if pat == "sweep":
            # ★1周ごとに向きが変わる。4種を順に回す
            cycle = int((n + ph) / self.SWEEP_BEATS)
            u = ((n + ph) % self.SWEEP_BEATS) / self.SWEEP_BEATS   # 0..1
            return self._sweep(u, self.SWEEP_DIRS[cycle % 4], k, cold)

        if pat == "build":
            # ★サビ前の煽り。点滅がどんどん速くなる。
            #   2026-09-10、本人の指定で 8拍 → 4拍 に。煽りが早く効く
            phase_in_cycle = (n % self.BUILD_BEATS) + ph
            # ★1拍に16回も点滅させると、速すぎて「ただのチラつき」になる。
            #   4分 → 8分 → 16分 と刻みが細かくなるくらいが、耳と合って気持ちいい
            u = phase_in_cycle / self.BUILD_BEATS

            # ★爆発直前の「溜め」。ここで一瞬すべて消す。
            #   Alan Walker のドロップ前は、たいてい無音と暗転が入る。
            #   止まりがあると、次の一発が効く（本人の指定・2026-09-10）
            if u >= self.BUILD_HOLD:
                return [[0, 0, 0]] * self.count

            v = u / self.BUILD_HOLD                            # 溜めまでを 0..1 に
            rate = 2.0 + v ** 2 * 11.0                         # 2 → 13 回/拍
            blink = (math.sin(phase_in_cycle * rate * math.tau) + 1) / 2
            f = (blink ** 3) * k
            c = white if v > 0.7 else cold                     # 終盤は白に
            return [self._mul(c, f)] * self.count

        if pat == "segments":
            # ★本人が提示した写真の画。回路図のように、四角い塊が飛び飛びに並ぶ。
            #   なめらかに減衰させない。**塊と黒の境目を立てる。**
            #   光る面積より、暗い面積のほうが広いこと。
            out = [[0, 0, 0]] * self.count
            nb = self.SEG_BLOCKS
            size = self.count / nb
            # 16分ごとに並びを組み替える（拍のうねりを持たせる）
            sub = int(ph * 2)
            key = n * 5 + sub * 11
            for b in range(nb):
                # 3つに1つくらいだけ点ける＝黒のほうが広くなる
                if (key * (b + 2) * 13 // 7) % 3 != 0:
                    continue
                lo, hi = int(b * size), int((b + 1) * size)
                # 塊ごとに、点いた瞬間から少し落ちる（ただし縁はぼかさない）
                # ★中途半端な明るさを作らない。写真の塊は「点いている」か「黒」。
                #   落としすぎると縁がぼやけて見え、回路図の硬さが消える
                fade = 1.0 - (ph * 2 % 1.0) * 0.22
                c = white if (b + n) % 5 == 0 else cold
                v = self._mul(c, fade * k)
                for i in range(lo, hi):
                    out[i] = list(v)
            return out

        if pat == "sparks":
            # ★粒が飛ぶ。揃った動きばかりだと上品になってしまう。
            #   乱数は使わない（同じ拍で同じ絵にする＝映像として決まる）
            out = [[0, 0, 0]] * self.count
            sub = int(ph * 4)                              # 16分で入れ替える
            seed = (n * 7 + sub * 13)
            for j in range(5):                             # 5粒
                i = (seed * (j + 3) * 31) % self.count
                fade = 1.0 - (ph * 4 % 1.0) * 0.7
                c = white if (j % 2 == 0) else cold
                out[i] = self._mul(c, fade * k)
            return out

        # strobe_hard: 16分でチカチカ刻む。拍の頭がいちばん強い
        # ★「もっとチカチカ」。4分だけだと落ち着いて見える
        sub = int(ph * 4)                                  # 16分の位置 0..3
        sub_ph = (ph * 4) % 1.0
        # ★16分を4つとも「見える強さ」で刻む。弱すぎると刻んでいないのと同じ。
        #   強弱は残す（全部同じだと平坦で、かえって派手に見えない）
        strength = (1.0, 0.62, 0.80, 0.55)[sub]
        f = (1.0 - sub_ph) ** 1.1 * strength               # 減衰を緩めて、粒を太く
        if sub == 3 and (n % 2 == 1):
            f = 0.0                                        # たまに抜く＝機械的に見えない
        c = white if (sub == 0 and n % 4 == 0) else cold
        return [self._mul(c, f * k)] * self.count

    HOLD_S = 20.0

    def show_pattern(self, name: str, hold_s: float | None = None,
                     now: float | None = None) -> None:
        """人が模様を選んだ。**音とは関係なく光り、しばらくして元に戻る。**"""
        now = time.time() if now is None else now
        self.pattern = name
        self.manual = True
        self.hold_until = now + (self.HOLD_S if hold_s is None else hold_s)
        if self.beat0 <= 0:
            self.beat0 = now

    def current_pattern(self, now: float | None = None) -> str:
        """いまの模様。**期限が切れていたら基本に戻す。**

        ★毎フレーム呼ばれる。ここで戻すので、時計を別に回さなくてよい。
        """
        now = time.time() if now is None else now
        if self.manual and self.hold_until and now >= self.hold_until:
            self.pattern = self.base_pattern
            self.manual = False
            self.hold_until = 0.0
        return self.pattern

    def emitted(self):
        """★実機のテープに**いま実際に出している色**。

        `colors()` は「模様の計算結果」。消灯中でも色を返すので、
        そのまま背景に流すと**実機は消えているのに画面のテープだけ光る**。
        画面と実機を合わせるため、点いているかの判定はここ1箇所に置く
        （2026-09-13：OFF なのに背景のテープが光っていた）。
        """
        self.current_pattern()          # ★期限切れならここで基本に戻る
        # ★バーストは人が意図してゲージを上げている。**消えていても点ける**
        from constants import burst_amount
        now = self.now()
        lit = (self.enabled or self.manual or self.talk in self.TALK_COLOR
               or burst_amount(self.burst) > 0
               # ★触られたら、消えていても返事をする
               or (self.poke_kind and now < self.poke_until)
               or (self.meter is not None and now < self.meter_until))
        return self.colors() if lit else [[0, 0, 0]] * self.count

    def frame(self) -> str:
        """★LEDストリームと poseストリームで、フレームの形が違う。

          pose : {"frame": "continuous", "yaw":…, "pitch":…}
          LED  : {"kind":  "continuous", "ts":…, "colors": […]}   ← "kind" と "ts" が必須

          同じ形で送ったら、728フレーム全部が黙って捨てられた
          （frames_received=728 / frames_sent=0 / frames_dropped=728）。
          **受理されなくてもエラーは返ってこない。** status を見るまで気づけない。
        """
        # ★会話中は踊っていない（enabled=False）。それでも光らせる。
        #   ここを enabled だけで閉じていたので、緑も青も一度も出ない作りだった
        #   （テストを先に書いたので、実装前に分かった）
        colors = self.emitted()
        return json.dumps({
            "source": "ddj-flx2",
            "kind": "continuous",
            "ts": int(time.time() * 1000),
            "colors": colors,
        })


