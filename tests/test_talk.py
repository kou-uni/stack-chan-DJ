"""会話（サブ講師）。

    参加者が話す → listen（文字に） → Ollama（考える） → say（喋る）

★当日の狙い（docs/requirements.md C19）:
  もくもくタイムに、スタックチャンへ音声で相談すると自律的に答える。
  **短く答えて、深い話は各自のエージェントへ振る。**

★実機の制約（2026-09-12 実測）:
  「beat mode is already using the device microphone」
  **踊りと会話は同じマイクを取り合う。同時には使えない。**
"""
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "app" / "dj"))

import presence as P      # noqa: E402
from talk import (Turn, needs_mic_handover, pick_reply,   # noqa: E402
                  MAX_SPOKEN_CHARS)


def test_踊りと会話でマイクを取り合う():
    """★同時に使えない。**切り替えが要る**ことを設計として持つ。"""
    assert needs_mic_handover(beat_active=True) is True
    assert needs_mic_handover(beat_active=False) is False


def test_喋る前に会話の状態が_listening_になる():
    """★LEDが緑になる。聞いているかどうかが見て分かる（配布物の約束）。"""
    pres = P.Presence(now=lambda: 0.0)
    t = Turn(pres)
    t.start_listening()
    assert pres.talk == "listening"
    assert pres.desired()["face"] != "idle", "聞いている顔になっていない"


def test_喋っている間は_speaking():
    pres = P.Presence(now=lambda: 0.0)
    t = Turn(pres)
    t.start_speaking()
    assert pres.talk == "speaking"


def test_終わったら会話の状態が消える():
    """★消し忘れると、LEDが緑のまま固まる。"""
    pres = P.Presence(now=lambda: 0.0)
    t = Turn(pres)
    t.start_listening(); t.done()
    assert pres.talk is None


def test_返事は短く切る():
    """★音声は読み飛ばせない。長いと地獄（本人の指摘・2026-09-10）。"""
    long = "あ" * 500
    out = pick_reply(long)
    assert len(out) <= MAX_SPOKEN_CHARS, f"{len(out)}文字は長すぎる"


def test_長い話は各自のエージェントへ振る():
    """★スタックチャンは受付と振り分け。深い話は手元のエージェントが持つ。"""
    out = pick_reply("あ" * 500)
    assert "エージェント" in out, "振り分けの一言が入っていない"


def test_短い返事はそのまま():
    out = pick_reply("バックアップとアンバインドを忘れずに。")
    assert out == "バックアップとアンバインドを忘れずに。"


def test_空の返事は喋らない():
    """★無音を喋らせない。失敗したときに黙るのが正しい。"""
    assert pick_reply("") == ""
    assert pick_reply("   ") == ""


# ── console に組み込む（2026-09-12）────────────────────
def test_聞く前にマイクを踊りから取り上げる():
    """★同じマイクを取り合う。踊ったまま listen を呼ぶとエラーになる（実測）。"""
    src = (ROOT / "app" / "dj" / "talk.py").read_text(encoding="utf-8")
    assert "needs_mic_handover" in src


def test_合図を出してから録る():
    """★「いつ話せばいいか」が分からないと、空振りする（実測で2回に1回）。

    LED が緑になってから録る。**緑＝話していい**は配布物の約束。
    """
    src = (ROOT / "app" / "dj" / "talk.py").read_text(encoding="utf-8")
    i = src.index("async def converse")
    body = src[i:]
    assert body.index('start_listening') < body.index('"listen"'), \
        "緑にする前に録り始めている"


def test_喋り終わったら会話の状態を消す():
    src = (ROOT / "app" / "dj" / "talk.py").read_text(encoding="utf-8")
    body = src[src.index("async def converse"):]
    assert "done()" in body or "finally" in body, "消し忘れると緑のまま固まる"


def test_聞き取れなければ黙らない():
    """★無言で終わると、相手は壊れたと思う。**聞き取れなかったと言う。**"""
    src = (ROOT / "app" / "dj" / "talk.py").read_text(encoding="utf-8")
    assert "UNHEARD" in src, "聞き取れなかったときの一言が無い"


# ── 人間らしさ（2026-09-12）────────────────────────
def test_返事は40字まで():
    """★60字は音声で10秒。**人は10秒も一人で喋らない。**

    実測：70文字 → 10.4秒の音声 → 体感18秒。長すぎる。
    """
    from talk import MAX_SPOKEN_CHARS as M
    assert M <= 45, f"{M}字は長い。音声だと{M*0.15:.0f}秒になる"


def test_考える前に相槌を返す():
    """★沈黙が一番不自然。**間を埋める。**

    人は「えーと」と言ってから考える。無音で2秒止まると壊れて見える。
    """
    from talk import FILLERS
    assert len(FILLERS) >= 3, "相槌が少ないと、毎回同じで機械に見える"
    for f in FILLERS:
        assert len(f) <= 8, f"相槌『{f}』が長い。相槌は短いから相槌"


def test_相槌は毎回変える():
    """★同じ相槌を繰り返すと、かえって機械に見える。"""
    from talk import pick_filler
    got = {pick_filler(i) for i in range(10)}
    assert len(got) >= 3, f"{len(got)}種類しか出ない"
    assert all(pick_filler(i) != pick_filler(i + 1) for i in range(9)), "連続で同じ"


def test_空の質問では考えない():
    """★聞き取れなかったのに頭脳へ投げると、知識をそのまま読み上げる（実測）。"""
    import asyncio
    from talk import think
    assert asyncio.run(think("")) == ""
    assert asyncio.run(think("   ")) == ""


def test_見出し記号は読み上げない():
    """★Markdown の見出しがそのまま音声に乗った（実測：「シャープ スタックチャンとは」）。"""
    from talk import pick_reply
    out = pick_reply("# スタックチャンとは\n\n> M5Stack のロボットです。")
    assert "#" not in out and ">" not in out, out


def test_聞いている間は考えていることが体に出る():
    """★止まっていると「聞いていない」ように見える。"""
    src = (ROOT / "app" / "dj" / "talk.py").read_text(encoding="utf-8")
    body = src[src.index("async def converse"):]
    assert "motion" in body, "listen に体の反応を渡していない"


def test_声と音量が決まっている():
    """★2026-09-12、実機で8種類を聞き比べて決めた。うっかり変わらないよう固定する。"""
    from talk import SPEAKER_ID, VOLUME
    assert SPEAKER_ID == 14, "冥鳴ひまり（落ち着いた女性）に決めた"
    assert VOLUME == 100, "会場は騒がしい。上限まで上げる"


def test_喋るときは必ず声を指定する():
    """★指定を忘れると既定の声に戻り、人格が途中で変わる。"""
    src = (ROOT / "app" / "dj" / "talk.py").read_text(encoding="utf-8")
    body = src[src.index("async def converse"):]
    says = body.count('gw.call("say"')
    with_voice = body.count("speaker_id=SPEAKER_ID")
    assert says == with_voice, f"{says}回喋るうち、声の指定は{with_voice}回だけ"


def test_文の途中で切らない():
    """★2026-09-12 の事故。「…構成や特徴長くなるから、続きは」と途中で切れた。

    40字で機械的に切って、文の途中に振り分け文をくっつけていた。
    **文の切れ目が無ければ、振り分け文だけを返す。**
    """
    from talk import pick_reply, HANDOFF
    # 句点が無く、切れ目が作れない長文
    out = pick_reply("スタックチャンの基本的な構成や特徴について詳しく説明すると" * 3)
    assert "特徴長く" not in out
    # 途中でぶつ切りにした語のあとに振り分け文が続いていないこと
    if HANDOFF in out:
        head = out[:out.index(HANDOFF)]
        assert head == "" or head.rstrip().endswith(("。", "！", "？", "、")), \
            f"文の途中で切って繋いでいる: 「{out}」"


def test_切れ目があればそこで切る():
    from talk import pick_reply, MAX_SPOKEN_CHARS
    out = pick_reply("ロボットに焼くソフトだよ。頭脳を選べる。" + "あ" * 200)
    assert out.startswith("ロボットに焼くソフトだよ。")
    assert len(out) <= MAX_SPOKEN_CHARS + len("長くなるから、続きは君のエージェントに聞いて。")


def test_頭脳のモデルが決まっている():
    """★2026-09-12、当日の質問3問で5モデルを実測して選んだ。

    **大きさより指示追従。**「2文以内」を守れるかで決まった。
    qwen3 系は思考過程を出すので会話に使えない（実測35.9秒）。
    """
    from talk import MODEL
    assert MODEL == "gemma3:4b"
    assert "qwen3" not in MODEL, "思考過程が出力に出るモデルは使わない"


def test_喋ったあと間を置いてから録る():
    """★2026-09-12 の事故。**自分の声を文字起こししていた。**

    波形で見ると、録音の最初0.5秒は実機自身の「どうぞ」だった。
    最大RMS 0.46（人の声は0.05程度）。スピーカーが真横にあるため。

    ★DJのときと同じ形（自分のサーボ音で踊り続けた）。
      **出力が入力に回り込む**のは、この機体の構造的な癖。
    """
    from talk import SAY_TAIL_S
    assert SAY_TAIL_S >= 0.4, f"{SAY_TAIL_S}秒では自分の声が残る"
    src = (ROOT / "app" / "dj" / "talk.py").read_text(encoding="utf-8")
    body = src[src.index("async def converse"):]
    i_say = body.index('text=pick_filler') if 'text=pick_filler' in body else 0
    assert "SAY_TAIL_S" in body, "録る前の間が入っていない"


def test_意味のない前置きを落とす():
    """★「了解しました」「〜に基づいて」は、音声だと時間の無駄でしかない。

    指示で禁止しても書いてくるので、**こちら側で落とす。**
    """
    from talk import pick_reply
    for bad in ("了解しました。ファームは焼くソフトです。",
                "はい、承知しました。ファームは焼くソフトです。",
                "スタックチャンの前提知識に基づいて、質問にお答えします。"
                "ファームは焼くソフトです。",
                "ご質問ありがとうございます。ファームは焼くソフトです。"):
        out = pick_reply(bad)
        assert out.startswith("ファームは"), f"前置きが残っている: 「{out}」"


def test_前置きだけなら振り分けに回す():
    """★前置きを落として何も残らないなら、答えていない。"""
    from talk import pick_reply, HANDOFF
    out = pick_reply("了解しました。お答えします。")
    assert out == "" or HANDOFF in out, out


def test_喋り終わりを待つ関数が用意されている():
    """★呼ぶ側が毎回 sleep を書くと、いつか忘れて自分の声を録る。"""
    from talk import say_and_wait, SAY_TAIL_S
    assert SAY_TAIL_S >= 0.9, f"{SAY_TAIL_S}秒では足りない（呼び出しは鳴り終わる0.3秒前に返る）"
    assert callable(say_and_wait)
