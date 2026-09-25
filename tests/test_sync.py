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
