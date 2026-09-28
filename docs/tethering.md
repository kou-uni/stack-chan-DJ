# テザリングで実機を MacBook に繋ぐ（当日の形）

**2026-09-29 に書いた。** 家では実機は `192.168.0.123`（Mac Studio）を固定で見に来る。
会場は iPhone テザリング（`172.20.10.x`）で**番地帯が違う**ので、別名（`rescue.md` §3a）は効かない。
**実機にテザリングの SSID を教えるついでに、向き先2つを MacBook の IP に書き換える。** これ1回。

**NVS は消さない。** 消すと Wi-Fi だけでなく画面・LED・音の設定も飛ぶ（`display` `led_strip` `audio` `aec` `model` `websocket`）。
設定画面は**保存済み SSID を残したまま追加**できる。

## 0. 先に MacBook を当日の形にする

```bash
git clone https://github.com/kou-uni/stack-chan-DJ.git && cd stack-chan-DJ && ./scripts/bootstrap.sh
```

- 名簿 `event/rec/guests.toml` を Mac Studio から手で運ぶ（git に無い）
- **Mac Studio 側は `./scripts/stop.sh`**（gateway を2台上げない）

## 1. iPhone テザリング → MacBook → IP を控える

1. iPhone：設定 → インターネット共有 → **「互換性を優先」オン**（2.4GHz。実機は 5GHz に繋がれない）
2. MacBook をそのテザリングに繋ぐ
3. ```bash
   ./scripts/tether_ip.sh        # IP と、実機に打つ URL 2行が出る（172.20.10.x のはず）
   ./.venv/bin/python scripts/status.py   # 上3行（console / OTAスタブ / VOICEVOX）が○
   ```

## 2. 実機を設定モードに入れる（3通り。上から）

| 方法 | いつ | やること |
|---|---|---|
| **A. 起動直後に画面を短くタップ** | 家でも会場でも | 電源を入れて**顔が出る前**（起動中）に画面を1回ちょんと触る → 「Wi-Fi 設定モード」と出る |
| B. 60秒待つ | 会場（家の SSID が無い場所） | 保存済みの Wi-Fi が見つからないと **60 秒で自動で**設定モードに入る |
| C. NVS を消す | 最後の手段 | `esptool erase-region 0x9000 0x6000`。**先に `read-flash 0x9000 0x6000 nvs.bin` で退避。** 画面・音の設定も飛ぶ |

設定モードに入ると実機が **`Xiaozhi-91C4`** という Wi-Fi を立てる（末尾は MAC `…:91:c4`）。

## 3. 設定画面で 3 つ入れる

1. MacBook（またはもう1台の iPhone）を **`Xiaozhi-91C4`** に繋ぐ → ブラウザで **http://192.168.4.1**
2. 一覧から **iPhone のテザリング名**を選び、パスワードを入れる（家の SSID は保存済み一覧に残ってよい）
3. **Advanced** を開いて、`tether_ip.sh` が出した2行をそのまま:
   - **OTA URL** `http://<MacBookのIP>:8778/`
   - **WebSocket URL** `ws://<MacBookのIP>:8775/`
   - Token・Fallback は触らない
4. 保存 → 実機が再起動 → テザリングに繋ぎ → OTA スタブ → gateway → **顔が出る**（30 秒は待つ）

```bash
./.venv/bin/python scripts/status.py     # 4行目「実機 繋がっている」と、向き先が MacBook の IP
```

来なければ `./scripts/rescue.sh --serial`（USB で実機の言い分を聞く）。

## 4. 当日、会場で

- 同じ iPhone のテザリングなら、MacBook はたいてい**同じ IP**をもらう。`tether_ip.sh` で確かめる
- 違っていたら：`./scripts/tether_ip.sh --alias <昨日実機に教えた IP>` → 実機を再起動
- iPhone を予備機に替えたら SSID が変わる → **2 と 3 をやり直す**（会場では B の 60 秒待ちで入れる）

## なぜこの形か

- 実機のファームに mDNS 探索が入っていない（`discovery_compiled_in=false`）ので、**向き先は IP 直書きしかない**
- `ota_url` は MCP から変えられない。**変えられるのは設定画面だけ。** だから SSID を教えるタイミングに寄せた
- OTA スタブが居ないと実機は gateway に来ない（`rescue.md`）。**向き先は2つセットで**同じ IP にする
