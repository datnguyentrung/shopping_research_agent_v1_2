import traceback
import uuid

from app.memory.session_store import get_or_create_session
from app.schemas.entities import A2UIChunk, MessageChunk
from app.schemas.requests import ChatRequest

from app.core.shopping_flow.handlers.category_drilldown import handle_category_drilldown
from app.core.shopping_flow.handlers.initial import handle_initial_phase
from app.core.shopping_flow.handlers.product_swipe import handle_product_swipe
from app.core.shopping_flow.handlers.questionnaire import handle_questionnaire
from app.utils.trace_log import chunk_summary, short_preview, trace_print


PHASE_EVENT_HANDLERS = {
    "CATEGORY_DRILLDOWN": handle_category_drilldown,
    "QUESTIONNAIRE": handle_questionnaire,
    "PRODUCT_SWIPE": handle_product_swipe,
}


async def stream_shopping_agent(payload: ChatRequest):
    """Route user conversation through explicit phase handlers.

    Design note:
    - We use a State-style dispatch map (phase -> handler) to keep each phase isolated.
    - This removes a very long if/elif chain and makes flow updates safer.
    """
    session_id = getattr(payload, "sessionId", None) or str(uuid.uuid4())
    session = get_or_create_session(session_id)
    session["_trace_id"] = session_id

    trace_print(
        session_id,
        "stream_shopping_agent",
        "enter",
        messagePreview=short_preview(payload.message),
        hasHiddenEvents=payload.hidden_events is not None,
        currentPhase=session.get("phase"),
    )

    if not payload.hidden_events:
        trace_print(session_id, "stream_shopping_agent", "dispatch_initial_phase")
        chunk_idx = 0
        async for chunk in handle_initial_phase(payload, session):
            chunk_idx += 1
            trace_print(
                session_id,
                "stream_shopping_agent",
                "yield_chunk",
                source="handle_initial_phase",
                index=chunk_idx,
                chunk=chunk_summary(chunk),
            )
            yield chunk
        trace_print(session_id, "stream_shopping_agent", "initial_phase_completed", yielded=chunk_idx)
        return

    action = payload.hidden_events.action
    data = payload.hidden_events.payload

    trace_print(
        session_id,
        "stream_shopping_agent",
        "hidden_event_received",
        action=action,
        dataPreview=short_preview(data),
    )

    try:
        phase = session.get("phase")
        trace_print(session_id, "stream_shopping_agent", "phase_resolved", phase=phase)

        if phase == "PRODUCT_SWIPE":
            chunk_idx = 0
            async for chunk in handle_product_swipe(session, session_id, action, data):
                chunk_idx += 1
                trace_print(
                    session_id,
                    "stream_shopping_agent",
                    "yield_chunk",
                    source="handle_product_swipe",
                    index=chunk_idx,
                    chunk=chunk_summary(chunk),
                )
                yield chunk
            trace_print(session_id, "stream_shopping_agent", "product_swipe_completed", yielded=chunk_idx)
            return

        phase_handler = PHASE_EVENT_HANDLERS.get(phase)
        if phase_handler:
            trace_print(
                session_id,
                "stream_shopping_agent",
                "dispatch_phase_handler",
                phase=phase,
                handler=phase_handler.__name__,
            )
            chunk_idx = 0
            async for chunk in phase_handler(payload, session, action, data):
                chunk_idx += 1
                trace_print(
                    session_id,
                    "stream_shopping_agent",
                    "yield_chunk",
                    source=phase_handler.__name__,
                    index=chunk_idx,
                    chunk=chunk_summary(chunk),
                )
                yield chunk
            trace_print(
                session_id,
                "stream_shopping_agent",
                "phase_handler_completed",
                phase=phase,
                yielded=chunk_idx,
            )
        else:
            trace_print(
                session_id,
                "stream_shopping_agent",
                "no_phase_handler",
                phase=phase,
                action=action,
            )
            # Emit a lightweight ack so FE can observe hidden-event roundtrip.
            yield A2UIChunk(
                a2ui={
                    "type": "a2ui_hidden_event_status",
                    "data": {
                        "status": "ignored",
                        "phase": phase,
                        "action": action,
                    },
                }
            )
    except Exception as exc:
        print(f"Error in hidden event processing: {exc}")
        traceback.print_exc()
        trace_print(
            session_id,
            "stream_shopping_agent",
            "error",
            phase=session.get("phase"),
            action=action,
            errorType=type(exc).__name__,
            error=str(exc),
        )
        yield MessageChunk(content=f"Có lỗi xảy ra: {str(exc)}")
        session["phase"] = "ERROR"
