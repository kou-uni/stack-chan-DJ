#!/usr/bin/env python3
"""背景スクリーン（iPad）と、スマホの操作パネルの土台。

## これは何か

console が持っている「いまの音の状態」を、**そのままブラウザへ流す**だけのサーバ。

    実機のマイク ──▶ gateway ──▶ console ──▶ iPad の背景
                                        └──▶ スマホの操作パネル（あとで）

★「スタックチャンが指令している」は**事実**。
  背景を動かしているのは、実機が聴いた音そのもの。演出ではない。

★サーバは1本にする。背景と操作パネルで分けない。
  Phase 2（スマホから触れる）がそのままここに乗る。

## 送るもの

**小さく保つ。** 毎拍たくさん送ると、iPad より先にネットワークが詰まる。
絵をどう描くかは**ブラウザ側の仕事**。ここは状態だけを渡す。
"""
from __future__ import annotations

import asyncio
import contextlib
import json
import time
from pathlib import Path

HERE = Path(__file__).resolve().parent

# ★会場では IP も機械名も変わる（家＝Mac Studio／会場＝MacBook、テザリング）。
#   **変わらない名前を1つ作って、そこに全部ぶら下げる。**
#   iPad はいつでも http://stackchan.local:8779/ を開けばよい。
STAGE_HOST = "stackchan.local"


def stage_state(led, presence, now: float | None = None) -> dict:
    """いまの状態を、画面が使う形にして返す。**純粋な変換。**

    - `beat` は秒ではなく**拍の中の位置 0..1**。画面はこれで光る
    - `series` は LED と**同じ関数**から採る（テープと画面で色が食い違わない）
    """
    n, ph = led._phase()
    return {
        "bpm": float(led.bpm or 0.0),
        "n": int(n),
        "beat": float(ph),
        "series": led._series_name(n),
        "dancing": bool(led.enabled),
        "drop": bool(led.flash_white),
        "groove": float(getattr(led, "groove", 1.0)),
        "mode": presence.mode,
        "talk": presence.talk,
    }


async def run_stage(con, host: str, port: int, hz: float = 20.0):
    """背景と操作パネルを配る。**実機が無くても落ちない。**"""
    from aiohttp import web, WSMsgType

    async def index(_req):
        return web.FileResponse(HERE / "stage.html")

    async def ws(req):
        sock = web.WebSocketResponse(heartbeat=20)
        await sock.prepare(req)
        print(f"→ 背景スクリーンが繋がりました: {req.remote}")
        try:
            while not sock.closed:
                await sock.send_str(json.dumps(
                    stage_state(con.led, con.presence)))
                await asyncio.sleep(1.0 / hz)
        except (ConnectionResetError, asyncio.CancelledError):
            raise
        except Exception:
            pass
        finally:
            with contextlib.suppress(Exception):
                await sock.close()
            print("← 背景スクリーンが切れました")
        return sock

    # ── 外から操作するパネル（ROADMAP Phase 2）─────────────
    #   ★同じ console の中に置く。別プロセスにすると書き手が2人になる（I2 違反）
    from panel import (AskDesk, CameraFeed, apply_action, check_token,
                       load_token, panel_state, perform, split_speech)
    ask_desk = AskDesk()
    token = load_token()

    async def _shoot() -> bytes | None:
        """実機で1枚撮って、その中身を返す。★パスではなく中身。"""
        await con.gw.call("take_photo", question="")
        shots = sorted((Path.home() / ".stackchan" / "captures").glob("*.jpg"),
                       key=lambda p: p.stat().st_mtime, reverse=True)
        return shots[0].read_bytes() if shots else None

    feed = CameraFeed(_shoot)

    def guard(req):
        return check_token(req.query.get("k"), token)

    async def guide(_req):
        """なでかたの案内。★鍵なしで開ける。**操作ではないので誰が見てもよい**
        （会場でQRから開いてもらう）。"""
        return web.FileResponse(HERE / "guide.html")

    async def panel(req):
        # ★鍵が違っても画面は返す。中で「鍵がちがいます」と出る方が、
        #   真っ白より原因が分かる（api 側は必ず弾く）
        return web.FileResponse(HERE / "panel.html")

    async def api_state(req):
        if not guard(req):
            return web.json_response({"error": "鍵がちがいます"}, status=403)
        s = panel_state(con)
        s["watching"] = feed.viewers      # ★映像が流れているかを外から見えるように
        return web.json_response(s)

    async def api_act(req):
        if not guard(req):
            return web.json_response({"error": "鍵がちがいます"}, status=403)
        try:
            body = await req.json()
        except Exception:
            return web.json_response({"error": "読めない指示"}, status=400)
        try:
            out = await apply_action(con, str(body.get("action", "")),
                                     str(body.get("value", "")))
        except ValueError as exc:
            return web.json_response({"error": str(exc)}, status=400)
        except Exception as exc:
            # ★実機が落ちていても、パネルは落ちない
            return web.json_response(
                {"error": f"実機に届きません（{type(exc).__name__}）"}, status=502)
        return web.json_response(out)

    async def api_camws(req):
        """映像を WebSocket で送る。**開いた瞬間から映る。**

        ★`multipart/x-mixed-replace` は cloudflared が溜め込んで通らなかった
          （2026-09-12 実測: トンネル越し 8秒で 0 バイト）。
          **WebSocket は同じ経路で背景スクリーンが通っている。確実な方を使う。**
        """
        sock = web.WebSocketResponse(heartbeat=20, max_msg_size=0)
        if not guard(req):
            await sock.prepare(req)
            await sock.close(code=4403, message=b"key")
            return sock
        await sock.prepare(req)
        try:
            async with feed.viewer():
                while not sock.closed:
                    img = await feed.wait_new(timeout=8.0)
                    if img:
                        await sock.send_bytes(img)
        except (ConnectionResetError, asyncio.CancelledError):
            pass
        except Exception:
            pass
        finally:
            with contextlib.suppress(Exception):
                await sock.close()
        return sock

    async def api_ask(req):
        """スマホから質問。**声と文字の両方で返す。**

        ★外にいる人には声が聞こえない。文字が本体。
        """
        if not guard(req):
            return web.json_response({"error": "鍵がちがいます"}, status=403)
        try:
            q = str((await req.json()).get("text", ""))
        except Exception:
            return web.json_response({"error": "読めない指示"}, status=400)
        try:
            r = await ask_desk.ask(con, q)
        except Exception as exc:
            return web.json_response(
                {"error": f"答えられません（{type(exc).__name__}）"}, status=502)
        return web.json_response({**r, "state": panel_state(con)})

    async def api_speak(req):
        """書いた台本を、そのまま読ませる。**一方通行でよい長話用。**

        `[happy]` で表情、`[pause=1.5]` で間、改行で区切り。
        """
        if not guard(req):
            return web.json_response({"error": "鍵がちがいます"}, status=403)
        try:
            body = await req.json()
        except Exception:
            return web.json_response({"error": "読めない指示"}, status=400)
        script = str(body.get("script", ""))
        if not script.strip():
            return web.json_response({"error": "台本が空"}, status=400)
        if body.get("dry"):
            # ★焼く前に読み合わせできるように。**実機を鳴らさず割り方だけ見る**
            return web.json_response({"ok": True, "lines": [
                {"text": l.text, "face": l.face, "pause": l.pause_before}
                for l in split_speech(script)]})
        try:
            r = await perform(con, script)
        except Exception as exc:
            return web.json_response(
                {"error": f"読ませられません（{type(exc).__name__}）"}, status=502)
        return web.json_response({**r, "state": panel_state(con)})

    async def api_history(req):
        if not guard(req):
            return web.json_response({"error": "鍵がちがいます"}, status=403)
        return web.json_response({"items": ask_desk.history()})

    async def api_photo(req):
        """最後に撮った写真を返す。★パスは外に出さない。"""
        if not guard(req):
            return web.Response(status=403)
        shots = sorted((Path.home() / ".stackchan" / "captures").glob("*"),
                       key=lambda p: p.stat().st_mtime, reverse=True)
        if not shots:
            return web.Response(status=404)
        return web.FileResponse(shots[0])

    app = web.Application()
    app.add_routes([web.get("/", index), web.get("/ws", ws),
                    web.get("/panel", panel),
                    web.get("/guide", guide),
                    web.get("/api/state", api_state),
                    web.post("/api/act", api_act),
                    web.get("/api/photo", api_photo),
                    web.get("/api/camws", api_camws),
                    web.post("/api/ask", api_ask),
                    web.post("/api/speak", api_speak),
                    web.get("/api/history", api_history)])
    runner = web.AppRunner(app, access_log=None)
    await runner.setup()
    site = web.TCPSite(runner, host, port)
    await site.start()
    ip = current_ip()
    print(f"\n背景スクリーン {'='*40}")
    print(f"  iPad で開く: {stage_url(port)}")
    print(f"  （届かないときは http://{ip or '<LAN IP>'}:{port}/ ）\n")
    print_qr(stage_url(port))
    print(f"\n操作パネル {'='*42}")
    print(f"  スマホで開く: http://{ip or '<LAN IP>'}:{port}/panel?k={token}")
    print("  ★鍵は ~/.config/stackchan/panel-token。**人に見せない**")
    print("  外から使う: scripts/expose.sh\n")
    try:
        await asyncio.Future()
    finally:
        with contextlib.suppress(Exception):
            await runner.cleanup()


def stage_url(port: int) -> str:
    """iPad で開く URL。**機械名にも IP にも依存しない。**"""
    return f"http://{STAGE_HOST}:{port}/"


def current_ip() -> str:
    """いまの LAN IP。★既定経路のインターフェースから取る。

    列挙順で拾うと、有線と Wi-Fi が同じ網に居るときに日替わりで変わる。
    """
    import subprocess
    out = subprocess.run(["route", "-n", "get", "default"],
                         capture_output=True, text=True).stdout
    iface = next((l.split()[-1] for l in out.splitlines() if "interface:" in l), "")
    if not iface:
        return ""
    return subprocess.run(["ipconfig", "getifaddr", iface],
                          capture_output=True, text=True).stdout.strip()


def print_qr(url: str) -> None:
    """端末に QR を出す。**会場では iPad のカメラで読むのが一番速い。**"""
    try:
        import qrcode
    except ImportError:
        return
    q = qrcode.QRCode(border=1)
    q.add_data(url)
    q.make(fit=True)
    m = q.get_matrix()
    # 上下2行を1行にまとめて、端末で正方形に見せる
    for y in range(0, len(m), 2):
        row = ""
        for x in range(len(m[0])):
            top = m[y][x]
            bot = m[y + 1][x] if y + 1 < len(m) else False
            row += ("█" if top and bot else "▀" if top else "▄" if bot else " ")
        print("  " + row)


class Advertiser:
    """mDNS で `stackchan.local` を名乗る。

    ★IP は毎回変わる（家 → テザリング）。**名前で引けるようにする。**
      名乗ったまま IP が変わると引けなくなるので、変化を見て名乗り直す。

    ★同期版の zeroconf を asyncio の中から呼ぶと、自分のループを待って固まる
      （実測：TimeoutError）。**非同期版を使う。**

    ★ここが失敗しても console は止めない。
      名前で引けなくても、IP を直接叩けば画面は出る。**degrade して動かす。**
    """

    def __init__(self, port: int):
        self.port, self._zc, self._info, self.ip = port, None, None, ""
        self.ok = False

    async def advertise(self, ip: str) -> bool:
        import socket
        from zeroconf import ServiceInfo
        from zeroconf.asyncio import AsyncZeroconf

        await self.stop()
        if not ip:
            return False
        try:
            self._zc = AsyncZeroconf()
            self._info = ServiceInfo(
                "_http._tcp.local.",
                "stackchan-stage._http._tcp.local.",
                addresses=[socket.inet_aton(ip)],
                port=self.port,
                server=f"{STAGE_HOST}.",       # ← この名前で A レコードが出る
                properties={"path": "/"},
            )
            await self._zc.async_register_service(self._info)
        except Exception as exc:
            print(f"⚠ {STAGE_HOST} を名乗れませんでした（{exc}）。"
                  f"IP で開いてください: http://{ip}:{self.port}/")
            self._zc = self._info = None
            self.ok = False
            self.ip = ip                       # IP は覚える（再試行を繰り返さない）
            return False
        self.ip, self.ok = ip, True
        return True

    async def stop(self) -> None:
        with contextlib.suppress(Exception):
            if self._zc and self._info:
                await self._zc.async_unregister_service(self._info)
            if self._zc:
                await self._zc.async_close()
        self._zc = self._info = None
        self.ok = False


async def watch_network(adv: Advertiser, period_s: float = 5.0):
    """IP が変わったら名乗り直す。**家 → 会場のテザリングで必ず変わる。**"""
    try:
        while True:
            ip = current_ip()
            if ip and ip != adv.ip:
                was = adv.ip
                if await adv.advertise(ip):
                    print(f"\n  ■ ネットワークが変わりました "
                          f"{was or '(なし)'} → {ip}")
                    print(f"    iPad で開く: {stage_url(adv.port)}\n")
            await asyncio.sleep(period_s)
    finally:
        await adv.stop()
