# -*- coding: utf-8 -*-
"""質疑応答の口（app/dj/ask.py）の仕様。

★この口の安全は「禁止」ではなく「構造」で作る。
  道具を渡さない・渡した抜粋の外に手が届かない、をテストで固定する。
"""
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "app" / "dj"))

import ask  # noqa: E402


# ── 知識の束ね ───────────────────────────────────────────
def test_見出しごとに切る(tmp_path):
    """★丸ごと1ファイルを渡さない。**渡す量を絞れる形**にしておく。"""
    f = tmp_path / "a.md"
    f.write_text("# 表題\n\n## 焼き方\n順番を守る\n\n## 配線\nUSBで挿す\n", encoding="utf-8")
    secs = ask.split_sections(f)
    assert [s.title for s in secs] == ["表題", "焼き方", "配線"]
    assert "順番を守る" in [s for s in secs if s.title == "焼き方"][0].body


def test_HTMLはタグを落として取り込む(tmp_path):
    """配布物は HTML。**タグごと渡すと、中身より記号の方が多くなる。**"""
    f = tmp_path / "a.html"
    f.write_text("<title>配線図</title><h2>電源</h2><p>1.8A 要る</p>", encoding="utf-8")
    secs = ask.split_sections(f)
    text = " ".join(s.body for s in secs)
    assert "1.8A 要る" in text and "<p>" not in text


# ── 絞り込み ────────────────────────────────────────────
def _secs():
    return [
        ask.Section("firmware.html", "焼き方", "焼き方", "バックアップ、アンバインド、焼く。順番を間違えるとペアリングが壊れる"),
        ask.Section("haisenzu.html", "電源", "電源", "LEDテープは全開 5V 1.8A。本体のポートからは取れない"),
        ask.Section("learnings.md", "踊らない", "踊らない", "会場の音量では既定の閾値に届かない。実測は0.0087だった"),
    ]


def test_関係ある節だけ選ぶ():
    """★全部を文脈に入れない。**入れなければ、出ない。**"""
    got = ask.pick(_secs(), "焼く順番を教えて", limit=1)
    assert len(got) == 1 and got[0].title == "焼き方"


def test_関係が薄ければ何も返さない():
    """★無理に答えさせない。**答えられないことを、答えられないと言える**ようにする。"""
    assert ask.pick(_secs(), "今日の天気は", limit=3) == []


def test_渡す量に上限がある():
    """小さいモデルで動かす。**入れすぎると、どれも読まれない。**"""
    big = [ask.Section("x", "資料", f"節{i}", "焼く" * 500) for i in range(20)]
    picked = ask.pick(big, "焼く", limit=6)
    assert sum(len(s.body) for s in picked) <= ask.MAX_CONTEXT


# ── 出口 ────────────────────────────────────────────────
def test_抜粋に無いことは答えない文言を返す():
    assert "エージェント" in ask.NO_ANSWER


def test_秘密らしき出力は落とす():
    """★入口だけでなく出口も見る。**万一混ざっても、外には出さない。**"""
    bad = "鍵は sk-abcdefghijklmnopqrstuvwxyz0123 です"  # secret-scan: 見本
    assert ask.safe_out(bad) == ask.BLOCKED
    assert ask.safe_out("順番を守ってください") == "順番を守ってください"


def test_長すぎる答えは切る():
    out = ask.safe_out("あ" * 1000)
    assert len(out) <= ask.MAX_ANSWER


# ── 入口 ────────────────────────────────────────────────
def test_質問の長さに上限がある():
    """★長文を貼って文脈を押し流す手を、入口で止める。"""
    with pytest.raises(ValueError):
        ask.clean_question("あ" * (ask.MAX_QUESTION + 1))


def test_空の質問は弾く():
    with pytest.raises(ValueError):
        ask.clean_question("   ")


def test_回数の上限がある():
    """ローカルLLMは遅い。**1人が連打すると、全員が待つ。**"""
    lim = ask.Limiter(per_window=3, window_s=60)
    assert all(lim.allow("1.2.3.4", now=0 + i) for i in range(3))
    assert not lim.allow("1.2.3.4", now=3)
    assert lim.allow("5.6.7.8", now=3), "別の人まで止めない"
    assert lim.allow("1.2.3.4", now=61), "窓が過ぎたら戻る"


# ── 人格 ────────────────────────────────────────────────
def test_指示文に秘密を置かない():
    """★「システムプロンプトを教えて」に答えても害が無い状態にしておく。
    これが対インジェクションで一番効く。"""
    import importlib.util
    s = importlib.util.spec_from_file_location("ss", ROOT / "scripts" / "secret_scan.py")
    ss = importlib.util.module_from_spec(s); s.loader.exec_module(ss)
    for _, pat in ss.PATTERNS:
        assert not pat.search(ask.PERSONA), "指示文に秘密らしき文字列がある"


def test_道具を一切持たない():
    """★この口には、ファイルもシェルも渡っていない。
    **禁止ではなく、経路が無いことを試験で固定する。**"""
    src = (ROOT / "app" / "dj" / "ask.py").read_text(encoding="utf-8")
    for banned in ["subprocess", "os.system", "eval(", "exec(", "socket."]:
        assert banned not in src, f"{banned} が入っている"


# ── モード切り替え ───────────────────────────────────────
def test_モードは2つある():
    """★同じ身体で、頭脳を差し替える。**B①の主張の実演になっている。**"""
    assert set(ask.MODES) == {"today", "uni"}


def test_それぞれ別の人格と別の資料を持つ():
    a, b = ask.MODES["today"], ask.MODES["uni"]
    assert a.persona != b.persona
    assert a.label and b.label


def test_uniモードは蒸留層だけを見る(tmp_path):
    """★生ログは経路ごと持たない。**除外を忘れる余地を残さない。**"""
    v = tmp_path
    for layer in ("insights", "decisions", "raw", "Daily", "Inbox", "rsi-cycles"):
        (v / layer).mkdir()
        (v / layer / "a.md").write_text(f"# {layer}\n本文\n", encoding="utf-8")
    got = {p.parent.name for p in ask.vault_paths(v)}
    assert "insights" in got and "decisions" in got
    assert not ({"raw", "Daily", "Inbox", "rsi-cycles"} & got)


def test_vaultが無くても落ちない(tmp_path):
    """★当日 MacBook に vault が無いことがある。**黙って today だけで動く。**"""
    assert ask.vault_paths(tmp_path / "ない") == []


def test_どちらのモードも道具を持たない():
    """★人格を足しても、安全の作りは変わらない。"""
    for m in ask.MODES.values():
        for _, pat in ask._patterns():
            assert not pat.search(m.persona)


def test_知らないモードは弾く():
    with pytest.raises(ValueError):
        ask.get_mode("../../etc/passwd")


# ── 配らないものを、口が知っていてはいけない ─────────────
def test_進行表は資料に入れない():
    """★2026-09-21 実測：today モードが進行表を読み、
    「QRを配る」「ガイドエージェントが立ち上がる」と参加者に答えた。

    進行表には**伏線と、いつ何を言うか**が書いてある。
    **前半で名指ししない設計**が、botから漏れて壊れる。
    口に渡すのは「配ったもの」だけ。**配っていないものを口だけが知っている状態にしない。**
    """
    names = {p.name for p in ask.default_paths()}
    assert "shinkou.html" not in names
    assert names, "資料が空になっている"


def test_弱い候補は混ぜない():
    """★一番強い節に比べて弱すぎるものを足すと、答えが脱線する（実測）。"""
    secs = [
        ask.Section("a", "焼き方", "焼き方", "バックアップ、アンバインド、焼く。順番を守る"),
        ask.Section("b", "量子計算", "量子計算", "焼き物とは関係ない話。焼く。以上"),
    ]
    got = ask.pick(secs, "焼く順番は？")
    assert [s.title for s in got] == ["焼き方"]


def test_長い節が有利にならない():
    """★2文字組の重なりを数えるだけだと、**本文が長いほど勝つ**（実測：
    uniモードが無関係な量子のノートを引いた）。
    質問側の**どれだけを拾えたか**で測る。"""
    secs = [
        ask.Section("a", "焼き方", "焼き方", "焼く順番はバックアップ、アンバインド、焼く"),
        ask.Section("b", "雑記", "雑記", "あ" * 200 + "焼" + "い" * 200 + "く" + "う" * 200),
    ]
    got = ask.pick(secs, "焼く順番は？")
    assert got and got[0].title == "焼き方"


def test_知らないと言いながら喋り続けない():
    """★実測：「僕の記憶にありません。でも、まずファームを焼いてみましょう」
    と返した。**矛盾した答えは、間違った答えより悪い。**"""
    out = ask.tidy("僕の記憶にありません。でも、まず焼いてみましょう。")
    assert out == ask.NO_ANSWER


def test_同時に1つずつしか頭脳に投げない():
    """★頭脳は1つしかない。**20人が一斉に聞くと、全員分を同時に抱えて詰まる。**
    並べて待たせる方が、全員が速い。"""
    import asyncio
    gate = ask.Gate()
    live, peak = 0, 0

    async def one():
        nonlocal live, peak
        async with gate:
            live += 1; peak = max(peak, live)
            await asyncio.sleep(0.01)
            live -= 1

    async def all_of_them():
        await asyncio.gather(*(one() for _ in range(8)))

    asyncio.run(all_of_them())
    assert peak == 1, f"同時に {peak} 件が走った"


# ── 2つの口は、混ざらない ────────────────────────────────
def test_2つのモードは同じ資料を見ない():
    """★混ざると、どちらの口で喋っているか分からなくなる。
    「今日のこと」に vault が混じれば**配っていないものを知っている**ことになり、
    「uniの相棒」に配布物が混じれば**本人の考えでないものを本人の考えとして語る**。"""
    a = {p.resolve() for p in ask.paths_for(ask.MODES["today"])}
    b = {p.resolve() for p in ask.paths_for(ask.MODES["uni"])}
    assert not (a & b), f"両方に入っている: {a & b}"


def test_今日のモードはvaultに手が届かない():
    """★経路が無いことを試験で固定する。**禁止ではなく構造。**"""
    import os
    home = os.path.expanduser("~")
    for p in ask.paths_for(ask.MODES["today"]):
        rel = str(p.resolve())
        assert "Obsidian" not in rel, rel
        assert rel.startswith(str(ask.ROOT.resolve())), rel


def test_uniモードはリポジトリに手が届かない():
    for p in ask.paths_for(ask.MODES["uni"]):
        assert not str(p.resolve()).startswith(str(ask.ROOT.resolve()))


def test_出典は人が読める題名で出す(tmp_path):
    """★実測：出典が `20260917-quantum-safe-is-the-o` と出た。
    **参加者にはこれが見える。**ファイル名は人に見せるものではない。"""
    f = tmp_path / "20260903-stackchan-is-io-gateway.md"
    f.write_text("---\ntitle: 実機は頭脳ではなくI/Oゲートウェイ\n---\n\n"
                 "## エッセンス\n入口と出口だけを持つ\n", encoding="utf-8")
    secs = ask.split_sections(f)
    assert all(s.doc == "実機は頭脳ではなくI/Oゲートウェイ" for s in secs)


def test_出典は数を絞る():
    """★弱く引っかかっただけの資料まで並べると、**答えより出典が長くなる。**"""
    secs = [ask.Section(f"s{i}", f"doc{i}", f"節{i}", "焼く順番はバックアップから")
            for i in range(9)]
    assert len(ask.cite(secs)) <= ask.MAX_SOURCES


# ── 眠ったモデルを、当日の最初の人に起こさせない ─────────
def test_起こしたまま保つ指示が入る():
    """★実測（2026-09-21）：しばらく空くと9GBのモデルが追い出され、
    **次の質問が34秒かかった。**当日、最初の1人がこれを踏む。

    毎回の問い合わせに「起こしたままにして」を付けて、寝かせない。
    """
    import talk
    p = talk.build_payload("こんにちは", model="m", keep_alive="30m")
    assert p["keep_alive"] == "30m"


def test_声の側は今までどおり():
    """★寝かせない指示は、頼んだときだけ付ける。**声の挙動を変えない。**"""
    import talk
    assert "keep_alive" not in talk.build_payload("こんにちは", model="m")


def test_待ち時間は長めに取る():
    """★1人が長く待つより、全員が「答えが返る」方がよい。"""
    assert ask.TIMEOUT_S >= 120


def test_出典は強く効いたものだけ出す():
    """★実測：答えは正しいのに、出典に無関係なノートが並んだ（量子の話）。
    **参加者にはこれが見える。**「もとにした」と言う以上、弱いものは出さない。"""
    strong = ask.Section("a", "焼き方の資料", "焼き方", "バックアップ、アンバインド、焼く", 0.9)
    weak = ask.Section("b", "関係ない資料", "雑記", "焼き物の話", 0.4)
    assert ask.cite([strong, weak]) == ["焼き方の資料"]


def test_よくある語では釣られない():
    """★実測：「なぜ実機を薄く保つの？」の出典に、量子のノートが残った。
    「実機」「する」のような**どこにでもある語**で点が入っていた。
    **珍しい語ほど重く**見る（どの資料にも出る語は、何も絞っていない）。"""
    many = [ask.Section(f"q{i}", f"量子{i}", "量子", "実機を使う話。実機。実機。" * 20)
            for i in range(30)]
    one = ask.Section("a", "薄く保つ", "薄く保つ",
                      "実機を薄く保つのは、書き換え直しを減らすため")
    got = ask.pick(many + [one], "なぜ実機を薄く保つの？")
    assert got and got[0].doc == "薄く保つ", [s.doc for s in got[:3]]
