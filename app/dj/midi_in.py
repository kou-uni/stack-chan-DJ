#!/usr/bin/env python3
"""DDJ-FLX2 からの MIDI 入力。つまみとボタンを解釈する。

console.py の Console から切り出した mixin。**中身は1行も変えていない。**
Console がこれらを継承して1つのクラスになる。
"""
from __future__ import annotations

import asyncio
import json
import math
import random
import time

import mido

from constants import (ROOT, MAPPING, YAW_MIN, YAW_MAX, PITCH_REL_MIN,
                       PITCH_REL_MAX, MODE_IDLE, MODE_DJ, MODE_LABEL,
                       MODE_FACE, MODE_ORDER, _scale)  # noqa: F401


class MidiMixin:
    # ── MIDI を読む
    def _find_midi(self):
        names = mido.get_input_names()
        hint = self.cfg.get("port_hint", "DDJ")
        return next((n for n in names if hint.lower() in n.lower()),
                    names[0] if names else None)

    async def midi_loop(self):
        """MIDI を読み続ける。**挿し直しに追従する。**

        ★以前は起動時に一度だけ探していた。
          DJ機材を後から挿すと、console を立ち上げ直すまで効かなかった。
          抜き差しは現場で普通に起きる。**順番を気にしなくていいのが正しい。**
        """
        announced = False
        while True:
            port = self._find_midi()
            if not port:
                if not announced:
                    print("⚠ MIDI入力が無い。挿されたら自動で拾います")
                    announced = True
                await asyncio.sleep(3.0)
                continue

            print(f"MIDI: {port}")
            for slot, c in self.ctl.items():
                kind = "CC" if c["kind"] == "cc" else "Note"
                print(f"  {c['label']:<22} {kind} ch{c['ch']} #{c['num']}")
            print()
            announced = False

            try:
                with mido.open_input(port) as inport:
                    while True:
                        for msg in inport.iter_pending():
                            await self._handle(msg)
                        await asyncio.sleep(0.002)
                        if port not in mido.get_input_names():
                            raise OSError("MIDI が抜かれました")
            except asyncio.CancelledError:
                raise
            except Exception as exc:
                print(f"⚠ MIDI が切れました（{exc}）。挿し直しを待ちます")
                await asyncio.sleep(2.0)

    async def _handle(self, msg):
        if msg.type == "control_change":
            slot = self.cc.get((msg.channel, msg.control))
            if slot == "yaw":
                self.pose.yaw = _scale(msg.value, YAW_MIN, YAW_MAX)
                self.pose.touch()
                await self.wake_servos()
                self._show_pose("yaw")
            elif slot == "pitch":
                self.pose.pitch = _scale(msg.value, PITCH_REL_MIN, PITCH_REL_MAX)
                self.pose.touch()
                await self.wake_servos()
                self._show_pose("pitch")
        elif msg.type == "note_on" and msg.velocity > 0:
            # ★ON と OFF を別のボタンに分ける。トグルにしない。
            #   MASTER は押しっぱなしで使う人がいるので、トグルだと事故る。
            #   OFF 専用なら、何度押しても、点けても消しても OFF になるだけ。
            if (msg.channel, msg.note) == (self.args.off_ch, self.args.off_note):
                if self.mode != MODE_IDLE:
                    await self.set_mode(MODE_IDLE, why="MASTER")
                return
            # ★PLAY は ON にするだけ。トグルにしない。
            #   DJはセット中に何度も押すので、押すたびに切り替わったら使えない。
            #   OFF はモードパッドか、曲が来ない時間による自動復帰で行う。
            if (msg.channel, msg.note) == (self.args.play_ch, self.args.play_note):
                if self.mode != MODE_DJ:
                    await self.set_mode(MODE_DJ, why="PLAY")
                self._silent_since = None
                return
            slot = self.note.get((msg.channel, msg.note))
            if slot:
                face = self.ctl[slot].get("avatar", "idle")
                print(f"  ▶ {self.ctl[slot]['label']} → {face}")
                await self.show_face(face, slot)
            else:
                # 未割当のボタン。PLAY などの番号を調べるのに使う
                print(f"  ? 未割当のボタン: Note ch{msg.channel} #{msg.note}"
                      f"   → --play-ch {msg.channel} --play-note {msg.note} で PLAY にできます")
