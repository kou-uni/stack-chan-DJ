# 運用手順

## 起動（順番が重要）

```bash
cd ~/stackchan-lab

# 1. OTAスタブ（これが無いと実機が6桁コードで止まる）
./.venv/bin/python scripts/ota_stub.py --port 8778 &

# 2. gateway（8775=実機 / 8767=MCP / 8776=写真）
./scripts/gateway.sh &

# 3. 実機の電源を入れる → 自動で繋がる

# 4. コンソール
./.venv/bin/python app/dj/console.py --beat --led-pattern wave --led-brightness 1.0
```

**★ gateway より先に console を上げない。** `beat_mode_start` が motion を有効にして
始まるので、モード設定が上書きされる。

## 操作

| 操作 | 割り当て |
|---|---|
| **PLAY**（左デッキ） | DJモード **ON** |
| **MASTER**（中央・ロゴ下） | DJモード **OFF**（何度押してもOFF） |
| つまみ（ch6 #23） | 首を左右に。触っている間は優先 |
| つまみ（ch0 #15） | うなずき |
| パッド #4〜#7 | 笑う／驚く／恥ずかしがる／しょんぼり |
| 頭を撫でる | 照れる（モードは変わらない） |

## 会場での調整（サウンドチェック時）

```bash
# 1. 実際にかける曲を流しながら、耳が何を聞いているか測る
./.venv/bin/python scripts/hear.py --sec 8

# 2. 感度を自動で選ぶ
./.venv/bin/python scripts/tune_beat.py
```

`hear.py` の見どころは **「平均の1.65倍を超える山が毎秒何回か」**。
1.2回/秒を下回ると踊らない。RMSだけ見ても分からない。

**実測の目安**（この部屋 / 2026-09-08）

| | 音量(RMS) |
|---|---|
| 無音 | 0.0035 |
| 会場想定の曲 | 0.005〜0.009 |
| サーボが動いている間 | **0.16**（音楽の13倍） |

## 詰まったとき

| 症状 | 原因と対処 |
|---|---|
| 実機が繋がらない | OTAスタブが落ちている。`curl http://127.0.0.1:8778/` |
| 6桁コードが画面に出る | 同上 |
| 踊らない | `hear.py` で音量を測る。0.0045未満なら音量不足 |
| 踊り続けて止まらない | サーボ音を拾っている。`--listen-check-s` を短く |
| LEDが光らない | `stackchan_follow_led_stream` の `status` で `frames_dropped` を見る |
| 首が変な方を向く | **pitch は「45からの差」で送る。** 45を送ると90→85にクランプされ真下 |
| 設定を変えたのに反映されない | プロセスを `pkill -9` してから起動。起動時刻をファイル更新時刻と比べる |

## 検証の型

**「直した」と言う前に、必ず実機の角度を測る。**

```bash
./.venv/bin/python - <<'PY'
import serial, time, re
s=serial.Serial("/dev/cu.usbmodem201101",115200,timeout=0.2); s.reset_input_buffer()
buf,t0=b"",time.time()
while time.time()-t0<8: buf+=s.read(4096)
s.close()
v=[re.search(r"yaw=(-?\d+).*?pitch=(\d+)",l).groups() for l in
   buf.decode("utf-8","replace").splitlines() if "set_head_angles" in l
   and re.search(r"yaw=(-?\d+).*?pitch=(\d+)",l)]
ys=[int(a) for a,b in v]; ps=[int(b) for a,b in v]
print(f"{len(v)}件  yaw {min(ys)}〜{max(ys)}  pitch {min(ps)}〜{max(ps)} (45=正面)")
PY
```


## 会場での立ち上げ（テザリング）

**家と会場で変わるのは3つ。**

| | 家 | 会場 |
|---|---|---|
| 母艦 | Mac Studio | **MacBook** |
| 網 | 自宅Wi-Fi（有線もあり） | **iPhone のテザリング** |
| IP | だいたい固定 | **毎回変わる** |

**だから IP を覚えない。名前で開く。**

    http://stackchan.local:8779/     ← iPad はいつでもこれ

`stackchan.local` は console が mDNS で名乗る。**どの Mac で動かしても同じ名前**になる。
IP が変わったら（家 → テザリング）**自動で名乗り直す**。

### 順番

    ① iPhone のテザリングをON（2.4GHz を有効に）
    ② MacBook をテザリングに繋ぐ
    ③ console を立ち上げる          ← 端末に QR が出る
    ④ iPad をテザリングに繋ぐ → QR を読む
    ⑤ スタックチャンの電源を入れる  ← 最後でよい
    ⑥ DDJ-FLX2 を MacBook に挿す    ← いつでもよい

**★③と⑤の順番は自由。** console は実機を待ちながら画面を出す。
設営中に iPad だけ先に出しておける。

**★実機は 2.4GHz にしか乗らない。** テザリングの「最大互換性」をONにする。

### 会場で確認すること

    ./.venv/bin/python scripts/doctor.py

全部 ○ になってから曲を流す。**× があるまま始めない。**

### 名前で開けないとき

テザリングによっては mDNS が通らないことがある。そのときは端末に出る IP を直接使う。

    起動時のログ:  （届かないときは http://172.20.10.x:8779/ ）

## 困ったら健康診断

    ./.venv/bin/python scripts/doctor.py          点検だけ
    ./.venv/bin/python scripts/doctor.py --fix    直せるものは直す

9項目を見て、直せるものは直す（購読のやり直し・beat mode・表情・console の起動）。
終了コードは 0＝問題なし / 1＝直っていないものがある。

## 表情が既定の顔に戻ったとき

**実機の電源を切ると、自作の表情は消える**（PSRAM に載せているため）。

console を起動し直せば自動で読み込む。ログにこう出ていれば入っている。

    表情を読み込みました: avatar_layered.raw（537,600 バイト）

console を止めずに入れ直したいときは `scripts/reload_avatar.py` を実行する。

恒久的に焼き込む手順は docs/learnings.md の「表情が電源で消える件」を参照。


## 立ち上げ・立ち下げ

### 常駐にしてある場合（推奨）

    ./scripts/service.sh install     一度だけ。以後ログイン時に自動で上がる

**普段やることは「スタックチャンの電源を入れる」だけ。**
console は実機が来るまでずっと待っていて、電源が入った瞬間に繋がる。

    ./scripts/service.sh status      いまの状態
    ./scripts/service.sh restart     入れ直す
    ./scripts/service.sh logs        ログを追う
    ./scripts/service.sh uninstall   常駐をやめる

落ちても20〜40秒で自動復帰する（実測）。

### 手で立ち上げる場合

    ./scripts/gateway.sh                          # 1. gateway（別ターミナルで出しっぱなし）
    ./.venv/bin/python scripts/status.py          # 2. 実機が繋がっているか見る
    ./.venv/bin/python app/dj/console.py          # 3. console

console は実機が繋がるまで最大20秒待つ。居なければはっきり止まる。
表情は起動時に自動で読み込む。

### 立ち下げ

    ./scripts/stop.sh

Ctrl-C でも同じ。**3〜4秒で片付いて終わる。**

    止めています …
    片付けました（beat停止・購読解除・正面・待機顔）

**`kill -9` は使わない。** 片付けが1つも走らず、実機は踊ったまま、
gateway は購読したまま残る。

### 片付いたか確かめる

    ./.venv/bin/python scripts/status.py

全部 × なら片付いている。× のまま残っていたら、console を立ち上げ直して
もう一度 `stop.sh` で落とせば戻る。
