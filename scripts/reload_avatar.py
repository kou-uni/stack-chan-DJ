#!/usr/bin/env python3
"""自作の表情を実機へ入れ直す。

★実機の電源を切ると表情は消える（PSRAM に載っているため）。
  console を起動し直せば自動で入るが、止めたくないときはこれを使う。

    ./.venv/bin/python scripts/reload_avatar.py
"""
import asyncio
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "app" / "dj"))
from gateway import Gateway                       # noqa: E402

BLOB = ROOT / "app" / "avatar" / "avatar_layered.raw"


async def main() -> int:
    if not BLOB.exists():
        print(f"表情のデータが無い: {BLOB}")
        print("app/avatar/pack_avatar.py で作り直してください")
        return 1
    async with Gateway("http://127.0.0.1:8767/mcp") as gw:
        r = await gw.call("load_avatar_set", archive_path=str(BLOB), mode="layered")
        c = getattr(r, "content", None)
        body = c[0].text if c else str(r)
        ok = '"ok": true' in body or '"ok":true' in body
        print(("入れ直しました" if ok else "失敗") + f": {BLOB.name}（{BLOB.stat().st_size:,} バイト）")
        if not ok:
            print(body[:300])
            return 1
        await gw.call("set_avatar", face="happy")
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
