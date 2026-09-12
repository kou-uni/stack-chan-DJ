# docs

**一次資料は [00-concept.md](00-concept.md) 1本。** ここを分割コピーしない（内容がずれる）。

節の索引だけ置く。

| 節 | 内容 | よく見るとき |
|---|---|---|
| 1 | スタックチャンとは / K151のスペック | 説明するとき |
| 2 | UX としての価値、期待値のズレやすい点 | 台本を書くとき |
| 3 | アーキテクチャ（3層 / ルーティング原則 / トリガー） | 実装の判断 |
| 4 | 想定ユースケース（カレンダー・家電・筋トレ） | v1以降 |
| 5 | **ファーム比較（5択と採否）** | 焼く前 |
| 6 | **プライバシーリスク** | イベント前 |
| 7 | **構成（本命）と未検証の懸念** | 詰まったとき |
| 8 | 構築手順（関門2つ） | W1〜W3 |
| 9 | 物理・初期設定・引っかかりポイント | 実機を触るとき |
| 10 | 外デモの実務 | → `../event/checklist.md` に展開済み |
| 11 | デモで映える要素 | → `../event/run-of-show.md` に展開済み |
| 12 | 応用テクニック（感情タグ / ESP-NOW / ライセンス） | 実装の判断 |

## 思考の側は Obsidian

判断・知見・未解決の問いは vault に切ってある。

- ハブ：`interests/stackchan-robot-app`
- 決定：ファーム選択、頭脳を自宅に置く判断、イベント形式
- 問い：Funnel が ws を通すか、自前ビルドでアプリ連携が切れるか

---

## 2026-09-03 に一次情報で確認したこと

公式リポジトリを読んで、`00-concept.md` の前提が3点はっきりした。**メモ本体は書き換えていない**（一次資料なので）。差分はここに置く。

### 1. Funnel は wss を通す（懸念は概ね解消）

stackchan-mcp の `docs/remote-access.md` に、
**ESP32 が `wss://<node>.<tailnet>.ts.net/` に繋ぐ前提**で手順が書かれている。
Funnel が待てるのは HTTPS の **443 / 8443 / 10000 のみ**なので、ローカルポートをそこに寄せる。

```bash
tailscale funnel --bg --https=443 http://localhost:8000
```

残る不確実性は「通るか」ではなく「遅延と帯域」。帯域は Tailscale 管理で調整不可。

### 2. ~~stackchan-mcp は音声をやらない~~ → **誤り。訂正（2026-09-08）**

`docs/architecture.md` の「Phase 5 = 音声は未実装」という記述を信じたが、
**リポジトリを clone して中身を見たら、既に実装済みだった。**
設計文書が古い。`ls` と `CHANGELOG` を先に見るべきだった。

`vendor/stackchan-mcp` に実物がある。gateway が既に持っているもの：

- `say()` / `listen()` — TTS(VOICEVOX等) と STT(faster-whisper ローカル・MIT)
- `set_mouth_sequence()` — リップシンクをデバイス側でキュー再生
- **`beat_mode_start()`** — 周辺音からBPM推定 → ビート同期の head sway + LEDフラッシュ
- `stackchan_follow_pose_stream()` — 外部WSに1:1追従（角速度クランプ内蔵）
- `examples/cloudflare-relay/` — Cloudflare Workers の WS リレー

**帰結：**
1. **Phase 3（踊り）の中核が既にある。** DDJ との配線なしで「音が鳴れば踊る」が成立する
2. **Phase 4 で xiaozhi-esp32-server が要らない可能性が高い** → 下の x86 問題が消える

### 3. 公式 Docker イメージは x86 のみ（★要対処）

`docs/Deployment.md`：**v0.8.2 以降のイメージは x86 のみ。ARM64 は手動ビルドが必要。**
Mac Studio は Apple Silicon なので、`docker compose up` がそのままでは通らない。

選択肢は3つ。W1 でどれか決める → `questions/xiaozhi-server-on-apple-silicon`

| 案 | 中身 | 懸念 |
|---|---|---|
| A. ローカル実行 | Docker を使わず Python で直接動かす | 依存の解決が面倒。ただし**推論がネイティブ速度** |
| B. 自前ビルド | ARM64 向けに手動ビルド | 時間を食う。更新のたびに再ビルド |
| C. x86 エミュ | `platform: linux/amd64` | STT が重い。**9月末の締切に対して危険** |

締切から逆算すると **A が本命**。9/26 までに音が出る方が、構成の綺麗さより優先。

### 確定したエンドポイント

| | 形式 |
|---|---|
| WebSocket | `ws://<host>:8000/xiaozhi/v1/` |
| OTA | `http://<host>:8003/xiaozhi/ota/` |
| 管理画面 | `http://<host>:8002` |

STT は SenseVoiceSmall（`models/SenseVoiceSmall/model.pt`）、設定は `data/.config.yaml`。
