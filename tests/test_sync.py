# -*- coding: utf-8 -*-
"""「この機械で直したものは、もう1台に伝わるか」

★当日は MacBook、家では Mac Studio。**同じものを2回直すと、片方が必ず古くなる。**
  方針（コードは1本・機械ごとに変えるのは設定だけ）を、**落ちる形で固定する。**
"""
import importlib.util
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
_spec = importlib.util.spec_from_file_location("sync_check", ROOT / "scripts" / "sync_check.py")
sc = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(sc)


def test_調整した値が機械の中だけに残っていない():
    """★`.env.gateway` は git に入らない。**ここで調整すると伝わらない。**

    秘密は入っていないので、**調整は見本（git）の側に書く。**
    """
    assert sc.env_drift() == []


def test_他人のコードへの改変が差分として取り出してある():
    """★`vendor/` に置いたままだと、別の機械で復元できない。"""
    assert sc.vendor_drift() == []


def test_置き去りのファイルが無い():
    """★作り直せないのに git に無いものは、**手で運ぶことになる。**"""
    assert sc.stray_files() == []


def test_見本に秘密を書いていない():
    """★見本は git に入る。**調整を書く場所であって、鍵を書く場所ではない。**"""
    import re
    ex = ROOT / ".env.gateway.example"
    if not ex.exists():
        return
    spec = importlib.util.spec_from_file_location("ss", ROOT / "scripts" / "secret_scan.py")
    ss = importlib.util.module_from_spec(spec); spec.loader.exec_module(ss)
    assert ss.scan([ex]) == []


def test_生成できるものは持ち運ばない():
    """★表情の画像は `make_faces.py` から作り直せる。**git に入れない。**

    入れると、直すたびに2箇所（コードと画像）を揃えることになる。
    """
    assert (ROOT / "app" / "avatar" / "make_faces.py").exists()
    tracked = sc.sh("git", "ls-files", "app/avatar/").splitlines()
    assert not [p for p in tracked if p.endswith((".png", ".raw"))], \
        "生成物が git に入っている"


def test_台本は配る場所に置かない():
    """★台本を参加者に渡すと、**F の回収（伏線）が前半で割れる。**

    `docs/pages/` は `/p` で一覧になる＝配る場所。**そこに置かない。**
    """
    from pathlib import Path
    pages = {p.name for p in (ROOT / "docs" / "pages").glob("*.html")}
    assert "text.html" not in pages, "台本が配る場所に出ている"
    assert (ROOT / "event" / "kamishibai" / "text.js").exists()


def test_OTAスタブは常駐に入っている():
    """★2026-09-26：手で `&` 起動していたスタブが死んで、実機が半日 gateway に来なかった。
    実機は起動時に ota_url へ問い合わせ、**通るまで WebSocket に来ない。**
    常駐の一員でなければ、Mac を再起動した日に必ず再発する。"""
    s = (ROOT / "scripts" / "service.sh").read_text(encoding="utf-8")
    assert "ota_stub.py" in s and "com.uni.stackchan.ota" in s
    st = (ROOT / "scripts" / "status.py").read_text(encoding="utf-8")
    assert "8778" in st, "status.py がスタブを見ていない"


def test_VOICEVOXも常駐に入っている():
    """★2026-09-26：手で & 起動していた VOICEVOX が死んでいて、撫でも NFC も無言だった。
    OTA スタブと同じ形。**手で立てたものは、いつか止まって、誰も気づかない。**"""
    s = (ROOT / "scripts" / "service.sh").read_text(encoding="utf-8")
    assert "voicevox/macos-arm64/run" in s and "com.uni.stackchan.voice" in s
    assert "50021" in (ROOT / "scripts" / "status.py").read_text(encoding="utf-8")


def test_質疑応答botのモデルを新しいMacでも落とす():
    """★bootstrap は think-model しか落としていなかった。qwen2.5:14b が無いと当日 bot が黙る（2026-09-29）。"""
    import sys
    sys.path.insert(0, str(ROOT / "app" / "dj"))
    import ask
    pull = (ROOT / "scripts" / "pull-models.sh").read_text(encoding="utf-8")
    assert "ask.DEFAULT_MODEL" in pull, "pull-models.sh が質疑応答のモデル名を ask.py から取っていない"
    assert ask.DEFAULT_MODEL.startswith("qwen2.5")
    for name in ("bootstrap.sh", "sync.sh"):
        assert "pull-models.sh" in (ROOT / "scripts" / name).read_text(encoding="utf-8"), f"{name} が pull-models.sh を呼んでいない"


def test_頭なでの受け口を新しいMacでも置く():
    """★notify.yml は機械ごとのホーム直下。git にも bootstrap にも無く、新しい Mac では頭なでが黙る（2026-09-29）。"""
    tpl = (ROOT / "config" / "notify.yml.example").read_text(encoding="utf-8")
    assert "jsonl:" in tpl and "enabled: true" in tpl.split("jsonl:", 1)[1].split("\n", 2)[1]
    for name in ("bootstrap.sh", "sync.sh"):
        assert "ensure-notify.sh" in (ROOT / "scripts" / name).read_text(encoding="utf-8"), f"{name} が ensure-notify.sh を呼んでいない"
