"""Explicit Claude SDK client lifecycle for production queries."""

from __future__ import annotations

from collections.abc import AsyncIterator, Callable

import anyio
from claude_agent_sdk import ClaudeAgentOptions, ClaudeSDKClient

ClientFactory = Callable[[ClaudeAgentOptions], ClaudeSDKClient]


class ExplicitClientQuery:
    """Expose an explicit client session through the legacy query callable ABI."""

    def __init__(self, client_factory: ClientFactory = ClaudeSDKClient) -> None:
        self._client_factory = client_factory

    def __call__(
        self, *, prompt: str, options: ClaudeAgentOptions
    ) -> AsyncIterator[object]:
        return self._stream(prompt, options)

    async def _stream(
        self, prompt: str, options: ClaudeAgentOptions
    ) -> AsyncIterator[object]:
        client = self._client_factory(options)
        await client.connect()
        try:
            await client.query(prompt)
            async for message in client.receive_response():
                yield message
        finally:
            with anyio.CancelScope(shield=True):
                await client.disconnect()
