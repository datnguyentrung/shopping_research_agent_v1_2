import json
import os
from datetime import datetime
from functools import lru_cache
from typing import Any


_TRUE_VALUES = {"1", "true", "yes", "y", "on"}


@lru_cache(maxsize=1)
def is_trace_stream_enabled() -> bool:
    raw = os.getenv("TRACE_STREAM", "false")
    return str(raw).strip().lower() in _TRUE_VALUES


def refresh_trace_stream_flag() -> None:
    is_trace_stream_enabled.cache_clear()


def trace_plain(message: str) -> None:
    if not is_trace_stream_enabled():
        return
    print(message)


def short_preview(value: Any, max_len: int = 240) -> str:
    text = str(value)
    if len(text) <= max_len:
        return text
    return text[:max_len] + "..."


def product_summary(product: Any) -> dict[str, Any]:
    product_dict = product.model_dump(by_alias=False) if hasattr(product, "model_dump") else product
    if not isinstance(product_dict, dict):
        return {"raw": short_preview(product_dict)}

    return {
        "productId": product_dict.get("product_id") or product_dict.get("productId") or product_dict.get("id"),
        "name": product_dict.get("name"),
        "priceCurrent": product_dict.get("price_current") or product_dict.get("priceCurrent"),
        "ratingStar": product_dict.get("rating_star") or product_dict.get("ratingStar"),
        "platform": product_dict.get("platform"),
    }


def chunk_summary(chunk: Any) -> dict[str, Any]:
    summary = {"modelType": type(chunk).__name__}
    if not hasattr(chunk, "model_dump"):
        summary["preview"] = short_preview(chunk)
        return summary

    payload = chunk.model_dump(exclude_none=True, by_alias=True)
    summary["rootType"] = payload.get("type")
    a2ui_payload = payload.get("a2ui") or {}
    if isinstance(a2ui_payload, dict):
        summary["a2uiType"] = a2ui_payload.get("type")
        product = (a2ui_payload.get("data") or {}).get("product") if isinstance(a2ui_payload.get("data"), dict) else None
        if isinstance(product, dict):
            summary["productId"] = product.get("productId") or product.get("product_id")
            summary["productName"] = product.get("name")
    return summary


def trace_print(trace_id: str, component: str, stage: str, **details: Any) -> None:
    if not is_trace_stream_enabled():
        return

    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S.%f")[:-3]
    print(f"[trace][{timestamp}][{trace_id}][{component}][{stage}]")
    if details:
        print(json.dumps(details, ensure_ascii=False, indent=2, default=str))
