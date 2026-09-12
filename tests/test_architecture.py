"""docs/architecture.md の不変条件を守らせる。

★これは「設計に従っているか」の試験。機能の試験ではない。
  設計文書が先。コードがそちらに寄る。逆ではない。

★落ちたら、コードか設計文書のどちらかを直す。
  **黙って例外を足さない。** 例外を足すなら設計文書の §4 にも書く。
"""
import ast
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DJ = ROOT / "app" / "dj"
sys.path.insert(0, str(DJ))

DOC = ROOT / "docs" / "architecture.md"

# 実機の状態を書くツールと、**その持ち主**。docs/architecture.md §3 の表と一致させる。
# ★「どのファイルからでも呼べる」ではなく「持ち主は1人」を検査する。
#   ここを増やすときは設計文書も直すこと。黙って例外を足さない。
OWNERS = {
    # 表示の状態 —— 反映役だけが書く
    "set_avatar":              "reconcile.py",
    "set_blink":               "reconcile.py",
    "set_all_leds":            "reconcile.py",
    "beat_mode_update":        "reconcile.py",
    # 起動・停止の手続き —— console だけが持つ
    "beat_mode_start":         "console.py",
    "beat_mode_stop":          "console.py",
    "move_head":               "console.py",   # 片付けのみ。普段は Arbiter 経由
    "set_servo_torque":        "console.py",
    # 実機の設定・出力 —— 表示状態ではないが、持ち主は1人に保つ
    "set_auto_torque_release": "expression.py",  # 実機側の設定。起動時に一度だけ
    "set_mouth_sequence":      "expression.py",  # 口は実機のキュー再生。出力ストリーム
    "set_brightness":          "expression.py",
    "set_led":                 "reconcile.py",
    "set_leds":                "reconcile.py",
    "clear_leds":              "reconcile.py",
}


def _calls(path: Path):
    """そのファイルが呼んでいる gw.call のツール名を、行番号つきで返す。"""
    src = path.read_text(encoding="utf-8")
    out = []
    for m in re.finditer(r'\.call\(\s*"([a-z_0-9]+)"', src):
        line = src[:m.start()].count("\n") + 1
        out.append((m.group(1), line))
    return out


def _files():
    return sorted(p for p in DJ.rglob("*.py") if p.name != "doctor.py")


# ── I1 ────────────────────────────────────────────────
def test_I1_状態ごとに持ち主は1人():
    """★今日の2件の事故はどちらもここ。持ち主のいない状態を作らない。"""
    bad = []
    for p in _files():
        for tool, line in _calls(p):
            owner = OWNERS.get(tool)
            if owner and p.name != owner:
                bad.append(f"{p.relative_to(ROOT)}:{line}  {tool}"
                           f"（持ち主は {owner}）")
    assert not bad, (
        "持ち主でない場所から実機の状態を書いている（設計 §4 I1）:\n  "
        + "\n  ".join(bad)
        + "\n\n→ Presence に「あるべき姿」を置き、Reconciler に書かせること")


def test_I1_表示の状態は反映役が独占している():
    """★表情・瞬き・LED・gatewayの踊り。ここが割れると顔が戻らなくなる。"""
    for tool in ("set_avatar", "set_blink", "set_all_leds", "beat_mode_update"):
        owners = {p.name for p in _files() for t, _ in _calls(p) if t == tool}
        assert owners <= {"reconcile.py"}, f"{tool} を書いているのが {owners}"


# ── I2 ────────────────────────────────────────────────
def test_I2_首の出所は_Arbiter_だけ():
    from motion.pose import PoseState
    src = (DJ / "motion" / "pose.py").read_text(encoding="utf-8")
    assert "_sync_arbiter" in src
    frame = src[src.index("def frame"):]
    assert "_sync_arbiter" in frame, "frame() が Arbiter を通らずに角度を作っている"
    assert hasattr(PoseState, "emit")


# ── I3 ────────────────────────────────────────────────
def test_I3_gateway側の踊りは常に切れている():
    """★首を動かす人が2人いてはいけない。

    gateway の beat mode にも首とLEDを動かす機能があるが、使わない。
    実機を動かすのは console のストリームだけ。
    `beat_mode_start` はそれを有効にして始まるので、毎周期切り直す。
    （2026-09-09、診断ツールがここを有効にして止まらなくなった）
    """
    import presence
    p = presence.Presence()
    for mode in (presence.MODE_IDLE, presence.MODE_DJ):
        for dancing in (False, True):
            p.mode, p.dancing = mode, dancing
            assert p.desired()["beat_motion"] is False, \
                f"mode={mode} dancing={dancing} で gateway に踊らせている"


# ── I4 ────────────────────────────────────────────────
def test_I4_初期化の順番は1箇所():
    src = (DJ / "console.py").read_text(encoding="utf-8")
    assert src.count('gw.call("beat_mode_start"') == 1
    init = src[src.index("async def init_device"):src.index("async def device_watchdog")]
    assert init.index("load_avatar") < init.index("beat_mode_start") < init.index("set_mode")


# ── I5 ────────────────────────────────────────────────
def test_I5_オーバーレイは必ず期限を持つ():
    """★期限のない上書きは、いつか消し忘れて顔が戻らなくなる。"""
    import inspect

    import presence
    sig = inspect.signature(presence.Presence.overlay)
    assert "seconds" in sig.parameters, "overlay() は期限を必ず取る"
    p = presence.Presence(now=lambda: 0.0)
    p.overlay("cheer", "happy", seconds=1.5)
    assert p.desired()["face"] == "happy"
    p.now = lambda: 2.0                           # 期限を過ぎたら
    assert p.desired()["face"] != "happy", "期限が過ぎても残っている"


# ── I6 ────────────────────────────────────────────────
def test_I6_待機に戻ったら瞬きは_ON():
    import presence
    p = presence.Presence(now=lambda: 0.0)
    p.overlay("knob", "embarrassed", seconds=1.0)
    assert p.desired()["blink"] is False, "顔を作っている間は瞬きを止める"
    p.now = lambda: 5.0
    assert p.desired()["blink"] is True, "待機に戻ったら必ず瞬きする"


# ── I7 ────────────────────────────────────────────────
def test_I7_診断は安全な状態で終える():
    src = (DJ / "doctor.py").read_text(encoding="utf-8")
    i = src.index('gw.call("beat_mode_start"')
    j = src.index("c.repair(", i)
    assert "motion_enabled=False" in src[i:j], \
        "診断が踊りを有効にしたまま終わっている（設計 §4 I7）"


# ── 文書とコードが揃っているか ────────────────────────
def test_設計文書が存在して不変条件を全部書いている():
    doc = DOC.read_text(encoding="utf-8")
    for i in range(1, 8):
        assert f"**I{i}**" in doc, f"I{i} が設計文書に無い"


def test_状態の名前が文書とコードで一致する():
    import presence
    doc = DOC.read_text(encoding="utf-8")
    for name in (presence.MODE_IDLE, presence.MODE_DJ):
        assert f"`{name.upper()}`" in doc or f"`{name}`" in doc, \
            f"モード {name} が設計文書に無い"


def test_起動時に組み立てるループが全部存在する():
    """★消したメソッドを tasks に残すと、起動した瞬間に落ちる。

    2026-09-09、`blink_keeper` を消したのに tasks から外し忘れ、
    常駐が起動直後に死んでいた。**型検査では見つからない。**
    """
    src = (DJ / "console.py").read_text(encoding="utf-8")
    names = set(re.findall(r"tasks\.append\(con\.(\w+)\(", src))
    assert names, "tasks の組み立てが見つからない"

    defined = set()
    for path in DJ.rglob("*.py"):
        for node in ast.walk(ast.parse(path.read_text(encoding="utf-8"))):
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                defined.add(node.name)
    missing = sorted(names - defined)
    assert not missing, f"tasks に載っているが実装が無い: {missing}"
