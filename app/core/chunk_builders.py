from app.core.shopping_flow.final_summary import generate_final_summary_with_llm
from app.core.shopping_flow.product_filters import (
    apply_product_filters,
    parse_budget_bounds as _parse_budget_bounds,
    parse_vnd_amount as _parse_vnd_amount,
)
from app.core.shopping_flow.stream import stream_shopping_agent
from app.core.shopping_flow.ui_chunks import (
    build_interactive_product_chunk as _build_interactive_product_chunk,
    build_questionnaire_chunk as _build_questionnaire_chunk,
)
from app.schemas.entities import A2UIChunk, ChatStreamChunk, MessageChunk
from app.schemas.requests import ChatRequest
# Legacy function kept for compatibility with adk_client flow.
def build_hidden_event_chunks(payload: ChatRequest) -> list[ChatStreamChunk]:
    if payload.hidden_events is None:
        return []
    return [
        A2UIChunk(
            a2ui={
                "action": payload.hidden_events.action,
                "payload": payload.hidden_events.payload,
                "status": "handled",
            }
        ),
        MessageChunk(content="Da xu ly hidden event thanh cong."),
    ]
__all__ = [
    "stream_shopping_agent",
    "build_hidden_event_chunks",
    "_build_questionnaire_chunk",
    "_build_interactive_product_chunk",
    "_parse_vnd_amount",
    "_parse_budget_bounds",
    "apply_product_filters",
    "generate_final_summary_with_llm",
]
