import traceback
import uuid

from app.memory.session_store import get_or_create_session
from app.schemas.entities import MessageChunk
from app.schemas.requests import ChatRequest

from app.core.shopping_flow.handlers.category_drilldown import handle_category_drilldown
from app.core.shopping_flow.handlers.initial import handle_initial_phase
from app.core.shopping_flow.handlers.product_swipe import handle_product_swipe
from app.core.shopping_flow.handlers.questionnaire import handle_questionnaire


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
    session_id = getattr(payload, "sessionId", str(uuid.uuid4()))
    session = get_or_create_session(session_id)

    if not payload.hidden_events:
        async for chunk in handle_initial_phase(payload, session):
            yield chunk
        return

    action = payload.hidden_events.action
    data = payload.hidden_events.payload

    try:
        phase = session.get("phase")
        if phase == "PRODUCT_SWIPE":
            async for chunk in handle_product_swipe(session, session_id, action, data):
                yield chunk
            return

        phase_handler = PHASE_EVENT_HANDLERS.get(phase)
        if phase_handler:
            async for chunk in phase_handler(payload, session, action, data):
                yield chunk
    except Exception as exc:
        print(f"Error in hidden event processing: {exc}")
        traceback.print_exc()
        yield MessageChunk(content=f"Có lỗi xảy ra: {str(exc)}")
        session["phase"] = "ERROR"
