#!/usr/bin/env python3
"""カメラで顔を探して、その人の方を向く。

console.py の Console から切り出した mixin。**中身は1行も変えていない。**
Console がこれらを継承して1つのクラスになる。
"""
from __future__ import annotations

import asyncio
import json
import math
import random
import time

from constants import (ROOT, MAPPING, YAW_MIN, YAW_MAX, PITCH_REL_MIN,
                       PITCH_REL_MAX, MODE_IDLE, MODE_DJ, MODE_LABEL,
                       MODE_FACE, MODE_ORDER, _scale)  # noqa: F401


class VisionMixin:
    # ── ① 客と目を合わせる
    async def face_loop(self):
        """本体のカメラで顔を探し、いちばん大きく写っている人（＝近い人）の方を向く。

        「自分に向かって踊ってくれた」は、群衆の中でも個人に届く体験になる。

        ★カメラは踊りを止めてから撮る。動きながらだとブレる。
          「聴き入る」と同じで、**止まる理由が増えるだけ**なので、
          撮影も振り付けの一部（客席を見渡す仕草）として見せる。
        """
        import cv2, numpy as np, base64
        casc = cv2.CascadeClassifier(str(ROOT / "app" / "vision" /
                                         "haarcascade_frontalface_default.xml"))
        if casc.empty():
            print("⚠ 顔検出器を読めません。カメラ機能は無効です")
            return
        while True:
            await asyncio.sleep(self.args.face_every_s)
            if self.mode != MODE_DJ or not self.pose.dance:
                continue

            self.pose.hold = (0, 0)                  # 正面で止めて撮る
            await asyncio.sleep(0.45)
            r = await self.gw.call("take_photo", question="客席")
            img = None
            for b in getattr(r, "content", []) or []:
                if getattr(b, "type", "") == "image" and getattr(b, "data", None):
                    buf = np.frombuffer(base64.b64decode(b.data), np.uint8)
                    img = cv2.imdecode(buf, cv2.IMREAD_GRAYSCALE)
            self.pose.hold = None
            if img is None:
                continue

            faces = casc.detectMultiScale(img, 1.2, 4, minSize=(24, 24))
            if len(faces) == 0:
                continue
            # いちばん大きい顔＝いちばん近い人
            x, y, w, h = max(faces, key=lambda f: f[2] * f[3])
            cx = (x + w / 2) / img.shape[1]          # 0..1（左→右）
            # カメラの画角ぶんだけ首を向ける
            yaw = (cx - 0.5) * 2 * self.args.camera_fov_deg
            print(f"  ◉ 客を見つけた（{len(faces)}人 / 一番近い人は {yaw:+.0f}°）")
            await self.look_at(yaw)

    async def look_at(self, yaw: float):
        """その人の方を向いて、目を合わせて、頷いてから踊りに戻る。"""
        yaw = max(-70, min(70, yaw))
        self.pose.hold = (yaw, 0)
        self.presence.overlay("face", "happy", seconds=2.0)
        await asyncio.sleep(0.5)
        for pit in (20, 0, 18, 0):                   # 「見つけたよ」の頷き
            self.pose.hold = (yaw, pit)
            await asyncio.sleep(0.10)
        self.pose.hold = None
