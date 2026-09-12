#!/usr/bin/env python3
"""健康診断。**点検して、直せるものは直す。**

    ./.venv/bin/python scripts/doctor.py          点検だけ
    ./.venv/bin/python scripts/doctor.py --fix    直せるものは直す

★これは「中身」で、入口ではない。
  いまは Mac のコマンドから呼ぶが、あとでスマホ（HTTP）や
  頭を撫でる操作からも同じ `run()` を呼ぶ。**中身は1つに保つ。**

★詰まったとき、どこが悪いかを人が推理しないで済むようにするのが目的。
  9月8日は「動かない」の原因が実機の切断だと分かるまでに時間を使った。
"""
from __future__ import annotations

import asyncio
import json
import os
import subprocess
import sys
import tomllib
import unicodedata
from dataclasses import dataclass, field
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "app" / "dj"))

from gateway import Gateway                       # noqa: E402
from constants import PITCH_REL_MAX, YAW_MAX      # noqa: E402

CONFIG = ROOT / "app" / "dj" / "config.toml"
MAPPING = ROOT / "app" / "dj" / "mapping.json"
AVATAR_BYTES = 537_600                            # layered = 14枚ぶん

OK, WARN, NG, FIXED = "ok", "warn", "ng", "fixed"
MARK = {OK: "○", WARN: "△", NG: "×", FIXED: "✓"}


@dataclass
class Check:
    name: str
    state: str
    detail: str
    hint: str = ""                                # 人がやること
    fixed: str = ""                               # 直したときの一言

    def repair(self, msg: str) -> None:
        """直したら、直ったことにする。★×のまま残すと『まだ壊れている』に見える。"""
        self.fixed, self.state = msg, FIXED


@dataclass
class Report:
    checks: list[Check] = field(default_factory=list)
    note: str = ""                                # 検査項目ではない補足

    def add(self, *a, **kw) -> Check:
        c = Check(*a, **kw)
        self.checks.append(c)
        return c

    @property
    def repaired(self) -> int:
        return sum(1 for c in self.checks if c.state == FIXED)

    @property
    def worst(self) -> str:
        for s in (NG, WARN, OK):
            if any(c.state == s for c in self.checks):
                return s
        return OK


def _conf() -> dict:
    """config.toml を平らにして読む。無くても既定値で動く。"""
    flat = {}
    if CONFIG.exists():
        for k, v in tomllib.loads(CONFIG.read_text(encoding="utf-8")).items():
            flat.update(v if isinstance(v, dict) else {k: v})
    return {k.replace("-", "_"): v for k, v in flat.items()}


def _json(res) -> dict:
    c = getattr(res, "content", None)
    return json.loads(c[0].text if c else str(res))


async def run(fix: bool = False) -> Report:
    """点検する。fix=True なら直せるものは直す。"""
    r = Report()
    cfg = _conf()

    # ── ① 手元のファイル（実機に繋がなくても分かる）─────────────
    blob = ROOT / cfg.get("avatar", "app/avatar/avatar_layered.raw")
    if not blob.is_absolute():
        blob = ROOT / blob
    if not blob.exists():
        r.add("表情のデータ", NG, f"{blob.name} が無い",
              hint="app/avatar/pack_avatar.py で作り直す")
    elif blob.stat().st_size != AVATAR_BYTES:
        r.add("表情のデータ", NG,
              f"{blob.stat().st_size:,} バイト（正しくは {AVATAR_BYTES:,}）",
              hint="pack_avatar.py で作り直す")
    else:
        r.add("表情のデータ", OK, f"{blob.name}  {AVATAR_BYTES:,} バイト")

    # ── ② 常駐しているか ─────────────────────────────────
    pids = subprocess.run(["pgrep", "-f", "app/dj/console.py"],
                          capture_output=True, text=True).stdout.split()
    if pids:
        r.add("console", OK, f"動いている PID {' '.join(pids)}")
    else:
        c = r.add("console", NG, "動いていない",
                  hint="./scripts/service.sh install で常駐にする")
        if fix:
            subprocess.run(
                ["launchctl", "kickstart",
                 f"gui/{os.getuid()}/com.uni.stackchan.console"],
                capture_output=True)
            c.repair("立ち上げを頼んだ（20秒ほどで上がる）")

    # ── ③ DJ機材 ──────────────────────────────────────
    try:
        import mido
        hint = json.loads(MAPPING.read_text(encoding="utf-8")).get("port_hint", "DDJ")
        ports = [n for n in mido.get_input_names() if hint.lower() in n.lower()]
        if ports:
            r.add("DJ機材", OK, ports[0])
        else:
            r.add("DJ機材", WARN, "見つからない",
                  hint="USBを挿せば3秒で拾う。立ち上げ直しは要らない")
    except Exception as exc:
        r.add("DJ機材", WARN, f"調べられない（{exc}）")

    # ── ③.5 背景スクリーン（iPad から届くか）─────────────────
    import socket
    port = int(cfg.get("stage_port", 8779))
    if port > 0:
        alive = False
        with socket.socket() as sk:
            sk.settimeout(1.0)
            alive = sk.connect_ex(("127.0.0.1", port)) == 0
        if not alive:
            r.add("背景スクリーン", NG, f"ポート {port} が開いていない",
                  hint="console が動いていれば開く")
        else:
            # ★名前で引けるか。会場では IP が毎回変わるので、ここが要
            try:
                ip = socket.gethostbyname("stackchan.local")
                r.add("背景スクリーン", OK,
                      f"http://stackchan.local:{port}/  →  {ip}")
            except OSError:
                from stage import current_ip
                r.add("背景スクリーン", WARN,
                      f"名前で引けない。IP で開く: http://{current_ip()}:{port}/",
                      hint="テザリングによっては mDNS が通らない。IP を使う")

    # ── ④ gateway と実機 ───────────────────────────────
    url = cfg.get("gateway", "http://127.0.0.1:8767/mcp")
    try:
        async with Gateway(url) as gw:
            r.add("gateway", OK, url)

            st = _json(await gw.call("get_status"))
            if not st.get("connected"):
                r.add("実機", NG, "gateway に繋がっていない",
                      hint="スタックチャンの電源とWi-Fiを見る。"
                           "戻れば console が自分で組み直す")
                return r                            # 実機が居ないと以降は測れない
            r.add("実機", OK, f"{st.get('device_id')}  ツール{st.get('tools_count')}個")

            # 音の取り込み
            b = _json(await gw.call("beat_meta_snapshot"))
            quiet = float(cfg.get("quiet_level", 0.0045))
            if not b.get("active"):
                c = r.add("beat mode", NG, "止まっている",
                          hint="曲を流しても踊らない状態")
                if fix:
                    await gw.call("beat_mode_start",
                                  sensitivity=float(cfg.get("sensitivity", 0.5)),
                                  motion_intensity=float(cfg.get("motion_intensity", 1.0)),
                                  color=list(cfg.get("led_color", [0, 90, 255])))
                    # ★beat_mode_start は gateway 側の踊りを**有効にして**始まる。
                    #   モードを持っているのは console。診断ツールが勝手に踊らせない。
                    #   ここを切らないと、OFF のまま音に反応して止まらなくなる（実際そうなった）。
                    await gw.call("beat_mode_update",
                                  motion_enabled=False, led_enabled=False)
                    c.repair("かけ直した（踊りは切ったまま。PLAY で始まります）")
            elif not b.get("capture_healthy"):
                r.add("beat mode", NG, f"音が取れていない（{b.get('capture_state')}）",
                      hint="実機を再起動すると直ることが多い")
            else:
                lv = b.get("level", 0.0)
                state = OK if lv >= quiet else WARN
                r.add("音の取り込み", state,
                      f"{b.get('capture_state')}  音量={lv:.5f}  BPM={b.get('bpm')}",
                      hint="" if state == OK
                           else f"下限 {quiet} に届いていない。曲を流すか音量を上げる")

            # ストリーム
            for label, tool, port_key in (
                    ("pose ストリーム", "stackchan_follow_pose_stream", "pose_port"),
                    ("LED ストリーム", "stackchan_follow_led_stream", "led_port")):
                d = _json(await gw.call(tool, action="status"))
                if d.get("running"):
                    r.add(label, OK, "購読中")
                else:
                    c = r.add(label, NG, "購読が切れている",
                              hint="首やLEDが動かない状態")
                    if fix:
                        args = {"url": f"ws://{cfg.get('host','127.0.0.1')}:"
                                       f"{cfg.get(port_key)}/"}
                        if "led" in tool:
                            args["target"] = cfg.get("led_target", "base_ring")
                        await gw.call(tool, action="start", **args)
                        c.repair("購読しなおした")

            # 首の位置（可動範囲に居るか）
            h = _json(await gw.call("get_head_angles"))
            yaw, pitch = h.get("yaw", 0), h.get("pitch", 45)
            if abs(yaw) > YAW_MAX or not (45 - PITCH_REL_MAX <= pitch <= 45 + PITCH_REL_MAX):
                r.add("首の位置", NG, f"yaw={yaw} pitch={pitch} が可動範囲の外")
            elif pitch >= 80:
                r.add("首の位置", NG, f"pitch={pitch} ＝ ほぼ真下を向いている")
            else:
                r.add("首の位置", OK, f"yaw={yaw}  pitch={pitch}")

            # 表情は「入っているか」を問い合わせる手段が無い。直すことだけできる。
            # ★点検のときに △ を出さない。毎回出る警告は、いずれ誰も読まなくなる。
            if fix:
                res = _json(await gw.call("load_avatar_set",
                                          archive_path=str(blob), mode="layered"))
                r.add("表情の読み込み", OK if res.get("ok") else NG,
                      f"{res.get('bytes_transferred', 0):,} バイトを転送")
            else:
                r.note = "表情が入っているかは問い合わせられない。怪しければ --fix で入れ直す"

    except Exception as exc:
        r.add("gateway", NG, f"繋がらない（{exc}）",
              hint="./scripts/service.sh status で見る")

    return r


def _width(s: str) -> int:
    """表示幅。★日本語は2桁ぶん。文字数で揃えると桁がずれる。"""
    return sum(2 if unicodedata.east_asian_width(ch) in "WF" else 1 for ch in s)


def _pad(s: str, w: int) -> str:
    return s + " " * max(0, w - _width(s))


def show(r: Report) -> int:
    w = max(_width(c.name) for c in r.checks)
    for c in r.checks:
        print(f"{MARK[c.state]} {_pad(c.name, w)}  {c.detail}")
        if c.fixed:
            print(f"  {' ' * w}  → {c.fixed}")
        elif c.hint and c.state != OK:
            print(f"  {' ' * w}    {c.hint}")

    print()
    if r.note:
        print(f"（{r.note}）")
    if r.worst == OK:
        if r.repaired:
            print(f"{r.repaired}件 直しました。曲を流して PLAY を押せば踊ります")
        else:
            print("全部そろっています。曲を流して PLAY を押せば踊ります")
        return 0
    if r.worst == WARN:
        print("動きますが、気になる点があります（上の △）")
        return 0
    print("直っていないものがあります（上の ×）。--fix で直せることもあります")
    return 1
