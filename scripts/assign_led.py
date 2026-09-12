#!/usr/bin/env python3
"""LEDの模様を、DJコントローラのキーに割り当てる。

    ./.venv/bin/python scripts/assign_led.py            # 未割り当てだけ回す
    ./.venv/bin/python scripts/assign_led.py --all      # 全部やり直す
    ./.venv/bin/python scripts/assign_led.py --only laser,sweep
    ./.venv/bin/python scripts/assign_led.py --show     # いまの割り当てを見る

## 流れ

**模様を実際に光らせながら、名前を声で言います。** 気に入ったキーを押してください。
押さずに待てば飛ばします（あとで割り当てられます）。

★端末は見なくていい。**光っているものを見て、キーを押すだけ。**
★console は自動で止めて、終わったら戻します（MIDIとLEDを取り合わないため）。
"""
import argparse
import asyncio
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "app" / "dj"))
from gateway import Gateway          # noqa: E402
from harness import ConsolePause     # noqa: E402
from led import LedState             # noqa: E402

GW = "http://127.0.0.1:8767/mcp"
MAP = ROOT / "app" / "dj" / "mapping.json"
FPS = 14
WAIT_S = 25.0

# 声で言う名前。★英単語のままだと聞き取れない
SAY = {
    "wave": "うぇーぶ", "strobe": "すとろぼ", "chase": "ちぇいす",
    "rainbow": "れいんぼー", "split": "すぷりっと", "mix": "みっくす",
    "laser": "れーざー", "sweep": "すいーぷ", "build": "びるど",
    "sparks": "すぱーくす", "strobe_hard": "はげしい すとろぼ",
    "segments": "せぐめんつ", "show": "しょー",
}


def load() -> dict:
    return json.loads(MAP.read_text(encoding="utf-8"))


def save(d: dict) -> None:
    MAP.write_text(json.dumps(d, ensure_ascii=False, indent=2) + "\n",
                   encoding="utf-8")


def assigned(d: dict) -> dict[str, dict]:
    """模様 → 割り当て済みのキー。"""
    out = {}
    for k, v in d.get("controls", {}).items():
        if v.get("led_pattern"):
            out[v["led_pattern"]] = {"key": k, **v}
    return out


def taken(d: dict) -> set[tuple]:
    """すでに使われている（種類, ch, num）。★奪わない。"""
    return {(v.get("kind"), v.get("ch"), v.get("num"))
            for v in d.get("controls", {}).values()}


async def listen_key(port: str, used: set[tuple], secs: float):
    """キーが押されるのを待つ。**すでに使われているキーは無視する。**"""
    import mido
    loop = asyncio.get_running_loop()
    got: asyncio.Future = loop.create_future()

    def reader():
        with mido.open_input(port) as inp:
            for msg in inp:
                if got.done():
                    return
                if msg.type != "note_on" or getattr(msg, "velocity", 0) == 0:
                    continue
                key = ("note", msg.channel, msg.note)
                if key in used:
                    print(f"      （ch{msg.channel} #{msg.note} は使用中。別のキーを）")
                    continue
                loop.call_soon_threadsafe(
                    lambda k=key: got.done() or got.set_result(k))
                return

    task = asyncio.ensure_future(asyncio.to_thread(reader))
    try:
        return await asyncio.wait_for(asyncio.shield(got), timeout=secs)
    except asyncio.TimeoutError:
        return None
    finally:
        if not got.done():
            got.cancel()
        task.cancel()


async def show_pattern(gw, name: str, count: int, brightness: float,
                       stop: asyncio.Event) -> None:
    s = LedState(count=count, pattern=name, max_brightness=brightness)
    s.enabled = True
    s.bpm = 124.0
    import time
    s.beat0 = time.time()
    while not stop.is_set():
        await gw.call("port_b_ws2812_set_strip",
                      colors=json.loads(s.frame())["colors"])
        await gw.call("port_b_ws2812_refresh")
        await asyncio.sleep(1.0 / FPS)


async def run(a) -> int:
    d = load()
    have = assigned(d)
    todo = [p for p in LedState.PATTERNS
            if a.all or p not in have]
    if a.only:
        want = {x.strip() for x in a.only.split(",")}
        todo = [p for p in LedState.PATTERNS if p in want]
    if not todo:
        print("全部 割り当て済みです（--all でやり直せます）")
        return 0

    import mido
    ports = [p for p in mido.get_input_names() if "FLX" in p or "DDJ" in p]
    if not ports:
        print("★ DJコントローラが見つかりません")
        return 1
    port = ports[0]
    print(f"  コントローラ: {port}")
    print(f"  これから {len(todo)} 個。押さずに待てば飛ばします\n")

    async with Gateway(GW) as gw:
        await gw.call("port_b_ws2812_init", led_count=a.count)
        for i, name in enumerate(todo, 1):
            used = taken(d)
            print(f"  [{i}/{len(todo)}] {name}")
            await gw.call("say", text=f"{SAY.get(name, name)}。すきなキーを おしてください",
                          speaker_id=14)
            stop = asyncio.Event()
            show = asyncio.ensure_future(
                show_pattern(gw, name, a.count, a.brightness, stop))
            key = await listen_key(port, used, WAIT_S)
            stop.set()
            await asyncio.gather(show, return_exceptions=True)
            await gw.call("port_b_ws2812_clear")

            if key is None:
                print("      → とばしました\n")
                continue
            kind, ch, num = key
            slot = f"led_{name}"
            d.setdefault("controls", {})[slot] = {
                "kind": kind, "ch": ch, "num": num,
                "label": f"LED {name}", "led_pattern": name,
                "confirmed": "2026-09-12",
            }
            save(d)
            print(f"      → ch{ch} #{num} に割り当てました\n")
            await gw.call("say", text="おっけー", speaker_id=14)
        await gw.call("port_b_ws2812_clear")
    return 0


def show_current() -> int:
    d = load()
    have = assigned(d)
    for p in LedState.PATTERNS:
        v = have.get(p)
        mark = f"ch{v['ch']} #{v['num']}" if v else "—"
        print(f"  {p:<14} {mark}")
    return 0


if __name__ == "__main__":
    ap = argparse.ArgumentParser(description="LEDの模様をDJのキーに割り当てる")
    ap.add_argument("--all", action="store_true")
    ap.add_argument("--only")
    ap.add_argument("--show", action="store_true")
    ap.add_argument("--count", type=int, default=30)
    ap.add_argument("--brightness", type=float, default=0.65)
    a = ap.parse_args()
    if a.show:
        raise SystemExit(show_current())
    with ConsolePause():
        import time as _t
        _t.sleep(3)          # ★console が MIDI と LED を離すのを待つ
        raise SystemExit(asyncio.run(run(a)))
