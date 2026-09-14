# docs — どれを更新し、どれを更新しないか

**2026-09-14 に整理した。** 数が増えて、どれが生きているか分からなくなったため。

## 更新し続けるもの

### 決めごと・設計

| 文書 | 役割 | いつ直すか |
|---|---|---|
| [00-concept.md](00-concept.md) | **一次資料。** 分割コピーしない | 前提が変わったとき |
| [requirements.md](requirements.md) | 与件と哲学。当日の主張の出どころ | 主張が動いたとき |
| [architecture.md](architecture.md) | 状態の設計と**どの機械で動くか**（§3.5） | 配置が動いたとき |
| [master-and-hybrid.md](master-and-hybrid.md) | **落ちたときの退避**（primary / standby） | ⚠️ 未実装・未実測 |

### 手を動かすとき

| 文書 | 役割 |
|---|---|
| [runbook.md](runbook.md) | 動かす・止める・確かめる |
| [firmware-flash.md](firmware-flash.md) | ファームを焼く |
| [wiring.md](wiring.md) | 物理の配線 |
| [dj-midi-map.md](dj-midi-map.md) | DJ機材の割り当て |
| [dj-sync.md](dj-sync.md) | 拍とDJ同期の考え方 |
| [remote-workbench.md](remote-workbench.md) | 外から焼き直す・戻す |
| [vendor-patches.md](vendor-patches.md) | vendor に当てた改変 |
| [conversation-server.md](conversation-server.md) | 会話サーバ（**当面使わない**。経緯つき） |

### 育てるもの

| 文書 | 役割 |
|---|---|
| [learnings.md](learnings.md) | **当日のテキストの素材。** 詰まって抜けたら、その場で書く |
| [ideas.md](ideas.md) | まだ決まっていない思いつき |
| [textbook.md](textbook.md) | 当日の教材 |
| [persona.md](persona.md) / [ux-conversation.md](ux-conversation.md) | 人格と会話のUX |
| [build-steps.md](build-steps.md) | フェーズの手順。⚠️ **ROADMAP と二重管理になりつつある** |

## 更新しないもの

[archive/](archive/) — 役目を終えた文書。**経緯を辿るために残してある。**

## 当日のもの

`../event/` に置いてある（進行・持ち物・口上・台本）。**ここから分割コピーしない。**

## 思考の側は Obsidian

判断・知見・未解決の問いは vault に切ってある（ハブ：`interests/stackchan-robot-app`）。
