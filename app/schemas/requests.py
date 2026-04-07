from typing import Any

from pydantic import BaseModel, Field, model_validator


class HiddenEventRequest(BaseModel):
    action: str = Field(..., min_length=1)
    payload: Any = None


class ChatRequest(BaseModel):
    message: str = ""
    sessionId: str | None = None  # Session ID để maintain state giữa các request
    hidden_events: HiddenEventRequest | None = None

    @model_validator(mode="after")
    def validate_payload(self) -> "ChatRequest":
        if not self.message.strip() and self.hidden_events is None:
            raise ValueError("Either message or hidden_events is required")
        return self


class SearchRequest(BaseModel):
    keyword: str = Field(..., min_length=1)
    category_filter: str | None = None


# Schema API đầu vào của user