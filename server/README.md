# server — Mac Studio 側

xiaozhi-esp32-server を Docker で立てて、LLM は Ollama に向ける。

## 手順

```bash
cd ~/stackchan-lab/server
cp .env.example .env      # 中身を埋める（.env は git に入らない）
# ★ 先に docker-compose.yml のイメージ名・タグを公式 README で確認する
docker compose up -d
docker compose logs -f
```

## Ollama を Docker から見せる

Mac のホストで Ollama を動かし、コンテナからは `host.docker.internal` で叩く。
Ollama 側は **ローカルネットワーク提供をオン**にしておく（デフォルトは 127.0.0.1 のみ）。

```bash
launchctl setenv OLLAMA_HOST 0.0.0.0:11434   # 設定アプリ側のトグルでも可
curl http://localhost:11434/api/tags          # 疎通確認
```

## モデル

小さい方から。往復遅延（会場 → Funnel → 自宅 → 推論 → 戻り）が乗るので、
体感は「モデルの賢さ」より「最初の音が出るまでの時間」で決まる。

| モデル | 用途 |
|---|---|
| `llama3.2:3b` | まずこれ。速度の基準を取る |
| `qwen2.5:14b` | 会話の質が要るとき。遅ければ捨てる |

## 注意

- **スリープさせない**。`../scripts/keep-awake.sh`
- 接続先URLの切替を楽にしておく。現地で戻せないと詰む → `../scripts/endpoints.md`
