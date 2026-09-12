"""パネルから会話させる仕様。

## 誰が、どこで

**外出先の本人。声は聞こえない。** 当日は「もくもくタイム中の質問受け」になる。

- **聞こえないので、答えは文字でも返す。** 喋らせて終わりは、外では無反応と同じ
- 喋るのは短く、**画面には全文**。声と文字で役割が違う
- Ollama は数秒かかる。**待たせるなら、待っていると分かるように**
"""
import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "app" / "dj"))
from panel import AskDesk   # noqa: E402


class FakeGw:
    def __init__(self): self.said = []
    async def call(self, tool, **kw):
        if tool == "say":
            self.said.append(kw["text"])
        class R: content = [type("T", (), {"text": '{"ok":true}'})()]
        return R()


class FakePresence:
    def __init__(self): self.talk = None


class FakeCon:
    def __init__(self): self.gw, self.presence = FakeGw(), FakePresence()


def desk(answer="スタックチャンは手のひらサイズのロボットです。" * 4, **kw):
    async def think(q, **_): return answer
    return AskDesk(think=think, **kw)


def run(c): return asyncio.run(asyncio.wait_for(c, timeout=10))


def test_答えは声と文字の両方で返る():
    """★外にいる人には聞こえない。**喋らせて終わりは無反応と同じ。**"""
    con, d = FakeCon(), desk()
    r = run(d.ask(con, "スタックチャンって何？"))
    assert con.gw.said, "喋っていない"
    assert len(r["full"]) > len(r["spoken"]), "画面に全文が返っていない"


def test_喋るのは切り詰める():
    """★上限は会場より緩い（パネルは読めるので）。それでも青天井にしない。"""
    con, d = FakeCon(), desk()
    r = run(d.ask(con, "スタックチャンって何？"))
    assert len(r["spoken"]) <= 90, r["spoken"]


def test_空の質問は投げない():
    """★聞き取れていないのに投げると、知識をそのまま読み上げる。"""
    con, d = FakeCon(), desk()
    r = run(d.ask(con, "   "))
    assert r["full"] == "" and not con.gw.said


def test_考えている間は状態が見える():
    """★数秒かかる。**待っていると分かるようにする。**"""
    con = FakeCon()
    seen = []

    async def slow(q, **_):
        seen.append(con.presence.talk)
        return "はい"
    r = run(AskDesk(think=slow).ask(con, "やあ"))
    assert seen == ["speaking"] or seen == ["listening"], seen
    assert con.presence.talk is None, "終わったのに状態が残っている"


def test_答えが空でも黙って終わらない():
    """★無言が一番壊れて見える。"""
    con, d = FakeCon(), desk(answer="")
    r = run(d.ask(con, "むずかしい質問"))
    assert con.gw.said, "何も返していない"
    assert r["full"]


def test_やりとりが残る():
    """★画面に履歴を出す。**押した結果が流れて消えない。**"""
    con, d = FakeCon(), desk()
    run(d.ask(con, "ひとつめ"))
    run(d.ask(con, "ふたつめ"))
    h = d.history()
    assert [x["q"] for x in h] == ["ひとつめ", "ふたつめ"]


def test_履歴は溜め込まない():
    con, d = FakeCon(), desk(keep=3)
    for i in range(6):
        run(d.ask(con, f"q{i}"))
    assert len(d.history()) == 3


def test_同時に二つ投げても壊れない():
    """★連打される。**実機は1台。**"""
    con, d = FakeCon(), desk()
    async def go():
        return await asyncio.gather(d.ask(con, "A"), d.ask(con, "B"))
    rs = run(go())
    assert all(r for r in rs)
    assert con.presence.talk is None


# ── 声に何を乗せるか（2026-09-12 実地）────────────────
#
# 実際に訊いたら、声が **「長くなるから、続きは君のエージェントに聞いて」だけ**
# になった。1文目が40字をわずかに超えて、切り出しに失敗したため。
#
# ★会場の40字制限は「人が待っている」から。**パネルは読める。**
#   同じ制約を持ち込むと、**答えたのに答えていないように聞こえる。**

def test_一文なら丸ごと喋る():
    con = FakeCon()
    a = "スタックチャンは、M5Stackという手のひらサイズのオープンソースロボットです。"
    r = run(desk(answer=a).ask(con, "なに？"))
    assert r["spoken"] == a, f"1文なのに切っている: {r['spoken']}"


def test_長すぎるときは意味のある所で切る():
    con = FakeCon()
    a = "一文目です。" + "とても長い説明が続きます。" * 12
    r = run(desk(answer=a).ask(con, "なに？"))
    assert r["spoken"].startswith("一文目です。")
    assert len(r["spoken"]) <= 90


def test_振り分け文だけにしない():
    """★答えたのに答えていないように聞こえる。"""
    con = FakeCon()
    a = "スタックチャンは、M5Stackという手のひらサイズのオープンソースロボットです。"
    r = run(desk(answer=a).ask(con, "なに？"))
    assert "続きは" not in r["spoken"], r["spoken"]
