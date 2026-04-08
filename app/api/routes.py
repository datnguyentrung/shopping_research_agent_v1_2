from collections.abc import AsyncIterator

from fastapi import APIRouter
from sse_starlette import EventSourceResponse

from app.core.adk_client import stream_chat_chunks
from app.core.chunk_builders import stream_shopping_agent
from app.schemas.requests import ChatRequest

router = APIRouter(prefix="/chat", tags=["chat"])


# app/api/routes.py

async def _event_generator(payload: ChatRequest) -> AsyncIterator[dict[str, str]]:
    try:
        async for chunk in stream_chat_chunks(payload):
            # Kiểm tra: Nếu chunk là một Pydantic Model (có model_dump_json)
            if hasattr(chunk, "model_dump_json"):
                yield {"data": chunk.model_dump_json(exclude_none=True, by_alias=True)}
            # Nếu chunk lỡ là string (do flow_runtime trả về text thô)
            elif isinstance(chunk, str):
                import json
                yield {"data": json.dumps({"type": "message", "content": chunk})}
            else:
                # Trường hợp bất khả kháng
                import json
                yield {"data": json.dumps({"type": "message", "content": str(chunk)})}

        yield {"data": "[DONE]"}
    except Exception as exc:
        # In traceback ra terminal để bạn dễ sửa code
        import traceback
        traceback.print_exc()

        # Gửi lỗi về cho giao diện một cách thân thiện
        from app.schemas.entities import ErrorChunk
        yield {"data": ErrorChunk(error="Hệ thống đang bận, vui lòng thử lại sau.").model_dump_json()}
        yield {"data": "[DONE]"}

@router.post("/stream")
async def stream_chat(payload: ChatRequest) -> EventSourceResponse:
    async def _event_generator():
        try:
            async for chunk in stream_shopping_agent(payload):
                if hasattr(chunk, "model_dump_json"):
                    yield {"data": chunk.model_dump_json(exclude_none=True, by_alias=True)}
            yield {"data": "[DONE]"}
        except Exception as exc:
            import traceback
            traceback.print_exc()
            from app.schemas.entities import ErrorChunk
            yield {"data": ErrorChunk(error=str(exc)).model_dump_json()}
            yield {"data": "[DONE]"}

    return EventSourceResponse(
        _event_generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )

# Các endpoint (vd: /run_sse, /chat)
