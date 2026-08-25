"""Explicit Claude client lifecycle regression coverage."""

from __future__ import annotations

import anyio
import pytest

from manim_quality.agents._claude_client import ExplicitClientQuery


class FakeClient:
    def __init__(self, options, *, fail_receive: bool = False) -> None:
        self.options = options
        self.fail_receive = fail_receive
        self.events: list[object] = []

    async def connect(self) -> None:
        self.events.append("connect")

    async def query(self, prompt: str) -> None:
        self.events.append(("query", prompt))

    async def receive_response(self):
        self.events.append("receive")
        yield "message"
        if self.fail_receive:
            raise RuntimeError("receive failed")

    async def disconnect(self) -> None:
        self.events.append("disconnect")


def test_explicit_client_disconnects_after_complete_response() -> None:
    created: list[FakeClient] = []

    def factory(options):
        client = FakeClient(options)
        created.append(client)
        return client

    async def collect():
        query = ExplicitClientQuery(client_factory=factory)
        return [item async for item in query(prompt="review", options="opts")]

    assert anyio.run(collect) == ["message"]
    assert created[0].events == [
        "connect",
        ("query", "review"),
        "receive",
        "disconnect",
    ]


def test_explicit_client_disconnects_after_receive_failure() -> None:
    client = FakeClient("opts", fail_receive=True)

    async def collect():
        query = ExplicitClientQuery(client_factory=lambda options: client)
        return [item async for item in query(prompt="review", options="opts")]

    with pytest.raises(RuntimeError, match="receive failed"):
        anyio.run(collect)

    assert client.events[-1] == "disconnect"
