# app/dj — DDJ-FLX2 連携

設計は [../../docs/dj-sync.md](../../docs/dj-sync.md)。

## 作る順

- [ ] `midi_dump.py` — DDJ-FLX2 の MIDI をただ表示する（**まずこれ**。実機不要）
- [ ] `jog_to_head.py` — ジョグの回転 → `move_head`
- [ ] `pads_to_face.py` — パッド / PLAY → 表情・LED
- [ ] `link_tempo.py` — Ableton Link から BPM と拍位置
- [ ] テンポ＋位相を実機へ渡し、**刻むのは実機側**にする

## 前提

- DDJ-FLX2 はクラスコンプライアント。macOS に USB MIDI として出る（ドライバ不要）
- rekordbox の Ableton Link は **Performance モードのみ**
- 制御は stackchan-mcp のツール（`move_head` / `set_avatar` / `set_led`）を叩く形

## 注意

**サーボを全拍で振らない。2拍に1回から。** 曲間は休ませる。
