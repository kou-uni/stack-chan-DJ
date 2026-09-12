"""会話のUX。設計は docs/ux-conversation.md。

★「性能が変だ」と思われる瞬間は、いつも同じ形をしている：
  ① 間違った答えを自信ありげに返す  ← いちばん壊れて見える
  ② 無言で終わる
  聞き取れないこと自体は、実はそこまで悪くない。

★だから **精度を上げる**のではなく、**外れても壊れて見えない**形にする。
"""
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "app" / "dj"))

from talk import (echo_back, route, CONFIDENT_MIN,   # noqa: E402
                  ASK_AGAIN, TO_AGENT, TOPICS)


def test_聞き取れた話題を復唱する():
    """★誤認識を隠さない。隠すから壊れて見える。"""
    assert echo_back("ファームってなんですか").startswith("ファーム")
    assert "だね" in echo_back("ファームってなんですか")


def test_話題が拾えなければ復唱しない():
    assert echo_back("あーうー") == ""


def test_全文でなくキーワードで拾う():
    """★振り分けに必要なのは話題だけ。一字一句は要らない。

    多少崩れても、キーワードが1つ残っていれば成立する。
    """
    for heard in ("ファームって何ですか", "ファームの話",
                  "あーファームってなんだっけ", "ふぁーむ"):
        assert route(heard).topic == "firm", heard


def test_崩れた聞き取りでも話題が拾える():
    """実測で出た崩れ方。★これでも動くこと。"""
    assert route("バックアップは必要ですか").topic == "backup"
    assert route("アンバインドってなんですか").topic == "unbind"
    assert route("自分でも作れますか").topic == "start"


def test_話題が分からなくても黙らない():
    """★2026-09-12 に方針を変えた。

    最初は「分からなければ聞き返す」にしていたが、**聞こえているのに
    聞き返すのは失礼**（「おはよう」を無視した）。
    聞こえたなら応じる。聞き返すのは**本当に何も聞こえなかったとき**だけ。
    """
    r = route("んんb ターフォースでかん")
    assert r.topic == "chat"
    assert r.reply and r.reply != ASK_AGAIN


def test_空なら聞き返す():
    """★無言で終わらない。**壊れたと思われる。**"""
    for s in ("", "   ", None):
        assert route(s).reply == ASK_AGAIN


def test_知らない話題はエージェントへ振る():
    """★「知らない」を故障ではなく性格にする。"""
    from talk import SMALL_TALK
    assert route("今日の天気は").reply
    r = route("量子コンピュータについて教えて")
    assert r.reply in (SMALL_TALK, TO_AGENT) or "エージェント" in r.reply


def test_決め台詞は短い():
    """★音声は読み飛ばせない。決め台詞が長いと台無し。"""
    for line in (ASK_AGAIN, TO_AGENT):
        assert len(line) <= 30, f"「{line}」は長い"


def test_確信の下限が決まっている():
    """★どこから「分かった」とみなすかを、数字で持つ。"""
    assert 0.0 < CONFIDENT_MIN <= 1.0


def test_話題は当日のものだけ():
    """★何でも答えるロボットにしない。**受付と振り分けに徹する。**"""
    assert set(TOPICS) >= {"firm", "backup", "unbind", "start", "privacy"}
    assert len(TOPICS) <= 12, "話題を増やしすぎると、どれも浅くなる"


def test_撫でたら聞き始める():
    """★合図を待たせない。**人が起動を決める。**

    タイミング問題が構造的に消える。騒音にも強い。
    """
    src = (ROOT / "app" / "dj" / "talk.py").read_text(encoding="utf-8")
    assert "async def on_touch" in src, "撫でて会話を始める入口が無い"


def test_復唱してから答える():
    src = (ROOT / "app" / "dj" / "talk.py").read_text(encoding="utf-8")
    body = src[src.index("async def converse"):]
    assert "echo_back" in body, "復唱していない"
    i_echo, i_ans = body.index("echo_back"), body.index("route(")
    assert i_echo < body.rindex("say"), "復唱が答えより後にある"


def test_合図は実機から出す():
    """★端末は当日誰も見ない。合図は首とLEDで出す。"""
    src = (ROOT / "app" / "dj" / "talk.py").read_text(encoding="utf-8")
    body = src[src.index("async def converse"):]
    assert "start_listening" in body, "LEDの合図が無い"
    assert "motion" in body, "体の反応が無い"
    assert "print(" not in body, "端末に出している（当日は誰も見ない）"


def test_頭脳は話題が分かったときだけ使う():
    """★分からないのに頭脳へ投げると、的外れな答えを自信ありげに返す。

    これが「性能が変だ」と思われる最大の原因。
    """
    src = (ROOT / "app" / "dj" / "talk.py").read_text(encoding="utf-8")
    body = src[src.index("async def converse"):]
    i_route, i_think = body.index("route("), body.index("think(")
    assert i_route < i_think, "振り分けの前に頭脳へ投げている"


def test_起動の手段が複数用意されている():
    """★タッチセンサが動かないことがある（2026-09-12、I2Cに現れず）。

    **1つの入力に依存しない。** どの手段でも
    「人が起動を決める」というジャーニーは変わらない。
    """
    src = (ROOT / "app" / "dj" / "talk.py").read_text(encoding="utf-8")
    assert "async def on_touch" in src
    assert "async def on_request" in src, "撫でる以外の入口が無い"


def test_撫でた瞬間に手応えを返す():
    """★2026-09-12。動いていたのに「無反応」と言われた。

    撫でてから緑になるまで約1秒、その間**無音・無動作**。
    ログ上は成功していても、**その人には効いたと分からない。**

    > 触った瞬間に返す。**遅れて返るのは、返っていないのと同じ。**
    """
    src = (ROOT / "app" / "dj" / "talk.py").read_text(encoding="utf-8")
    body = src[src.index("async def converse"):]
    i_ack = body.index("_acknowledge")
    i_listen = body.index('"listen"')
    assert i_ack < i_listen, "聞き始める前に手応えを返していない"


def test_手応えは動きと顔で返す():
    """★音だけだと騒がしい会場で埋もれる。**体で返す。**"""
    src = (ROOT / "app" / "dj" / "talk.py").read_text(encoding="utf-8")
    ack = src[src.index("async def _acknowledge"):]
    ack = ack[:ack.index("\n\n\n")] if "\n\n\n" in ack else ack
    assert "hold" in ack or "move" in ack, "首の動きが無い"
    assert "overlay" in ack, "顔が変わらない"


def test_聞こえたのに聞き返さない():
    """★2026-09-12。「おはよう」と言ったのに「ん? もういっかい」と返した。

    **聞こえているのに聞き返すのは失礼。** 話題の外でも、聞こえたなら応じる。

        何も聞こえない  → 「ん? もういっかい」
        聞こえた        → 雑談として短く返す
    """
    from talk import route, ASK_AGAIN
    for greeting in ("おはよう", "こんにちは", "はじめまして", "ありがとう"):
        r = route(greeting)
        assert r.reply != ASK_AGAIN, f"「{greeting}」を聞き返している"
        assert r.reply, f"「{greeting}」に無言"


def test_挨拶には挨拶を返す():
    from talk import route
    assert any(w in route("おはよう").reply for w in ("おはよう", "はよ"))
    assert "ありがと" in route("ありがとう").reply or "どういたし" in route("ありがとう").reply


def test_知らない話でも黙らない():
    """★話題の外でも、聞こえたなら何か返す。無言が一番壊れて見える。"""
    from talk import route, ASK_AGAIN
    r = route("きのう映画を見たんだけどさ")
    assert r.reply and r.reply != ASK_AGAIN


def test_本当に聞こえないときだけ聞き返す():
    from talk import route, ASK_AGAIN
    assert route("").reply == ASK_AGAIN
    assert route("   ").reply == ASK_AGAIN


def test_会話中に撫でられても無視しない():
    """★2026-09-12。90秒で4回撫でて、2回しか反応しなかった。

    会話は10〜20秒かかる。その間の撫でを黙って捨てていた。
    **黙って捨てると「反応が悪い」に見える。**

        暇なとき   → 会話を始める
        会話中     → **すぐ小さくうなずく**（順番待ちが伝わる）
    """
    src = (ROOT / "app" / "dj" / "talk.py").read_text(encoding="utf-8")
    assert "class TalkDesk" in src, "手が空いているかを持つ入口が無い"
    assert "busy" in src


def test_取りこぼしを数える():
    """★「反応が悪い」を感想で終わらせない。**数えて直す。**"""
    import asyncio as _a
    from talk import TalkDesk

    class G:
        async def call(self, *a, **k): return None

    class C:
        def __init__(self):
            import presence as _p
            from motion.pose import PoseState
            self.presence, self.pose = _p.Presence(), PoseState()
            self.args = type("A", (), {"beat": False})()
        async def hand_mic_to_talk(self): pass
        async def hand_mic_back(self): pass

    desk = TalkDesk(G(), C())
    desk.busy = True
    _a.run(desk.on_touch("stroke"))
    _a.run(desk.on_touch("stroke"))
    assert desk.deferred == 2, f"取りこぼしを数えていない（{desk.deferred}）"
