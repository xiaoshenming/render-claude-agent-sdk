"""Public SDK response lifecycle with deterministic same-task disconnect."""

from contextlib import asynccontextmanager

from claude_agent_sdk import ClaudeSDKClient


@asynccontextmanager
async def closing_query(iterator):
    try:
        yield iterator
    finally:
        close = getattr(iterator, "aclose", None)
        if close is not None:
            await close()


async def managed_query(*, prompt, options):
    # receive_response ends at ResultMessage. Leaving the public client
    # context disconnects the transport without waiting for stream EOF.
    async with ClaudeSDKClient(options=options) as client:
        await client.query(prompt)
        async for message in client.receive_response():
            yield message
