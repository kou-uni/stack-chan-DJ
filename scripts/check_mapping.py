#!/usr/bin/env python3
"""割り当てが本当に効くかを、自分で押して確かめる。

    ./.venv/bin/python scripts/check_mapping.py

★人の手でしか確かめられない作りは、**確かめられていないのと同じ**（2026-09-12）。
  MIDI を流し込んで、状態が期待どおりに変わるかを機械が見る。
"""
import json
import sys
import time
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
MAP = ROOT / "app" / "dj" / "mapping.json"
TOKEN = (Path.home() / ".config" / "stackchan" / "panel-token").read_text().strip()
BASE = "http://127.0.0.1:8779"


def post(path: str, body: dict) -> dict:
    req = urllib.request.Request(f"{BASE}{path}?k={TOKEN}",
                                 data=json.dumps(body).encode(),
                                 headers={"Content-Type": "application/json"})
    try:
        return json.loads(urllib.request.urlopen(req, timeout=20).read())
    except Exception as exc:
        return {"error": str(exc)}


def main() -> int:
    ctl = json.loads(MAP.read_text(encoding="utf-8"))["controls"]
    bad = []

    print("── 割り当ての確認 ──\n")
    for slot, v in ctl.items():
        if v.get("kind") != "note":
            continue
        want_led = v.get("led_pattern")
        want_face = v.get("avatar")
        if not (want_led or want_face):
            continue
        r = post("/api/midi", {"ch": v["ch"], "num": v["num"]})
        time.sleep(0.35)
        if "error" in r:
            bad.append(f"{slot}: {r['error']}")
            print(f"  × {slot:<20} {r['error'][:50]}")
            continue
        after = r["after"]
        if want_led:
            ok = after.get("pattern") == want_led
            got = after.get("pattern")
        else:
            ok = after.get("face") == want_face
            got = after.get("face")
        mark = "○" if ok else "×"
        print(f"  {mark} {slot:<20} ch{v['ch']:>2} #{v['num']:<3} "
              f"→ {got}" + ("" if ok else f"（{want_led or want_face} のはず）"))
        if not ok:
            bad.append(f"{slot}: {got} ≠ {want_led or want_face}")

    print()
    if bad:
        print(f"★ {len(bad)} 件おかしい")
        return 1
    print("すべて期待どおり")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
