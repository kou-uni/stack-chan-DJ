#!/usr/bin/env python3
"""スタックチャンの顔を、本家 m5stack-avatar の描画コードを移植して生成する。

    ./.venv/bin/python app/avatar/make_faces.py --face 1.0   # 本家の寸法そのまま
    ./.venv/bin/python app/avatar/make_faces.py --face 1.9   # 比率はそのままで大きく
    ./.venv/bin/python app/avatar/pack_avatar.py             # → avatar_layered.raw

## なぜ自前で作るのか

ファーム同梱の `avatar_images.cc` は **1×1の黒い点のプレースホルダ**。絵が入っていない。

## 「ソースからそのまま」持ってきている

本家 stack-chan/m5stack-avatar（MIT）には**画像が無く、描画コードだけ**がある。
なので絵を真似るのではなく、**コードを移植した**。参照したのは:

    src/faces/FaceTemplates.hpp  SimpleFace の配置と寸法
    src/Eyes.cpp                 EllipseEye::draw   目の形と表情ごとの削り方
    src/Mouths.cpp               RectMouth::draw    口（楕円ではなく長方形）

SimpleFace の実測値（320×240 上）:

    右目 中心(90, 93)  EllipseEye(16,16) → fillEllipse の半径は 8
    左目 中心(230, 96) 同上
    口   中心(163,148) RectMouth(minW=50, maxW=90, minH=4, maxH=60)
    眉   height=0 なので描かれない

**左右の目の y が 93/96、口の x が 163（中心160から3px右）とずれている。**
この非対称が表情の正体。揃えると無機質になるので、拡大しても崩れは保つ。

## にじみについて（消せない分がある）

ファームは 160×120 の素材を `lv_image_set_scale(512)` で2倍にするが、
**LVGL の補間を切っていない**（`lv_image_set_antialias` を呼んでいない）。
つまり拡大時に必ず1〜2ピクセルの滲みが乗る。ファームを再ビルドしない限り消せない。

→ **細い要素を作らないことが唯一の対策。**
   8px の目に 2px の滲みは致命傷だが、46px の目なら輪郭が少し柔らかいだけになる。
   `--face` で比率を保ったまま拡大できるようにしてあるのはこのため。
"""
from __future__ import annotations

import argparse
from pathlib import Path

try:
    from PIL import Image, ImageDraw
except ImportError:
    raise SystemExit("./.venv/bin/pip install Pillow")

OUT_W, OUT_H = 160, 120
SS = 8                        # 内部の描画倍率
W, H = OUT_W * SS, OUT_H * SS

BG = (0, 0, 0)
FG = (255, 255, 255)
BLUSH = (226, 88, 80)

# ── SimpleFace の実測値（320×240 基準）──
EYE_W = EYE_H = 16            # EllipseEye(16, 16) は幅・高さ
EYE_R_POS = (90, 93)          # 右目 (x, y)
EYE_L_POS = (230, 96)         # 左目
MOUTH_POS = (163, 148)
M_MIN_W, M_MAX_W = 50, 90
M_MIN_H, M_MAX_H = 4, 60

ORDER = (
    ["idle", "happy", "thinking", "sad", "surprised", "embarrassed"]
    + ["eyes_open", "eyes_half", "eyes_closed"]
    + ["mouth_closed", "mouth_half", "mouth_open", "mouth_e", "mouth_u"]
)

FACE = 1.0     # パーツの大きさの倍率
MOUTH = 1.0    # 口だけの倍率。★目と同じ倍率で拡大すると口が画面の半分を覆う
               #   （本家の口は開いたとき60pxあるので、2倍で120px＝画面の半分）
USE_EFFECT = True   # 表情ごとの漫画マーク（Effect.h の移植）を焼き込むか
SPREAD = 1.0   # 画面中心からの距離の倍率。★大きさと位置は別に扱う。
               #   一緒に拡大すると、目が大きくなると同時に外へ飛んで画面から出る。


def px(v: float) -> float:
    """320×240 の座標を、内部キャンバスの座標に直す。"""
    return v / 2 * SS


def about(v: float, center: float) -> float:
    """画面中心 center からの距離を SPREAD 倍する。非対称のズレはそのまま保たれる。"""
    return center + (v - center) * SPREAD


def eye(d, pos, *, expression="neutral", is_left=False, open_ratio=1.0, grow=1.0):
    """EllipseEye::draw の移植。座標名も本家に合わせてある。"""
    x = px(about(pos[0], 160))
    y = px(about(pos[1], 120))
    width_ = px(EYE_W) * FACE * grow
    height_ = px(EYE_H) * FACE * grow

    # 目を閉じているとき／Sleepy は、高さ4の横棒になる
    if open_ratio == 0 or expression == "sleepy":
        h = px(4) * FACE
        d.rectangle([x - width_ / 2, y - h / 2 + height_ / 4,
                     x + width_ / 2, y + h / 2 + height_ / 4], fill=FG)
        return

    # Happy は楕円を2枚と長方形で「上向きの弧」を切り出す
    if expression == "happy":
        base_y = y + height_ / 4
        th = px(4) * FACE
        d.ellipse([x - width_ / 2, base_y - (height_ / 4 + th),
                   x + width_ / 2, base_y + (height_ / 4 + th)], fill=FG)
        d.ellipse([x - (width_ / 2 - th), base_y + th - (height_ / 4 + th),
                   x + (width_ / 2 - th), base_y + th + (height_ / 4 + th)], fill=BG)
        d.rectangle([x - width_ / 2, base_y + th / 2,
                     x + width_ / 2 + 1, base_y + th / 2 + height_ / 4 + 1], fill=BG)
        return

    d.ellipse([x - width_ / 2, y - height_ / 2,
               x + width_ / 2, y + height_ / 2], fill=FG)

    x0, y0 = x - width_ / 2, y - height_ / 2
    x1 = x + width_ / 2
    if expression == "angry":
        x2 = x0 if is_left else x1
        d.polygon([(x0, y0), (x1, y0), (x2, y - height_ / 4)], fill=BG)
    elif expression == "sad":
        x2 = x1 if is_left else x0
        d.polygon([(x0, y0), (x1, y0), (x2, y - height_ / 4)], fill=BG)
    elif expression == "doubt":
        d.rectangle([x0, y0, x1, y - height_ / 4], fill=BG)


def mouth(d, open_ratio: float, *, width_scale=1.0):
    """RectMouth::draw の移植。楕円ではなく長方形。"""
    h = (M_MIN_H + (M_MAX_H - M_MIN_H) * open_ratio) * MOUTH
    w = (M_MIN_W + (M_MAX_W - M_MIN_W) * (1 - open_ratio)) * MOUTH * width_scale
    cx = px(about(MOUTH_POS[0], 160))
    cy = px(about(MOUTH_POS[1], 120))
    d.rectangle([cx - px(w) / 2, cy - px(h) / 2, cx + px(w) / 2, cy + px(h) / 2], fill=FG)


# ── Effect.h の移植 ──
# 本家は表情とは別に「漫画のマーク」を画面の隅に描くレイヤーを持っている。
# 目の削り方の差（8px）はこの解像度で滲みに負けるが、
# **独立した図形は絶対に見落とさない**ので、こちらの方が効く。
#
# 本家はマークの半径を呼吸に合わせて変える（r += r*0.4*offset）。
# こちらは静止画14枚を焼くだけなので、サイズは固定になる。

def _heart(d, x, y, r, color=FG):
    """drawHeartMark の移植。円2つ＋三角2つで作る。"""
    import math
    x, y, r = px(x), px(y), px(r)
    d.ellipse([x - r, y - r / 2, x, y + r / 2], fill=color)          # fillCircle(x-r/2, y, r/2)
    d.ellipse([x, y - r / 2, x + r, y + r / 2], fill=color)          # fillCircle(x+r/2, y, r/2)
    a = (math.sqrt(2) * r) / 4.0
    d.polygon([(x, y), (x - r / 2 - a, y + a), (x + r / 2 + a, y + a)], fill=color)
    d.polygon([(x, y + r / 2 + 2 * a), (x - r / 2 - a, y + a),
               (x + r / 2 + a, y + a)], fill=color)


def _sweat(d, x, y, r, color=FG):
    """drawSweatMark の移植。円＋上向きの三角。"""
    import math
    x, y, r = px(x), px(y), px(r)
    d.ellipse([x - r, y - r, x + r, y + r], fill=color)
    a = (math.sqrt(3) * r) / 2
    d.polygon([(x, y - r * 2), (x - a, y - r * 0.5), (x + a, y - r * 0.5)], fill=color)


def _anger(d, x, y, r, color=FG):
    """drawAngerMark の移植。太い十字を描いて内側を背景色で抜く＝井桁。"""
    x, y, r = px(x), px(y), px(r)
    t = px(2)
    d.rectangle([x - r / 3, y - r, x - r / 3 + (r * 2) / 3, y + r], fill=color)
    d.rectangle([x - r, y - r / 3, x + r, y - r / 3 + (r * 2) / 3], fill=color)
    d.rectangle([x - r / 3 + t, y - r, x - r / 3 + (r * 2) / 3 - t, y + r], fill=BG)
    d.rectangle([x - r, y - r / 3 + t, x + r, y - r / 3 + (r * 2) / 3 - t], fill=BG)


def _chill(d, x, y, r, color=FG):
    """drawChillMark の移植。長さの違う縦線3本＝落ち込み。"""
    x, y, r = px(x), px(y), px(r)
    # ★本家は幅3pxの線を r/2 間隔で3本引くが、160×120 に縮小すると塊になる。
    #   線を太く、間隔を広げて「線が3本」と読めるようにする。
    w = px(6)
    for dx, k in ((-r * 0.55, 0.55), (0, 0.8), (r * 0.55, 1.0)):
        d.rectangle([x + dx - w / 2, y, x + dx + w / 2, y + r * k], fill=color)


def _bubble(d, x, y, r, color=FG):
    """drawBubbleMark の移植。輪郭だけの円2つ＝寝ている泡。"""
    x, y, r = px(x), px(y), px(r)
    w = max(2.0, px(1.5))
    d.ellipse([x - r, y - r, x + r, y + r], outline=color, width=int(w))
    d.ellipse([x - r / 4 - r / 4, y - r / 4 - r / 4,
               x - r / 4 + r / 4, y - r / 4 + r / 4], outline=color, width=int(w))


# 表情 → マーク（本家 Effect::draw の switch そのまま。位置と大きさだけ調整）
#
# ★本家の値をそのまま使うと2つ壊れる。
#   ・汗 r=7 は、160×120 に縮小すると点にしかならない
#   ・落ち込み線(y=0) と 怒り(y=50) は、上端すぎて切れる
#   マークは「離れて見て分かる」ためのものなので、大きく・内側に寄せる。
#   形そのもの（円2つ＋三角2つ の心臓、井桁の怒り…）は移植のまま。
EFFECTS = {
    "happy":   (_heart,  272,  56, 20),
    "thinking":(_sweat,  278, 104, 15),   # 本家では Doubt
    "sad":     (_chill,  256,  36, 40),
    "_angry":  (_anger,  266,  74, 22),
    "_sleepy": (_bubble, 276,  52, 16),
}


def effect(d, name):
    if not USE_EFFECT:
        return
    e = EFFECTS.get(name)
    if e:
        fn, x, y, r = e
        fn(d, x, y, r)


def blush(d):
    """本家には無い、恥ずかしがる用の追加。目のすぐ外下に置く。"""
    ew = px(EYE_W) * FACE
    for pos, sx in ((EYE_R_POS, -1), (EYE_L_POS, +1)):
        cx = px(about(pos[0], 160)) + sx * ew * 1.1
        cy = px(about(pos[1], 120)) + ew * 1.0
        d.ellipse([cx - ew * 0.9, cy - ew * 0.58, cx + ew * 0.9, cy + ew * 0.58], fill=BLUSH)


def draw(name: str) -> Image.Image:
    im = Image.new("RGB", (W, H), BG)
    d = ImageDraw.Draw(im)
    R = dict(pos=EYE_R_POS, is_left=False)
    L = dict(pos=EYE_L_POS, is_left=True)
    both = lambda **kw: (eye(d, **R, **kw), eye(d, **L, **kw))

    if name in ("idle", "eyes_open", "mouth_closed"):
        both(); mouth(d, 0.0)
    elif name == "happy":
        both(expression="happy"); mouth(d, 0.30); effect(d, "happy")
    elif name == "thinking":
        both(expression="doubt"); mouth(d, 0.0); effect(d, "thinking")
    elif name == "sad":
        both(expression="sad"); mouth(d, 0.10); effect(d, "sad")
    elif name == "surprised":
        both(grow=1.35); mouth(d, 1.0)
    elif name == "embarrassed":
        blush(d); both(expression="happy"); mouth(d, 0.18); effect(d, "happy")
    elif name == "eyes_half":
        both(expression="sleepy"); mouth(d, 0.0)
    elif name == "eyes_closed":
        both(open_ratio=0.0); mouth(d, 0.0)
    elif name == "mouth_half":
        both(); mouth(d, 0.5)
    elif name == "mouth_open":
        both(); mouth(d, 1.0)
    elif name == "mouth_e":
        both(); mouth(d, 0.40, width_scale=1.45)
    elif name == "mouth_u":
        both(); mouth(d, 0.75, width_scale=0.55)
    # ── 見比べ用（14枚には入らない）──
    elif name == "_angry":
        both(expression="angry"); mouth(d, 0.10); effect(d, "_angry")
    elif name == "_sleepy":
        both(expression="sleepy"); mouth(d, 0.0); effect(d, "_sleepy")
    else:
        raise SystemExit(f"未知のフレーム: {name}")
    return im


def crisp(im: Image.Image) -> Image.Image:
    """縮小したあと中間色を捨てる。

    ★「一番近い色」で振り分けてはいけない。白と黒の中間の灰色は、
      距離で測ると BLUSH に一番近くなり、口の縁が赤く滲む（実際そうなった）。
      赤みを先に判定し、残りは明度だけで白黒に分ける。
    """
    small = im.resize((OUT_W, OUT_H), Image.LANCZOS)
    p = small.load()
    for y in range(OUT_H):
        for x in range(OUT_W):
            r, g, b = p[x, y]
            if r - max(g, b) > 40:
                p[x, y] = BLUSH
            else:
                p[x, y] = FG if (r * 299 + g * 587 + b * 114) // 1000 >= 128 else BG
    return small


def main() -> int:
    global FACE, MOUTH, SPREAD, USE_EFFECT
    ap = argparse.ArgumentParser(description="本家の描画コードを移植して顔を作る")
    ap.add_argument("--out", type=Path, default=Path(__file__).parent / "frames")
    ap.add_argument("--face", type=float, default=1.0,
                    help="目と口の大きさ。1.0=本家そのまま")
    ap.add_argument("--no-effect", action="store_true", help="漫画マークを焼き込まない")
    ap.add_argument("--mouth", type=float, default=1.0,
                    help="口の大きさ。目と別にする（同じにすると口が画面を覆う）")
    ap.add_argument("--spread", type=float, default=1.0,
                    help="画面中心からの距離。1.0=本家の配置のまま")
    ap.add_argument("--single", help="この名前の1枚だけ 320×240 で書き出す")
    ap.add_argument("--sheet", action="store_true", help="全14枚を並べる")
    a = ap.parse_args()
    FACE = a.face
    USE_EFFECT = not a.no_effect
    MOUTH = a.mouth
    SPREAD = a.spread

    if a.single:
        out = Path(__file__).parent / f"single_{a.single}_{a.face:g}.png"
        crisp(draw(a.single)).resize((OUT_W * 2, OUT_H * 2), Image.NEAREST).save(out)
        print(out); return 0

    a.out.mkdir(parents=True, exist_ok=True)
    for i, name in enumerate(ORDER):
        crisp(draw(name)).save(a.out / f"{i:02d}_{name}.png")
    print(f"14枚（--face {a.face:g}）: {a.out}")

    if a.sheet:
        Z = 2
        sheet = Image.new("RGB", (OUT_W * Z * 5, OUT_H * Z * 3), (34, 38, 44))
        for i, name in enumerate(ORDER):
            im = Image.open(a.out / f"{i:02d}_{name}.png").resize((OUT_W * Z, OUT_H * Z), Image.NEAREST)
            sheet.paste(im, ((i % 5) * OUT_W * Z, (i // 5) * OUT_H * Z))
        sheet.save(Path(__file__).parent / "preview.png")
        print("並べた画像: preview.png")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
