"""LEDの見せ場。**ド派手であること**を仕様として固定する。

参考：Alan Walker のライブ演出
  - 寒色（深い青〜シアン）に、白の強いフラッシュ
  - 拍の頭で焼けるように光り、すぐ落ちる（点きっぱなしにしない）
  - 細い光が高速で走る（レーザーのような線）
  - サビ前は点滅が速くなる（ビルドアップ）

★「派手」は感想では測れない。**数字で固定する。**
"""
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "app" / "dj"))
from led import LedState  # noqa: E402

N = 30                      # 外付けテープ（M5Stack A093）


def _frames(pattern, n=120, beats=8, **kw):
    """指定した拍数ぶんを、**決め打ちで**走査する。

    ★時計に頼ると、どの拍を見ているかが実行のたびに変わる。
      ビルドアップのように「拍の位置で速さが変わる」ものは測れない。
      模様の計算を直接叩いて、拍を自分で進める。
    """
    s = LedState(count=N, pattern=pattern, max_brightness=1.0, **kw)
    out = []
    for i in range(n):
        t = i / n * beats                          # 0 → beats 拍
        out.append(s._show(int(t), t % 1.0, 1.0))
    return out


def _peak(colors):
    return max(max(c) for c in colors)


def _lit(colors):
    return sum(1 for c in colors if max(c) > 20)


def _head(colors):
    """いちばん明るい粒の位置。走査型はここが動く。"""
    return max(range(len(colors)), key=lambda i: max(colors[i]))


# ★測るものが2種類ある。混ぜない。
FLASH = ("show", "build")       # 全灯型 …「落差」で殴る
SCAN = ("laser", "sweep")       # 走査型 …「動き」で見せる


def test_拍の頭で焼けるように光る():
    """★どこかの瞬間、ほぼ全灯まで振り切ること。"""
    for pat in FLASH + SCAN:
        peaks = [_peak(f) for f in _frames(pat)]
        assert max(peaks) >= 220, f"{pat} は最大でも {max(peaks)}。派手さが足りない"


def test_全灯型は点きっぱなしにしない():
    """★ずっと明るいのは派手ではなく、ただ眩しい。落差を作る。"""
    for pat in FLASH:
        peaks = [_peak(f) for f in _frames(pat)]
        assert min(peaks) <= 60, f"{pat} は暗い瞬間が無い（最小 {min(peaks)}）"
        assert max(peaks) - min(peaks) >= 160, f"{pat} の落差が小さい"


def test_走査型は光が端から端まで動く():
    """★30個の長さを活かす。位置が動かないなら、テープである意味が無い。

    ★「いちばん明るい点」では測らない。laser は2本あるので、
      argmax は2本の間を飛ぶだけで、走った範囲を表さない。
      **時間をまたいで、光が触れた範囲**で測る。
    """
    for pat in SCAN:
        touched = set()
        for f in _frames(pat):
            touched |= {i for i, c in enumerate(f) if max(c) > 120}
        assert touched, f"{pat} が光っていない"
        assert max(touched) - min(touched) >= N * 0.6, \
            f"{pat} は {min(touched)}〜{max(touched)} しか光らない"


def test_走査型は線に見える():
    """★「線」と「地明かり」を分けて測る。

    拍の頭でうっすら全体が光るのは演出として正しい（体ができる）。
    だが**強く光っている粒**が広がると、線ではなく面になる。
    """
    for pat in SCAN:
        for f in _frames(pat, n=40):
            bright = sum(1 for c in f if max(c) > 120)
            assert bright <= N * 0.4, f"{pat} の線が太すぎる（強く光る粒 {bright}個）"


def test_寒色に寄せる():
    """★Alan Walker の色。青〜シアン〜白。赤やオレンジに寄らない。"""
    for pat in FLASH + SCAN:
        for f in _frames(pat, n=40):
            for c in f:
                r, g, b = c
                if max(c) < 30:
                    continue
                assert b >= r, f"{pat} が暖色に寄っている {c}"


def test_ビルドアップは終わりに向かって速くなる():
    """★サビ前の煽り。前半より後半のほうが点滅が細かい。"""
    # ★点滅が速いので、細かく標本化する（粗いと折り返して測れない）
    # ★1周期ぶんだけ見る。2周期を前半後半で比べても、同じ形が2回出るだけ
    fr = _frames("build", n=480, beats=4)
    peaks = [_peak(f) for f in fr]

    def crossings(xs):
        return sum(1 for a, b in zip(xs, xs[1:]) if (a > 128) != (b > 128))

    half = len(peaks) // 2
    first, second = crossings(peaks[:half]), crossings(peaks[half:])
    assert second > first, f"後半が速くなっていない（前半{first} 後半{second}）"


def test_サビは白で焼く():
    """★点滅するので、**ピークで**白に振り切ればよい。"""
    s = LedState(count=N, max_brightness=1.0)
    s.enabled, s.flash_white, s.bpm = True, True, 128.0
    top = 0
    for i in range(200):
        s.now = (lambda v=i * 0.005: v)
        top = max(top, min(min(c) for c in json.loads(s.frame())["colors"]))
    assert top >= 200, f"サビの白が弱い（最大 {top}）"


def test_会話の色は派手さより優先される():
    """★どんなに派手でも、聞いているときは緑。紙に書いてある。"""
    s = LedState(count=N, pattern="strobe", max_brightness=1.0)
    s.enabled, s.talk = True, "listening"
    for c in json.loads(s.frame())["colors"]:
        assert c[1] > c[0] and c[1] > c[2], f"緑になっていない {c}"


# ── ここから「もっと派手に」（2026-09-10）─────────────
def test_サビは白で点滅する_べた塗りにしない():
    """★2.5秒ずっと全灯白は、電流も超えるし、見た目も弱い。

    Alan Walker のドロップは**白の暴力的なストロボ**。
    点けっぱなしより、切れ目があるほうが強い。
    """
    s = LedState(count=N, max_brightness=1.0)
    s.enabled, s.flash_white, s.bpm = True, True, 128.0
    peaks = []
    for i in range(200):
        s.now = (lambda v=i * 0.005: v)          # ★時計を進める
        peaks.append(max(max(c) for c in json.loads(s.frame())["colors"]))
    assert max(peaks) >= 240, "サビの白が弱い"
    assert min(peaks) <= 40, "サビが点けっぱなし（電流も見た目も損）"


def test_チカチカが多い():
    """★「もっとチカチカ」。1拍あたりの明滅を数える。"""
    for pat, least in (("strobe_hard", 3), ("build", 4)):
        fr = _frames(pat, n=480, beats=8)
        peaks = [_peak(f) for f in fr]
        blinks = sum(1 for a, b in zip(peaks, peaks[1:]) if (a > 128) != (b > 128))
        per_beat = blinks / 2 / 8
        assert per_beat >= least, f"{pat} は1拍あたり {per_beat:.1f} 回。少ない"


def test_粒が飛ぶ():
    """★きれいに揃った動きだけだと、上品になってしまう。

    ばらけた粒が飛ぶ瞬間があること（エキセントリックさ）。
    """
    fr = _frames("show", n=480, beats=32)
    scattered = 0
    for f in fr:
        on = [i for i, c in enumerate(f) if max(c) > 120]
        if len(on) >= 3:
            gaps = [b - a for a, b in zip(on, on[1:])]
            if gaps and max(gaps) >= 3:        # 離れた場所が同時に光っている
                scattered += 1
    assert scattered >= 10, f"ばらけた瞬間が {scattered} しかない"


# ── laser を2本にする（2026-09-10・本人の指定）────────────
def test_レーザーは2本ある():
    """★交差する瞬間がいちばんきれい。1本だと通り過ぎるだけ。"""
    fr = _frames("laser", n=240, beats=4)
    two = 0
    for f in fr:
        on = [i for i, c in enumerate(f) if max(c) > 120]
        if len(on) >= 2:
            gaps = [b - a for a, b in zip(on, on[1:])]
            if gaps and max(gaps) >= 4:      # 離れた2つの塊
                two += 1
    assert two >= len(fr) * 0.4, f"2本に見える瞬間が {two}/{len(fr)} しかない"


def test_レーザーは逆方向に走る():
    """★同じ方向に2本だと、ただの太い線に見える。"""
    fr = _frames("laser", n=240, beats=4)

    def heads(f):
        on = [i for i, c in enumerate(f) if max(c) > 120]
        return (min(on), max(on)) if on else None

    seq = [h for h in (heads(f) for f in fr) if h]
    # 左端と右端が「逆向きに動く」区間があること
    opposite = 0
    for (a1, b1), (a2, b2) in zip(seq, seq[1:]):
        if (a2 - a1) * (b2 - b1) < 0:
            opposite += 1
    assert opposite >= 10, f"逆向きに動く瞬間が {opposite} しかない"


def test_交差した瞬間はいちばん明るい():
    """★すれ違いを見せ場にする。重なったら白く強くなる。"""
    fr = _frames("laser", n=240, beats=4)
    peaks = [_peak(f) for f in fr]
    assert max(peaks) >= 250, "交差の瞬間に強さが出ていない"


# ── sweep を4方向にする（2026-09-10・本人の指定）──────────
#   「片方から片方へストロボが流れる（1秒くらい）／逆に流れる／
#     両サイドから中央に集まる／中央から外に広がる」
def _sweep_at(beats, n=240, sec_per_cycle=None):
    """sweep を beats 拍ぶん走査する。"""
    s = LedState(count=N, pattern="sweep", max_brightness=1.0)
    return [s._show(int(i / n * beats), (i / n * beats) % 1.0, 1.0)
            for i in range(n)]


def _on(f, th=120):
    return [i for i, c in enumerate(f) if max(c) > th]


def test_sweepは4つの向きを持つ():
    """★1方向だけだと、すぐ見飽きる。"""
    from led import LedState as L
    assert hasattr(L, "SWEEP_DIRS"), "向きの定義が無い"
    assert len(L.SWEEP_DIRS) == 4, f"向きが {len(L.SWEEP_DIRS)} 種類しかない"
    assert set(L.SWEEP_DIRS) == {"ltr", "rtl", "in", "out"}


def test_sweepは端から端まで届く():
    touched = set()
    for f in _sweep_at(16):
        touched |= set(_on(f))
    assert min(touched) <= 2 and max(touched) >= N - 3, \
        f"端まで届いていない（{min(touched)}〜{max(touched)}）"


def test_中央に集まる向きがある():
    """★両サイドから中央へ。2つの塊が近づいて、中央で1つになる。"""
    s = LedState(count=N, pattern="sweep", max_brightness=1.0)
    gaps = []
    for i in range(60):
        f = s._sweep(0.0 + i / 60, "in", 1.0)
        on = _on(f)
        if len(on) >= 2:
            gaps.append(max(on) - min(on))
    assert gaps and gaps[0] > gaps[-1], \
        f"中央に集まっていない（最初 {gaps[0]} → 最後 {gaps[-1]}）"


def test_外へ広がる向きがある():
    s = LedState(count=N, pattern="sweep", max_brightness=1.0)
    gaps = []
    for i in range(60):
        f = s._sweep(0.0 + i / 60, "out", 1.0)
        on = _on(f)
        if len(on) >= 2:
            gaps.append(max(on) - min(on))
    assert gaps and gaps[-1] > gaps[0], \
        f"外へ広がっていない（最初 {gaps[0]} → 最後 {gaps[-1]}）"


def test_一往復は目が追える速さ():
    """★実機で見て決めた（2026-09-10）。

    0.70秒は速すぎて「走っている」ではなく「点滅」に見えた。
    **目が線を追える速さ**が、走行に見える条件。
    """
    from led import LedState as L
    sec = L.SWEEP_BEATS * 60.0 / 128.0
    # ★実機で4回調整して決めた幅（2026-09-10）。
    #   0.70秒=点滅に見える／1.17秒=遅い。**走行に見える幅は意外と狭い。**
    # ★実機で7回調整して決めた（2026-09-10）。最後は本人が 0.65 と数字で指定。
    #   1.17秒=遅い。**速い側の限界は、尾の長さで変わる**（尾が長いと速くても追える）。
    assert 0.40 <= sec <= 0.52, f"1周が {sec:.2f} 秒。走行に見えない"


def test_煽りは4拍で効く():
    """★本人の指定「もう少し早くして」（2026-09-10）。8拍は長い。"""
    from led import LedState as L
    assert L.BUILD_BEATS == 4, f"煽りが {L.BUILD_BEATS} 拍。長いと効きが遅い"


# ── 爆発直前の「溜め」（2026-09-10・本人の指定）──────────
def test_ビルドの最後に溜めがある():
    """★Alan Walker のドロップ前は、たいてい無音と暗転が入る。

    **止まりがあると、次の一発が効く。**
    """
    fr = _frames("build", n=400, beats=4)
    peaks = [_peak(f) for f in fr]
    tail = peaks[int(len(peaks) * 0.88):]          # 最後の12%
    assert max(tail) <= 30, f"溜めが無い（最後の明るさ {max(tail)}）"
    # 溜めの手前は、いちばん激しいこと
    before = peaks[int(len(peaks) * 0.70):int(len(peaks) * 0.85)]
    assert max(before) >= 220, "溜めの直前が弱い"


def test_混在は同じ模様を続けない():
    """★「ランダムで混在するのが最高」（本人）。ただし同じものは続けない。"""
    from led import LedState as L
    s = L(count=N, pattern="show", max_brightness=1.0)
    seq = [s._pick(n) for n in range(0, 200, 4)]
    assert len(set(seq)) >= 4, f"出てくる模様が {len(set(seq))} 種類しかない"
    assert all(a != b for a, b in zip(seq, seq[1:])), "同じ模様が続いている"


def test_混在は毎回同じ並びにならない():
    """★決まった順だと、見ているうちに次が読めてしまう。"""
    from led import LedState as L
    s = L(count=N, pattern="show", max_brightness=1.0)
    a = [s._pick(n) for n in range(0, 120, 4)]
    b = [s._pick(n) for n in range(1000, 1120, 4)]
    assert a != b, "並びが固定されている"


# ── 色のシリーズ（2026-09-10・本人の指定）──────────────
#   「赤と青が混在するというより、赤シリーズ・青シリーズみたいに分ける」
def _family(c):
    """その色がどっち側か。白と暗いのは中立。"""
    r, g, b = c
    if max(c) < 40:
        return None
    if b > r + 50:
        return "blue"
    if r > b + 50:
        return "red"
    return None                      # 白＝どちらでも使える


def test_1つの画の中で赤と青が混ざらない():
    """★同時に混ぜると濁る。**シリーズで切り替える。**"""
    for pat in ("strobe_hard", "laser", "sweep", "sparks", "build"):
        for f in _frames(pat, n=200, beats=64):
            fams = {_family(c) for c in f} - {None}
            assert len(fams) <= 1, f"{pat} で赤と青が同居している"


def test_赤シリーズも青シリーズも出てくる():
    seen = set()
    for f in _frames("show", n=600, beats=256):
        seen |= {_family(c) for c in f} - {None}
    assert seen == {"blue", "red"}, f"出てきたのは {seen} だけ"


def test_青が主で赤はたまに():
    """★Alan Walker に忠実に。青が基調、赤は差し色。"""
    from led import LedState as L
    s = L(count=N, max_brightness=1.0)
    fams = [s._series_name(n) for n in range(0, 512)]
    blue = fams.count("blue") / len(fams)
    assert blue >= 0.65, f"青が {blue:.0%} しかない"
    assert blue <= 0.90, f"青が {blue:.0%}。赤が出てこない"


def test_シリーズは模様より長く続く():
    """★模様と同時に色まで変わると、落ち着かない。色のほうが大きな単位。"""
    from led import LedState as L
    assert L.SERIES_BEATS > L.SHOW_BEATS, "色が模様より短い周期で変わっている"


# ── ブロック状の模様（2026-09-10・本人が提示した写真から）──────
#   赤い横棒が並ぶ、回路図のような画。なめらかな波ではなく四角い塊。
def test_ブロックの境目がはっきりしている():
    """★なめらかに減衰させない。**塊と黒の境目が立つ。**"""
    for f in _frames("segments", n=120, beats=16):
        on = [max(c) > 60 for c in f]
        # 中間の明るさ（ぼやけた縁）がほとんど無いこと
        mid = sum(1 for c in f if 60 < max(c) < 180)
        assert mid <= N * 0.25, f"縁がぼやけている（中間 {mid}個）"


def test_黒のほうが広い():
    """★写真は、光っている面積より暗い面積のほうが広い。"""
    ratios = []
    for f in _frames("segments", n=120, beats=16):
        ratios.append(sum(1 for c in f if max(c) > 60) / N)
    avg = sum(ratios) / len(ratios)
    assert avg <= 0.5, f"光りすぎ（平均 {avg:.0%}）"


def test_ブロックの並びが拍で変わる():
    seen = set()
    for f in _frames("segments", n=120, beats=16):
        seen.add(tuple(max(c) > 60 for c in f))
    assert len(seen) >= 6, f"並びが {len(seen)} 通りしかない"


def test_赤シリーズは深い赤():
    """★ピンク寄りではなく、血のような赤（写真の色）。"""
    from led import LedState as L
    for c in L.SERIES["red"]:
        r, g, b = c
        assert r >= 200, f"赤が浅い {c}"
        assert b <= 60, f"青が混ざってピンクに寄っている {c}"
