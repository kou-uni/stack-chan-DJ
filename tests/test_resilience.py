"""順序に依存しないこと。★どの順で電源を入れても動く、を守る。"""
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "app" / "dj"))


def _src(name):
    return (ROOT / "app" / "dj" / name).read_text(encoding="utf-8")


def test_実機の復帰を見張る仕組みがある():
    """実機の電源を入れ直したら、console を立ち上げ直さずに戻ること。"""
    s = _src("console.py")
    assert "async def device_watchdog" in s
    assert "device_watchdog(gw, con, args)" in s, "見張りがタスクに入っていない"


def test_生存確認は_gateway_側で完結する():
    """★実機に問い合わせるツールを短い間隔で叩くと、音声の取り込みを邪魔する。"""
    s = _src("console.py")
    wd = s[s.index("async def device_watchdog"):s.index("async def _cleanup")]
    assert 'gw.call("get_status")' in wd
    for heavy in ("get_head_angles", "get_touch_state", "get_device_info"):
        assert heavy not in wd, f"{heavy} は実機に問い合わせる。見張りに使わない"


def test_初期化の順番が1箇所にある():
    """★beat_mode_start → set_mode の順。2箇所に書くと、いつか片方だけ直す。"""
    s = _src("console.py")
    init = s[s.index("async def init_device"):s.index("async def device_watchdog")]
    assert init.index("load_avatar") < init.index("beat_mode_start"), "表情はいちばん先"
    assert init.index("beat_mode_start") < init.index("set_mode"), \
        "beat_mode_start を set_mode より後にすると、待機モードなのに踊り出す"
    assert s.count('gw.call("beat_mode_start"') == 1, \
        "初期化の順番が2箇所にあると、いつか片方だけ直して食い違う"


def test_復帰でも同じ初期化を通る():
    s = _src("console.py")
    wd = s[s.index("async def device_watchdog"):s.index("async def _cleanup")]
    assert "init_device(" in wd, "復帰が起動と違う手順を踏んではいけない"


def test_MIDI_は挿し直しに追従する():
    """DJ機材を後から挿しても効くこと。抜き差しは現場で普通に起きる。"""
    s = _src("midi_in.py")
    loop = s[s.index("async def midi_loop"):]
    assert "while True" in loop
    assert "_find_midi" in loop, "一度きりの検索だと、後から挿しても拾えない"
    assert "get_input_names" in loop, "抜かれたことに気づけない"


def test_常駐は実機をずっと待つ():
    """★常駐なら 0（無限）。20秒で諦めると、実機より先に上がったとき死ぬ。"""
    svc = (ROOT / "scripts" / "service.sh").read_text(encoding="utf-8")
    assert re.search(r'"--wait-device"\s+"0"', svc), "常駐は --wait-device 0 で登録すること"


def test_立ち下げは片付けてから終わる():
    s = _src("console.py")
    assert "_install_signals" in s, "SIGTERM を受けないと pkill で片付けが飛ぶ"
    assert "signal.SIGTERM" in s and "signal.SIGINT" in s
    cl = s[s.index("async def _cleanup"):s.index("def _install_signals")]
    assert cl.index("beat_mode_stop") < cl.index("follow_pose_stream"), "先に音を聴くのをやめる"
    assert cl.index("follow_pose_stream") < cl.index("move_head"), "購読を切ってから首を戻す"
    assert "wait_for" in cl, "片付けに制限時間が無いと、応答しない相手で止まらなくなる"


def test_瞬きは定期的に入れ直される():
    """★瞬きの持ち主が2人いた（console と gateway の beat mode）。

    いまは反映役が一定間隔で**全部送り直す**ので、誰が乱しても戻る。
    専用の見張り（blink_keeper）は要らなくなった。
    """
    import asyncio

    import presence as P
    from reconcile import Reconciler

    class Fake:
        def __init__(self): self.calls = []
        async def call(self, name, **a): self.calls.append(name)

    gw = Fake()
    r = Reconciler(gw, P.Presence(now=lambda: 0.0), quiet=True)
    asyncio.run(r.apply())
    gw.calls.clear()
    asyncio.run(r.apply())                       # 変化が無ければ送らない
    assert gw.calls == []
    asyncio.run(r.apply(force=True))             # 送り直しでは必ず戻す
    assert "set_blink" in gw.calls


def test_送り直しの間隔が決まっている():
    src = _src("reconcile.py")
    assert "resync_s" in src, "送り直しの間隔が無いと、乱れたまま戻らない"
    assert "force=force" in src, "定期的に全部送り直していない"
