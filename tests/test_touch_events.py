"""頭なでの受け取り。

★2026-09-12 の切り分け：
  実機は撫でられると**通知を送っている**（stackchan-event / stroke / duration_ms）。
  ところが `get_touch_state` は通知を保存しないので、**永遠に idle** を返す。
  **「問い合わせて読む」と思い込んで、ポーリングしていた。** 実際は押し出し型。

★しかも通知の届け先は**既定で全部 false**。開けないとどこにも届かない。
"""
import json
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "app" / "dj"))
from touch_events import TouchEvents   # noqa: E402


def _write(p, **kw):
    row = {"event_type": "touch", "subtype": "stroke", "duration_ms": 900,
           "ts": 1, "ts_unix": time.time(), "session_id": "s", "action": "head_stroke"}
    row.update(kw)
    with p.open("a", encoding="utf-8") as f:
        f.write(json.dumps(row) + "\n")


def test_新しい撫でを拾う(tmp_path):
    p = tmp_path / "e.jsonl"
    te = TouchEvents(p)
    te.catch_up()                       # 起動時点までは「読んだこと」にする
    assert te.poll() is None
    _write(p)
    ev = te.poll()
    assert ev and ev["subtype"] == "stroke"


def test_同じ撫でを二度返さない(tmp_path):
    """★二度返すと、会話が二回起動する。"""
    p = tmp_path / "e.jsonl"
    te = TouchEvents(p); te.catch_up()
    _write(p)
    assert te.poll() is not None
    assert te.poll() is None


def test_起動前の古い記録は無視する(tmp_path):
    """★起動した瞬間に、過去の撫でで会話が始まると事故になる。"""
    p = tmp_path / "e.jsonl"
    _write(p, ts_unix=time.time() - 3600)
    te = TouchEvents(p); te.catch_up()
    assert te.poll() is None


def test_ファイルが無くても落ちない(tmp_path):
    """★通知の設定を開け忘れることがある。**黙って落ちない。**"""
    te = TouchEvents(tmp_path / "ない.jsonl")
    te.catch_up()
    assert te.poll() is None


def test_壊れた行を飛ばす(tmp_path):
    p = tmp_path / "e.jsonl"
    te = TouchEvents(p); te.catch_up()
    with p.open("a", encoding="utf-8") as f:
        f.write("これはJSONではない\n")
    _write(p)
    ev = te.poll()
    assert ev and ev["subtype"] == "stroke"


def test_古すぎる撫では無視する(tmp_path):
    """★長く止まっていた間の撫でを、復帰した瞬間にまとめて処理しない。"""
    p = tmp_path / "e.jsonl"
    te = TouchEvents(p, max_age_s=10.0); te.catch_up()
    _write(p, ts_unix=time.time() - 60)
    assert te.poll() is None


def test_通知の設定が開いているか見られる():
    """★既定は全部 false。開いていないと**永遠に何も来ない**。"""
    from touch_events import notify_config_ok
    ok, why = notify_config_ok()
    assert isinstance(ok, bool) and isinstance(why, str)


def test_通知は指を離した瞬間に届く(tmp_path):
    """★2026-09-12 の学び。実測でこうなっていた。

        stroke  250899ms  ← 4分11秒ずっと1件
        stroke   75999ms  ← 1分16秒

    **撫でている間は届かない。離した瞬間に、長さつきで1件届く。**
    だから「撫でながら待つ」と、永遠に来ないように見える。

    ★長すぎるものは「置きっぱなし」なので、会話の合図にしない。
    """
    p = tmp_path / "e.jsonl"
    te = TouchEvents(p, max_stroke_ms=8000); te.catch_up()
    _write(p, duration_ms=250899)
    assert te.poll() is None, "置きっぱなしを合図にしている"
    _write(p, duration_ms=900)
    ev = te.poll()
    assert ev and ev["duration_ms"] == 900
