#!/usr/bin/env python3
"""カードを名簿に登録する。**かざす → 名前を打つ → 保存**、の繰り返し。

    ./.venv/bin/python scripts/nfc_enroll.py            # 対話で登録
    ./.venv/bin/python scripts/nfc_enroll.py --list     # 名簿を見る
    ./.venv/bin/python scripts/nfc_enroll.py --scan     # Port A に何がいるか（0x28 が出れば OK）

★名簿は event/rec/guests.toml。**人名なので git に入れない。**
  当日の MacBook へは**手で運ぶ**（checklist に入れてある）。
★実機の電源が入っていて、gateway が動いていること（console は止めていてよい）。
"""
from __future__ import annotations

import argparse
import asyncio
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "app" / "dj"))

import nfc  # noqa: E402
from gateway import Gateway  # noqa: E402

GATEWAY = "http://127.0.0.1:8767/mcp"


def load_table(path: Path) -> dict[str, str]:
    return dict(nfc.Guests.load(path).table)


def save_table(path: Path, table: dict[str, str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    lines = ["# NFC 名簿 — UID(16進小文字) = \"名前\"（さん付けは要らない）",
             "# ★人名。git に入れない。当日は MacBook へ手で運ぶ。", "", "[guests]"]
    for uid, name in sorted(table.items()):
        lines.append(f'{uid} = "{name}"')
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def add_guest(path: Path, uid: str, name: str) -> bool:
    """1件足す。★同じ鍵に別の名前は入れない（3バイトの鍵は重なりうる。登録時に気づく）。"""
    uid = uid.lower()
    table = load_table(path)
    if uid in table and table[uid] != name:
        print(f"  ★ {uid} は既に「{table[uid]}」です。別の人なら、そのカードは使わないでください（鍵が重なる）")
        return False
    table[uid] = name
    save_table(path, table)
    return True


async def scan() -> int:
    async with Gateway(GATEWAY) as gw:
        res = await gw.call("i2c_scan")
        print("  Port A:", res)
        return 0


async def enroll(path: Path) -> int:
    table = load_table(path)
    print(f"  名簿: {path}（{len(table)}人）")
    async with Gateway(GATEWAY) as gw:
        rc = nfc.Rc522(nfc.McpBus(gw))
        try:
            ver = await rc.init()
        except Exception as exc:                    # noqa: BLE001
            print(f"★ リーダーが見つかりません（Port A 0x28）: {exc}")
            print("  Unit を Port A に挿していますか。実機の電源は入っていますか。")
            return 1
        print(f"  リーダー OK（版 0x{ver:02x}）。カードをかざしてください。Ctrl-C で終わり。\n")
        seen: str | None = None
        while True:
            uid = await rc.poll_uid()
            if not uid or uid == seen:
                await asyncio.sleep(0.25)
                if not uid:
                    seen = None
                continue
            seen = uid
            cur = table.get(uid)
            print(f"  ▣ {uid}" + (f"  → いまは「{cur}」" if cur else "  → 未登録"))
            try:
                name = input("    名前（空なら飛ばす）> ").strip()
            except EOFError:
                break
            if name:
                if add_guest(path, uid, name):
                    table = load_table(path)
                    print(f"    ○ 保存しました: {uid} = {name}（{len(table)}人）\n")
            else:
                print()


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--list", action="store_true")
    ap.add_argument("--scan", action="store_true")
    ap.add_argument("--file", type=Path, default=nfc.GUESTS_PATH)
    ap.add_argument("--add", nargs=2, metavar=("UID", "名前"), help="対話せずに1件登録する")
    a = ap.parse_args()
    if a.add:
        ok = add_guest(a.file, a.add[0], a.add[1])
        if ok: print(f"  ○ 保存しました: {a.add[0].lower()} = {a.add[1]} → {a.file}")
        return 0 if ok else 1
    if a.list:
        t = load_table(a.file)
        print(f"  {a.file}（{len(t)}人）")
        for uid, name in sorted(t.items()):
            print(f"   {uid}  {name}")
        return 0
    if a.scan:
        return asyncio.run(scan())
    try:
        return asyncio.run(enroll(a.file))
    except KeyboardInterrupt:
        print("\n  終わります")
        return 0


if __name__ == "__main__":
    raise SystemExit(main())
