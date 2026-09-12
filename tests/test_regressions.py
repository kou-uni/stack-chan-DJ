"""2026-09-08 に実際に踏んだバグの再発防止。

★どれも実機を数時間触って見つけたもの。**もう二度と手で探さない。**
  リファクタでこれが1つでも落ちたら、その日と同じ時間を溶かすことになる。
"""
import json, math, sys
from pathlib import Path
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "app" / "dj"))


def _console_src() -> str:
    """アプリのソース全部を1本につなげて返す。

    ★1ファイルに固定しない。モジュール分割のたびにテストが落ちるのは、
      テストが「置き場所」を見ているから。見るべきは「あるかどうか」。
    """
    d = ROOT / "app" / "dj"
    return "\n".join(f.read_text(encoding="utf-8")
                     for f in sorted(d.rglob("*.py")))


# ── ① LEDストリームのフレーム形式 ──────────────────────
# 728フレーム全部が黙って捨てられた。エラーは一切返らなかった。
#   pose : {"frame": …, "yaw", "pitch"}
#   LED  : {"kind":  …, "ts", "colors"}   ← 別物
def test_LEDフレームは_kind_と_ts_を持つ():
    """★実際に出るフレームで見る。ソースの文字列検索だと移動しただけで落ちる。"""
    from led import LedState
    f = json.loads(LedState().frame())
    assert "kind" in f, "LEDは frame ではなく kind。間違えると全フレーム破棄される"
    assert "ts" in f, "ts が無いと検証に落ちる"
    assert "colors" in f
    assert "frame" not in f, "pose のキーを混ぜると全部捨てられる"


def test_LEDのtargetは_base_ring():
    """'base' は無効値。購読が黙って失敗する。"""
    from led import LedState
    assert LedState().target == "base_ring"
    assert 'default="base"' not in _console_src(), "CLI の既定値も base_ring であること"


# ── ② pitch の単位 ────────────────────────────────
# 45 を送ったら gateway が 45 を足して 90 → 85 にクランプ、真下に張り付いた。
def test_踊りのpitchは45を足していない():
    from motion.arbiter import PITCH_OFFSET_MAX
    assert PITCH_OFFSET_MAX <= 40, "45+40=85 が実機の下限。これを超える差は送れない"
    src = _console_src()
    assert "bob = 45.0" not in src, "pitch に 45 を足すと真下に張り付く"


# ── ③ 振り付けが本当に入っているか ─────────────────────
# 置換が3回空振りし、「入れました」と報告しながら一度も入っていなかった。
def test_振り付けのフレーズが実在する():
    """★grep ではなく「実際に違う動きをするか」で見る。

    以前は名前だけあって中身が入っていない事故が起きた。
    文字列検索だと、置換が空振りしても気づけない。
    """
    from motion import phrases as P

    sig = {}
    for ph in P.PHRASES:
        sig[ph] = tuple(round(v, 3)
                        for i in range(60)
                        for v in P.angles(ph, i * 0.1, (i % 30) / 30, 42.0, 9.0))

    for ph in ("scan", "point_l", "point_r", "accent", "double", "front", "nod2", "yes"):
        assert ph in sig, f"フレーズ {ph} が定義されていない"
        assert sig[ph] != sig["sway"], f"フレーズ {ph} が sway と同じ動き＝未実装"

    assert len(set(sig.values())) == len(P.PHRASES), "同じ動きのフレーズが混ざっている"


def test_客席は左右にいる_縦の動きは控えめ():
    """真上にも真下にも客はいない。横を大きく、縦は控えめに。"""
    src = _console_src()
    sway = float(src.split('"--sway-deg", type=float, default=')[1].split(',')[0])
    nod = float(src.split('"--nod-deg", type=float, default=')[1].split(',')[0])
    assert sway >= 30, "フロアの端まで届かない"
    assert nod < sway / 2, "縦が大きすぎる。客は上下にいない"


# ── ④ 起動順序 ───────────────────────────────────
# beat_mode_start が motion を有効にして始まるので、後から set_mode しないと上書きされる。
def test_beat_mode_startより後にモードを確定する():
    src = _console_src()
    assert src.index('"beat_mode_start"') < src.index('set_mode(args.mode'), \
        "beat_mode_start の後に set_mode しないと、待機モードでも首が振れる"


# ── ⑤ ヒステリシス ────────────────────────────────
# 閾値を1本だけ引くと、そこが振動点になる。今日3回踏んだ。
def test_開始と停止の閾値が別である():
    src = _console_src()
    assert "--stop-ratio" in src
    ratio = float(src.split('"--stop-ratio", type=float, default=')[1].split(',')[0])
    assert 0 < ratio < 1, "止める閾値は始める閾値より低くする"


# ── ⑥ 自己雑音 ───────────────────────────────────
# サーボ音は音楽の13倍。動いている間の観測は停止判断に使えない。
def test_音量の測定は停止中にだけ行う():
    src = _console_src()
    assert "_listen_check" in src
    ms = int(src.split('"--listen-check-ms", type=int, default=')[1].split(',')[0])
    assert ms >= 1200, "音量の窓が1.2秒。それより短いとサーボ音が残る"


# ── ⑦ MIDI の割り当てが実測値と一致しているか ──────────────
def test_MIDIの割り当てが記録と一致する():
    m = json.loads((ROOT / "app" / "dj" / "mapping.json").read_text(encoding="utf-8"))
    c = m["controls"]
    assert (c["yaw"]["ch"], c["yaw"]["num"]) == (6, 23)
    assert (c["pitch"]["ch"], c["pitch"]["num"]) == (0, 15)
    assert (c["btn_play"]["ch"], c["btn_play"]["num"]) == (0, 11)
    assert (c["btn_off"]["ch"], c["btn_off"]["num"]) == (6, 99)


# ── ⑧ アバターの仕様 ───────────────────────────────
def test_アバターは14枚で537600バイト():
    raw = ROOT / "app" / "avatar" / "avatar_layered.raw"
    if raw.exists():
        assert raw.stat().st_size == 14 * 160 * 120 * 2


# ── ⑧ 外付けLEDテープの購読 ──────────────────────
def test_外付けテープの購読には本数が要る():
    """2026-09-10。`led_count` を渡さずに購読を頼み、黙って失敗していた。

        {"ok": false, "error": "led_count is required for port_b/port_c"}

    ★ツールはエラーを**返す**が、例外は投げない。起動ログには何も出ない。
      本体リング(base_ring)では要らないので、外付けにした瞬間だけ壊れた。
    """
    src = (ROOT / "app" / "dj" / "console.py").read_text(encoding="utf-8")
    body = src[src.index("async def init_device"):src.index("async def device_watchdog")]
    i = body.index("stackchan_follow_led_stream")
    # 購読を頼む手前で、外付けなら本数を積んでいること
    assert "led_count" in body[:i], \
        "port_b / port_c への購読には led_count が必須（無いと黙って失敗する）"
    assert 'led_target != "base_ring"' in body[:i], \
        "本体リングと外付けで扱いを分けていない"


def test_ツールの戻り値を見て失敗に気づくようにする():
    """★エラーを返すだけのツールは、見ないと気づけない。"""
    src = _console_src()
    assert "def _check(" in src or "_ok(" in src, \
        "ツールの戻り値を確かめる仕組みが無い"


# ── ⑨ 日本語の聞き取りが崩れる ──────────────────────
def test_STTは無音を捨てる設定になっている():
    """2026-09-12。gateway の既定が vad_filter=False / beam_size=1 で、
    日本語が崩れた（「ファームってなんですか」→「パー持って何ですか今 本性 手措置が」）。

    ★8秒録って、実際に喋っているのは2秒ほど。
      残りの無音に対して Whisper が**幻聴**を出していた。
      **無音を捨てるだけで直る。**

    ★vendor を上書き再インストールすると消える改変なので、試験で見張る。
    """
    p = (ROOT / "vendor" / "stackchan-mcp" / "gateway" / "stackchan_mcp"
         / "stt" / "faster_whisper.py")
    src = p.read_text(encoding="utf-8")
    assert "STACKCHAN_STT_VAD" in src, "無音を捨てる設定が消えている（再インストールした？）"
    # ★コメント行は除いて見る（説明文に旧設定が書いてあるため）
    code = "\n".join(l for l in src.splitlines() if not l.strip().startswith("#"))
    assert "vad_filter=False" not in code, "無音を捨てない設定に戻っている"
    assert "beam_size=1," not in code, "精度より速度の設定に戻っている"


def test_話し終わり検出は実測の音量で判定する():
    """2026-09-12。最初「Opusフレームの長さ」で音量を推測しようとした。

    ★**根拠が無い**（可変ビットレートとは限らない）。
      デコードして RMS を測る。閾値（endpoint.SPEECH_LEVEL）と単位を揃えるため。
    """
    p = (ROOT / "vendor" / "stackchan-mcp" / "gateway" / "stackchan_mcp"
         / "stt" / "orchestrator.py")
    src = p.read_text(encoding="utf-8")
    i = src.index("def _frame_level")
    body = src[i:i + 1200]
    assert "decode" in body, "デコードせずに音量を推測している"
    assert "len(frame) / 200" not in body, "長さから推測する作りに戻っている"


def test_話し終わり検出が有効になっている():
    """2026-09-12。パスを `parents[4]` と数えて1つずれ、**黙って無効**になっていた。

    ★数えずに探す。そして**失敗したらログに出す**（握りつぶさない）。
    """
    import sys as _s
    _s.path.insert(0, str(ROOT / "vendor" / "stackchan-mcp" / "gateway"))
    from stackchan_mcp.stt.orchestrator import _make_endpointer
    assert _make_endpointer(8000) is not None, "話し終わり検出が無効になっている"


def test_無音のとき語彙を読み上げない():
    """2026-09-12。無音のとき、教えた語彙をそのまま幻聴した。

        「バックアップは必要ですか」→「ファームウェアのゲートウェア」

    ★`initial_prompt` の副作用。**教えた言葉が、そのまま出力に化ける。**
      「喋っていない確率」が高い区間を捨てて防ぐ。
    """
    p = (ROOT / "vendor" / "stackchan-mcp" / "gateway" / "stackchan_mcp"
         / "stt" / "faster_whisper.py")
    src = p.read_text(encoding="utf-8")
    assert "no_speech_prob" in src, "喋っていない区間を捨てていない"
    assert "no_speech_threshold" in src
