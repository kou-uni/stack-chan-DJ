# archive — 役目を終えた文書

**ここは読むためではなく、経緯を辿るために置いてある。**
**更新しない。** ここを直すくらいなら、生きている方を直す。

移した基準はひとつ。

> **その文書が「これから何をするか」を決めているか。**
> 決めていないなら（＝もう決まって、やり終えたなら）ここへ来る。

| 文書 | 何だったか | いま見るべき先 |
|---|---|---|
| `project-plan.md` | PM視点の計画 | [../../ROADMAP.md](../../ROADMAP.md) |
| `refactor-plan.md` | 2026-09-09 のリファクタ計画 | 完了。設計は [../architecture.md](../architecture.md) |
| `beat-detection-review.md` | 2026-09-08 の曲判定の追い込み | [../learnings.md](../learnings.md) |
| `setup-day1.md` | 出荷時ファームで基準を取る手順 | 完了。[../firmware-flash.md](../firmware-flash.md) |
| `firmware-strategy.md` | 焼くファームの5択比較 | 決着済み（xiaozhi系＋stackchan-mcp） |

## 移すときの決まり

- **消さない。** 判断の根拠がここにしか無いことがある
- `git mv` で移す。**履歴を切らない**
- 生きている文書からのリンクは `archive/` 付きに張り替える
- このファイルの表に1行足す。**行き先（いま見るべき先）を必ず書く**
