# ファーム戦略

**結論：事前ビルド済みバイナリを焼く。ソースからビルドしない。**
ただし**出荷時ファームを一度でも動かしたデバイス特有の罠**があるので、順番が重要。

（2026-09-08、`vendor/stackchan-mcp` の実物と README.ja.md で確認）

---

## 何を焼くか

| | 中身 | 採否 |
|---|---|---|
| **オプションA：事前ビルド済み** | Releases から `merged-binary.bin` を落として esptool で焼く。**ツールチェーン不要** | **★これ** |
| オプションB：ソースからビルド | ESP-IDF / Docker が要る。Kconfig を触れる | 罠を回避できなかったときだけ |

```bash
esptool.py --chip esp32s3 --port /dev/cu.usbmodem1101 -b 460800 \
  write_flash 0x0 merged-binary.bin
```

ベースは xiaozhi-esp32（上流 v2.2.6）のフォーク。K151 のボード定義が入っている。

---

## ★ 罠：出荷時ファームの NVS が残っていて、tenclass を呼び続ける

**これが今回一番踏みやすい。**

出荷時ファームは NVS に `websocket.url=wss://api.tenclass.net/...` を書き込んでいる。
新しいファームを焼いても **NVS は消えない**。すると：

- 「NVSが空ならビルド時デフォルトを使う」というフォールバックが**発動しない**
- **mDNS discovery も効かない**（`websocket.url` が空でないと動かない）
- デバイスはローカルの gateway ではなく、**tenclass を呼び続ける**

### 回避（プリビルドのままできる）

**WiFi 設定 UI から手で URL を入れて、NVS を上書きする。**

1. デバイスが WiFi 設定モードのとき `http://192.168.4.1` を開く
2. **Advanced タブ**に切り替える
3. **WebSocket Gateway URL** に `ws://<Mac StudioのLAN IP>:8765/` を入れる
4. 送信すると NVS の `websocket.url` が上書きされる

これで tenclass を見なくなる。**ソースビルドは不要。**

### それでも駄目なとき（オプションBに落ちる）

接続自体が成立せず UI にも入れない場合のみ、Kconfig の
`CONFIG_FORCE_DEFAULT_WEBSOCKET_URL=y` で NVS を強制上書きする。
これは**ビルド時オプションなのでソースビルドが要る**。最後の手段。

---

## 接続先の解決順序（ファームの挙動）

1. NVS `websocket.url`
2. **mDNS `_stackchan-mcp._tcp.local.`**（`CONFIG_STACKCHAN_MDNS_DISCOVERY` 有効かつ **NVS が空**のとき）
3. `CONFIG_DEFAULT_WEBSOCKET_URL`（ビルド時）
4. 全部空 → boot log にエラーを出して失敗

このあと `websocket.fallback_url` の候補が試される。

**mDNS は URL しか見つけない。** 認証は `websocket.token` が別に握る。

---

## ★ 我々の狙う構成は、公式の推奨構成そのものだった

README に載っている構成表の1行目がこれ。

| モード | Primary URL | Fallback URL |
|---|---|---|
| **LAN 自動検出 + relay fallback** | **空（mDNS）** | `wss://<relay-host>/` |

自分たちで考えた「mDNS で近い方を探し、居なければ自宅へ」は、**想定された使い方**だった。
無理をしていない、という確認になる。

---

## mDNS の名乗りは gateway 側のフラグで制御できる

自前で mDNS を実装する必要はなかった。

```bash
stackchan-mcp            # 既定で _stackchan-mcp._tcp.local. を広告する
stackchan-mcp --no-mdns  # 広告を止める
```

だから **standby ロジックは「gateway をどう起動するか」の制御**になる。
Mac Studio 側で MacBook の生死を見て、`--no-mdns` の有無を切り替える薄い監督プロセスを書けばいい。

### 複数の gateway が同時に名乗っていたら

ファームは**1回の browse で見つかった全ての gateway service を順に試す**。
壊れはしないが、**どれに繋がるかは不定**。
だから「MacBook が居るときは Mac Studio が名乗らない」という設計は依然として必要。

---

## 焼く順番

**gateway を先に立ててから焼く。** 焼いた直後に繋ぎ先が居ないと切り分けが増える。

1. **gateway を Mac Studio で起動**（`vendor/stackchan-mcp`。Python のみ。Apple Silicon 問題なし）
2. **出荷時ファームをバックアップ**（`esptool read_flash`）
3. **StackChan World からアンバインド** ← 忘れるとペアリング不整合
4. `merged-binary.bin` を焼く（足側USB-C）
5. WiFi 設定 UI で **2.4GHz に接続** ＋ **Advanced タブで `ws://<LAN IP>:8765/` を明示** ← 罠の回避
6. gateway のログに接続が出る。`move_head` が通る ← **Phase 1 の DoD**
7. 繋がってから `gateway_config_set url=""` で **primary を clear → mDNS に移行**して検証
8. `websocket.fallback_url` に relay（Funnel / Cloudflare relay）を入れる

**7 を「繋がった後」にやるのが肝。** 最初から mDNS を狙うと、
罠（NVS 残留）と mDNS 不調のどちらで失敗したのか分からなくなる。

---

## 戻し方

- **アンバインド** — アカウント紐付け解除。ファームはそのまま
- **M5Burner で書き戻し** — v3 →「StackChan」検索 → **Only Official** → Download → 足側USB-C → Burn

**往復自由。** 気軽に載せ替えてよい。

---

## 開発中の個人設定

ソースビルドをする場合のみ。gitignore 済みのローカルファイルに書く。

```bash
cd firmware
cat > sdkconfig.defaults.local <<'INNER'
CONFIG_DEFAULT_WEBSOCKET_URL="ws://<LAN IP>:8765/"
CONFIG_DEFAULT_WEBSOCKET_FALLBACK_URL="wss://<relay-host>/"
CONFIG_FORCE_DEFAULT_WEBSOCKET_URL=y
INNER
```

追跡対象の `sdkconfig.defaults` には**書かない**。
