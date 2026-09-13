# 会話サーバを自宅Macで動かす（Phase 4 / Step 7）

**2026-09-13 達成。** Apple Silicon で**Dockerを使わず**動いた。

    ws://192.168.0.123:8000/xiaozhi/v1/     ← 本体の接続先
    http://192.168.0.123:8003/xiaozhi/ota/  ← OTA/設定

## 何をどこで動かしているか

| | 選んだもの | どこで動くか |
|---|---|---|
| 音声区間検出 | SileroVAD | ローカル |
| 音声認識 | FunASR / SenseVoiceSmall | **ローカル**（`models/` に893MB） |
| 頭脳 | Ollama `qwen2.5:3b` | **ローカル**（localhost:11434） |
| 音声合成 | macOS `say`（自前の窓口） | **ローカル** |
| 記憶 | mem_local_short | **ローカル** |

★**既定のままだと EdgeTTS（Microsoft）へ音声を送る。**
このイベントの中心は「声も映像も、この部屋から出ない」なので、
既定で使うと**配布物に書いた約束を破る。**

ローカルで動く TTS の選択肢（fishspeech / gpt_sovits / paddle_speech）は
どれも**別のサーバを1本立てる**必要があり、締切に対して割に合わない。
macOS には最初から日本語の音声合成が入っている。**それを窓口にした。**

    app/voice/say_server.py     # say → wav を返すだけ。127.0.0.1 のみで待つ

## 置き場所と手順

```bash
# 1) 本体（このリポジトリには入れない。vendor は外に置く）
~/xiaozhi-esp32-server/main/xiaozhi-server

# 2) Python は 3.11。★3.14 では torch 2.2.2 が入らない
brew install python@3.11
/opt/homebrew/opt/python@3.11/bin/python3.11 -m venv .venv311
./.venv311/bin/python -m pip install -r requirements-mac.txt

# 3) 音声認識のモデル（893MB）
./.venv311/bin/python -c "from modelscope.hub.file_download import model_file_download as d; \
  d(model_id='iic/SenseVoiceSmall', file_path='model.pt', local_dir='models/SenseVoiceSmall')"

# 4) ローカルTTSの窓口
cd ~/stackchan-lab && ./.venv/bin/python app/voice/say_server.py

# 5) 会話サーバ
cd ~/xiaozhi-esp32-server/main/xiaozhi-server && ./.venv311/bin/python app.py
```

設定は `app/voice/xiaozhi-config.yaml`（本体の `data/.config.yaml` に置く）。

## 詰まったところ

- **`vosk==0.3.45` に macOS arm64 の wheel が無い。** 0.3.44 に落とす
  （vosk は使わない ASR の選択肢。入れないと pip 全体が止まる）
- `python -m modelscope` は実行できない。**API を直に呼ぶ**
- Python 3.14 では torch 2.2.2 が入らない。3.11 を別に入れる

## 次（Step 8：宅内で会話する）★未着手

本体の接続先を `ws://<MacのLAN IP>:8000/xiaozhi/v1/` に変える。

⚠️ **ここで制御（8765/8770/8771）が生きているかを確かめる。**
会話と制御の2本を同時に持てるかは未検証（`questions/stackchan-dual-connection`）。
**無理ならモード切替で割り切る。** 先に接続先を変えると、
DJの仕込みが全部止まる可能性がある。**当日までに戻せる形でやること。**
