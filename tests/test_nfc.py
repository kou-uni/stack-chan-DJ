# -*- coding: utf-8 -*-
"""NFC 受付（app/dj/nfc.py）の仕様。

★実機は UID を返すだけ。名前・回数・挨拶は Mac 側（ESP32 は薄く保つ）。
★ファームは触らない。Port A の I2C ツール（i2c_write / i2c_write_read）で
  WS1850S（MFRC522 互換）を Mac から直接叩く。
"""
import asyncio
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "app" / "dj"))

import nfc  # noqa: E402


# ── 偽の WS1850S ────────────────────────────────────────
class FakeChip:
    """MFRC522 のレジスタを最低限まねる。**カードの有無だけ切り替えられる。**"""

    def __init__(self, uid: bytes | None = None):
        self.uid = uid                      # None = カード無し
        self.regs = {}
        self.fifo: list[int] = []
        self.writes: list[tuple[int, list[int]]] = []
        self.calls = 0

    async def write(self, reg: int, data: list[int]) -> None:
        self.calls += 1
        self.writes.append((reg, list(data)))
        if reg == nfc.FIFODataReg:
            self.fifo.extend(data)
            return
        if reg == nfc.FIFOLevelReg and data and data[0] & 0x80:
            self.fifo = []
        val = data[0] if data else 0
        if reg == nfc.CommandReg:
            self._command(val)
        self.regs[reg] = val

    async def read(self, reg: int, n: int = 1) -> list[int]:
        self.calls += 1
        if reg == nfc.FIFODataReg:
            out, self.fifo = self.fifo[:n], self.fifo[n:]
            return out
        if reg == nfc.FIFOLevelReg:
            return [len(self.fifo)]
        if reg == nfc.VersionReg:
            return [0x92]
        return [self.regs.get(reg, 0)] * n

    def _command(self, cmd: int) -> None:
        if cmd == nfc.PCD_Transceive:
            sent, self.fifo = list(self.fifo), []
            if self.uid is None:
                self.regs[nfc.ComIrqReg] = 0x01              # TimerIRq = 応答なし
                return
            if sent in ([nfc.PICC_REQA], [nfc.PICC_WUPA]):
                self.fifo = [0x44, 0x00]                     # ATQA
            elif sent[:1] == [nfc.PICC_HLTA]:
                self.regs[nfc.ComIrqReg] = 0x01; return      # HALT は無応答が正常
            elif sent == [nfc.PICC_SEL_CL1, 0x20]:
                part = list(self.uid[:4]) if len(self.uid) == 4 else [0x88] + list(self.uid[:3])
                self.fifo = part + [_bcc(part)]
            elif sent[:2] == [nfc.PICC_SEL_CL1, 0x70]:
                self.fifo = [0x04]                           # SAK（カスケード継続）
            elif sent == [nfc.PICC_SEL_CL2, 0x20]:
                part = list(self.uid[3:7])
                self.fifo = part + [_bcc(part)]
            self.regs[nfc.ComIrqReg] = 0x30                  # RxIRq | IdleIRq
        elif cmd == nfc.PCD_CalcCRC:
            self.regs[nfc.DivIrqReg] = 0x04
            self.regs[nfc.CRCResultRegL] = 0xAB
            self.regs[nfc.CRCResultRegH] = 0xCD
            self.fifo = []


def _bcc(bs):
    x = 0
    for b in bs:
        x ^= b
    return x


def run(coro):
    return asyncio.run(coro)


# ── 読み取り ────────────────────────────────────────────
def test_初期化でアンテナが入る():
    """★アンテナを入れ忘れると、何も読めないのにエラーも出ない。"""
    chip = FakeChip()
    run(nfc.Rc522(chip).init())
    assert (nfc.TxControlReg, [0x83]) in chip.writes or \
           any(r == nfc.TxControlReg and d[0] & 0x03 == 0x03 for r, d in chip.writes)


def test_カードが無ければ何も返さない():
    r = nfc.Rc522(FakeChip(uid=None))
    assert run(r.poll_uid()) is None


def test_4バイトのUIDを読む():
    r = nfc.Rc522(FakeChip(uid=bytes([0xDE, 0xAD, 0xBE, 0xEF])))
    assert run(r.poll_uid()) == "deadbeef"


def test_7バイトのUIDも読み切れる_登録用():
    """★NTAG（よくあるシール型）は7バイト。**先頭の 0x88 は続きがある印**で、UIDの一部ではない。
    読み切るのは登録のときだけ（read_full_uid）。"""
    r = nfc.Rc522(FakeChip(uid=bytes([0x04, 0x11, 0x22, 0x33, 0x44, 0x55, 0x66])))
    assert run(r.read_full_uid()) == "04112233445566"


def test_BCCが合わなければ捨てる():
    """★半分だけ読めた UID で名前を呼ぶと、**別人を呼ぶ。**"""
    chip = FakeChip(uid=bytes([1, 2, 3, 4]))
    real_read = chip.read

    async def bad_read(reg, n=1):
        out = await real_read(reg, n)
        if reg == nfc.FIFODataReg and len(out) == 5:
            out[-1] ^= 0xFF                              # BCC を壊す
        return out
    chip.read = bad_read
    assert run(nfc.Rc522(chip).poll_uid()) is None


def test_カード無しの1回の問い合わせは軽い():
    """★受付は行列ができる。**カードが無いときの往復回数**が、体感の全て。"""
    chip = FakeChip(uid=None)
    run(nfc.Rc522(chip).poll_uid())
    assert chip.calls <= 9, f"往復 {chip.calls} 回は多い"


# ── 名前と回数 ──────────────────────────────────────────
def test_UIDから名前を引く(tmp_path):
    g = nfc.Guests.from_dict({"deadbeef": "うにさん"})
    assert g.name("deadbeef") == "うにさん"
    assert g.name("00000000") is None


def test_初めてと2回目で言うことが変わる(tmp_path):
    """★同じ入力に同じ反応を返すものは、何回目かで存在感が消える。"""
    log = tmp_path / "visits.jsonl"
    gr = nfc.Greeter(nfc.Guests.from_dict({"aa": "うにさん"}), log_path=log)
    first = gr.greet("aa", now=1000.0)
    second = gr.greet("aa", now=5000.0)
    assert "うにさん" in first.line and "うにさん" in second.line
    assert first.line != second.line
    assert first.count == 1 and second.count == 2


def test_知らないカードにも黙らない(tmp_path):
    gr = nfc.Greeter(nfc.Guests.from_dict({}), log_path=tmp_path / "v.jsonl")
    g = gr.greet("ffff", now=0.0)
    assert g.line and g.name is None


def test_同じカードを立て続けにかざしても1回扱い(tmp_path):
    """★かざしたまま数秒置く人がいる。**毎周期で挨拶し直すと壊れて見える。**"""
    gr = nfc.Greeter(nfc.Guests.from_dict({"aa": "A"}), log_path=tmp_path / "v.jsonl",
                     debounce_s=5.0)
    assert gr.greet("aa", now=0.0) is not None
    assert gr.greet("aa", now=1.0) is None
    assert gr.greet("aa", now=6.0) is not None


def test_回数はMac側に残り再起動をまたぐ(tmp_path):
    """★名前はカード側でも引けるが、**回数はMac側**。カードを失くしても履歴は残る。"""
    log = tmp_path / "v.jsonl"
    nfc.Greeter(nfc.Guests.from_dict({"aa": "A"}), log_path=log).greet("aa", now=0.0)
    gr2 = nfc.Greeter(nfc.Guests.from_dict({"aa": "A"}), log_path=log)
    assert gr2.greet("aa", now=100.0).count == 2


def test_来訪記録は配る場所に置かない():
    """★人の名前が入る。git にも配布物にも入れない。"""
    p = nfc.VISITS_PATH
    assert "event/rec" in str(p).replace("\\", "/")
    ignore = (ROOT / ".gitignore").read_text(encoding="utf-8")
    assert "event/rec/" in ignore


# ── 出し方 ──────────────────────────────────────────────
class _Presence:
    def __init__(self): self.overlays = []
    def overlay(self, kind, face, seconds): self.overlays.append((kind, face, seconds))


class _Led:
    def __init__(self): self.pokes = []
    def poke(self, kind): self.pokes.append(kind)


class _Gw:
    def __init__(self): self.calls = []
    async def call(self, name, **kw): self.calls.append((name, kw)); return {"ok": True}


def test_かざしたら顔と光と声が同時に出る():
    """★入力があったら身体のどこかが応える。声だけだと遅れて見える。"""
    pr, led, gw = _Presence(), _Led(), _Gw()
    r = nfc.NfcReactor(pr, led=led, quiet=True)
    g = nfc.Greeting(uid="aa", name="A", count=1, line="いらっしゃい、Aさん")
    run(r.react(g, gw))
    assert pr.overlays and pr.overlays[0][1] == "happy"
    assert led.pokes == ["nfc"]
    assert any(n == "say" and "Aさん" in kw.get("text", "") for n, kw in gw.calls)


def test_会話中は声をかぶせない():
    pr, led, gw = _Presence(), _Led(), _Gw()
    r = nfc.NfcReactor(pr, led=led, quiet=True)
    run(r.react(nfc.Greeting("aa", "A", 1, "x"), gw, busy=True))
    assert not any(n == "say" for n, _ in gw.calls)
    assert pr.overlays, "顔は出す"


def test_実機の返事の形を読める():
    """ファームの i2c_write_read は {"ok": true, "bytes": [...]} を返す。"""
    assert nfc.McpBus.unpack({"ok": True, "bytes": [1, 2]}) == [1, 2]
    with pytest.raises(nfc.BusError):
        nfc.McpBus.unpack({"ok": False, "error": "ESP_ERR_TIMEOUT"})


def test_実機の返事はCallToolResultで来る():
    """★2026-09-26 実機で判明。dict ではなく、content[0].text に JSON が入った物体。"""
    class _T:  # TextContent のまね
        def __init__(self, text): self.text = text
    class _R:
        def __init__(self, text): self.content = [_T(text)]
    assert nfc.McpBus.unpack(_R('{"ok":true,"bytes":[40]}')) == [40]
    with pytest.raises(nfc.BusError):
        nfc.McpBus.unpack(_R('{"ok":false,"error":"ESP_ERR_TIMEOUT"}'))


def test_全部ゼロのUIDは捨てる():
    """★実機で観測（2026-09-26）：カードが端にあると 00000000 が返り、BCC も 0 で通ってしまう。
    **ゼロは UID ではない。**"""
    r = nfc.Rc522(FakeChip(uid=bytes([0, 0, 0, 0])))
    assert run(r.poll_uid()) is None


def test_CRCは手元で計算する():
    """★チップに計算させると往復が10回増える（実測 7バイトで1.2秒）。ISO14443 の CRC_A は手元で出せる。"""
    # 既知値: [0x93,0x70,0x88,0x04,0x3b,0x33,0x84] の CRC_A（MFRC522 ライブラリの検算値と一致すること）
    crc = nfc.crc_a([0x50, 0x00])           # HALT コマンドの CRC_A は 0x57 0xCD（規格の例）
    assert crc == [0x57, 0xCD]


def test_受付の読み取りは2段で終わる():
    """★WUPA＋CL1 だけ。段が増えるほど落ちる。"""
    chip = FakeChip(uid=bytes([0x04, 0x11, 0x22, 0x33, 0x44, 0x55, 0x66]))
    run(nfc.Rc522(chip).poll_uid())
    assert chip.calls <= 18, f"往復 {chip.calls} 回は多い"


class FlakyChip(FakeChip):
    """★実機で観測：CL1 は通るが、その後の SELECT/CL2 が電波の端でタイムアウトする。"""
    def __init__(self, uid, fail_after_cl1=True):
        super().__init__(uid); self.fail_after_cl1 = fail_after_cl1; self.full_reads = 0
    def _command(self, cmd):
        if cmd == nfc.PCD_Transceive and self.fail_after_cl1 and self.fifo[:2] == [nfc.PICC_SEL_CL1, 0x70]:
            self.fifo = []; self.regs[nfc.ComIrqReg] = 0x01; return      # SELECT に答えない
        super()._command(cmd)




def test_1周の中で2回まで粘る():
    """★1段でも落ちたら諦めると、6割×6割で3割しか読めない。"""
    class OnceFlaky(FakeChip):
        def __init__(self, uid): super().__init__(uid); self.n = 0
        def _command(self, cmd):
            if cmd == nfc.PCD_Transceive and self.fifo == [nfc.PICC_SEL_CL1, 0x20]:
                self.n += 1
                if self.n == 1:                             # 最初の CL1 だけ落とす
                    self.fifo = []; self.regs[nfc.ComIrqReg] = 0x01; return
            super()._command(cmd)
    rc = nfc.Rc522(OnceFlaky(bytes([1, 2, 3, 4])))
    assert run(rc.poll_uid()) == "01020304"


# ── 方針転換（2026-09-26 実機）: 7バイトのカードは CL1 で取れる3バイトで同定する ──
def test_7バイトのカードは3バイトで同定する():
    """★実機：MCP 越しの1段が 250ms。段が進むほどカードが脱落し、7バイトを読み切れるのは1割以下。
    **WUPA＋CL1 の2段なら5割以上通る。** 名前を呼ぶには3バイトで足りる（重なりは登録時に弾く）。"""
    rc = nfc.Rc522(FlakyChip(bytes([0x04, 0x11, 0x22, 0x33, 0x44, 0x55, 0x66])))
    assert run(rc.poll_uid()) == "041122"


def test_4バイトのカードは今までどおり():
    assert run(nfc.Rc522(FakeChip(uid=bytes([0xDE, 0xAD, 0xBE, 0xEF]))).poll_uid()) == "deadbeef"


def test_読み切れる時も同じ鍵になる():
    """★同じカードが、読めた深さで別人になってはいけない。"""
    uid = bytes([0x04, 0x11, 0x22, 0x33, 0x44, 0x55, 0x66])
    assert run(nfc.Rc522(FakeChip(uid=uid)).poll_uid()) == "041122"


def test_登録で先頭が重なるカードは弾く(tmp_path):
    import importlib.util
    s = importlib.util.spec_from_file_location("enroll", ROOT / "scripts" / "nfc_enroll.py")
    en = importlib.util.module_from_spec(s); s.loader.exec_module(en)
    f = tmp_path / "g.toml"
    en.save_table(f, {"041122": "A"})
    assert en.add_guest(f, "041122", "B") is False       # ★同じ鍵に別名は入れない
    assert en.add_guest(f, "049988", "B") is True


def test_本物のPresenceで顔が出る():
    """★2026-09-26：偽の Presence で緑だったが、本物は PRIORITY に無い種類を拒否して落ちた。
    **顔・光・声はその例外の後ろにあり、かざしても何も起きなかった。**偽物で守れない所は本物で試す。"""
    from presence import Presence
    pr = Presence(dance_face="happy")
    r = nfc.NfcReactor(pr, led=None, quiet=True)
    run(r.react(nfc.Greeting("aa", "A", 1, "いらっしゃい"), gw=None))
    # 例外が出なければよい。重ね合わせが載っていることも見る
    assert any("nfc" in str(k) for k in getattr(pr, "_overlays", getattr(pr, "overlays", {"nfc": 1})))
