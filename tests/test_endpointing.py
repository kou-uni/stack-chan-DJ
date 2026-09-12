"""話し終わりを検出して、録音を早く切る。

★人は話し終わったら止まる。5秒固定で待つのが一番不自然だった（実測17.5秒）。
  無音が続いたら切る。**これだけで体感が変わる。**

★誤爆すると最悪。**言葉の途中の一瞬の間で切ったら、質問が半分になる。**
  だから「切る条件」を厳しく作って、ここで固定する。
"""
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "app" / "dj"))
from endpoint import Endpointer   # noqa: E402


def _feed(ep, pattern, frame_ms=60):
    """pattern は 'S'=喋っている / '.'=無音。1文字=1フレーム。"""
    for i, c in enumerate(pattern):
        if ep.feed(0.05 if c == "S" else 0.001, (i + 1) * frame_ms / 1000.0):
            return (i + 1) * frame_ms / 1000.0
    return None


def test_喋り終わって無音が続いたら切る():
    ep = Endpointer(silence_s=0.8, min_speech_s=0.3, max_s=5.0)
    t = _feed(ep, "S" * 30 + "." * 20)          # 1.8秒喋って1.2秒黙る
    assert t is not None, "切れていない"
    assert 2.4 <= t <= 3.2, f"{t:.1f}秒で切った。早すぎ／遅すぎ"


def test_言葉の途中の短い間では切らない():
    """★「ファームって……なんですか」の『……』で切ったら質問が壊れる。"""
    ep = Endpointer(silence_s=0.8, min_speech_s=0.3, max_s=5.0)
    t = _feed(ep, "S" * 15 + "." * 8 + "S" * 15 + "." * 20)
    assert t is not None and t > 2.0, f"{t}秒で切った。途中の間で切っている"


def test_一度も喋らなければ切らない():
    """★合図の前に録り始めたとき、無音だけで即終了すると質問を取り逃がす。"""
    ep = Endpointer(silence_s=0.8, min_speech_s=0.3, max_s=5.0)
    assert _feed(ep, "." * 60) is None, "無音だけで切った"


def test_喋りが短すぎたら切らない():
    """★咳払いや物音で切らない。"""
    ep = Endpointer(silence_s=0.8, min_speech_s=0.3, max_s=5.0)
    assert _feed(ep, "SS" + "." * 30) is None, "一瞬の音で切った"


def test_上限で必ず止まる():
    """★喋り続けられても、いつかは切る。"""
    ep = Endpointer(silence_s=0.8, min_speech_s=0.3, max_s=3.0)
    t = _feed(ep, "S" * 100)
    assert t is not None and t <= 3.1, f"{t}秒。上限で止まっていない"


def test_閾値は実測から来ている():
    """★実機のマイクは遠い。声でもピーク0.055しかない（2026-09-12 実測）。

    汎用の閾値をそのまま使うと、全部無音と判定される。
    """
    from endpoint import SPEECH_LEVEL
    assert SPEECH_LEVEL <= 0.02, f"{SPEECH_LEVEL} は実機の声には高すぎる"


def test_話し始める前に切らない():
    """★2026-09-12 の実測。合図から話し出すまで、人は1〜2秒かかる。

    その前に切ると、録音が1.6秒で終わって**何も録れない**。
    「喋った」と判定されるのは、echo や物音でも起きる。
    """
    ep = Endpointer(silence_s=0.8, min_speech_s=0.3, max_s=8.0, min_total_s=2.5)
    # 最初に短い物音（echo）→ そのあとずっと無音
    t = _feed(ep, "SSSSS" + "." * 60)
    assert t is None or t >= 2.5, f"{t}秒で切った。人が話し出す前"


def test_最低時間を過ぎれば普通に切れる():
    ep = Endpointer(silence_s=0.8, min_speech_s=0.3, max_s=8.0, min_total_s=2.5)
    # 2.5秒以降に喋って、そのあと無音
    t = _feed(ep, "." * 45 + "S" * 25 + "." * 20)
    assert t is not None and 3.8 <= t <= 5.2, f"{t}秒。切れ方がおかしい"
