#!/usr/bin/env python3
"""実機の受け入れ試験。**焼く前に基準を取り、焼いた後に突き合わせる。**

    # 焼く前
    ./.venv/bin/python scripts/device_check.py --save backup/before-flash.json

    # 焼いた後
    ./.venv/bin/python scripts/device_check.py --compare backup/before-flash.json

★焼くと全部が変わりうる。**直った1つの陰で、他が壊れても気づけない。**
  だから毎回同じ項目を、同じ順で測る。

★人の手が要る項目（頭なで・マイク・スピーカー・聞き取り）は `--manual` を
  付けたときだけ聞く。付けなければ「未確認」として残る。
  **「測れなかった」を「壊れた」と混ぜない。**
"""
import argparse
import asyncio
import json
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "app" / "dj"))
from acceptance import CHECKS, Result, compare, summarize   # noqa: E402
from gateway import Gateway                                  # noqa: E402
from harness import ConsolePause, port_busy, throwaway_ws    # noqa: E402
from touch_events import TouchEvents                         # noqa: E402

GW = "http://127.0.0.1:8767/mcp"
POSE_PORT, LED_PORT = 8770, 8771


def _j(r):
    c = getattr(r, "content", None)
    return json.loads(c[0].text) if c else {}


# ★合図は実機から出す。**端末は誰も見ない。**
#   以前、音声認識のタイミングを端末のカウントダウンで伝えて失敗した（2026-09-12）。
#   同じ穴を試験でも踏まない
SAY_TAIL_S = 1.0        # 自分の声がマイクに残る分。測る前に空ける


async def _cue(gw, text: str) -> None:
    """実機に喋らせて合図する。ログにも残す（あとで読み返すため）。"""
    print(f"\n     >>> {text} <<<")
    await gw.call("say", text=text, speaker_id=14)
    await asyncio.sleep(SAY_TAIL_S)


async def _timed(coro):
    t0 = time.time()
    out = await coro
    return out, time.time() - t0


async def run(gw, manual: bool) -> dict[str, Result]:
    R: dict[str, Result] = {}

    async def check(name, fn, note=""):
        try:
            ok, detail, value = await fn()
            R[name] = Result(name, ok, detail or note, value)
        except Exception as exc:
            R[name] = Result(name, False, f"例外 {type(exc).__name__}: {exc}"[:80])
        label = CHECKS.get(name, {}).get("label", name)
        r = R[name]
        mark = "○" if r.ok else ("×" if r.ok is False else "—")
        v = f"  {r.value:.2f}s" if r.value is not None else ""
        print(f"  {mark} {label:16s}{v}  {r.detail}")

    print("── 実機の受け入れ試験 ──\n")

    async def _tools():
        d = _j(await gw.call("get_status"))
        n = d.get("tools_count") or 0
        return n >= 35, f"{n}個", None
    await check("tools", _tools)

    async def _head():
        (_, t) = await _timed(gw.call("move_head", yaw=20, pitch=45))
        await asyncio.sleep(0.5)
        d = _j(await gw.call("get_head_angles"))
        await gw.call("move_head", yaw=0, pitch=45)
        moved = abs((d.get("yaw") or 0) - 20) <= 8
        return moved, f"yaw={d.get('yaw')} pitch={d.get('pitch')}", t
    await check("head", _head)

    async def _leds():
        (r, t) = await _timed(gw.call("set_all_leds", r=0, g=40, b=0))
        await asyncio.sleep(0.3)
        await gw.call("clear_leds")
        return '"ok":true' in str(_j(r)).replace(" ", "").lower() or _j(r).get("ok"), "12個", t
    await check("leds", _leds)

    async def _strip():
        d = _j(await gw.call("port_b_ws2812_init", led_count=30))
        if not d.get("ok"):
            return False, str(d)[:60], None
        await gw.call("port_b_ws2812_set_strip", colors=[[0, 20, 0]] * 30)
        await gw.call("port_b_ws2812_refresh")
        await asyncio.sleep(0.3)
        await gw.call("port_b_ws2812_clear")
        return True, f"{d.get('led_count')}個", None
    await check("led_strip", _strip)

    async def _avatar():
        blob = ROOT / "app" / "avatar" / "avatar_layered.raw"
        (r, t) = await _timed(gw.call("load_avatar_set",
                                      archive_path=str(blob), mode="layered"))
        d = _j(r)
        return bool(d.get("ok")), f"{d.get('bytes_transferred', 0):,}バイト", t
    await check("avatar", _avatar)

    async def _screen():
        d = _j(await gw.call("get_device_info"))
        b = (d.get("screen") or {}).get("brightness")
        return b is not None, f"明るさ {b}", None
    await check("screen", _screen)

    async def _camera():
        # ★take_photo は question が必須（引数を省くと検証エラーになる）
        (r, t) = await _timed(gw.call("take_photo", question="何が写っていますか"))
        c = getattr(r, "content", None)
        body = c[0].text if c else ""
        ok = "error" not in body[:40].lower() and len(body) > 10
        return ok, body[:50].replace("\n", " "), t
    await check("camera", _camera)

    async def _servo_power():
        d = _j(await gw.call("check_vm_en"))
        return bool(d.get("vm_en_high")), f"VM_EN={d.get('vm_en_high')}", None
    await check("servo_power", _servo_power)

    # ★ストリームは「いま張られているか」ではなく「張れるか」を見る。
    #   console が管理しているので、状態を見るだけだと試験の順番で結果が変わる
    async def _pose():
        await gw.call("stackchan_follow_pose_stream", action="start",
                      url=f"ws://127.0.0.1:{POSE_PORT}/")
        await asyncio.sleep(0.8)
        st = _j(await gw.call("stackchan_follow_pose_stream", action="status"))
        return bool(st.get("running")), st.get("connect_state", ""), None
    await check("pose_stream", _pose)

    async def _ledstream():
        d = _j(await gw.call("stackchan_follow_led_stream", action="start",
                             url=f"ws://127.0.0.1:{LED_PORT}/", target="port_b",
                             led_count=30))
        await asyncio.sleep(0.8)
        st = _j(await gw.call("stackchan_follow_led_stream", action="status"))
        ok = bool(st.get("running")) and not str(d.get("error") or "")
        return ok, f"{st.get('target')} {st.get('connect_state','')}", None
    await check("led_stream", _ledstream)

    async def _beat():
        await gw.call("beat_mode_start", sensitivity=0.5,
                      motion_intensity=1.0, color=[0, 90, 255])
        await gw.call("beat_mode_update", motion_enabled=False, led_enabled=False)
        await asyncio.sleep(2.5)
        d = _j(await gw.call("beat_meta_snapshot"))
        ok = bool(d.get("active") and d.get("capture_healthy"))
        return ok, f"{d.get('capture_state')} 音量={d.get('level', 0):.5f}", None
    await check("beat", _beat)

    async def _tts():
        await gw.call("beat_mode_stop")
        await asyncio.sleep(0.5)
        (r, t) = await _timed(gw.call("say", text="試験中です", speaker_id=14))
        d = _j(r)
        return bool(d.get("duration_ms")), f"{d.get('duration_ms')}ms の音声", t
    await check("tts", _tts)

    # ── 人の手が要るもの ────────────────────────────
    if manual:
        async def _touch():
            te = TouchEvents(max_stroke_ms=10 ** 9)
            te.catch_up()
            await _cue(gw, "あたまを、なでてください。二十秒はかります")
            te.catch_up()          # ★合図の前の分は数えない
            hits, t0 = 0, time.time()
            while time.time() - t0 < 20:
                if te.poll():
                    hits += 1
                await asyncio.sleep(0.3)
            return hits > 0, f"20秒で {hits}回 検出", float(hits)
        await check("touch", _touch)

        async def _mic():
            await gw.call("beat_mode_start", sensitivity=0.5,
                          motion_intensity=1.0, color=[0, 90, 255])
            await gw.call("beat_mode_update", motion_enabled=False, led_enabled=False)
            await asyncio.sleep(1.5)
            await gw.call("beat_mode_stop")
            await _cue(gw, "八びょうかん、ふつうの声で話してください")
            await gw.call("beat_mode_start", sensitivity=0.5,
                          motion_intensity=1.0, color=[0, 90, 255])
            await gw.call("beat_mode_update", motion_enabled=False, led_enabled=False)
            await asyncio.sleep(0.5)
            peak = 0.0
            for _ in range(8):
                d = _j(await gw.call("beat_meta_snapshot"))
                peak = max(peak, d.get("level") or 0.0)
                await asyncio.sleep(1.0)
            await gw.call("beat_mode_stop")
            return peak >= 0.004, f"最大音量 {peak:.5f}", None
        await check("mic", _mic)

        async def _speaker():
            # ★端末の入力待ちにしない。**当日、端末は誰も見ない。**
            #   自分の声がマイクに回り込むのを利用して、鳴ったことを機械が確かめる
            #   （この機体はスピーカーとマイクが同じ筐体にある＝必ず回り込む）
            await gw.call("beat_mode_start", sensitivity=0.5,
                          motion_intensity=1.0, color=[0, 90, 255])
            await gw.call("beat_mode_update", motion_enabled=False, led_enabled=False)
            await asyncio.sleep(1.5)
            quiet = (_j(await gw.call("beat_meta_snapshot")).get("level") or 0.0)
            task = asyncio.ensure_future(
                gw.call("say", text="聞こえていますか。聞こえていますか",
                        speaker_id=14))
            peak = 0.0
            for _ in range(6):
                await asyncio.sleep(0.4)
                peak = max(peak, _j(await gw.call("beat_meta_snapshot")).get("level") or 0.0)
            await task
            await gw.call("beat_mode_stop")
            # ★自分の声は人の声の10倍で入る（実測 0.45 対 0.05）
            return peak > max(0.02, quiet * 4), f"回り込み {peak:.4f}（静音時 {quiet:.4f}）", None
        await check("speaker", _speaker)

        async def _stt():
            await _cue(gw, "ファームってなんですか、と言ってください")
            (r, t) = await _timed(gw.call("listen", duration_ms=8000,
                                          language="ja", model="small"))
            txt = (_j(r).get("text") or "").strip()
            return bool(txt), f"「{txt[:30]}」", t
        await check("stt", _stt)

        await _cue(gw, "しけん、おわりました。ありがとうございます")
    else:
        for name in ("touch", "mic", "speaker", "stt"):
            R[name] = Result(name, None, "人の手が要る（--manual で測る）")
            print(f"  — {CHECKS[name]['label']:16s}  人の手が要る（--manual で測る）")

    return R


def to_json(R: dict[str, Result]) -> str:
    return json.dumps({k: vars(v) for k, v in R.items()},
                      ensure_ascii=False, indent=1)


def from_json(text: str) -> dict[str, Result]:
    return {k: Result(**v) for k, v in json.loads(text).items()}


async def _wait_free(ports, timeout=10.0) -> bool:
    """console が口を離すのを待つ。★止めた直後はまだ握っている。"""
    t0 = time.time()
    while time.time() - t0 < timeout:
        if not any(port_busy(p) for p in ports):
            return True
        await asyncio.sleep(0.3)
    return False


async def main(a) -> int:
    if a.keep_console:
        # ★逃げ道。ただし console が同時に書くので、比較の基準には使わない
        print("※ console を動かしたまま測ります（基準には使わないこと）\n")
        async with Gateway(GW) as gw:
            R = await run(gw, a.manual)
    else:
        # ★console は「唯一の書き手」。測る間だけ黙ってもらう。
        #   二人が書けば、測った値が誰のものか分からなくなる
        with ConsolePause():
            if not await _wait_free([POSE_PORT, LED_PORT]):
                print(f"★ ポート {POSE_PORT}/{LED_PORT} が空きません")
                return 1
            # ★ストリーム試験の相手を自分で用意する。
            #   console を止めただけだと繋ぐ先が無く、**偽の×**が出る
            async with throwaway_ws(POSE_PORT), throwaway_ws(LED_PORT):
                async with Gateway(GW) as gw:
                    R = await run(gw, a.manual)
            print("\n  console を戻します")

    if a.save:
        Path(a.save).write_text(to_json(R), encoding="utf-8")
        print(f"\n基準を保存しました: {a.save}")

    if a.compare:
        before = from_json(Path(a.compare).read_text(encoding="utf-8"))
        diffs = compare(before, R)
        print("\n" + "=" * 50)
        print(summarize(diffs))
        print("=" * 50)
        return 1 if any(d.kind == "デグレ" for d in diffs) else 0

    bad = [r for r in R.values() if r.ok is False]
    return 1 if bad else 0


if __name__ == "__main__":
    p = argparse.ArgumentParser(description="実機の受け入れ試験")
    p.add_argument("--save", help="結果を基準として保存する")
    p.add_argument("--compare", help="保存した基準と突き合わせる")
    p.add_argument("--keep-console", action="store_true",
                   help="console を止めずに測る（★同時に書かれるので基準には使えない）")
    p.add_argument("--manual", action="store_true",
                   help="人の手が要る項目（頭なで・マイク・スピーカー・聞き取り）も測る")
    raise SystemExit(asyncio.run(main(p.parse_args())))
