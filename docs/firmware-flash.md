# ファームを焼く手順（2026-09-12 実施・検証済み）

**いま載っているもの:** PR #374 適用版（main + fix/touch-responsiveness）を **ota_1** から起動。

## 戻し方（先に書く）

**appは上書きしていない。ota_0 に前のファームがそのまま残っている。**

```bash
cd ~/stackchan-lab
# otadata の entry1 を消すと seq=1 に戻り、ota_0 から起動する
./.venv/bin/python -c "open('/tmp/blank.bin','wb').write(b'\xff'*4096)"
./.venv/bin/python -m esptool --port /dev/cu.usbmodem201101 write-flash 0xe000 /tmp/blank.bin
```

丸ごと戻すなら `backup/full-before-pr374-20260912.bin`（16MB・焼く直前の全体）。

## パーティション

| ラベル | 開始 | サイズ | |
|---|---|---|---|
| nvs | 0x9000 | 16KB | WiFi設定。**`merged-binary.bin` を焼くと消える** |
| otadata | 0xd000 | 8KB | どちらの app から起動するか |
| ota_0 | 0x20000 | 4.1MB | 焼く前のファーム（v2.2.6 / Jul 12 2026） |
| ota_1 | 0x410000 | 4.1MB | **いま起動している**（v2.2.6 / Sep 12 2026 + PR #374） |
| assets | 0x800000 | 8.4MB | 表情の素材。app だけ焼けば触らない |

`起動スロット = (最大の有効 seq - 1) % 2`
`crc = zlib.crc32(seqの4バイト, 0xffffffff)` ★変種が多い。**実機の値で検算すること**

## 手順

```bash
# 1) ソースを取る（★vendor/ は触らない。こちらのローカル改変が乗っている）
cd ~/stackchan-lab
git clone --depth 1 -b fix/touch-responsiveness \
  https://github.com/tsuru0805/stackchan-mcp.git build/pr374
cd build/pr374 && git submodule update --init --recursive --depth 1

# 2) ビルド（★ESP-IDF は入れない。上流CIと同じ Docker で）
colima start --cpu 8 --memory 8
cd firmware && docker run --rm -v "$PWD":/project -w /project \
  espressif/idf:v5.5.2 python ./scripts/release.py stackchan
#   → build/xiaozhi.bin（app のみ・3.0MB）
#   → build/merged-binary.bin（★NVSを消す。使わない）

# 3) 焼く前に全部退避（★Docker から USB には届かない。母艦側でやる）
cd ~/stackchan-lab
./.venv/bin/python -m esptool --port /dev/cu.usbmodem201101 --baud 921600 \
  read-flash 0 0x1000000 backup/full-before-XXX.bin

# 4) 基準を取る
./.venv/bin/python scripts/device_check.py --manual --save backup/before-flash.json

# 5) サービスを止めて、使っていない側に焼く
launchctl bootout gui/$(id -u)/com.uni.stackchan.console
launchctl bootout gui/$(id -u)/com.uni.stackchan.gateway
./.venv/bin/python -m esptool --port /dev/cu.usbmodem201101 --baud 921600 \
  write-flash 0x410000 build/pr374/firmware/build/xiaozhi.bin

# 6) 起動先を切り替える（scripts/ota_select.py）
./.venv/bin/python scripts/ota_select.py 1

# 7) 起動ログで**設定が効いていること**を確かめる
#    Si12T: init OK: ctrl=0x03 out1=0x00 sens12=0x02 sens34=0x00
#    Ota: Running partition: ota_1

# 8) サービスを戻して突き合わせる
./.venv/bin/python scripts/device_check.py --manual --compare backup/before-flash.json
```

## 感度の調整（個体差が出るところ）

`firmware/main/boards/stackchan/stackchan.cc` の `Si12T::Begin()`。

```
レジスタ 0x02 = CH1(下位4bit) + CH2(上位4bit)
4bit = HL<<3 | M   M: 0=0.50%（最も敏感）… 7=3.55%（最も鈍い）
書いている値: 0x02 → CH1=0.90%, CH2=0.50%
レジスタ 0x03 = 0x00 → CH3=0.50%
```

**うちの個体はこの値で問題なし**（`out1=0x00` = 待機中に誤発火しない、20秒で15回検出）。

- 待機中に勝手に反応する → M を上げる（鈍くする）
- 軽く触っても反応しない → M を下げる

**起動ログに読み戻した値が出る。** 変えたら必ずそこで確認する。
