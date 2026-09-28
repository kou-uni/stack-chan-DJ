# 本番は USB ケーブルで繋ぐ（2026-09-29）

会場の Wi-Fi が 5GHz だけ・ログイン画面つき・端末どうし通信禁止でも止まらないように、
**実機は USB ケーブルで MacBook に繋ぐ。** 実機の Wi-Fi は使わない。

```
スタックチャン ══USB-C══ MacBook ══USB══ DJ機材
                           │
                        Wi-Fi（会場の。5GHz でも可）── iPad（背景）
```

- 実機から見ると USB が有線 LAN になる（CDC-NCM。macOS は設定なしで認識する）
- 実機 192.168.7.2 が Mac に番地（192.168.7.x）を配り、**配った番地の gateway に繋ぐ**。Mac 側の設定は要らない
- 経路は配らないので、Mac のネットは Wi-Fi のまま
- 当日の作業はない。挿して電源を入れるだけ

## 切り替え

```bash
./.venv/bin/python scripts/usb_wired.py          # いまの状態
./.venv/bin/python scripts/usb_wired.py on       # USB で繋ぐ（本番の形）
./.venv/bin/python scripts/usb_wired.py off      # Wi-Fi で繋ぐ
```

gateway 経由で切り替えて再起動まで送る。ボタンもケーブルの抜き差しも要らない。

- **USB で繋いでいる間は USB シリアルが使えない**（esptool・`set_target.py`・`rescue.sh --serial`）。使うときは `off`
- `on` のまま Mac が見えないと（充電器につないだ等）、15 秒待って **Wi-Fi で繋ぐ**
- 電池があるので、ケーブルを抜いても再起動しない

## 実機で確かめたこと（2026-09-29、家）

- USB だけで繋がる。Mac を見つけるまで 1.8 秒。doctor 全項目 ○（音の取り込み・首・LED・pose）
- Mac のネットは Wi-Fi（en0）のまま
- `on` ⇄ `off` を gateway だけで往復できる。`off` で USB シリアルが戻る
- `on` で Mac が見えないときは Wi-Fi に逃げる

## 要るもの

- ファーム **`firmware/xiaozhi-usb-20260929.bin`** 以降（git の外。#7）。いま実機の ota_0 に入っている。
  ota_1 には 9/26 版（Wi-Fi のみ）が残っていて、`./scripts/flash-slot.sh --back` で戻れる
- 改変は `vendor-patches/stackchan-mcp.patch`（ファームの `boards/common/usb_wired.*`、gateway の `set_usb_wired` / `reboot_device`）

## 詰まりどころ（実機で踏んだ）

- **表情データ・写真の URL は「実機が繋いできた経路の番地」で作る**（gateway の esp32_client.local_host）。
  VISION_HOST（起動時の Wi-Fi の番地）のままだと、USB の実機から届かず顔が出ない（`http_open_failed`）
- **家で Mac Studio の console が動いていると `stackchan.local` を取られる**（背景が Mac Studio 側を開く）。
  家でも会場と同じにするため、2026-09-29 に Mac Studio の console / gateway / OTA の常駐を外した（戻すなら Mac Studio で `./scripts/service.sh install`）
- 起動直後は OFF モード。**左デッキの PLAY で DJ モード**（LED と背景の照明が点く）。MASTER で OFF

- **Mac は前にもらった番地を頼んでくる。** 番地を決め打ち（192.168.7.1）にすると繋がらない。だから「配った番地」に繋ぐ
- **USB の割り当ては RTC 側のレジスタにあり、ソフトの再起動では戻らない。** `off` のときは起動時にシリアルへ戻している
- 書き込み直後は Mac 側の USB シリアルが固まることがある → ケーブルを挿し直す
- ファームをビルドするときは、サブモジュールも取る: `git -C vendor/stackchan-mcp submodule update --init`
