# -*- coding: utf-8 -*-
"""NFC 受付 — カードをかざすと名前を呼んで挨拶する。仕様は tests/test_nfc.py。

## 作り（2026-09-26）

    M5Stack RFID 2 Unit（WS1850S）── Grove Port A（I2C 0x28）── 実機
                                                                  │ i2c_write / i2c_write_read（MCP）
                                                                  ▼
    Mac:  Rc522（読む） → Greeter（誰か・何回目か） → NfcReactor（顔・光・声）

★**ファームは触らない。** ファームには Port A を叩く汎用 I2C ツールが既にある。
  実機は UID を返すだけで、**名前・回数・挨拶は全部 Mac 側**（ESP32 は薄く保つ）。
  3日前に焼き直さずに済む。

★**名前はここ、回数もここ。** vault のノート（名前はカードに）から変えた。
  Mac から I2C を叩く以上、Mac が落ちれば UID も読めない。カードに名前を書いても
  救えないので、**運ぶのは1ファイル（guests.toml）**に寄せた。

★**回数は残す、名前は配らない。** 来訪記録は event/rec/（git に入らない）。
"""
from __future__ import annotations

import asyncio
import json
import random
import time
from dataclasses import dataclass
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
GUESTS_PATH = ROOT / "event" / "rec" / "guests.toml"     # ★人名。git に入れない
VISITS_PATH = ROOT / "event" / "rec" / "visits.jsonl"

# ── MFRC522 / WS1850S のレジスタ（I2C はレジスタ番号そのまま）──
CommandReg, ComIEnReg, DivIEnReg, ComIrqReg, DivIrqReg, ErrorReg = 0x01, 0x02, 0x03, 0x04, 0x05, 0x06
FIFODataReg, FIFOLevelReg, ControlReg, BitFramingReg, CollReg = 0x09, 0x0A, 0x0C, 0x0D, 0x0E
ModeReg, TxModeReg, RxModeReg, TxControlReg, TxASKReg = 0x11, 0x12, 0x13, 0x14, 0x15
CRCResultRegH, CRCResultRegL = 0x21, 0x22
TModeReg, TPrescalerReg, TReloadRegH, TReloadRegL = 0x2A, 0x2B, 0x2C, 0x2D
VersionReg = 0x37

PCD_Idle, PCD_CalcCRC, PCD_Transceive, PCD_SoftReset = 0x00, 0x03, 0x0C, 0x0F
PICC_REQA, PICC_SEL_CL1, PICC_SEL_CL2 = 0x26, 0x93, 0x95

I2C_ADDR = 0x28
I2C_SPEED = 100_000          # ★ファーム内のメモ: 400k で応答しない Unit があった。100k が M5 の既定


class BusError(RuntimeError):
    pass


class McpBus:
    """実機の Port A を、MCP の I2C ツールで叩く。"""

    def __init__(self, gw, addr: int = I2C_ADDR, speed: int = I2C_SPEED):
        self.gw, self.addr, self.speed = gw, addr, speed

    @staticmethod
    def unpack(res) -> list[int]:
        # ★gw.call は MCP の CallToolResult を返す。中身は content[0].text の JSON 文字列
        #   （2026-09-26 実機で判明。dict だと思い込んでいた）
        content = getattr(res, "content", None)
        if content:
            res = "".join(getattr(c, "text", "") for c in content)
        if isinstance(res, str):
            try:
                res = json.loads(res)
            except ValueError as exc:
                raise BusError(f"読めない返事: {res[:80]}") from exc
        if not isinstance(res, dict) or not res.get("ok"):
            raise BusError(str((res or {}).get("error", res)))
        return [int(b) for b in res.get("bytes", [])]

    async def write(self, reg: int, data: list[int]) -> None:
        res = await self.gw.call("i2c_write", addr=self.addr, bytes=[reg, *data],
                                 scl_speed_hz=self.speed)
        self.unpack(res if isinstance(res, (dict, str)) else {"ok": True})

    async def read(self, reg: int, n: int = 1) -> list[int]:
        res = await self.gw.call("i2c_write_read", addr=self.addr, write_bytes=[reg],
                                 n_bytes=n, scl_speed_hz=self.speed)
        return self.unpack(res)


class Rc522:
    """WS1850S を MFRC522 として扱う。**返すのは UID の16進だけ。**

    ★往復（MCP → Wi-Fi → I2C）が1回あたり数十ms。**回数を数えて設計する。**
      カードが無いときの1周は 9 往復以内（試験で固定）。
    """

    def __init__(self, bus, timer_wait_s: float = 0.03):
        self.bus = bus
        self.timer_wait_s = timer_wait_s
        self.version: int | None = None

    async def init(self) -> int:
        b = self.bus
        await b.write(CommandReg, [PCD_SoftReset])
        await asyncio.sleep(0.05)
        await b.write(TModeReg, [0x8D])           # タイマ自動開始
        await b.write(TPrescalerReg, [0x3E])
        await b.write(TReloadRegH, [0x00])
        await b.write(TReloadRegL, [30])          # ≈ 25ms で TimerIRq（応答なし）
        await b.write(TxASKReg, [0x40])           # 100% ASK
        await b.write(ModeReg, [0x3D])            # CRC 初期値 0x6363
        cur = (await b.read(TxControlReg))[0]
        if cur & 0x03 != 0x03:
            await b.write(TxControlReg, [cur | 0x03])   # アンテナ ON
        self.version = (await b.read(VersionReg))[0]
        return self.version

    async def _transceive(self, data: list[int], bits: int = 0) -> list[int] | None:
        """1往復。応答が無ければ None。"""
        b = self.bus
        await b.write(BitFramingReg, [bits & 0x07])
        await b.write(ComIrqReg, [0x7F])          # 割り込みフラグを消す
        await b.write(FIFOLevelReg, [0x80])       # FIFO を空に
        await b.write(FIFODataReg, data)
        await b.write(CommandReg, [PCD_Transceive])
        await b.write(BitFramingReg, [0x80 | (bits & 0x07)])   # StartSend
        await asyncio.sleep(self.timer_wait_s)    # ★何度も覗かず、タイマ分だけ1回待つ
        irq = (await b.read(ComIrqReg))[0]
        if irq & 0x01 and not irq & 0x30:         # TimerIRq だけ ＝ 誰もいない
            return None
        if not irq & 0x30:
            await asyncio.sleep(self.timer_wait_s)
            irq = (await b.read(ComIrqReg))[0]
            if not irq & 0x30:
                return None
        err = (await b.read(ErrorReg))[0]
        if err & 0x13:                            # BufferOvfl / ParityErr / ProtocolErr
            return None
        n = (await b.read(FIFOLevelReg))[0]
        if n == 0:
            return []
        return await b.read(FIFODataReg, n)

    async def _crc(self, data: list[int]) -> list[int]:
        b = self.bus
        await b.write(CommandReg, [PCD_Idle])
        await b.write(DivIrqReg, [0x04])
        await b.write(FIFOLevelReg, [0x80])
        await b.write(FIFODataReg, data)
        await b.write(CommandReg, [PCD_CalcCRC])
        for _ in range(5):
            if (await b.read(DivIrqReg))[0] & 0x04:
                break
            await asyncio.sleep(0.005)
        await b.write(CommandReg, [PCD_Idle])
        lo = (await b.read(CRCResultRegL))[0]
        hi = (await b.read(CRCResultRegH))[0]
        return [lo, hi]

    @staticmethod
    def _bcc_ok(five: list[int]) -> bool:
        x = 0
        for v in five[:4]:
            x ^= v
        return len(five) == 5 and x == five[4]

    async def poll_uid(self) -> str | None:
        """カードがあれば UID（16進小文字）。無ければ None。"""
        atqa = await self._transceive([PICC_REQA], bits=7)
        if atqa is None:
            return None
        part = await self._transceive([PICC_SEL_CL1, 0x20])
        if not part or not self._bcc_ok(part):
            return None
        if part[0] != 0x88:                       # 4バイト UID
            return bytes(part[:4]).hex()
        # 7バイト UID: CL1 を select してから CL2 を読む
        sel = [PICC_SEL_CL1, 0x70, *part[:5]]
        sel += await self._crc(sel)
        if await self._transceive(sel) is None:
            return None
        part2 = await self._transceive([PICC_SEL_CL2, 0x20])
        if not part2 or not self._bcc_ok(part2):
            return None
        return bytes(part[1:4] + part2[:4]).hex()


# ── 誰か・何回目か ────────────────────────────────────────
class Guests:
    """UID → 名前。**運ぶのはこの1ファイルだけ**（event/rec/guests.toml）。"""

    def __init__(self, table: dict[str, str]):
        self.table = {k.lower(): v for k, v in table.items()}

    @classmethod
    def from_dict(cls, d: dict) -> "Guests":
        return cls(dict(d))

    @classmethod
    def load(cls, path: Path = GUESTS_PATH) -> "Guests":
        if not path.exists():
            return cls({})
        import tomllib
        with path.open("rb") as f:
            data = tomllib.load(f)
        return cls({str(k): str(v) for k, v in (data.get("guests") or {}).items()})

    def name(self, uid: str) -> str | None:
        return self.table.get(uid.lower())


@dataclass
class Greeting:
    uid: str
    name: str | None
    count: int
    line: str


# ★同じ入力に同じ反応を返すものは、何回目かで存在感が消える
LINES_FIRST = ["いらっしゃい、{name}！", "{name}、来てくれてありがとう！", "やあ、{name}！"]
LINES_AGAIN = ["また来たね、{name}！", "おかえり、{name}！", "{name}、待ってたよ！"]
LINES_MANY = ["{name}、今日は{count}回目だね！", "{name}、{count}回目！常連さんだ", "{name}、また会えたね。{count}回目！"]
LINES_UNKNOWN = ["はじめまして！名前、まだ聞いてないや", "そのカード、まだ知らないなあ。だれ？", "こんにちは！はじめての人だ"]


class Greeter:
    """UID から、何と言うかを決める。**実機も時計も触らない**ので試験できる。"""

    def __init__(self, guests: Guests, log_path: Path = VISITS_PATH, debounce_s: float = 6.0):
        self.guests, self.log_path, self.debounce_s = guests, log_path, debounce_s
        self.counts: dict[str, int] = {}
        self._last: dict[str, float] = {}
        self._last_line: str | None = None
        self._load()

    def _load(self) -> None:
        if not self.log_path.exists():
            return
        for line in self.log_path.read_text(encoding="utf-8").splitlines():
            try:
                row = json.loads(line)
                self.counts[row["uid"]] = self.counts.get(row["uid"], 0) + 1
            except (ValueError, KeyError):
                continue

    def greet(self, uid: str, now: float | None = None) -> Greeting | None:
        now = time.time() if now is None else now
        uid = uid.lower()
        last = self._last.get(uid)
        if last is not None and now - last < self.debounce_s:
            self._last[uid] = now                  # ★かざしたままなら、離すまで数えない
            return None
        self._last[uid] = now
        name = self.guests.name(uid)
        count = self.counts.get(uid, 0) + 1
        self.counts[uid] = count
        if name is None:
            pool = LINES_UNKNOWN
        elif count == 1:
            pool = LINES_FIRST
        elif count == 2:
            pool = LINES_AGAIN
        else:
            pool = LINES_MANY
        rest = [l for l in pool if l != self._last_line] or list(pool)
        tpl = random.choice(rest)
        self._last_line = tpl
        line = tpl.format(name=f"{name}さん" if name else "", count=count).replace("さんさん", "さん")
        self._remember(uid, name, count, now)
        return Greeting(uid, name, count, line)

    def _remember(self, uid, name, count, now) -> None:
        try:
            self.log_path.parent.mkdir(parents=True, exist_ok=True)
            with self.log_path.open("a", encoding="utf-8") as f:
                f.write(json.dumps({"at": now, "uid": uid, "name": name, "count": count},
                                   ensure_ascii=False) + "\n")
        except OSError as exc:
            print(f"★ 来訪を残せませんでした: {exc}")


# ── 出す ────────────────────────────────────────────────
class NfcReactor:
    """挨拶を、顔・光・声にする。**出すだけ。**（touch.py と同じ型）"""

    def __init__(self, presence, led=None, face_s: float = 3.0, quiet: bool = False,
                 speaker_id: int = 14):
        self.presence, self.led, self.face_s, self.quiet = presence, led, face_s, quiet
        self.speaker_id = speaker_id

    async def react(self, g: Greeting, gw=None, busy: bool = False) -> None:
        if not self.quiet:
            who = g.name or "（未登録）"
            print(f"    ▣ NFC {g.uid} {who} {g.count}回目 「{g.line}」")
        self.presence.overlay("nfc", "happy", self.face_s)
        if self.led is not None:
            self.led.poke("nfc")
        if gw is not None and not busy and g.line:
            try:
                await gw.call("say", text=g.line, speaker_id=self.speaker_id)
            except Exception:
                pass                                # ★喋れなくても顔と光は出ている


class NfcMixin:
    """console 側の入口。**問い合わせ型**（タッチと違い、実機は押してこない）。"""

    async def nfc_loop(self):
        args = self.args
        bus = McpBus(self.gw, addr=args.nfc_addr, speed=args.nfc_speed)
        rc = Rc522(bus)
        try:
            ver = await rc.init()
            print(f"    ▣ NFC リーダー 0x{args.nfc_addr:02x} 版 0x{ver:02x}"
                  f"（{args.nfc_poll_s}秒ごと）")
        except Exception as exc:                    # noqa: BLE001
            print(f"    ★ NFC リーダーが見つかりません（Port A 0x{args.nfc_addr:02x}）: {exc}")
            return                                  # ★無くても他は動かす
        greeter = Greeter(Guests.load(), debounce_s=args.nfc_debounce_s)
        reactor = NfcReactor(self.presence, led=self.led, face_s=args.nfc_face_s,
                             quiet=args.quiet)
        if not greeter.guests.table:
            print(f"    ▲ 名簿が空です: {GUESTS_PATH}（scripts/nfc_enroll.py で登録）")
        while True:
            try:
                uid = await rc.poll_uid()
                if uid:
                    g = greeter.greet(uid)
                    if g:
                        busy = bool(getattr(self.presence, "talk", None))
                        await reactor.react(g, self.gw, busy=busy)
            except Exception as exc:                # noqa: BLE001
                if not args.quiet:
                    print(f"    ★ NFC: {type(exc).__name__}: {str(exc)[:60]}")
                await asyncio.sleep(1.0)
            await asyncio.sleep(args.nfc_poll_s)
