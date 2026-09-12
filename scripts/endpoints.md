# 接続先URLの切替メモ

**現地で戻せないと詰む。** ここを見れば戻せる状態を常に保つ。

## パスは確定済み（2026-09-03、公式 docs/Deployment.md より）

| 用途 | 形式 |
|---|---|
| WebSocket | `ws://<host>:8000/xiaozhi/v1/` |
| OTA | `http://<host>:8003/xiaozhi/ota/` |
| 管理画面 | `http://<host>:8002` |

## 3つの向き先

| 用途 | URL | 使う場面 |
|---|---|---|
| 宅内LAN | `ws://<MacのLAN IP>:8000/xiaozhi/v1/` | 第一関門・自宅での開発 |
| Funnel | `wss://<node>.<tailnet>.ts.net/xiaozhi/v1/` | 第二関門・イベント本番 |
| 出荷時（XiaoZhiクラウド） | M5Burner で公式ファームに書き戻す | 全部ダメだったときの保険 |

## Tailscale Funnel（stackchan-mcp の remote-access.md より）

Funnel が待てるのは **HTTPS の 443 / 8443 / 10000 のみ**。ローカルポートを寄せる形になる。

```bash
tailscale funnel --bg --https=443 http://localhost:8000     # WebSocket（8765 ではなく 8000 に読み替え）
tailscale funnel status
tailscale funnel --https=443 off                            # 止める
```

**wss は通る**とドキュメントに明記あり（ESP32 は `wss://<node>.<tailnet>.ts.net/` に繋ぐ前提で書かれている）。
ただし帯域は Tailscale 管理で調整不可、遅延は経路次第。

## 切替の手順

1. 本体をダウンロードモードにする（底面 RST を3秒長押し、隣のLEDが緑になったら離す）
2. 書き込みツールか WiFi設定UI で接続先URLを変更
3. 再起動して LED を見る：**緑＝聞いている / 青＝喋っている / 消灯＝待機**

## 出荷時に戻す

M5Burner v3 →「StackChan」検索 → **Only Official** にチェック → Download →
**足側の USB-C** で接続 → Burn。ポートが出ないときはダウンロードモードへ。往復自由。
