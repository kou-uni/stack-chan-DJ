# MacBook を当日の形にする

**当日、頭脳もふくめて全部この機械に載る。** ここが通らないと、会場では何も動かない。

## 手で運ぶものは無い

以前は「Mac Studio から 2GB 強をコピー」という想定だった。**いまは要らない。**
GitHub に入っていないものは、**取ってくるか、その場で作る**ようにしてある。

| 要るもの | どうやって手に入るか |
|---|---|
| `vendor/stackchan-mcp` | 公開リポジトリを clone。**版を固定し、改変を patch で当て直す** |
| `vendor/m5stack-avatar` | 公開リポジトリを clone（版を固定） |
| `vendor/voicevox` 2GB | VOICEVOX 公式のリリースから取得 |
| 表情データ `.raw` | その場で生成（`make_faces` → `pack_avatar`） |
| `.env.gateway` | 雛形（`.env.gateway.example`）からコピー |
| Ollama + `gemma3:4b` | `brew` と `ollama pull` |
| パネルの鍵 | console の初回起動で自動生成 |

## 手順

```bash
git clone https://github.com/kou-uni/stack-chan-DJ.git
cd stack-chan-DJ
./scripts/bootstrap.sh
```

**これだけ。** 途中で止まったら、止まった理由が日本語で出る。直してもう一度走らせる
（何度走らせても同じ結果になるように書いてある）。

終わったら:

```bash
vendor/voicevox/macos-arm64/run --host 127.0.0.1 --port 50021 &
./.venv/bin/python scripts/doctor.py      # 全部○になるか
```

実機の電源を入れて同じ Wi-Fi に乗せる。**本体の設定は触らない**（mDNS で探すため）。
DJ機材(DDJ-FLX2)は USB なので、**この機械に挿す**。

## Claude Code に任せるなら

MacBook にも Claude Code を入れるなら、clone したあと、そのまま貼ってよい。

```
このリポジトリを、この MacBook で当日使える状態にしてください。

  ./scripts/bootstrap.sh

やってほしいこと:
- スクリプトを走らせる。**止まったら、止まった理由を読んで直してから、もう一度走らせる**
- 直したことが「この機械だけの事情」なら、その場で直して終わり。
  **どの機械でも起きること**なら、スクリプト側を直して push する
- 終わったら doctor.py を出して、○にならない行があれば原因を切り分ける

守ってほしいこと:
- **コードは1本。** 機械ごとに分岐を足さない。違いは config.toml と .env.gateway だけ
- `.env.gateway` と `~/.config/stackchan/panel-token` の中身を画面に出さない
- 実機が繋がっていない状態でも、ここまでは全部できる

背景:
- 当日は 2026-09-29、Crypto Cafe and Bar。この機械に gateway・console・
  背景サーバ・VOICEVOX・Ollama が全部載る。DJ機材が USB なのでこの機械でしか動かない
- 詳しくは docs/macbook-setup.md と CLAUDE.md
```

## 通ったと言える条件

1. `./scripts/bootstrap.sh` が最後まで走る（試験が全部通る）
2. `doctor.py` が全部 ○
3. 実機が**この MacBook に**繋がる（`scripts/status.py` で「実機 繋がっている」）
4. 曲を流すと踊り、DJ機材のつまみで首が動く
5. iPad で背景が開いて、LEDが実機と同じ色で光る

**3 から先は実機が要る。** 1と2は実機なしで確かめられるので、先にそこまで通す。

## 詰まりどころ

- **`vendor/stackchan-mcp` の改変が当たらない** … 版がずれている。
  `vendor-patches/*.pin` の版と `docs/vendor-patches.md` を突き合わせる
- **VOICEVOX が落ちてこない** … 2GB。回線が細いと失敗する。
  手で入れて `vendor/voicevox/macos-arm64/run` に置けばよい
- **Python の版** … `torch` を使う会話サーバは 3.11 が要るが、
  **こちらは要らない**（会話は `talk.py` の経路）
