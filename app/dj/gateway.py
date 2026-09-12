#!/usr/bin/env python3
"""gateway（MCP）への口。

console.py から切り出した。**振る舞いは1行も変えていない。**
"""
from __future__ import annotations

import json

import websockets


import contextlib

from mcp import ClientSession
from mcp.client.streamable_http import streamablehttp_client


class Gateway:
    """MCP ツールを呼ぶ薄いラッパ。--dry-run ならログに出すだけ。"""

    def __init__(self, url: str, dry_run: bool = False):
        self.url, self.dry_run = url, dry_run
        self._session: ClientSession | None = None
        self._stack: contextlib.AsyncExitStack | None = None

    async def __aenter__(self):
        if self.dry_run:
            print("── dry-run: gateway には繋ぎません ──")
            return self
        self._stack = contextlib.AsyncExitStack()
        read, write, _ = await self._stack.enter_async_context(
            streamablehttp_client(self.url))
        self._session = await self._stack.enter_async_context(
            ClientSession(read, write))
        await self._session.initialize()
        print(f"gateway に接続: {self.url}")
        return self

    async def __aexit__(self, *exc):
        if self._stack:
            await self._stack.aclose()

    async def call(self, name: str, **args):
        if self.dry_run or self._session is None:
            print(f"    → {name}({', '.join(f'{k}={v}' for k, v in args.items())})")
            return None
        try:
            return await self._session.call_tool(name, args)
        except Exception as exc:
            print(f"    ! {name} が失敗: {exc}")
            return None


