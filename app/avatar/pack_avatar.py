#!/usr/bin/env python3
"""自作の顔を load_avatar_set 用の raw RGB565 に固める。

    ./.venv/bin/python app/avatar/pack_avatar.py --init      # 雛形14枚を書き出す
    ./.venv/bin/python app/avatar/pack_avatar.py             # frames/ を固める

出力を gateway に渡す:

    load_avatar_set(archive_path="…/app/avatar/avatar_layered.raw", mode="layered")

## 仕様（ソースで確認済み）

- 1フレーム = **160×120 の RGB565**（38,400 バイト）
- layered = **14枚**（顔6 + 目3 + 口5）= 537,600 バイト
- matrix  = 90枚（6×3×5）= 3,456,000 バイト
- **RGB565 にアルファは無い。** どの1枚も「画面全体の完成画」でなければならない
  → 目や口だけを透過で書き出すと、そのフレームが選ばれた瞬間に崩れた顔が出る

## 作画の注意（同梱の avatar-authoring-notes.md より）

- **全フレームを同じジオメトリで描く。** 顔の位置や目の高さが数ピクセルずれるだけで、
  切り替わるたびに「跳ねて」見える。1枚のマスターから派生させること
- パーツは作画ツールの中ではレイヤーで持ち、**書き出し時に合成して平らにする**。
  合成済みの絵から切り抜くと、前の背景の縁が薄い輪郭として残る
- matrix（3.3MB）は Wi-Fi 省電力が効いていると転送に2〜3分かかることがある。
  **まずは layered（525KB）で試す**
"""
from __future__ import annotations

import argparse
import struct
import sys
from pathlib import Path

try:
    from PIL import Image, ImageDraw
except ImportError:
    sys.exit("./.venv/bin/pip install Pillow")

W, H = 160, 120
FRAME_BYTES = W * H * 2

# layered の並び。顔6 → 目3 → 口5
LAYERED = (
    [f"face_{n}" for n in ("idle", "happy", "thinking", "sad", "surprised", "embarrassed")]
    + [f"eyes_{n}" for n in ("open", "half", "closed")]
    + [f"mouth_{n}" for n in ("closed", "half", "open", "e", "u")]
)


def to_rgb565(img: Image.Image) -> bytes:
    """RGB を RGB565 リトルエンディアンに詰める。"""
    if img.size != (W, H):
        raise SystemExit(f"寸法が違う: {img.size} → {W}x{H} にしてください")
    out = bytearray()
    for r, g, b in list(img.convert("RGB").getdata()):
        out += struct.pack("<H", ((r & 0xF8) << 8) | ((g & 0xFC) << 3) | (b >> 3))
    return bytes(out)


def write_placeholders(d: Path) -> None:
    """差し替え前提の雛形。名前と用途が画面に出るので、取り違えを防げる。"""
    d.mkdir(parents=True, exist_ok=True)
    palette = {"face": (18, 22, 30), "eyes": (10, 30, 45), "mouth": (35, 15, 20)}
    for i, name in enumerate(LAYERED):
        kind = name.split("_")[0]
        img = Image.new("RGB", (W, H), palette[kind])
        dr = ImageDraw.Draw(img)
        dr.rectangle([2, 2, W - 3, H - 3], outline=(90, 110, 130))
        dr.text((8, 44), f"{i:02d}", fill=(220, 230, 240))
        dr.text((8, 60), name, fill=(150, 200, 240))
        img.save(d / f"{i:02d}_{name}.png")
    print(f"雛形を書き出しました: {d}  （14枚）")
    print("この14枚を差し替えてから、もう一度このスクリプトを実行してください。")


def pack(d: Path, out: Path) -> None:
    missing, blob = [], bytearray()
    for i, name in enumerate(LAYERED):
        hits = sorted(d.glob(f"{i:02d}_*.png")) or sorted(d.glob(f"{name}.png"))
        if not hits:
            missing.append(f"{i:02d}_{name}.png")
            continue
        blob += to_rgb565(Image.open(hits[0]))
    if missing:
        raise SystemExit("足りないフレーム:\n  " + "\n  ".join(missing))
    if len(blob) != 14 * FRAME_BYTES:
        raise SystemExit(f"サイズが合わない: {len(blob)} / 期待 {14 * FRAME_BYTES}")
    out.write_bytes(blob)
    print(f"書き出しました: {out}")
    print(f"  {len(blob):,} バイト（14フレーム × {FRAME_BYTES:,}）")
    print(f"\ngateway から:\n  load_avatar_set(archive_path=\"{out}\", mode=\"layered\")")


def main() -> int:
    ap = argparse.ArgumentParser(description="自作アバターを RGB565 に固める")
    ap.add_argument("--init", action="store_true", help="雛形14枚を書き出す")
    ap.add_argument("--frames", type=Path, default=Path(__file__).parent / "frames")
    ap.add_argument("--out", type=Path, default=Path(__file__).parent / "avatar_layered.raw")
    a = ap.parse_args()
    if a.init:
        write_placeholders(a.frames)
    else:
        pack(a.frames, a.out)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
