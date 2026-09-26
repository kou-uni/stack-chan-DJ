#!/usr/bin/env python3
"""OTA関門を通すためだけの最小サーバー。

xiaozhi 系ファームは起動時に `ota_url` へ問い合わせる。
そこで activation セクションを返されると、成功するまで無限ループして
WebSocket 接続まで進まない（本体に6桁コードが出て止まる）。

このサーバーは「新しいファームは無い / アクティベーション不要」とだけ答える。
それだけでファームは関門を抜け、自前ゲートウェイに繋ぎに行く。

    ./.venv/bin/python scripts/ota_stub.py --port 8778
"""
from __future__ import annotations

import argparse
import json
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer


class Handler(BaseHTTPRequestHandler):
    version = "1.16.0"

    def _reply(self):
        # activation を入れない = アクティベーション不要。
        # firmware.version を現在と同じにする = 新しい版は無い。
        body = json.dumps({
            "firmware": {"version": self.version, "url": ""},
            "server_time": {"timestamp": 0, "timezone_offset": 540},
        }).encode()
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_POST(self):
        n = int(self.headers.get("Content-Length") or 0)
        if n:
            self.rfile.read(n)
        self._reply()

    def do_GET(self):
        self._reply()

    def log_message(self, fmt, *args):
        # ★実機は起動のたびにここへ来る。**1行残せば「実機が再起動した時刻」が Mac 側で分かる**
        #   （2026-09-26。gateway は電源断を検知できない＝FIN が来ないので、起動の証拠がここにしか無い）
        import sys, time
        sys.stderr.write(time.strftime("%Y-%m-%d %H:%M:%S") + f" 実機から {self.client_address[0]} {self.command} {self.path}\n")
        sys.stderr.flush()


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--host", default="0.0.0.0")
    ap.add_argument("--port", type=int, default=8778)
    ap.add_argument("--version", default="1.16.0",
                    help="本体の現在バージョンと同じ値にする（新版なし扱いになる）")
    a = ap.parse_args()
    Handler.version = a.version
    print(f"OTA スタブ: http://{a.host}:{a.port}/  （version={a.version} / activation なし）")
    ThreadingHTTPServer((a.host, a.port), Handler).serve_forever()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
