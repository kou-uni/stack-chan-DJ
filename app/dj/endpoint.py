#!/usr/bin/env python3
"""話し終わりの検出。**人は話し終わったら止まる。**

5秒固定で待つのが一番不自然だった（実測17.5秒のうち5秒が待ち時間）。
無音が続いたら切る。**これだけで体感が変わる。**

## 誤爆すると最悪

**言葉の途中の一瞬の間で切ったら、質問が半分になる。**
「ファームって……なんですか」の「……」で切ったら、もう取り返せない。

だから条件を3つ重ねる。

    ⓪ **最低これだけは録る**              … 人が話し出すまで1〜2秒かかる
    ① まず**一定以上しゃべった**こと      … 咳払いや物音で切らない
    ② そのあと**無音が続いた**こと        … 途中の短い間では切らない
    ③ どうであれ**上限で止める**          … 喋り続けられても終わる

## 閾値は実測から

実機のマイクは遠い。**声でもピーク 0.055**（2026-09-12 実測）。
汎用の閾値（0.05 など）を使うと、**全部が無音と判定される。**
"""
from __future__ import annotations

# これを超えたら「喋っている」。★実機の声は小さい。高くすると全部無音になる
SPEECH_LEVEL = 0.008


class Endpointer:
    """フレームごとの音量を見て、切るべき瞬間を返す。

    ★状態を持つだけ。実機も時計も触らない（試験できるように）。
    """

    def __init__(self, silence_s: float = 0.8, min_speech_s: float = 0.3,
                 max_s: float = 8.0, level: float = SPEECH_LEVEL,
                 min_total_s: float = 2.5):
        self.silence_s = silence_s
        self.min_speech_s = min_speech_s
        self.max_s = max_s
        # ★合図から話し出すまで、人は1〜2秒かかる（実測）。
        #   その前に切ると、物音や余韻を「喋った」と誤判定して1.6秒で終わる
        self.min_total_s = min_total_s
        self.level = level
        self.spoken_s = 0.0          # 喋っていた合計
        self._silence_from: float | None = None
        self._last_t = 0.0

    def feed(self, level: float, t: float) -> bool:
        """1フレーム分。**切るなら True。**

        level : そのフレームの音量（0..1）
        t     : 録音開始からの秒数
        """
        dt = max(0.0, t - self._last_t)
        self._last_t = t

        if level >= self.level:
            self.spoken_s += dt
            self._silence_from = None
        elif self._silence_from is None:
            self._silence_from = t

        # ③ 上限。喋り続けられても、いつかは切る
        if t >= self.max_s:
            return True

        # ⓪ 人が話し出すまでの時間は、とにかく待つ
        if t < self.min_total_s:
            return False

        # ① まず一定以上しゃべっていること
        if self.spoken_s < self.min_speech_s:
            return False

        # ② そのあと無音が続いたこと
        return (self._silence_from is not None
                and t - self._silence_from >= self.silence_s)
