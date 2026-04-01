from app.schemas.entities import A2UIChunk, ChatStreamChunk, MessageChunk
from app.schemas.requests import ChatRequest


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

