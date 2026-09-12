#!/usr/bin/env python3
"""DJコンソール — DDJ-FLX2 でスタックチャンを演奏する。

gateway をデーモンモードで動かしておくこと（Claude Code と実機を共有できる）:

    cd vendor/stackchan-mcp/gateway
    uv run stackchan-mcp serve --transport streamable-http

そのうえで:

    ./.venv/bin/python app/dj/console.py              # 実機に繋ぐ
    ./.venv/bin/python app/dj/console.py --dry-run    # 実機なしで動作確認

割り当ては app/dj/mapping.json を読む（1つずつ実測して確定したもの）。
"""
from __future__ import annotations

import argparse
import asyncio
import contextlib
import json
import math
import os
import signal
import sys
import time
from pathlib import Path

try:
    import mido
    import websockets
    from mcp import ClientSession
    from mcp.client.streamable_http import streamablehttp_client
except ImportError as exc:
    raise SystemExit(f"依存が足りない ({exc})。"
                     " ./.venv/bin/pip install mido python-rtmidi websockets 'mcp>=1.27,<2.0'")

sys.path.insert(0, str(Path(__file__).resolve().parent))
from motion.arbiter import HeadArbiter          # noqa: E402
from motion import phrases                     # noqa: E402

from constants import (ROOT, MAPPING, YAW_MIN, YAW_MAX, PITCH_REL_MIN,
                       PITCH_REL_MAX, MODE_IDLE, MODE_DJ, MODE_LABEL,
                       MODE_FACE, MODE_ORDER, _scale)  # noqa: F401



# ★ここにあった Gateway / PoseState / LedState は別ファイルに移した。
#   console.py は「つなぐ役」だけを持つ。
from gateway import Gateway                     # noqa: E402
from led import LedState                        # noqa: E402
from motion.pose import PoseState               # noqa: E402

# Console の中身は役割ごとに mixin へ分けた。console.py は「つなぐ役」だけ。
from expression import ExpressionMixin          # noqa: E402
from midi_in import MidiMixin                   # noqa: E402
from audio import AudioMixin                    # noqa: E402
from jog import Jog
from touch import TouchMixin                    # noqa: E402
from vision import VisionMixin                  # noqa: E402
import settings                                 # noqa: E402
import presence as presence_mod                 # noqa: E402
from presence import Presence                   # noqa: E402
from reconcile import Reconciler                # noqa: E402
import verify                                   # noqa: E402
from stage import (run_stage, stage_url, Advertiser,   # noqa: E402
                   watch_network)

# ────────────────────────────────────────────────────────────────

# モードが決めるのは「音に反応するか」だけ。
#
# ★最初は 待機/DJ/手動 の3つにしたが、区別が曖昧だった。
#   つまみも表情も全モードで効くので、待機と手動の違いが実質なかった。
#   **モードは1つの軸だけを表す**ようにする。多いほど良いわけではない。
#
#   つまみ・表情パッド・うなずき・頭なでは、**モードと無関係に常に効く**。
#   それらは「人が今まさに操作している」ので、勝手に無効化してはいけない。


class Console(ExpressionMixin, MidiMixin, AudioMixin, TouchMixin, VisionMixin):
    """つなぐ役。**実機の状態は Presence に言い、Reconciler が書く**（設計 §4 I1）。"""

    # ── 状態を動かす共通の道具。ここ以外に持たせない ────────────
    async def hand_mic_to_talk(self) -> None:
        """踊りからマイクを取り上げる。**beat mode の持ち主は console**（設計 I1）。

        ★実機は踊りと会話で同じマイクを取り合う（2026-09-12 実測）。
          「beat mode is already using the device microphone」
        """
        if self.args.beat:
            await self.gw.call("beat_mode_stop")
            await asyncio.sleep(0.6)

    async def hand_mic_back(self) -> None:
        """会話が終わったら、踊りにマイクを返す。

        ★`beat_mode_start` は `init_device` の1箇所にしか書かない（設計 I4）。
          ここで書き直すと、いつか片方だけ直して食い違う。**同じ関数を通す。**
        """
        if self.args.beat:
            await init_device(self.gw, self, self.args, why="会話からの復帰")

    def set_talk(self, state: str | None) -> None:
        """会話の状態。**LEDの色の意味はここで決まる**（緑=聞く／青=喋る）。

        ★配布物（event/handson-guide.md）に書いてある色と一致させること。
          紙を見た人が緑を探すのに緑が光らなければ、その紙は嘘になる。
        """
        self.presence.talk = state
        self.led.talk = state

    def set_dancing(self, on: bool) -> None:
        """踊っているかどうか。**首と顔で食い違わないよう1箇所で切り替える。**"""
        self.pose.dance = on
        self.presence.dancing = on

    async def home_head(self) -> None:
        """首を正面へ。**Arbiter を通す**（設計 I2。move_head を直接叩かない）。"""
        self.pose.hold = (0.0, 0.0)
        await asyncio.sleep(0.6)                   # ストリームが届くだけ待つ
        self.pose.hold = None

    async def set_torque(self, on: bool) -> None:
        """脱力／起こす。トルクは表示状態ではないので Presence には載せない。"""
        await self.gw.call("set_servo_torque", yaw=on, pitch=on)
        self._torque_off = not on
    def __init__(self, gw: Gateway, cfg: dict, args):
        self.gw, self.cfg, self.args = gw, cfg, args
        # ★あるべき姿はここに一元化する。実機に書くのは Reconciler だけ（設計 I1）
        self.presence = Presence(dance_face=args.beat_face)
        self.reconciler = Reconciler(gw, self.presence, quiet=args.quiet)
        self.pose = PoseState(hold_s=args.knob_hold)
        # ★右レコードでスポットライトを振る（触っていなければ自動に返る）
        self.jog = Jog()
        self.led = LedState(count=args.led_count, target=args.led_target,
                            max_brightness=args.led_brightness,
                            pattern=args.led_pattern, cycle_beats=args.led_cycle_beats)
        self.ctl = cfg["controls"]
        self.idle_after = cfg.get("avatar_policy", {}).get("auto_return_to_idle_sec", 4)

        self._torque_off = False

        self._knob_was = False
        self._last_check = 0.0
        self.mode = MODE_IDLE
        self._silent_since = None
        self._hold_i = 0
        self.locked_bpm = None
        self._last_pose_print = 0.0
        self._loop: asyncio.AbstractEventLoop | None = None

        # (ch, num) → 用途 の逆引きを作る
        self.cc: dict[tuple[int, int], str] = {}
        self.note: dict[tuple[int, int], str] = {}
        for slot, c in self.ctl.items():
            key = (c["ch"], c["num"])
            (self.cc if c["kind"] == "cc" else self.note)[key] = slot

    async def wake_servos(self):
        """脱力状態で首を動かそうとしたら、トルクを戻す。"""
        if self._torque_off:
            await self.gw.call("set_servo_torque", yaw=True, pitch=True)
            self._torque_off = False
            print("    （トルクを戻しました）")

    async def set_mode(self, mode: str, why: str = "", force: bool = False) -> None:
        """モードを変える。**実機は触らない。あるべき姿を変えるだけ。**

        ★以前はここで顔・瞬き・LED・beat mode を直接叩いていた。
          反映役が持つようになったので、宣言するだけでよくなった。
        """
        if mode == self.mode and not force:
            return
        self.mode = mode
        self.presence.mode = mode
        print(f"\n  ■ モード: {MODE_LABEL[mode]}" + (f"（{why}）" if why else ""))

        # 踊りは DJ モードのときだけ
        if mode != MODE_DJ:
            self.led.enabled = False
            self.led.swoon = False
            self.set_dancing(False)
            await self.home_head()

    @staticmethod
    def _as_json(result):
        if result is None:
            return None
        for b in getattr(result, "content", []) or []:
            t = getattr(b, "text", None)
            if t:
                try:
                    return json.loads(t)
                except Exception:
                    return None
        return None


async def ws_server(state, host: str, port: int, hz: float, label: str, gate=None):
    """gate() が False を返す間はフレームを送らない（首の主導権を譲る）。"""
    interval = 1.0 / hz

    async def handler(ws):
        print(f"→ {label} を購読開始: {getattr(ws, 'remote_address', '?')}")
        try:
            while True:
                if gate is None or gate():
                    await ws.send(state.frame())
                await asyncio.sleep(interval)
        except websockets.exceptions.ConnectionClosed:
            print(f"← {label} の購読が切れました")

    # ★ `async with serve(...)` にしないこと。
    #   抜けるとき、開いている接続が閉じるのを無期限に待つ。
    #   gateway が繋ぎっぱなしなので、Ctrl-C しても畳まれなくなる（実測）。
    server = await websockets.serve(handler, host, port)
    try:
        print(f"{label}: ws://{host}:{port}/  ({hz:.0f} Hz)")
        await asyncio.Future()
    finally:
        server.close()
        with contextlib.suppress(Exception):
            await asyncio.wait_for(asyncio.shield(server.wait_closed()), 2.0)


async def wait_for_device(gw, timeout_s: float = 20.0) -> bool:
    """実機が gateway に繋がるまで待つ。

    ★2026-09-08、実機が起動しきる前に console を立ち上げたせいで
      beat_mode_start が "No ESP32 device connected" で黙って失敗し、
      「再起動したら動かない」状態になった。
      ツール呼び出しは**エラーを返すだけで例外にならない**ので気づけない。

    だから、始める前に一度だけ実際に問い合わせて、居ることを確かめる。
    """
    if gw.dry_run:
        return True
    forever = timeout_s <= 0                       # 0 = 実機が来るまでずっと待つ（常駐向け）
    end = time.time() + timeout_s
    warned = False
    while True:
        try:
            r = await gw.call("get_head_angles")
            c = getattr(r, "content", None)
            body = c[0].text if c else str(r)
            if "error" not in body:
                if warned:
                    print("  実機が繋がりました。続けます")
                return True
        except Exception:
            body = ""
        if not forever and time.time() >= end:
            print("\n★ 実機が gateway に繋がっていません。")
            print("  スタックチャンの電源とWi-Fiを確認して、繋がってから起動し直してください。")
            print("  （このまま起動しても、首は動きません）\n")
            return False
        if not warned:
            print("実機を待っています … スタックチャンの電源を入れてください"
                  + ("（ずっと待ちます）" if forever else ""))
            warned = True
        await asyncio.sleep(1.0)


async def load_avatar(gw, args) -> None:
    """自作の表情を実機へ読み込ませる。

    ★顔のデータは実機の RAM に載っている。**電源を切ると消えて、既定の顔に戻る。**
      2026-09-08、実機を再起動したら表情が元に戻っていた。
      焼き直しではなく、毎回の起動で読ませるのが正しい。
    """
    if gw.dry_run or not args.avatar:
        return
    path = Path(args.avatar)
    if not path.is_absolute():
        path = ROOT / path
    if not path.exists():
        print(f"★ 表情のデータが無い: {path}")
        print("  app/avatar/pack_avatar.py で作り直してください")
        return
    r = await gw.call("load_avatar_set", archive_path=str(path.resolve()), mode="layered")
    c = getattr(r, "content", None)
    body = c[0].text if c else str(r)
    if '"ok": true' in body or '"ok":true' in body:
        print(f"表情を読み込みました: {path.name}（{path.stat().st_size:,} バイト）")
    else:
        print(f"★ 表情の読み込みに失敗: {body[:200]}")


async def _check(gw, tool: str, **args) -> bool:
    """ツールを呼び、**戻り値を見て失敗に気づく。**

    ★gateway のツールは、失敗しても例外を投げない。`{"ok": false, "error": ...}`
      を**返すだけ**なので、呼びっぱなしだと起動ログに何も出ずに壊れる。
      2026-09-10、外付けLEDテープの購読が `led_count` 不足で黙って失敗していた。
    """
    r = await gw.call(tool, **args)
    c = getattr(r, "content", None)
    body = c[0].text if c else str(r)
    if '"ok": false' in body or '"ok":false' in body or '"error"' in body:
        print(f"★ {tool} が失敗しました: {body[:200]}")
        return False
    return True


async def init_device(gw, con, args, why: str = "起動") -> None:
    """実機に対する初期化。**起動時と、実機が戻ってきたときの両方で使う。**

    ★順番に意味がある。ここが唯一の置き場所。
      ① 表情を読み込む   — 電源で消えるので毎回
      ② ストリームを購読 — 首とLEDの通り道
      ③ beat mode 開始   — motion/led を有効にして始まる
      ④ モードを確定     — ③に上書きされないよう、必ず最後
    """
    await load_avatar(gw, args)

    # ★会場は騒がしい。スピーカーは上限まで上げておく（実機の設定）
    await _check(gw, "set_volume", volume=args.volume)

    if not args.no_subscribe:
        await asyncio.sleep(0.5)
        await _check(gw, "stackchan_follow_pose_stream", action="start",
                     url=f"ws://{args.host}:{args.pose_port}/")

        # ★外付けテープは、先に初期化してから購読を頼む。
        #   さらに購読側にも本数が要る（無いと黙って失敗する）。
        led_args = {"url": f"ws://{args.host}:{args.led_port}/",
                    "target": args.led_target}
        if args.led_target != "base_ring":
            init = ("port_b_ws2812_init" if args.led_target.startswith("port_b")
                    else "port_c_ws2812_init")
            await _check(gw, init, led_count=args.led_count)
            led_args["led_count"] = args.led_count
        await _check(gw, "stackchan_follow_led_stream", action="start", **led_args)

    if args.beat:
        # ★beat_mode_start は motion/led を有効にして始まる。
        #   set_mode より後に呼ぶと、待機モードなのに首を振り始める（実際そうなった）。
        await gw.call("beat_mode_start", sensitivity=args.sensitivity,
                      motion_intensity=args.motion_intensity,
                      color=list(args.led_color))
        print(f"beat mode 開始  感度={args.sensitivity}  振り幅={args.motion_intensity}"
              f"  停止判定={args.beat_timeout_ms}ms  踊る顔={args.beat_face}")

    # 全部そろえてから、最後にモードを確定させる
    await con.set_mode(args.mode, why=why, force=True)


async def device_watchdog(gw, con, args, poll_s: float = 5.0):
    """実機が居なくなって戻ってきたら、黙って組み直す。

    ★実機の電源を入れ直すと、表情は消え、beat mode は死に、購読も切れる。
      以前はここで console を手で立ち上げ直していた。**その必要を無くす。**

    ★生存確認は gateway 側だけで完結する `get_status` を使う（実測16ms）。
      実機に問い合わせるツールを短い間隔で叩くと、音声の取り込みを邪魔する。
    """
    if gw.dry_run:
        return
    present = True
    while True:
        await asyncio.sleep(poll_s)
        try:
            body = (await gw.call("get_status")).content[0].text
            now = '"connected": true' in body.lower()
        except Exception:
            now = False

        if present and not now:
            present = False
            print("\n⚠ 実機が居なくなりました。戻ってくるまで待ちます")
        elif not present and now:
            print("\n実機が戻りました。組み直します …")
            try:
                await asyncio.sleep(2.0)               # 実機側が立ち上がりきるのを待つ
                con.reconciler.forget()            # 実機が入れ替わった。全部送り直す
                await init_device(gw, con, args, why="実機の復帰")
                print("組み直しました。そのまま使えます\n")
                present = True
            except Exception as exc:
                print(f"★ 組み直しに失敗（{exc}）。次の確認でやり直します")


async def _cleanup(gw, args, con=None):
    """gateway 側を元に戻す。**踊ったまま放置しない。**

    ★片付けは必ず時間で区切る。相手（gateway・実機）が応答しないとき、
      待ち続けると止まらなくなる。落ちないより、片付け損ねる方がまし。
    """
    async def steps():
        if args.beat:
            await gw.call("beat_mode_stop")
        if not args.no_subscribe:
            await gw.call("stackchan_follow_pose_stream", action="stop")
            await gw.call("stackchan_follow_led_stream", action="stop")
        # 正面に戻して待機の顔にする。踊りかけの角度で放置しない。
        # ★首はストリームを切ったあとなので、ここだけ直接動かす（設計 §4 I1 の例外）。
        #   サーボの脱力は実機側の自動脱力（既定8秒）に任せる。
        await gw.call("move_head", yaw=0, pitch=45)
        # ★顔と瞬きは反映役に任せる。「待機に戻す」と宣言して一度だけ反映する。
        if con is not None:
            con.presence.mode = MODE_IDLE
            con.set_dancing(False)
            for kind in list(presence_mod.PRIORITY):
                con.presence.clear(kind)
            await con.reconciler.apply(force=True)

    if gw.dry_run:
        return
    try:
        await asyncio.wait_for(steps(), timeout=8.0)
        print("片付けました（beat停止・購読解除・正面・待機顔）")
    except (TimeoutError, asyncio.TimeoutError):
        print("★ 片付けが8秒で終わりませんでした。gateway 側に残っているかもしれません")
    except Exception as exc:
        print(f"★ 片付けに失敗: {exc}")


def _install_signals() -> asyncio.Event:
    """SIGINT / SIGTERM を受けたら畳む合図にする。

    ★2026-09-08 実測: SIGTERM（pkill）は既定だと即死し、片付けが1つも走らなかった。
      beat mode が回りっぱなし、ストリームも購読したままになる。
      Ctrl-C だけ通って pkill が通らないのは、運用としておかしい。
    """
    stop = asyncio.Event()
    loop = asyncio.get_running_loop()
    for sig in (signal.SIGINT, signal.SIGTERM):
        with contextlib.suppress(NotImplementedError):
            loop.add_signal_handler(sig, stop.set)
    return stop


async def _verify_then_stop(args, gw, con):
    """--verify: 自分の pose ストリームを覗いて角度を測り、片付けて終わる。

    ★ここは os._exit で落とす。ws サーバや MIDI のループは
      cancel しても素直に畳まれないことがあり、待つと固まる（実際そうなった）。
      片付けだけは必ず済ませてから落とす。
    """
    await asyncio.sleep(2.0)                       # サーバが立つのを待つ
    code = await verify.watch(args.host, args.pose_port)
    with contextlib.suppress(Exception):
        await asyncio.wait_for(_cleanup(gw, args, con), 5.0)
    sys.stdout.flush()
    os._exit(code)


async def main_async(args):
    cfg = json.loads(MAPPING.read_text(encoding="utf-8"))

    async with Gateway(args.gateway, args.dry_run) as gw:
        # ★Console は実機に触らずに組める。**先に組んで、画面サーバを立てる。**
        #   会場では、ロボットの電源を入れる前から iPad を出しておきたい。
        #   実機待ちの後ろに置くと、繋ぐまで画面が真っ暗になる。
        con = Console(gw, cfg, args)
        con.pose.sway_deg = args.sway_deg
        con.pose.nod_deg = args.nod_deg
        con.pose.subdiv = args.subdiv
        con.pose.ramp_per_s = 1.0 / max(0.1, args.ramp_s)
        con.pose.fall_per_s = 1.0 / max(0.1, args.fall_s)
        con.pose.phrase_beats = args.phrase_beats

        # 画面と mDNS は、実機を待つ前に走らせておく
        early = []
        if args.stage_port > 0:
            adv = Advertiser(args.stage_port)
            early = [asyncio.ensure_future(run_stage(con, "0.0.0.0",
                                                     args.stage_port)),
                     asyncio.ensure_future(watch_network(adv))]

        # ここから先は実機が要る
        if not await wait_for_device(gw, args.wait_device):
            for t in early:
                t.cancel()
            return 1
        await con.start_idle_behaviour()

        tasks = [
            ws_server(con.pose, args.host, args.pose_port, args.hz, "pose ストリーム",
                      gate=con.pose.emit),
            ws_server(con.led, args.host, args.led_port, 20.0, "LED ストリーム"),
            con.midi_loop(),
            con.mouth_to_beat(),
        ]
        if args.beat:
            tasks.append(con.beat_supervisor())
        if args.touch_poll_s > 0:
            tasks.append(con.touch_loop())
        tasks.append(con.reconciler.loop())
        tasks.append(device_watchdog(gw, con, args))
        tasks.append(con.knob_face_loop())
        tasks.append(con.groove_loop())
        if args.beat:
            tasks.append(con.spike_loop())
        if args.face_every_s > 0:
            tasks.append(con.face_loop())
        # ★測るだけ。目で見て判断する前に、機械に数えさせる。
        checker = _verify_then_stop(args, gw, con) if args.verify else None

        await init_device(gw, con, args, why="起動")
        print("\n準備できました。つまみを回してください。Ctrl-C で終了\n")
        if checker is not None:
            tasks.append(checker)                  # 測り終わったら中から落とす
        stop = _install_signals()
        runners = early + [asyncio.ensure_future(t) for t in tasks]
        try:
            done, _ = await asyncio.wait(
                [*runners, asyncio.ensure_future(stop.wait())],
                return_when=asyncio.FIRST_COMPLETED)
            if stop.is_set():
                print("\n止めています …")
            for r in runners:                       # 走っているループを畳む
                r.cancel()
            _, pending = await asyncio.wait(runners, timeout=3.0)
            if pending:
                names = ", ".join(sorted(
                    getattr(t.get_coro(), "__qualname__", "?") for t in pending))
                print(f"★ 畳めなかったループ: {names}")
            for d in done:                          # ループ側の例外は握りつぶさない
                if d in runners and not d.cancelled() and d.exception():
                    raise d.exception()
        finally:
            await _cleanup(gw, args, con)
        return 0


def _pre_config(ap):
    """--config だけ先に拾う。設定ファイルの場所自体は設定ファイルに書けないため。"""
    pre = argparse.ArgumentParser(add_help=False)
    pre.add_argument("--config", type=Path)
    return pre.parse_known_args()[0].config


def main() -> int:
    ap = argparse.ArgumentParser(description="DDJ-FLX2 でスタックチャンを演奏する")
    ap.add_argument("--gateway", default="http://127.0.0.1:8767/mcp")
    ap.add_argument("--dry-run", action="store_true", help="実機に繋がず、呼ぶツールを表示するだけ")
    ap.add_argument("--host", default="127.0.0.1")
    ap.add_argument("--pose-port", type=int, default=8770)
    ap.add_argument("--led-port", type=int, default=8771)
    ap.add_argument("--hz", type=float, default=30.0, help="pose 送信レート。gateway が 20Hz に落とす")
    ap.add_argument("--beat", action="store_true", help="beat mode も同時に走らせる")
    ap.add_argument("--sensitivity", type=float, default=0.3,
                    help="0=下限が高くキックだけ拾う 1=下限が低く細かい音も拾う。★大きい音ほど下げる。scripts/tune_beat.py で選べる")
    ap.add_argument("--beat-timeout-ms", type=int, default=3500,
                    help="最後の拍からこれだけ経ったら『聞こえていない』とみなす")
    ap.add_argument("--beat-silent-polls", type=int, default=5,
                    help="この回数連続で聞こえなければ踊りを畳む")
    ap.add_argument("--mode", default=MODE_IDLE, choices=MODE_ORDER,
                    help="起動時のモード")
    ap.add_argument("--dj-timeout-min", type=float, default=5.0,
                    help="DJモードで曲が来ない時間がこれを超えたら自動でOFFに戻る。0で無効")
    # ★0 にすると頭なでを止められる。押し出し型なので「間隔」ではないが、
    #   設定ファイルとの互換のため名前は変えない
    ap.add_argument("--touch-poll-s", type=float, default=0.8,
                    help="頭タッチを見る間隔。0で無効。★短くすると拍の検出を邪魔する")
    ap.add_argument("--touch-face-s", type=float, default=3.0, help="撫でられた顔を出す秒数")
    ap.add_argument("--knob-face", default="embarrassed",
                    help="つまみを触っている間の表情。空文字で無効")
    ap.add_argument("--touch-stuck-polls", type=int, default=4,
                    help="同じ生値がこの回数続いたら『固着』とみなしてタッチを無視する")
    ap.add_argument("--off-ch", type=int, default=6, help="OFFボタン（MASTER）のチャンネル")
    ap.add_argument("--off-note", type=int, default=99, help="OFFボタン（MASTER）のノート番号")
    ap.add_argument("--play-ch", type=int, default=0, help="PLAYボタンのチャンネル（-1で無効）")
    ap.add_argument("--play-note", type=int, default=11, help="PLAYボタンのノート番号")
    ap.add_argument("--listen-face", default="embarrassed",
                    help="耳を澄ましている間の顔。♥と頬がつくので『聴き入っている』に見える。"
                         "空文字で無効")
    ap.add_argument("--face-every-s", type=float, default=18.0,
                    help="何秒ごとに客席を見渡して顔を探すか。0で無効")
    ap.add_argument("--camera-fov-deg", type=float, default=35.0,
                    help="カメラの画角の半分。画面端の人が何度の方向にいるか")
    ap.add_argument("--spike-ratio", type=float, default=2.2,
                    help="直近の中央値の何倍で『跳ねた』とみなすか")
    ap.add_argument("--spike-hold-s", type=float, default=2.5, help="サビの全力時間")
    ap.add_argument("--spike-cooldown-s", type=float, default=6.0,
                    help="反応してから次に反応するまでの間隔")
    ap.add_argument("--phrase-beats", type=int, default=8,
                    help="何拍で振り付けを切り替えるか")
    ap.add_argument("--listen-check-s", type=float, default=4.0,
                    help="この秒数ごとに首を一瞬止めて、音楽が続いているか確かめる。0で無効")
    ap.add_argument("--listen-check-ms", type=int, default=1500,
                    help="耳を澄ます時間。★音量の窓が1.2秒なので、それより長く待たないと "
                         "直前のサーボ音が窓に残る（0.9秒だと 0.095 という残響を拾った）")
    ap.add_argument("--quiet-level", type=float, default=0.0045,
                    help="踊りだす音量の下限。実測：無音 0.0035 / 小さめの曲 0.009 / "
                         "しっかり鳴っている曲 0.026")
    # ★会場は広くなく、DJもそこまで大音量にしない。実測の下寄りを満点に置く。
    #   無音 0.0035 / 控えめな曲 0.005〜0.009 / 大きめ 0.02。0.005 で満点にする。
    ap.add_argument("--full-level", type=float, default=0.0050,
                    help="この音量で満点。★実測のDJ音量に合わせる（理想値を置かない）")
    ap.add_argument("--full-confidence", type=float, default=0.12,
                    help="この確信度で満点")
    ap.add_argument("--min-groove", type=float, default=0.55,
                    help="踊ると判定したときの最低の強さ。小さすぎると動いて見えない")
    ap.add_argument("--stop-ratio", type=float, default=0.7,
                    help="止める閾値は quiet-level のこの倍率。1未満にして往復を防ぐ")
    ap.add_argument("--quiet-polls", type=int, default=2,
                    help="静かな観測がこの回数続いたら即止める（曲の終わり用）")
    ap.add_argument("--beat-poll-s", type=float, default=1.0,
                    help="拍の様子を見る間隔。★短くすると音声フレームを奪って検出を壊す")
    ap.add_argument("--beat-face", default="happy", help="踊っている間の表情")
    ap.add_argument("--knob-hold", type=float, default=2.0,
                    help="つまみを離してから何秒で首を踊りに明け渡すか")
    ap.add_argument("--motion-intensity", type=float, default=1.0,
                    help="beat mode 側の振り幅。いまは自前で振るので未使用")
    ap.add_argument("--sway-deg", type=float, default=42.0,
                    help="左右の振り幅。フロアの端まで届かせる（サーボ上限は±90°）")
    ap.add_argument("--ramp-s", type=float, default=1.2, help="乗り出すまでの時間（助走）")
    ap.add_argument("--fall-s", type=float, default=1.2, help="止まるまでの時間")
    ap.add_argument("--nod-deg", type=float, default=9.0,
                    help="縦の動き。★客は左右にいるので控えめにする")
    ap.add_argument("--subdiv", type=float, default=1.0,
                    help="1=1拍で1往復 2=半拍で1往復（倍の速さ）")
    ap.add_argument("--auto-release-ms", type=int, default=8000, help="動きが止まって何msで脱力するか")
    ap.add_argument("--mouth-period", type=float, default=2.0, help="口のキューを積み直す間隔（秒）")
    ap.add_argument("--fallback-bpm", type=float, default=0.0, help="BPMが取れないときの既定値。0で無効")
    ap.add_argument("--no-mouth", action="store_true", help="口を動かさない")
    ap.add_argument("--quiet", action="store_true", help="つまみの現在値を表示しない")
    ap.add_argument("--no-subscribe", action="store_true", help="ストリームの購読を gateway に頼まない")
    ap.add_argument("--stage-port", type=int, default=8779,
                    help="背景スクリーン／操作パネルのポート。0で無効")
    ap.add_argument("--volume", type=int, default=100,
                    help="実機スピーカーの音量（0-100）。会場は騒がしいので既定は最大")
    ap.add_argument("--wait-device", type=float, default=20.0,
                    help="起動時に実機を待つ秒数。0 でずっと待つ（常駐運用向け）")
    ap.add_argument("--avatar", default=str(ROOT / "app" / "avatar" / "avatar_layered.raw"),
                    help="起動時に読み込む表情データ。空文字で読み込まない")
    ap.add_argument("--config", type=Path, default=None,
                    help="設定ファイル。既定は app/dj/config.toml。CLI 引数の方が強い")
    ap.add_argument("--verify", action="store_true",
                    help="起動して10秒ぶん実際に送った角度を測り、範囲に収まっているか報告して終わる")
    ap.add_argument("--led-color", type=int, nargs=3, default=(0, 90, 255), metavar=("R", "G", "B"))
    ap.add_argument("--led-target", default="base_ring",
                    choices=("base_ring", "port_b", "port_c"),
                    help="base_ring（本体12個）/ port_b / port_c（外付けテープ A093）。"
                         "★'base' は無効値。指定を間違えると購読が黙って失敗する")
    ap.add_argument("--led-count", type=int, default=12,
                    help="LEDの個数。A093(0.5m)なら 30")
    ap.add_argument("--led-pattern", default="strobe", choices=LedState.PATTERNS,
                    help="strobe=拍で全灯 chase=粒が回る rainbow=虹が回る split=半分ずつ")
    ap.add_argument("--led-cycle-beats", type=int, default=8,
                    help="何拍ごとに色を変えるか")
    ap.add_argument("--led-brightness", type=float, default=0.35,
                    help="明るさ上限 0..1。★A093 は全開 1.8A で Grove から取れない。既定 0.35")
    # ★ config.toml を先に読んで既定値を差し替える。CLI 引数はそのあとで勝つ。
    used = settings.load(ap, _pre_config(ap))
    args = ap.parse_args()
    args.led_color = tuple(args.led_color)
    if used and not args.quiet:
        print(f"設定: {used}")
    try:
        return asyncio.run(main_async(args)) or 0
    except KeyboardInterrupt:                        # 念のため（通常は合図で畳む）
        print("\n止めました")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
