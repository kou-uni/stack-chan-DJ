#!/usr/bin/env python3
"""当日の音声を録りながら、その場で文字起こしする。**部屋の外に出さない。**

    ./.venv/bin/python scripts/record_meeting.py                 # 録音＋文字起こし
    ./.venv/bin/python scripts/record_meeting.py --list          # マイクを見る
    ./.venv/bin/python scripts/record_meeting.py --device 1      # マイクを選ぶ
    ./.venv/bin/python scripts/record_meeting.py --transcribe-only  # 後から起こす

Ctrl-C で止める。**途中で落ちても、もう一度動かせば続きから。**

★録るのは Mac のマイク。**スタックチャンのマイクは会話に専念させる**（本人の指示）。
★音声も文字起こしも、この Mac の中だけで終わる（ffmpeg / faster-whisper）。
"""
import argparse
import asyncio
import re
import subprocess
import sys
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "app" / "dj"))
from meeting import Transcript, finished_chunks   # noqa: E402

CHUNK_S = 60
MODEL = "small"


def list_devices() -> None:
    r = subprocess.run(["ffmpeg", "-f", "avfoundation", "-list_devices", "true",
                        "-i", ""], capture_output=True, text=True)
    hit = False
    for line in r.stderr.splitlines():
        if "audio devices" in line:
            hit = True
            continue
        if hit:
            m = re.search(r"\[(\d+)\] (.+)$", line)
            if not m:
                break
            print(f"  {m.group(1)}  {m.group(2)}")


async def record(out: Path, device: str) -> asyncio.subprocess.Process:
    out.mkdir(parents=True, exist_ok=True)
    # ★16kHz モノラル。whisper がその形で使う。**大きく録っても精度は上がらない**
    return await asyncio.create_subprocess_exec(
        "ffmpeg", "-hide_banner", "-loglevel", "error",
        "-f", "avfoundation", "-i", f":{device}",
        "-ac", "1", "-ar", "16000",
        "-f", "segment", "-segment_time", str(CHUNK_S), "-reset_timestamps", "1",
        str(out / "c%05d.wav"),
        stdout=asyncio.subprocess.DEVNULL, stderr=asyncio.subprocess.PIPE)


async def transcribe_loop(d: Path, tr: Transcript, stop: asyncio.Event) -> None:
    from faster_whisper import WhisperModel
    print(f"  文字起こしを準備しています（{MODEL}）…")
    model = await asyncio.to_thread(WhisperModel, MODEL, device="cpu",
                                    compute_type="int8")
    print("  準備できました。録りながら起こします\n")
    while True:
        did = False
        for p in finished_chunks(d, closed=stop.is_set()):
            if tr.done(p.name):
                continue
            idx = int(re.sub(r"\D", "", p.stem) or 0)
            try:
                segs, _ = await asyncio.to_thread(
                    model.transcribe, str(p), language="ja",
                    vad_filter=True, beam_size=1)
                text = "".join(s.text for s in segs).strip()
            except Exception as exc:
                # ★1つ失敗しても止めない。3時間の途中で死ぬのが一番困る
                print(f"  × {p.name}: {type(exc).__name__}")
                text = ""
            tr.add(p.name, idx * CHUNK_S, text)
            if text:
                print(f"  [{idx * CHUNK_S // 60}:{idx * CHUNK_S % 60:02d}] {text[:70]}")
            did = True
        if stop.is_set() and not did:
            return
        await asyncio.sleep(1.0 if did else 3.0)


async def main(a) -> int:
    day = datetime.now().strftime("%Y%m%d-%H%M")
    d = ROOT / "event" / "rec" / (a.session or day)
    tr = Transcript(d / "transcript.jsonl")
    stop = asyncio.Event()

    proc = None
    if not a.transcribe_only:
        proc = await record(d, a.device)
        print(f"録音中: {d}")
        print("  Ctrl-C で止めます。**部屋の外には出しません**\n")

    task = asyncio.ensure_future(transcribe_loop(d, tr, stop))
    try:
        if proc:
            await proc.wait()
        else:
            stop.set()
        await task
    except (KeyboardInterrupt, asyncio.CancelledError):
        pass
    finally:
        if proc and proc.returncode is None:
            proc.terminate()
            try:
                await asyncio.wait_for(proc.wait(), timeout=5)
            except asyncio.TimeoutError:
                proc.kill()
        stop.set()
        try:
            await asyncio.wait_for(task, timeout=600)
        except (asyncio.TimeoutError, asyncio.CancelledError):
            pass
    print(f"\n  {len(tr.lines())} 行  → {tr.path}")
    print(f"  素材にする: ./.venv/bin/python scripts/highlights.py {d.name}")
    return 0


if __name__ == "__main__":
    p = argparse.ArgumentParser(description="当日の音声を録って文字起こしする")
    p.add_argument("--device", default="0", help="マイク番号（--list で確認）")
    p.add_argument("--list", action="store_true", help="マイクを一覧する")
    p.add_argument("--session", help="保存先の名前（既定は日時）")
    p.add_argument("--transcribe-only", action="store_true",
                   help="録音せず、たまっている塊だけ起こす")
    a = p.parse_args()
    if a.list:
        list_devices()
        raise SystemExit(0)
    raise SystemExit(asyncio.run(main(a)))
