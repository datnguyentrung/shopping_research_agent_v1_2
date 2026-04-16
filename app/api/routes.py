from collections.abc import AsyncIterator
import json
import time
from datetime import datetime
from typing import Any

from fastapi import APIRouter
from sse_starlette import EventSourceResponse

from app.core.adk_client import stream_chat_chunks
from app.core.chunk_builders import stream_shopping_agent
from app.schemas.requests import ChatRequest
from app.schemas.entities import DoneChunk
from app.utils.trace_log import is_trace_stream_enabled

router = APIRouter(prefix="/chat", tags=["chat"])


def _trace_log(trace_id: str, stage: str, **details: Any) -> None:
    if not is_trace_stream_enabled():
        return

    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S.%f")[:-3]
    print(f"[chat/stream][{timestamp}][{trace_id}][{stage}]")
    if details:
        print(json.dumps(details, ensure_ascii=False, indent=2, default=str))


def _short_text(value: Any, max_len: int = 240) -> str:
    text = str(value)
    if len(text) <= max_len:
        return text
    return text[:max_len] + "..."


def _extract_product_preview(chunk_payload: dict[str, Any]) -> dict[str, Any] | None:
    if chunk_payload.get("type") != "a2ui":
        return None

    a2ui_payload = chunk_payload.get("a2ui") or {}
    if a2ui_payload.get("type") != "a2ui_interactive_product":
        return None

    product = (a2ui_payload.get("data") or {}).get("product") or {}
    return {
        "productId": product.get("productId") or product.get("product_id"),
        "name": product.get("name"),
        "priceCurrent": product.get("priceCurrent") or product.get("price_current"),
        "ratingStar": product.get("ratingStar") or product.get("rating_star"),
        "productUrl": product.get("productUrl") or product.get("product_url"),
    }


# app/api/routes.py
async def _event_generator(payload: ChatRequest) -> AsyncIterator[dict[str, str]]:
    try:
        async for chunk in stream_chat_chunks(payload):
            # Kiểm tra: Nếu chunk là một Pydantic Model (có model_dump_json)
            if hasattr(chunk, "model_dump_json"):
                yield {"data": chunk.model_dump_json(exclude_none=True, by_alias=True)}
            # Nếu chunk lỡ là string (do flow_runtime trả về text thô)
            elif isinstance(chunk, str):
                yield {"data": json.dumps({"type": "message", "content": chunk})}
            else:
                # Trường hợp bất khả kháng
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
        trace_id = payload.sessionId or f"anonymous-{id(payload)}"
        start_time = time.perf_counter()
        received_count = 0
        sent_count = 0
        product_count = 0

        _trace_log(
            trace_id,
            "request_received",
            messagePreview=_short_text(payload.message),
            messageLength=len(payload.message or ""),
            hasHiddenEvents=payload.hidden_events is not None,
            hiddenAction=getattr(payload.hidden_events, "action", None),
        )

        try:
            async for chunk in stream_shopping_agent(payload):
                received_count += 1
                chunk_type = type(chunk).__name__

                if hasattr(chunk, "model_dump"):
                    chunk_payload = chunk.model_dump(exclude_none=True, by_alias=True)
                    root_type = chunk_payload.get("type")
                    a2ui_type = (chunk_payload.get("a2ui") or {}).get("type")
                    product_preview = _extract_product_preview(chunk_payload)

                    _trace_log(
                        trace_id,
                        "chunk_received",
                        index=received_count,
                        modelType=chunk_type,
                        rootType=root_type,
                        a2uiType=a2ui_type,
                    )

                    if product_preview:
                        product_count += 1
                        _trace_log(
                            trace_id,
                            "product_selected",
                            index=received_count,
                            product=product_preview,
                        )

                    event_data = chunk.model_dump_json(exclude_none=True, by_alias=True)
                    sent_count += 1
                    _trace_log(
                        trace_id,
                        "chunk_sent_to_fe",
                        index=received_count,
                        sentCount=sent_count,
                        eventBytes=len(event_data.encode("utf-8")),
                        eventPreview=_short_text(event_data),
                    )
                    yield {"data": event_data}
                    continue

                _trace_log(
                    trace_id,
                    "chunk_skipped_non_pydantic",
                    index=received_count,
                    modelType=chunk_type,
                    rawPreview=_short_text(chunk),
                )

            _trace_log(
                trace_id,
                "stream_completed",
                receivedCount=received_count,
                sentCount=sent_count,
                productCount=product_count,
                elapsedMs=round((time.perf_counter() - start_time) * 1000, 2),
            )
            done_chunk = DoneChunk().model_dump_json(exclude_none=True, by_alias=True)
            sent_count += 1
            _trace_log(
                trace_id,
                "done_chunk_sent_to_fe",
                sentCount=sent_count,
                eventBytes=len(done_chunk.encode("utf-8")),
                eventPreview=_short_text(done_chunk),
            )
            yield {"data": done_chunk}
            _trace_log(trace_id, "done_sent")
            yield {"data": "[DONE]"}
        except Exception as exc:
            import traceback
            traceback.print_exc()
            _trace_log(
                trace_id,
                "stream_failed",
                errorType=type(exc).__name__,
                error=str(exc),
                receivedCount=received_count,
                sentCount=sent_count,
                productCount=product_count,
                elapsedMs=round((time.perf_counter() - start_time) * 1000, 2),
            )
            from app.schemas.entities import ErrorChunk
            yield {"data": ErrorChunk(error=str(exc)).model_dump_json()}
            _trace_log(trace_id, "error_chunk_sent")
            yield {"data": "[DONE]"}
            _trace_log(trace_id, "done_sent_after_error")

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
