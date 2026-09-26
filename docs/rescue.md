# レスキュー — 実機が gateway に来ないとき

**2026-09-26 に半日溶かした話から起こした。** 上から順に。飛ばさない。
**1コマンド版は `./scripts/rescue.sh`**（この文書の手順を機械が回して、止まっている場所を言う）。

## 0. まず1行で全部見る

```bash
./.venv/bin/python scripts/status.py
```

| 出た行 | 意味 | 次 |
|---|---|---|
| `× OTAスタブ 止まっている` | ★**実機は OTA 確認が通るまで WebSocket に来ない。** ここが9割 | `./scripts/service.sh install`（常駐に入れ直す）→ 実機を再起動 |
| `× gateway 繋がらない` | gateway が落ちている | `launchctl kickstart -k gui/$(id -u)/com.uni.stackchan.gateway` |
| `× 実機 繋がっていない`（他は○） | 実機側で止まっている | **2 へ** |
| `実機の向き先 ws://…` | 実機が見に来る**固定 IP** | **その IP をこの Mac が持っているか** → 3 |

## 1. 何が変わったかを、時系列で並べる

**もっともらしい変化点に飛びつかない。** 9/26 は「前夜に Tailscale が上がった」に飛びついて2時間失った。
実機は Tailscale が上がった後も5時間繋がっていた。**時系列を並べれば外せた。**

```bash
grep -E "ESP32 connecting|ESP32 ready|disconnected" ~/Library/Logs/stackchan/com.uni.stackchan.gateway.log | tail -5
```

最後に繋がっていた時刻と、切れた時刻を見る。**その間に Mac で何をしたか**を思い出す（再起動・ログアウト・ネットワークの抜き差し）。

## 2. ★実機の言い分を聞く（USB シリアル）— Mac 側で推理する前に、これ

**実機がどこへ繋ごうとして、何で止まっているかは、シリアルにしか出ない。**

1. **上の箱（CoreS3 本体）**の USB-C を、データ通信できるケーブルで Mac に挿す（台側は給電だけ）
2. ```bash
   ./scripts/rescue.sh --serial        # 実機をリセットして起動ログを 45 秒読み、要点だけ出す
   ```
3. 読み方

| ログ | 止まっている場所 | 直し方 |
|---|---|---|
| `Failed to connect to <IP>:8778` | **OTA スタブ**が居ない／IP が違う | スタブを立てる。IP が違うなら **3** |
| `Alert … 6桁` / `activation` | OTA が本物のクラウドを向いている | `ota_url` をスタブに向け直す（設定画面から） |
| `Failed to connect to <IP>:8775` | gateway が居ない／IP が違う | gateway を上げる。IP が違うなら **3** |
| `WiFi connecting` のまま | Wi-Fi に繋がっていない | 2.4GHz の SSID か。設定モードに入れ直す |
| `Got IP` は出るのに何も試さない | 設定が空 or 壊れている | **4** |

★**この実機のファームには mDNS 探索が入っていない**（`gateway_config_get` → `discovery_compiled_in=false`）。
実機は **固定 IP** を見に来る。「mDNS で見つかるはず」は、いまの build では嘘。

## 3. 実機が見に来る IP を、この Mac が持っていない（★当日の MacBook がこれになる）

実機は `ws://<IP>:8775/`（gateway）と `http://<IP>:8778/`（OTA）を**同じ IP** で見る。

**手が2つ。どちらか。**

**(a) この Mac にその IP を持たせる**（実機を触らない。当日はこれ）

```bash
# 実機が見に来る IP を、いまの LAN 側インターフェースに別名として足す
IP=$(./.venv/bin/python scripts/status.py 2>/dev/null | sed -n 's/.*向き先 *ws:\/\/\([0-9.]*\):.*/\1/p')
DEV=$(route -n get default | awk '/interface:/{print $2}')
sudo ifconfig "$DEV" alias "$IP" 255.255.255.0        # ★sudo が要る。当日は準備の時間に
```

→ そのまま実機を再起動すれば来る。**LAN 上に同じ IP が居ないことだけ確かめる**（`ping` で返事が無いこと）。

**(b) 実機の向き先を変える**（gateway に**繋がっているとき**だけできる）

```bash
# WebSocket の向き先は MCP から変えられる。★OTA の向き先（ota_url）は変えられない
./.venv/bin/python - <<'PY'
import asyncio,sys; sys.path.insert(0,"app/dj"); from gateway import Gateway
async def go():
    async with Gateway("http://127.0.0.1:8767/mcp") as gw:
        print(await gw.call("gateway_config_set", url="ws://<新しいIP>:8775/"))
asyncio.run(go())
PY
```

★**ota_url は MCP から変えられない。** だから (b) だけでは次の起動で OTA に落ちる。**(a) を主にする。**

## 4. どうしようもないとき（順に強くなる）

| 段 | やること | 失うもの |
|---|---|---|
| ① | **実機をリセット**（USB から: `./scripts/rescue.sh --reset`／本体のリセットボタン） | 何も失わない |
| ② | **設定モードに入れ直す**：NVS の `wifi` を消す → 起動時に設定 AP が立つ → ブラウザから Wi-Fi と **OTA URL** と **WebSocket URL** を入れ直す<br>`esptool erase-region 0x9000 0x6000`（`learnings.md` L758） | Wi-Fi と向き先の設定（入れ直せばよい） |
| ③ | **前の面（OTA スロット）に戻す**：`./scripts/flash-slot.sh --back`（= `ota_select.py 1`）。★9/26 から **ota_0=新（省電力なし）／ota_1=旧** | 今の面のファーム（前の面が動くなら困らない） |
| ④ | **焼き直す**：`firmware/merged-binary.bin` を `esptool write_flash 0x0` | 表情データ（`reload_avatar.py` で戻る）。NVS は消えない |
| ⑤ | **出荷時に戻す**：`backup/` から `write_flash 0x0` | 自前構成ぜんぶ。会話はクラウドに戻る＝**プライバシーの主張が逆に濃くなる**ので、話としては成立する |

**⑤の手前で、当日は「デモ録画」に切り替える。** 録画は必ず持っていく（checklist）。

## 5. 再発防止（入れたもの）

- **OTA スタブを常駐に**（`service.sh install` の一員）。手で `&` 起動していたのが原因だった
- **`status.py` の1行目が OTA スタブ**。沈黙は故障と見分けがつかない。見えるようにした
- **`status.py` に「実機の向き先」**。当日、別の Mac で受けるときに真っ先に見る行
- **`preflight.sh`（出発前）が status を含む**
- `sync.sh` / `CLAUDE.md` の「mDNS で見つかる」を訂正

## 6. 当日の教材に使う一言

> 「2時間、ネットワークを疑いました。答えは USB ケーブル1本の先にありました。
> 　**沈黙している側の言い分を聞かずに、こちら側で推理していた**んです」
