#!/usr/bin/env python3
"""会話。**スタックチャンがサブ講師になる。**

    参加者が話す ──▶ listen（文字に） ──▶ Ollama（考える） ──▶ say（喋る）

全部この部屋の中で完結する。**声はクラウドに出ない。**
当日の主張（docs/requirements.md B3）そのものなので、ここを外に出さない。

## 狙い（C19）

もくもくタイムに、音声で相談すると自律的に答える。
**短く答えて、深い話は各自のエージェントへ振る。**

- 音声は読み飛ばせない。**長い返事は地獄になる**
- スタックチャンは**受付と振り分け**。全体を見て、誰に何を渡すか決める
- 手順そのものは、参加者の Claude Code が持っている（C15 のリポジトリ）

## 実機の制約（2026-09-12 実測）

    beat mode is already using the device microphone

**踊りと会話は、同じマイクを取り合う。同時には使えない。**
時間割で分けてある（A 触る＝踊る／D もくもく＝会話）ので、
モードの切り替えでマイクを渡す。
"""
from __future__ import annotations

import contextlib
import os
import re
from pathlib import Path

# 一度に喋らせる上限。★これを超えたら振り分けに回す。
#   実測：70文字 → 音声10.4秒 → 体感18秒。**人は10秒も一人で喋らない。**
MAX_SPOKEN_CHARS = 40

# 考えている間に返す相槌。★沈黙が一番不自然。**間を埋める。**
#   人は「えーと」と言ってから考える。無音で2秒止まると壊れて見える。
FILLERS = ("うん", "なるほど", "えーと", "ふむ", "そうだね")


def pick_filler(n: int) -> str:
    """n 回目の相槌。★同じものを繰り返すと、かえって機械に見える。"""
    return FILLERS[n % len(FILLERS)]

# 振り分けの一言。★手元のエージェントを使わせる導線になる
HANDOFF = "長くなるから、続きは君のエージェントに聞いて"

# 聞き取れなかったときの一言。★無言で終わると「壊れた」と思われる
UNHEARD = "ごめん、聞き取れなかった"

# 声。★2026-09-12、実機で8種類を聞き比べて決めた（VOICEVOX 冥鳴ひまり）。
#   落ち着いた女性の声。サブ講師として、煽らずに答える役に合う
SPEAKER_ID = 14

# スピーカーの音量。★会場は騒がしい。上限まで上げる（実機は100が上限）
VOLUME = 100

# ── 話題（当日のものだけ）──────────────────────────
# ★何でも答えるロボットにしない。**受付と振り分けに徹する。**
#   全文ではなくキーワードで拾う。振り分けに一字一句の精度は要らない。
TOPICS = {
    "firm":    (("ファーム", "ふぁーむ", "ファーウ", "firmware", "焼く", "書き込"),
                "ロボットに焼くソフトだよ。これを入れ替えると頭脳を選べる"),
    "backup":  (("バックアップ", "バックア", "戻せ", "復元"),
                "焼く前に必ず取って。忘れると出荷時に戻せないよ"),
    "unbind":  (("アンバインド", "アンバイ", "バインド", "ペアリング"),
                "焼く前にアプリから解除するやつ。忘れると後が面倒"),
    "start":   (("作れ", "始め", "はじめ", "自分でも", "買え", "いくら", "キット"),
                "M5Stackの公式キットを買えば、今日の構成が作れるよ"),
    "privacy": (("プライバシ", "クラウド", "外に出", "送られ", "同意", "規約"),
                "出荷時は声も画像も海外に出る。今日は全部この部屋の中だよ"),
    "gateway": (("ゲートウェイ", "ゲートウェア", "母艦", "サーバ", "MCP", "エムシーピー"),
                "実機と頭脳の間に立つやつ。Pythonだけで動くよ"),
    "led":     (("LED", "エルイーディー", "テープ", "光", "ひかり"),
                "音を聴いて拍で光らせてる。模様は6種類あるよ"),
    "dance":   (("踊", "おど", "ダンス", "DJ", "ディージェイ", "曲", "音楽"),
                "マイクで音を聴いてテンポを測って踊ってるよ"),
    "you":     (("君は", "きみは", "あなた", "なまえ", "名前", "だれ", "誰"),
                "スタックチャン。中にAIは入ってなくて、頭脳は自宅のMacにあるよ"),
}

# 挨拶。★聞こえているのに聞き返すのは失礼（2026-09-12 の指摘）
GREETINGS = {
    ("おはよ",): "おはよう",
    ("こんにちは", "こんにちわ", "ちわ"): "こんにちは",
    ("こんばんは", "こんばんわ"): "こんばんは",
    ("はじめまして", "初めまして"): "はじめまして。スタックチャンだよ",
    ("ありがと", "サンキュ", "感謝"): "どういたしまして",
    ("またね", "ばいばい", "さよなら", "じゃあね"): "またね",
    ("すごい", "かわいい", "可愛い", "かっこい"): "ありがとう。うれしい",
    ("元気", "げんき"): "元気だよ。そっちは?",
}

# 話題の外だけど聞こえたとき。★無言が一番壊れて見える
SMALL_TALK = "うん。それ、君のエージェントに話すともっと面白いかも"

# 聞き取れなかった・分からないときの返し。
# ★どちらも**故障ではなく性格**に見えること。短いこと（音声は読み飛ばせない）
ASK_AGAIN = "ん? もういっかい"
TO_AGENT = "それは君のエージェントが詳しいよ"

# どこから「分かった」とみなすか
CONFIDENT_MIN = 0.5

# 喋り終わってから録り始めるまでの間。
# ★2026-09-12、**自分の声を文字起こししていた**（録音の最初0.5秒が実機の「どうぞ」）。
#   スピーカーとマイクが同じ筐体にあるので、出力が入力に回り込む。
#   DJのときの「自分のサーボ音で踊り続けた」と同じ形。**この機体の構造的な癖。**
#   実測（2026-09-12）：say の呼び出しは、音が鳴り終わる **0.2〜0.3秒前に返る**。
#   さらにスピーカーの余韻が乗るので、1.0秒待つ。
#   ★ここをケチると、自分の声を質問だと思って文字起こしする。
SAY_TAIL_S = 1.0

# 頭脳への指示。★**知識を渡さないと的外れになる**（実測）。
#   「ファームってなんですか」→ 知識なし「農業を主な仕事として行う施設」
#                            → 知識あり「ロボットの頭脳を変えられるソフト」
#   知識は knowledge.md に置く。ここに書かない（二重管理を避ける）
_KNOWLEDGE = Path(__file__).resolve().parent / "knowledge.md"


def system_prompt() -> str:
    """頭脳への指示。knowledge.md をそのまま渡す。"""
    try:
        return _KNOWLEDGE.read_text(encoding="utf-8")
    except OSError:
        return ("あなたはスタックチャンという小さなロボットで、勉強会のサブ講師です。"
                "日本語で2文以内・60文字以内。前置き禁止。")


def needs_mic_handover(beat_active: bool) -> bool:
    """会話の前に、踊りからマイクを取り上げる必要があるか。"""
    return bool(beat_active)


# 意味のない前置き。★音声だと時間の無駄でしかない。
#   指示で禁止しても書いてくるので、**こちら側で落とす**（2026-09-12 実測）。
_PREAMBLE = re.compile(
    r"^(?:"
    # ★「了解」だけ消して「しました」が残った。**語尾まで含めて落とす**
    r"(?:はい|ええ)[、。！,.\s]+"
    r"|(?:了解|承知|理解)(?:いた)?しました[、。！,.\s]*"
    r"|(?:かしこまりました|わかりました|分かりました)[、。！,.\s]*"
    r"|(?:ご質問|お問い合わせ)ありがとうございます[、。！,.\s]*"
    r"|[^。！？]{0,40}?(?:に基づ|を踏まえ|について)[^。！？]{0,40}?"
    r"(?:お答えします|説明します|回答します)[。！,.\s]*"
    r"|[^。！？]{0,20}?お答えします[。！,.\s]*"
    r")+",
)


def _drop_preamble(t: str) -> str:
    """前置きを落とす。**落として何も残らないなら、答えていない。**"""
    prev = None
    while prev != t:
        prev = t
        t = _PREAMBLE.sub("", t, count=1).lstrip()
    return t


def _speakable(text: str) -> str:
    """読み上げられる形にする。

    ★Markdown の記号がそのまま音声に乗った（実測：「シャープ スタックチャンとは」）。
      頭脳は Markdown を書きたがるので、こちら側で落とす。
    """
    t = (text or "").strip()
    if not t:
        return ""
    lines = []
    for ln in t.splitlines():
        ln = re.sub(r"^\s*[#>\-\*\d\.]+\s*", "", ln)      # 見出し・引用・箇条書き
        ln = re.sub(r"[*_`|\[\]]", "", ln)                   # 強調・表・リンク
        if ln.strip():
            lines.append(ln.strip())
    return _drop_preamble(" ".join(lines).strip())


def pick_reply(text: str) -> str:
    """喋らせる文を決める。**短く切って、続きは振る。**

    ★空なら喋らせない。失敗したときに黙るのが正しい
      （意味のない音を出すと、その場が止まる）。
    """
    t = _speakable(text)
    if not t:
        return ""
    if len(t) <= MAX_SPOKEN_CHARS:
        return t
    # ★文の切れ目でしか切らない。
    #   2026-09-12 の事故：40字で機械的に切って「…構成や特徴長くなるから、続きは」
    #   と途中に振り分け文をくっつけた。**意味が壊れる。**
    #   切れ目が無いなら、無理に読ませず振り分け文だけを返す。
    budget = MAX_SPOKEN_CHARS
    head = ""
    for mark in ("。", "！", "？"):
        i = t.rfind(mark, 0, budget)
        if i > len(head):
            head = t[:i + 1]
    return f"{head}{HANDOFF}。" if head else f"{HANDOFF}。"


class Turn:
    """1回のやりとり。**会話の状態を Presence に預ける。**

    ★LED と表情はここでは触らない。状態を宣言するだけ（設計 §4 I1）。
      聞いている＝緑／喋っている＝青 は、配布物に書いてある約束。
    """

    def __init__(self, presence):
        self.presence = presence

    def start_listening(self) -> None:
        self.presence.talk = "listening"

    def start_speaking(self) -> None:
        self.presence.talk = "speaking"

    def done(self) -> None:
        """★消し忘れると、LED が緑のまま固まる。"""
        self.presence.talk = None

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        self.done()
        return False


# 頭脳。★2026-09-12、当日の質問3問で5モデルを実測して決めた。
#   gemma3:4b     1.0秒  「実機に焼くソフトです。入れ替えれば頭脳を選べます」 ← 採用
#   qwen2.5:3b    0.8秒  正確だが長い。2文に収まらない
#   llama3.2:3b   1.7秒  遅く、内容も崩れる
#   qwen2.5:14b   1.5秒  簡潔だが振り分けの一言を地の文で書いてしまう
#   qwen3:4b     35.9秒  ★思考過程を英語で延々と出す。会話には使えない
#   **大きさより指示追従。**「2文以内」を守れるかで決まった
MODEL = "gemma3:4b"


# ★PATH を当てにしない。launchd の PATH には homebrew が入っていない
#   （2026-09-12、パネルからの質問が FileNotFoundError で落ちた）
OLLAMA_CANDIDATES = ("/opt/homebrew/bin/ollama", "/usr/local/bin/ollama",
                     "/usr/bin/ollama")


def find_ollama() -> str | None:
    """ollama の実体を探す。**絶対パスで返す。**"""
    import os
    import shutil
    env = os.environ.get("OLLAMA_BIN")
    if env and os.path.exists(env):
        return env
    for c in OLLAMA_CANDIDATES:
        if os.path.exists(c):
            return c
    return shutil.which("ollama")


# ★頭脳の在処。**設定に出す。** コードを機械ごとに分けない
#   （insights/20260908-one-codebase-config-only）
#
#   Mac Studio : 自分自身（既定）
#   MacBook    : 自宅の Mac Studio を指す。**当日「いま自宅まで往復しています」の実体**
#
#   OLLAMA_URL で上書きできる。console からは --think-url で渡る
DEFAULT_THINK_URL = "http://127.0.0.1:11434"


def think_url() -> str:
    return os.environ.get("OLLAMA_URL", DEFAULT_THINK_URL).rstrip("/")


def build_payload(question: str, model: str, keep_alive: str | None = None) -> dict:
    """頭脳に投げる中身を組む。**組み立てだけを、試験できる形で切り出す。**

    ★`keep_alive` は「答えたあとも、モデルを起こしたままにして」という指示。
      実測（2026-09-21）：しばらく空くと9GBのモデルが追い出され、
      **次の質問が34秒かかった。**当日、最初の1人がこれを踏む。
      ただし**頼まれたときだけ付ける**。声の側の挙動を変えない。
    """
    payload = {
        "model": model,
        "prompt": f"{system_prompt()}\n\n質問: {question}",
        "stream": False,
    }
    if keep_alive:
        payload["keep_alive"] = keep_alive
    return payload


async def think(question: str, model: str = MODEL, timeout_s: float = 60.0,
                ollama: str | None = None, url: str | None = None,
                keep_alive: str | None = None) -> str:
    """Ollama に訊く。**HTTP で叩く。**

    ★以前は `ollama run` を起動していた。同じ機械にしか頭脳を置けない作りで、
      当日 MacBook で console を動かすと**会場側の Ollama を探しに行く**。
      「頭脳は自宅」という主張と食い違うので、HTTP に変えた（2026-09-14）。

    `ollama` 引数は**後方互換のため残している**。渡されたら、その実体が
    無い場合に限り「見つからない」として空を返す（既存の試験がこれを見ている）。
    """
    # ★聞き取れなかったのに投げると、知識をそのまま読み上げる（実測）
    if not (question or "").strip():
        return ""
    if ollama is not None and not os.path.exists(ollama):
        print(f"★ ollama が見つかりません: {ollama}")
        return ""

    base = (url or think_url()).rstrip("/")
    payload = build_payload(question, model, keep_alive)
    try:
        import aiohttp
        timeout = aiohttp.ClientTimeout(total=timeout_s)
        async with aiohttp.ClientSession(timeout=timeout) as s:
            async with s.post(f"{base}/api/generate", json=payload) as r:
                if r.status != 200:
                    print(f"★ 頭脳が {r.status} を返しました（{base}）")
                    return ""
                data = await r.json()
    except Exception as exc:                       # noqa: BLE001
        # ★沈黙もクラッシュも同じくらい困る。**理由が分かる形で返す**
        print(f"★ 頭脳に繋がりません（{base}）: {exc}")
        return ""
    text = data.get("response") or ""
    # ★端末の制御文字が混ざることがある。潰さないと読み上げに乗る
    text = re.sub(r"\x1b\[[0-9;]*[A-Za-z]|[\x00-\x08\x0b-\x1f]", "", text)
    return text.strip()


async def say_and_wait(gw, text: str) -> None:
    """喋って、**鳴り終わるまで待つ。**

    ★`say` は音が鳴り終わる0.2〜0.3秒前に返る（実測）。
      そのまま録音に入ると、自分の声を質問だと思って文字起こしする。
    """
    await gw.call("say", text=text, speaker_id=SPEAKER_ID)
    await _sleep(SAY_TAIL_S)


async def _acknowledge(gw, con) -> None:
    """撫でられた瞬間の手応え。**遅れて返るのは、返っていないのと同じ。**

    ★2026-09-12、ログ上は成功していたのに「無反応」と言われた。
      緑になるまで約1秒、その間は無音・無動作だった。

    ★音だけだと騒がしい会場で埋もれる。**体で返す。**
      うなずき（首）＋顔。0.3秒で終わる短い反応にする。
    """
    con.presence.overlay("touch", "happy", seconds=1.2)
    with contextlib.suppress(Exception):
        con.pose.hold = (0.0, 14.0)      # ★45からの差。うなずき
        await _sleep(0.16)
        con.pose.hold = (0.0, -2.0)
        await _sleep(0.14)
        con.pose.hold = None


async def converse(gw, con, duration_ms: int = 8000, model: str = "small",
                   turn_no: int = 0) -> dict:
    """1回のやりとり。設計は docs/ux-conversation.md。

        ① 首をかしげて LED を緑に      … 合図は**実機から**出す（端末は誰も見ない）
        ② 聞く                        … 話し終わりで自動的に切れる
        ③ **復唱**                    … 誤認識を隠さない。違えば人が言い直せる
        ④ 振り分け                    … 話題が分からなければ**聞き返す**
        ⑤ 短く答える                  … 深い話はエージェントへ振る

    ★「性能が変だ」と思われるのは、**間違った答えを自信ありげに返す**とき。
      分からないときに聞き返すのは、故障ではなく性格に見える。
    """
    import json as _json

    def _j(r):
        c = getattr(r, "content", None)
        return _json.loads(c[0].text) if c else {}

    turn = Turn(con.presence)
    out = {"heard": "", "said": "", "topic": None}
    try:
        if needs_mic_handover(getattr(con.args, "beat", True)):
            await con.hand_mic_to_talk()

        # ⓪ 撫でられた手応えを、すぐ返す
        await _acknowledge(gw, con)

        # ① 合図は実機から。緑になって、首をかしげる
        turn.start_listening()
        await _sleep(SAY_TAIL_S)        # ★自分の声が消えるのを待つ

        # ② 聞く
        heard = _j(await gw.call("listen", duration_ms=duration_ms,
                                 language="ja", model=model,
                                 motion="face-only"))
        q = (heard.get("text") or "").strip()
        out["heard"] = q

        turn.start_speaking()

        # ③④ 振り分け。**頭脳へ投げる前に決める**
        r = route(q)
        out["topic"] = r.topic
        if r.topic is None:
            out["said"] = r.reply           # 「ん? もういっかい」
            await gw.call("say", text=r.reply, speaker_id=SPEAKER_ID)
            return out

        # ③ 復唱してから答える。誤認識がここで分かる
        await gw.call("say", text=echo_back(q), speaker_id=SPEAKER_ID)

        # ⑤ 短く答える。用意した一言で足りるので、頭脳は**補足のときだけ**
        answer = r.reply
        if len(q) > 12:                      # 具体的に訊かれていれば補う
            extra = pick_reply(await think(f"{echo_back(q)} 質問: {q}"))
            if extra and len(extra) <= MAX_SPOKEN_CHARS:
                answer = extra
        out["said"] = answer
        await gw.call("say", text=answer, speaker_id=SPEAKER_ID)
        return out
    finally:
        turn.done()
        with contextlib.suppress(Exception):
            await con.hand_mic_back()


async def on_request(gw, con, turn_no: int = 0) -> dict:
    """撫でる以外から会話を始める（スマホの操作パネル・進行役のパッド）。

    ★入力を1つに依存しない。**タッチセンサが動かないことがある**
      （2026-09-12、I2Cに現れなかった）。
      どの手段でも「人が起動を決める」というジャーニーは変わらない。
    """
    return await converse(gw, con, turn_no=turn_no)


async def on_touch(gw, con, event: str, turn_no: int = 0) -> dict | None:
    """頭を撫でられたら会話を始める。**起動は人が決める。**

    ★合図を待たせない。「いつ話せばいいか」が構造的に消える。
      騒がしくてもウェイクワードに頼らない（台本の「タップ起動を基本にする」）。
      そして**触れること自体が体験になる**（「最重要：触らせること」）。
    """
    if event not in ("stroke", "tap"):
        return None
    return await converse(gw, con, turn_no=turn_no)


async def _sleep(s: float):
    import asyncio as _a
    await _a.sleep(s)


# ── 振り分け（UX設計 docs/ux-conversation.md）──────────────
class Routed:
    """聞き取りの結果を、話題と返事に変えたもの。"""

    __slots__ = ("topic", "reply", "score")

    def __init__(self, topic, reply, score=0.0):
        self.topic, self.reply, self.score = topic, reply, score


def _find_topic(heard: str):
    """キーワードで話題を拾う。★全文の一致は求めない。"""
    t = (heard or "").strip()
    if not t:
        return None, 0.0
    best, best_score = None, 0.0
    low = t.lower()
    for name, (keys, _) in TOPICS.items():
        for k in keys:
            if k.lower() in low:
                # 長いキーワードほど確からしい
                sc = min(1.0, 0.5 + len(k) / 12.0)
                if sc > best_score:
                    best, best_score = name, sc
    return best, best_score


def echo_back(heard: str) -> str:
    """聞き取れた話題を復唱する。**誤認識を隠さない。**

    ★隠すから壊れて見える。復唱すれば、違ったときに人が言い直せる。
      そして復唱は人間がやること。キャラクターとして自然。
    """
    topic, _ = _find_topic(heard)
    if not topic:
        return ""
    word = TOPICS[topic][0][0]
    return f"{word}の話だね"


def _greeting(heard: str) -> str | None:
    """挨拶なら、挨拶を返す。"""
    low = (heard or "").lower()
    for keys, reply in GREETINGS.items():
        if any(k in low for k in keys):
            return reply
    return None


def route(heard: str | None) -> Routed:
    """聞き取りから、話題と返事を決める。

    ★「性能が変だ」と思われるのは、**間違った答えを自信ありげに返す**とき。
      分からないなら聞き返す。知らないならエージェントに振る。
      **どちらも故障ではなく性格に見える。**
    """
    t = (heard or "").strip()
    # ★本当に聞こえないときだけ聞き返す
    if not t:
        return Routed(None, ASK_AGAIN, 0.0)

    topic, score = _find_topic(t)
    if topic is not None and score >= CONFIDENT_MIN:
        return Routed(topic, TOPICS[topic][1], score)

    # ★聞こえているのに「もういっかい」は失礼。挨拶には挨拶を返す
    g = _greeting(t)
    if g:
        return Routed("greeting", g, 1.0)

    # 話題の外でも、聞こえたなら応じる。**無言が一番壊れて見える**
    return Routed("chat", SMALL_TALK, 0.0)


class TalkDesk:
    """会話の受付。**撫でられたら必ず何か返す。**

    ★2026-09-12、90秒で4回撫でて2回しか反応しなかった。
      会話は10〜20秒かかる。その間の撫でを**黙って捨てていた。**
      黙って捨てると「反応が悪い」に見える。**沈黙は故障と同じ。**

        暇なとき  → 会話を始める
        会話中    → **すぐ小さくうなずく**（順番待ちが伝わる）
    """

    def __init__(self, gw, con):
        self.gw, self.con = gw, con
        self.busy = False
        self.turns = 0          # 成立したやりとり
        self.deferred = 0       # 会話中に撫でられた回数（＝待たせた回数）

    async def on_touch(self, subtype: str) -> dict | None:
        if subtype not in ("stroke", "tap"):
            return None
        if self.busy:
            # ★いま手が離せないことを、体で返す。無視しない
            self.deferred += 1
            await self._wait_a_moment()
            return None
        self.busy = True
        try:
            self.turns += 1
            return await converse(self.gw, self.con, turn_no=self.turns)
        finally:
            self.busy = False

    async def _wait_a_moment(self) -> None:
        """順番待ちの合図。**短く。会話を邪魔しない。**"""
        with contextlib.suppress(Exception):
            self.con.pose.hold = (0.0, 9.0)
            await _sleep(0.12)
            self.con.pose.hold = None
