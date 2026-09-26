#!/usr/bin/env python3
"""スマホで開くための QR を、端末に出す。

    ./.venv/bin/python scripts/qr.py          # 一覧
    ./.venv/bin/python scripts/qr.py text     # 当日の台本（鍵つき）
    ./.venv/bin/python scripts/qr.py qa       # 参加者の質疑
    ./.venv/bin/python scripts/qr.py p        # 配布物の一覧

## なぜ要るか（2026-09-25）

★**URL をファイルに書いても、スマホからは読めない。**
  「`cat` してください」は、Mac の前にいる人にしか通じない。
  **相手が見ている場所から出す**（当日と同じ話）。
"""
from __future__ import annotations

import subprocess
import sys
from pathlib import Path

PORT = 8779
# 名前 → (道, 鍵が要るか, 何のためか)
PLACES = {
    "text":  ("/text",  True,  "当日の台本（37画面）★進行役だけ。人に送らない"),
    "panel": ("/panel", True,  "操作パネル ★人に送らない"),
    "qa":    ("/qa",    False, "参加者の質疑応答（Dの冒頭で配る）"),
    "p":     ("/p",     False, "配布物の一覧（10枚）"),
    "map":   ("/p/map", False, "地図（Bで進行役が指す）"),
    "guide": ("/guide", False, "なでかたの案内"),
}


def host() -> str:
    """LAN 側の自分の IP。★インターフェース名を書かない（機械ごとに違う）。
    外向きの経路から逆引きする。"""
    import socket
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.connect(("10.255.255.255", 1))      # ★送信はしない。経路を選ばせるだけ
        ip = s.getsockname()[0]
        s.close()
        return ip
    except OSError:
        return "127.0.0.1"


def token() -> str:
    p = Path.home() / ".config" / "stackchan" / "panel-token"
    return p.read_text().strip() if p.exists() else ""


def main() -> int:
    name = sys.argv[1] if len(sys.argv) > 1 else ""
    if name not in PLACES:
        print("どれを出しますか\n")
        for k, (path, keyed, why) in PLACES.items():
            print(f"  {k:6} {path:9} {'鍵つき' if keyed else '      '}  {why}")
        print(f"\n  ./.venv/bin/python scripts/qr.py <名前>")
        return 0

    path, keyed, why = PLACES[name]
    url = f"http://{host()}:{PORT}{path}"
    if keyed:
        t = token()
        if not t:
            print("★ 鍵がありません（console を一度起動すると作られます）")
            return 1
        url += f"?k={t}"

    try:
        import qrcode
    except ImportError:
        print("★ qrcode が要ります: ./.venv/bin/pip install qrcode")
        return 1
    q = qrcode.QRCode(border=1)
    q.add_data(url)
    q.make(fit=True)
    q.print_ascii(invert=True)
    print(f"  {why}")
    print(f"  ★同じ Wi-Fi のスマホで読んでください（外には出ていません）")
    if keyed:
        print("  ★このQRには鍵が入っています。**画面を人に見せない。**")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
