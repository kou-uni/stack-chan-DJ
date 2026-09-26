# -*- coding: utf-8 -*-
"""gateway が mDNS に載せる IP。**同じ LAN から届くものだけ。**

★2026-09-26：Tailscale.app が上がった夜から、実機が一度も gateway に来なくなった。
  広告に 100.88.x（Tailscale）が混ざっていた。実機はそこへ繋ぎに行って戻らない。
"""
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "vendor" / "stackchan-mcp" / "gateway"))

import pytest

adv = pytest.importorskip("stackchan_mcp.mdns_advertiser")


def test_Tailscaleの帯は載せない():
    got = adv._select_advertised_addresses([("192.168.0.179", 24), ("100.88.34.66", 32), ("192.168.0.123", 24)])
    assert "100.88.34.66" not in got
    assert set(got) == {"192.168.0.179", "192.168.0.123"}


def test_LANがあるなら他は載せない():
    got = adv._select_advertised_addresses([("203.0.113.5", None), ("192.168.0.179", 24)])
    assert got == ["192.168.0.179"]


def test_LANが無ければ従来どおり残す():
    """★何も載らないより、届くかもしれないものを載せる。"""
    got = adv._select_advertised_addresses([("203.0.113.5", None)])
    assert got == ["203.0.113.5"]
