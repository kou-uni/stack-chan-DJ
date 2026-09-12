# 外部ライブラリへのローカル改変

> `vendor/` は git 管理外（大きすぎる）。**だが改変を入れている。**
> 取り直したら消えるので、**何を変えたかをここに残す。**
>
> 改変は `tests/test_regressions.py` が見張っている。消えたらテストが落ちる。

## 取り直し方

```bash
git clone https://github.com/kisaragi-mochi/stackchan-mcp.git vendor/stackchan-mcp
./.venv/bin/pip install -e './vendor/stackchan-mcp/gateway[stt-faster-whisper,tts]'
./.venv/bin/python -m pytest tests/ -q     # ★ここで改変の欠落が分かる
```

そのうえで、下の改変を当て直す。

## 改変一覧

### 1. beat mode の動き出しの下限（2026-09-08）

`gateway/stackchan_mcp/beat/mode.py`

`MIN_MOTION_CONFIDENCE` が 0.35 固定で、**部屋の音量では一生踊り出さなかった**。
環境変数 `STACKCHAN_BEAT_MIN_CONFIDENCE` で変えられるようにした（実運用 0.12）。
あわせて `BeatSnapshot` に `level`（音量）を足し、スナップショットから読めるようにした。

### 2. 聞き取りの設定（2026-09-12）

`gateway/stackchan_mcp/stt/faster_whisper.py`

既定が `vad_filter=False` / `beam_size=1` で、**日本語が崩れた**
（「ファームってなんですか」→「パー持って何ですか今 本性 手措置が」）。

| 環境変数 | 既定 | 何のため |
|---|---|---|
| `STACKCHAN_STT_VAD` | 1 | 無音を捨てる。8秒中2秒しか喋っていない |
| `STACKCHAN_STT_BEAM` | 5 | 精度優先 |
| `STACKCHAN_STT_NORMALIZE` | 1 | **音量を持ち上げる**（実機の声はピーク0.055） |
| `STACKCHAN_STT_PROMPT` | — | **当日の語彙を先に教える。これが一番効いた** |
| `STACKCHAN_STT_NO_SPEECH` | 0.5 | 無音のとき語彙を幻聴するのを防ぐ |

### 3. 話し終わりの検出（2026-09-12）

`gateway/stackchan_mcp/stt/orchestrator.py`

`duration_ms` ぶん固定で待っていた。**人は話し終わったら止まる。**
フレームごとに音量を見て、無音が続いたら窓を閉じる（8秒→4秒）。

判定そのものは `app/dj/endpoint.py`（試験あり）。gateway 側はそれを呼ぶだけ。

| 環境変数 | 既定 |
|---|---|
| `STACKCHAN_STT_ENDPOINT` | 1（0で従来どおり時間で切る） |
| `STACKCHAN_STT_SILENCE_S` | 0.8 |
| `STACKCHAN_STT_MIN_SPEECH_S` | 0.3 |
| `STACKCHAN_STT_MIN_TOTAL_S` | 2.5（人が話し出すまで待つ） |
| `STACKCHAN_STT_DEBUG_WAV` | 0（1で録れた音を `/tmp` に保存。切り分け用） |

### 4. 実機イベントの追跡（2026-09-12・切り分け用）

`gateway/stackchan_mcp/esp32_client.py`

`STACKCHAN_TRACE_FRAMES=1` で、実機から来たイベントをそのままログに出す。
**通知が来ていないのか、受け口が閉じているのかを切り分ける**ために入れた。

## 設定ファイル（git 管理外）

| ファイル | 中身 |
|---|---|
| `.env.gateway` | ポートと上の環境変数 |
| `~/.config/stackchan-mcp/notify.yml` | **頭なでの通知先。既定は全部 false。開けないと届かない** |
| `~/.claude/stackchan-events.jsonl` | 頭なでの記録（利用ログ。git に入れない） |
