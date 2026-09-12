# stackchan-lab

**自宅の Mac Studio を頭脳にして、外に持ち出したスタックチャンをネット越しに動かす。**
その状態で Crypto Cafe and Bar のハンズオンイベントをやる。

構想の元ネタは [docs/00-concept.md](docs/00-concept.md)（2026-09-02 版、これが一次資料）。

---

## 構成

```
会場：スタックチャン(K151) + iPhoneテザリング(2.4GHz)
  │  WebSocket
  ▼
Tailscale Funnel (HTTPS/WSS 公開)
  │
  ▼
自宅 Mac Studio
  ├─ xiaozhi-esp32-server (Docker)     ← STT / ルーティング / TTS
  ├─ Ollama (qwen2.5:14b / llama3.2:3b) ← LLM
  └─ app/  記憶・人格・決定論ルーティング ← ここが「作るアプリ」
```

原則：**スタックチャンは頭脳ではなく I/O ゲートウェイ**。実機は薄く保つ。
確実性が要るもの（定時通知・センサー反応）は自分のコードで、曖昧な自然文だけ LLM に投げる。

---

## ディレクトリ

| 場所 | 中身 |
|---|---|
| `docs/` | 構想メモ（一次資料）、確認済みの差分、**遠隔ワークベンチ**、**DJ連携** |
| `server/` | Mac Studio 側の docker-compose と設定 |
| `app/` | 頭脳層。人格プロンプト、ルーティング、記憶、`app/dj/` |
| `scripts/` | 疎通チェック、スリープ抑止、接続先URL切替メモ |
| `event/` | Crypto Cafe and Bar 用の台本・参加者手順・チェックリスト |

---

## いまどこ

[ROADMAP.md](ROADMAP.md) を見る。関門は2つ。

1. **第一関門** 宅内で完結動作（テザリングなし、Funnelなし）
2. **第二関門** テザリング経由で家の外から動作

ここを越えるまで、SwitchBot もカレンダーも触らない。

**並走できるもの**（実機や関門を待たなくていい）

- [docs/remote-workbench.md](docs/remote-workbench.md) — 家に置いたまま外から焼く常設環境
- [docs/dj-sync.md](docs/dj-sync.md) — DDJ-FLX2 に合わせて踊らせる。MIDI を読むところはMacだけで書ける

---

## 環境（2026-09-03 時点の実測）

| | 状態 |
|---|---|
| Docker | 29.7.2 あり |
| Ollama | qwen2.5:14b / llama3.2:3b あり |
| Tailscale | **未インストール** ← 最初に入れる |
| xiaozhi-esp32-server | 公式Dockerイメージは **x86のみ**。ARM64は手動ビルドかローカル実行 |
| DDJ-FLX2 | あり。クラスコンプライアントなので macOS に USB MIDI として出る |
| 回線 | v6プラス(MAP-E)。ポート開放は使えない。トンネル前提 |
