#!/usr/bin/env python3
"""いまの声（VOICEVOX）を、xiaozhi-server から呼べる小さな窓口にする。

## なぜ自前で立てるか（2026-09-13）

xiaozhi-server の TTS は**ほぼ全部クラウド**（EdgeTTS も Microsoft へ送る）。
このイベントの中心は「**声も映像も、この部屋から出ない**」なので、
既定のまま使うと**配布物に書いた約束を破る。**

ローカルで動く選択肢（fishspeech / gpt_sovits / paddle_speech）は、
どれも**別のサーバを1本立てる**必要がある。締切から逆算して割に合わない。

そして**探す前に、すでに手元で動いていた。**
実機がいま喋っている声（撫での「さわりすぎ」やスピーチ）は、
gateway が **VOICEVOX**（`127.0.0.1:50021`、話者14＝冥鳴ひまり）で作っている。
**最初からローカルで、しかも本人の好きな声だった。**

> 新しく用意する前に、いま動いているものが何かを見る。
> 「クラウドを避ける」に気を取られて、**手元の答えを見落としていた**（2026-09-13）。

VOICEVOX は2段構え（`/audio_query` → `/synthesis`）なので、
xiaozhi の Custom TTS（1回のリクエストで wav を返す約束）には直接つながらない。
**この窓口が2段をまとめる。**

エンジンが落ちていたら macOS の `say` に落ちる。**当日、声が出ないよりはいい。**

xiaozhi-server 側は `TTS: CustomTTS` で、この窓口を叩く（`core/providers/tts/custom.py`）。
返すのは **wav のバイト列**だけ。

## 決めごと

- **外に出さない。** ここは 127.0.0.1 だけで待つ
- **テキストは残さない。** ログに本文を出さない（会話の中身が漏れる）
- 音声ファイルは作ったらすぐ消す
"""
from __future__ import annotations

import argparse
import asyncio
import os
import shutil
import tempfile
from pathlib import Path

import aiohttp
from aiohttp import ClientTimeout, web

# ★実機と同じ声。**2箇所に別々の番号を書かない**（app/dj が 14 を使っている）
VOICEVOX_URL = os.environ.get("STACKCHAN_VOICEVOX_URL", "http://127.0.0.1:50021")
VOICEVOX_SPEAKER = int(os.environ.get("STACKCHAN_VOICEVOX_SPEAKER", "14"))

# 落ちたときの逃げ道。`say -v ?` で一覧が出る
FALLBACK_VOICE = "Kyoko"


async def voicevox(session, text: str, speaker: int) -> bytes:
    """VOICEVOX で1文を wav にする。**2段（問い合わせ→合成）をここでまとめる。**"""
    async with session.post(f"{VOICEVOX_URL}/audio_query",
                            params={"text": text, "speaker": speaker},
                            timeout=ClientTimeout(total=20)) as r:
        r.raise_for_status()
        query = await r.json()
    async with session.post(f"{VOICEVOX_URL}/synthesis",
                            params={"speaker": speaker}, json=query,
                            timeout=ClientTimeout(total=60)) as r:
        r.raise_for_status()
        return await r.read()


async def synth(text: str, voice: str, rate: int) -> bytes:
    """1文を wav にする。**失敗したら例外。黙って空を返さない。**"""
    with tempfile.TemporaryDirectory() as d:
        out = Path(d) / "out.wav"
        proc = await asyncio.create_subprocess_exec(
            "say", "-v", voice, "-r", str(rate),
            "-o", str(out), "--data-format=LEI16@24000", text,
            stdout=asyncio.subprocess.DEVNULL,
            stderr=asyncio.subprocess.PIPE,
        )
        _, err = await proc.communicate()
        if proc.returncode != 0:
            raise RuntimeError(err.decode("utf-8", "replace")[:200])
        return out.read_bytes()


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--host", default="127.0.0.1")   # ★外には出さない
    ap.add_argument("--port", type=int, default=8781)
    ap.add_argument("--voice", default=FALLBACK_VOICE, help="VOICEVOX が落ちたとき")
    ap.add_argument("--speaker", type=int, default=VOICEVOX_SPEAKER)
    ap.add_argument("--rate", type=int, default=200, help="1分あたりの語数")
    args = ap.parse_args()

    if not shutil.which("say"):
        print("⚠ `say` が見つかりません（macOS 以外では動きません）")
        return 1

    async def handle(req: web.Request) -> web.Response:
        if req.method == "POST":
            body = await req.json()
            text = (body.get("text") or "").strip()
            voice = body.get("voice") or args.voice
            speaker = int(body.get("speaker") or args.speaker)
        else:
            text = (req.query.get("text") or "").strip()
            voice = req.query.get("voice") or args.voice
            speaker = int(req.query.get("speaker") or args.speaker)
        if not text:
            return web.Response(status=400, text="text が空")
        # ★まず実機と同じ声。落ちていたら macOS の声に逃げる
        try:
            wav = await voicevox(req.app["http"], text, speaker)
        except Exception as exc:                      # noqa: BLE001
            print(f"⚠ VOICEVOX が使えません（{exc}）。macOS の声に切り替えます")
            try:
                wav = await synth(text, voice, args.rate)
            except Exception as exc2:                 # noqa: BLE001
                # ★本文は出さない。**会話の中身をログに残さない**
                print(f"⚠ 合成に失敗（{len(text)}文字）: {exc2}")
                return web.Response(status=500, text="合成に失敗")
        return web.Response(body=wav, content_type="audio/wav")

    async def health(req: web.Request) -> web.Response:
        engine = None
        try:
            async with req.app["http"].get(f"{VOICEVOX_URL}/version",
                                           timeout=ClientTimeout(total=2)) as r:
                engine = (await r.text()).strip('"\n ')
        except Exception:                             # noqa: BLE001
            pass
        return web.json_response({"ok": True, "voicevox": engine,
                                  "speaker": args.speaker,
                                  "fallback": args.voice})

    async def _open(app):
        app["http"] = aiohttp.ClientSession()
        yield
        await app["http"].close()

    app = web.Application()
    app.cleanup_ctx.append(_open)
    app.router.add_route("*", "/tts", handle)
    app.router.add_get("/health", health)
    print(f"ローカルTTS: http://{args.host}:{args.port}/tts"
          f"  VOICEVOX 話者{args.speaker}（落ちたら {args.voice}）")
    web.run_app(app, host=args.host, port=args.port, print=None)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
