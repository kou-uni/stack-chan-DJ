#!/usr/bin/env python3
"""macOS の `say` を、xiaozhi-server から呼べる小さな窓口にする。

## なぜ自前で立てるか（2026-09-13）

xiaozhi-server の TTS は**ほぼ全部クラウド**（EdgeTTS も Microsoft へ送る）。
このイベントの中心は「**声も映像も、この部屋から出ない**」なので、
既定のまま使うと**配布物に書いた約束を破る。**

ローカルで動く選択肢（fishspeech / gpt_sovits / paddle_speech）は、
どれも**別のサーバを1本立てる**必要がある。締切から逆算して割に合わない。

macOS には最初から日本語の音声合成が入っている。**それを窓口にするだけでよい。**

    say -v Kyoko -o out.wav --data-format=LEI16@24000

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
import shutil
import tempfile
from pathlib import Path

from aiohttp import web

# ★日本語の声。`say -v ?` で一覧が出る。Kyoko は標準で入っている
DEFAULT_VOICE = "Kyoko"


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
    ap.add_argument("--voice", default=DEFAULT_VOICE)
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
        else:
            text = (req.query.get("text") or "").strip()
            voice = req.query.get("voice") or args.voice
        if not text:
            return web.Response(status=400, text="text が空")
        try:
            wav = await synth(text, voice, args.rate)
        except Exception as exc:                      # noqa: BLE001
            # ★本文は出さない。**会話の中身をログに残さない**
            print(f"⚠ 合成に失敗（{len(text)}文字）: {exc}")
            return web.Response(status=500, text="合成に失敗")
        return web.Response(body=wav, content_type="audio/wav")

    async def health(_req: web.Request) -> web.Response:
        return web.json_response({"ok": True, "voice": args.voice})

    app = web.Application()
    app.router.add_route("*", "/tts", handle)
    app.router.add_get("/health", health)
    print(f"ローカルTTS: http://{args.host}:{args.port}/tts  声={args.voice}")
    web.run_app(app, host=args.host, port=args.port, print=None)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
