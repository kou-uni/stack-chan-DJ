"""外から操作するパネルの仕様。ROADMAP Phase 2。

## 誰が、どこで使うか（CLAUDE.md §1.5）

**本人・外出先・スマホ・片手。** 電車の中かもしれない。画面は小さい。

- 押すのは**大きなボタン数個**。文字入力は最後の手段
- **動いた証拠が要る**。家のロボットは見えないので、ロボット自身のカメラで返す
- **公開されている前提で作る**。cloudflared のURLは短いが、公開は公開

## 書き手を増やさない

パネルは実機に直接書かない。**console の presence / pose を動かすだけ。**
console が唯一の書き手（architecture.md I2）という前提を、パネルで壊さない。
"""
import sys
import asyncio
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "app" / "dj"))
from panel import apply_action, check_token, make_token, panel_state  # noqa: E402
from presence import Presence, MODE_DJ, MODE_IDLE                     # noqa: E402


class FakePose:
    def __init__(self): self.hold = None


class FakeLed:
    def __init__(self):
        self.pattern, self.enabled, self.bpm, self.manual = "show", False, 0.0, False

    def show_pattern(self, name):
        self.pattern, self.manual = name, True


class FakeGw:
    def __init__(self): self.calls = []

    async def call(self, tool, **kw):
        self.calls.append((tool, kw))
        class R:
            content = [type("T", (), {"text": '{"ok": true, "image_path": "/tmp/a.jpg"}'})()]
        return R()


class FakeCon:
    def __init__(self):
        self.presence, self.pose, self.led, self.gw = Presence(), FakePose(), FakeLed(), FakeGw()


def run(coro): return asyncio.run(coro)


# ── 鍵 ────────────────────────────────────────────
def test_wrong_or_missing_token_is_refused():
    """★公開URLに置く。鍵が無ければ何もさせない。"""
    real = make_token()
    assert check_token(real, real)
    assert not check_token("", real)
    assert not check_token(None, real)
    assert not check_token(real[:-1] + "0" * 1, real) or real.endswith("0")


def test_token_is_not_guessable():
    a, b = make_token(), make_token()
    assert a != b and len(a) >= 32


# ── 操作 ──────────────────────────────────────────
def test_head_buttons_move_the_pose_not_the_device():
    """★実機に直接書かない。console の pose を動かすだけ。"""
    con = FakeCon()
    run(apply_action(con, "head", "left"))
    assert con.pose.hold is not None and con.pose.hold[0] < 0
    run(apply_action(con, "head", "right"))
    assert con.pose.hold[0] > 0
    run(apply_action(con, "head", "center"))
    assert con.pose.hold == (0, 0)      # ★戻す指示。仕様変更 2026-09-12
    assert con.gw.calls == [], "パネルが実機を直接叩いている"


def test_head_stays_inside_the_safe_range():
    """★可動域を超えるとサーボが潰れる。首は yaw±90 / pitch±40。"""
    con = FakeCon()
    for v in ("left", "right", "up", "down"):
        run(apply_action(con, "head", v))
        yaw, pitch = con.pose.hold
        assert -90 <= yaw <= 90, (v, yaw)
        assert -40 <= pitch <= 40, (v, pitch)


def test_face_is_a_temporary_overlay():
    """★期限のない上書きは作らない（presence の約束）。"""
    con = FakeCon()
    run(apply_action(con, "face", "happy"))
    assert con.presence.desired()["face"] == "happy"


def test_mode_can_be_switched():
    con = FakeCon()
    run(apply_action(con, "mode", "dj"))
    assert con.presence.mode == MODE_DJ
    run(apply_action(con, "mode", "off"))
    assert con.presence.mode == MODE_IDLE


def test_led_pattern_switches():
    con = FakeCon()
    run(apply_action(con, "led", "laser"))
    assert con.led.pattern == "laser"


def test_unknown_action_is_refused():
    """★知らない指示は黙って無視しない。**沈黙は故障と見分けがつかない。**"""
    con = FakeCon()
    with pytest.raises(ValueError):
        run(apply_action(con, "selfdestruct", "1"))
    with pytest.raises(ValueError):
        run(apply_action(con, "led", "そんな模様はない"))
    with pytest.raises(ValueError):
        run(apply_action(con, "head", "ななめ"))


def test_say_goes_to_the_device_and_is_length_capped():
    """★長文を流し込まれない。読み上げが終わらなくなる。"""
    con = FakeCon()
    run(apply_action(con, "say", "あ" * 500))
    tool, kw = con.gw.calls[0]
    assert tool == "say" and len(kw["text"]) <= 60


def test_photo_returns_where_the_picture_is():
    """★動いた証拠。家のロボットは見えない。"""
    con = FakeCon()
    r = run(apply_action(con, "photo", ""))
    assert con.gw.calls[0][0] == "take_photo"
    assert r.get("image_path")


# ── 見せる状態 ────────────────────────────────────
def test_state_says_what_the_person_needs_to_know():
    con = FakeCon()
    s = panel_state(con)
    for k in ("mode", "dancing", "talk", "pattern", "face"):
        assert k in s, k


# ── 外にいる人は、ロボットが見えない（2026-09-12 実地で判明）─────
#
# 本人の言葉：**「ボタンを押してるけど反応ないね」**
# 実機は動いていた。届いてもいた。**画面が何も返していなかった。**
#
# ★見えない相手を操作させるなら、**見せることが機能**。

def test_center_actually_centers():
    """★「まんなか」は中央に戻す指示。固定を外すだけでは動かない。

    実測: center を押しても実機は (53, 44) のまま動かなかった。
    """
    con = FakeCon()
    run(apply_action(con, "head", "right"))
    run(apply_action(con, "head", "center"))
    assert con.pose.hold == (0, 0), "中央に戻す指示が出ていない"


def test_dj_mode_hands_the_head_back():
    """★DJにしたら首を返す。固定したままだと踊れない。"""
    con = FakeCon()
    run(apply_action(con, "head", "left"))
    run(apply_action(con, "mode", "dj"))
    assert con.pose.hold is None, "DJにしても首を握ったまま"


def test_every_action_reports_the_new_state():
    """★押した瞬間に画面を更新できるよう、結果に状態を載せる。

    往復を2回すると遅い。**1回で返す。**
    """
    con = FakeCon()
    for a, v in (("head", "left"), ("face", "happy"), ("mode", "dj"),
                 ("led", "laser")):
        r = run(apply_action(con, a, v))
        assert "state" in r, f"{a} が状態を返していない"
        assert r["state"]["mode"] in ("off", "dj")


# ── 首の上下の向き（2026-09-12、本人の指摘と写真で確定）──────
#
# 本人：**「上にしたら下向くんだけど？」**
#
# 実機で撮って確かめた（yaw を窓の方へ向けて縦の手がかりを入れた）:
#
#     pitch 10 → 観葉植物・窓・床のあたり   ＝ **下**
#     pitch 80 → 天井の見切り               ＝ **上**
#
# **pitch が大きいほど上。** コード内のコメント（「45 を送ると真下になる」）を
# 測らずに信じて、逆に割り当てていた。
#
# ★書かれていることではなく、**撮って確かめたこと**を仕様にする。

def test_up_looks_up_and_down_looks_down():
    """★▲を押したら上を向く。実測: pitch が大きいほど上。"""
    from panel import HEAD
    assert HEAD["up"][1] > 0, "▲が上を向いていない（pitch は大きいほど上）"
    assert HEAD["down"][1] < 0, "▼が下を向いていない"


def test_up_and_down_are_symmetric():
    """★上下で効きが違うと、操作していて気持ち悪い。"""
    from panel import HEAD
    assert HEAD["up"][1] == -HEAD["down"][1]


def test_left_and_right_are_symmetric():
    from panel import HEAD
    assert HEAD["left"][0] == -HEAD["right"][0]


# ── 軸を混ぜない（2026-09-12 本人の指摘）──────────────
#
# > **「左を向いた時、斜め上を見直します。そのまま単純に左を向けばいいのでは」**
#
# ◀ を押すと高さも中央に戻っていた。下を向いてから左を押すと、
# **首を上げながら横を向く。** 押したのは「左」だけなのに。
#
# ★1つのボタンは1つの軸だけ動かす。**触っていない軸は保つ。**

def test_左右は高さを変えない():
    con = FakeCon()
    run(apply_action(con, "head", "down"))
    down_pitch = con.pose.hold[1]
    run(apply_action(con, "head", "left"))
    assert con.pose.hold[1] == down_pitch, "左を向いたら高さが変わった"
    assert con.pose.hold[0] < 0


def test_上下は向きを変えない():
    con = FakeCon()
    run(apply_action(con, "head", "right"))
    right_yaw = con.pose.hold[0]
    run(apply_action(con, "head", "up"))
    assert con.pose.hold[0] == right_yaw, "上を向いたら左右が変わった"
    assert con.pose.hold[1] > 0


def test_まんなかは両方戻す():
    con = FakeCon()
    run(apply_action(con, "head", "left"))
    run(apply_action(con, "head", "down"))
    run(apply_action(con, "head", "center"))
    assert con.pose.hold == (0, 0)


def test_固定していない状態から押しても壊れない():
    con = FakeCon()
    con.pose.hold = None
    run(apply_action(con, "head", "left"))
    assert con.pose.hold == (-55, 0)
