"""受け入れ試験の判定。**ファームを焼く前後で、劣化を見逃さない。**

★2026-09-12、タッチの不具合を直すためにファームを焼き替える。
  焼くと**全部が変わりうる**（首・LED・カメラ・マイク・スピーカー・表情・
  ストリーム・beat mode）。**直った1つの陰で、他が壊れても気づけない。**

    焼く前  基準を記録する
    焼く後  同じ試験を回して、**差分だけ**を見る

★判定ロジックは実機なしで試験する（ここ）。実機を叩く部分は薄く保つ。
"""
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "app" / "dj"))
from acceptance import CHECKS, Result, compare, summarize   # noqa: E402


def _snap(**over):
    base = {c: Result(c, True, "ok") for c in CHECKS}
    for k, v in over.items():
        base[k] = v
    return base


def test_調べる項目が網羅されている():
    """★焼くと全部変わりうる。**主要な機能を全部見る。**"""
    need = {"tools", "head", "leds", "avatar", "touch", "mic", "speaker",
            "camera", "pose_stream", "led_stream", "beat", "stt", "tts"}
    missing = need - set(CHECKS)
    assert not missing, f"見ていない機能がある: {sorted(missing)}"


def test_同じなら差分なし():
    a = _snap(); b = _snap()
    assert compare(a, b) == []


def test_壊れたら検出する():
    """★これが本題。焼いたあと動かなくなったものを必ず出す。"""
    before = _snap()
    after = _snap(head=Result("head", False, "角度が返らない"))
    diff = compare(before, after)
    assert len(diff) == 1 and diff[0].kind == "デグレ"
    assert diff[0].name == "head"


def test_直ったものも出す():
    """★何が直ったかも記録する。焼いた意味を測るため。"""
    before = _snap(touch=Result("touch", False, "反応しない"))
    after = _snap()
    diff = compare(before, after)
    assert len(diff) == 1 and diff[0].kind == "改善"


def test_値の悪化も検出する():
    """★動いてはいるが遅くなった、を見逃さない。"""
    before = _snap(head=Result("head", True, "ok", value=0.20))
    after = _snap(head=Result("head", True, "ok", value=0.95))
    diff = compare(before, after, worse_ratio=1.5)
    assert diff and diff[0].kind == "劣化"


def test_誤差では騒がない():
    before = _snap(head=Result("head", True, "ok", value=0.20))
    after = _snap(head=Result("head", True, "ok", value=0.22))
    assert compare(before, after, worse_ratio=1.5) == []


def test_測れなかったものは劣化と区別する():
    """★「試験できなかった」を「壊れた」と混ぜない。**判断を誤らせる。**"""
    before = _snap()
    after = _snap(camera=Result("camera", None, "人の確認が要る"))
    diff = compare(before, after)
    assert diff and diff[0].kind == "未確認"


def test_まとめは結論から出る():
    before = _snap(touch=Result("touch", False, "反応しない"))
    after = _snap(head=Result("head", False, "角度が返らない"))
    text = summarize(compare(before, after))
    assert text.splitlines()[0].startswith(("★", "デグレ", "問題"))
    assert "head" in text


def test_人手が要る項目が明示されている():
    """★自動で測れないものは、**測れないと分かる形**にする。"""
    manual = [c for c, spec in CHECKS.items() if spec.get("manual")]
    assert "touch" in manual, "タッチは人が触らないと測れない"
    assert len(manual) <= 4, "人手の項目が多すぎると、当日回せない"


def test_人手の項目でも端末入力を求めない():
    """★2026-09-12。スピーカーの確認で y/n を端末から聞いていた。

    **当日、端末は誰も見ない。** そして自動試験が止まる。
    機械が確かめられるものは、機械に確かめさせる。
    """
    src = (ROOT / "scripts" / "device_check.py").read_text(encoding="utf-8")
    assert "input()" not in src and "to_thread(input)" not in src, \
        "端末の入力待ちが残っている"


# ── 数字の向き（2026-09-12 に実測して気づいた） ──────────────
#
# 基準取りで「頭なで 20秒で1回」が出た。value=1.0 で保存される。
# ところが compare() は **小さいほど良い**（秒数）前提で書かれていた。
# 焼いて 15回 に**直った**瞬間、15 > 1.0×1.5 で「劣化」と報告してしまう。
#
# ★直ったことをデグレと呼ぶ試験は、無いより悪い。


def test_touch_hits_more_is_better():
    """★撫での検出回数は多いほど良い。増えたら改善であって劣化ではない。"""
    before = {"touch": Result("touch", True, "20秒で 1回", 1.0)}
    after = {"touch": Result("touch", True, "20秒で 15回", 15.0)}
    kinds = [d.kind for d in compare(before, after)]
    assert "劣化" not in kinds, f"増えたのに劣化と言っている: {kinds}"


def test_touch_hits_fewer_is_worse():
    """★逆に減ったら見逃さない。焼いて悪化したのに黙るほうが怖い。"""
    before = {"touch": Result("touch", True, "20秒で 15回", 15.0)}
    after = {"touch": Result("touch", True, "20秒で 2回", 2.0)}
    assert [d.kind for d in compare(before, after)] == ["劣化"]


def test_seconds_still_smaller_is_better():
    """★秒数の向きは変えない。遅くなったら劣化のまま。"""
    before = {"tts": Result("tts", True, "", 1.0)}
    after = {"tts": Result("tts", True, "", 3.0)}
    assert [d.kind for d in compare(before, after)] == ["劣化"]
