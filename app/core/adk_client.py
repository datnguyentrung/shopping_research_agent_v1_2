import asyncio
from collections.abc import AsyncIterator

from app.core.chunk_builders import build_hidden_event_chunks
from app.core.orchestrator_runtime import get_flow_runtime
from app.schemas.entities import ChatStreamChunk, MessageChunk
from app.schemas.requests import ChatRequest

_flow_runtime = get_flow_runtime()


async def stream_chat_chunks(payload: ChatRequest) -> AsyncIterator[ChatStreamChunk]:
    """Generate response chunks in a format compatible with FE SSE consumer."""
    if payload.hidden_events:
        for chunk in build_hidden_event_chunks(payload):
            yield chunk
            await asyncio.sleep(0.02)
        return

    message = payload.message.strip()
    if not message:
        return

    async for text in _flow_runtime.stream_text(message):
        yield MessageChunk(content=text)
        await asyncio.sleep(0.02)
