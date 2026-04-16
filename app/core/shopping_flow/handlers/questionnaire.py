import traceback

from app.schemas.entities import A2UIChunk, MessageChunk
from app.schemas.requests import ChatRequest
from app.core.shopping_flow.phase_utils import search_and_prepare_stream
from app.core.shopping_flow.product_filters import parse_budget_bounds
from app.core.shopping_flow.ui_chunks import build_interactive_product_chunk, build_questionnaire_chunk
from app.utils.trace_log import product_summary, short_preview, trace_print


async def handle_questionnaire(payload: ChatRequest, session: dict, action: str, data):
    """Collect attribute answers then trigger search + ranking pipeline."""
    trace_id = session.get("_trace_id", "unknown")
    trace_print(
        trace_id,
        "handle_questionnaire",
        "enter",
        action=action,
        dataPreview=short_preview(data),
        remainingAttributes=len(session.get("attributes", [])),
        answersCount=len(session.get("answers", [])),
    )

    if action not in ["SUBMIT_SURVEY", "SKIP_SURVEY"]:
        trace_print(trace_id, "handle_questionnaire", "skip_unsupported_action", action=action)
        return

    last_options_text = ""
    if action == "SUBMIT_SURVEY":
        last_options_text = "Đang cập nhật: " + (", ".join(str(x) for x in data) if isinstance(data, list) else str(data))
    elif action == "SKIP_SURVEY":
        last_options_text = "Đã bỏ qua tiêu chí."

    if action == "SUBMIT_SURVEY":
        if "answers" not in session:
            session["answers"] = []
        session["answers"].append(
            {
                "attribute_id": session.get("current_attribute_id"),
                "selected_options": data,
            }
        )
        trace_print(
            trace_id,
            "handle_questionnaire",
            "answer_recorded",
            attributeId=session.get("current_attribute_id"),
            totalAnswers=len(session["answers"]),
        )

    if session["attributes"]:
        next_attr = session["attributes"].pop(0)
        session["current_attribute_id"] = next_attr["id"]
        trace_print(
            trace_id,
            "handle_questionnaire",
            "emit_next_question",
            attributeId=next_attr["id"],
            remaining=len(session["attributes"]),
        )
        if last_options_text:
            yield A2UIChunk(a2ui={"type": "a2ui_processing_status", "data": {"statusText": last_options_text}})
        yield build_questionnaire_chunk(next_attr, allow_multiple=True)
        return

    yield A2UIChunk(
        a2ui={
            "type": "a2ui_processing_status",
            "data": {"statusText": "Đang tìm kiếm dựa trên sở thích của bạn...", "progressPercent": 60},
        }
    )

    first_prod = None

    try:
        final_search_keyword = f"{session.get('original_keyword', '')} {session.get('leaf_category_name', '')}".strip()
        min_price_filter = None
        max_price_filter = None
        for ans in session.get("answers", []):
            for option in ans.get("selected_options", []):
                parsed_min, parsed_max = parse_budget_bounds(str(option))
                if parsed_min is not None:
                    min_price_filter = parsed_min
                if parsed_max is not None:
                    max_price_filter = parsed_max

        user_message = payload.message.strip() if hasattr(payload, "message") and payload.message else ""
        trace_print(
            trace_id,
            "handle_questionnaire",
            "search_pipeline_start",
            finalSearchKeyword=final_search_keyword,
            minPrice=min_price_filter,
            maxPrice=max_price_filter,
            answersCount=len(session.get("answers", [])),
            userMessagePreview=short_preview(user_message),
        )

        raw_products, ranked_stream = await search_and_prepare_stream(
            final_search_keyword=final_search_keyword,
            user_message=user_message,
            answers=session.get("answers", []),
            min_price_filter=min_price_filter,
            max_price_filter=max_price_filter,
            trace_id=trace_id,
        )
        session["raw_products"] = raw_products
        session["pending_products"] = []

        yield A2UIChunk(
            a2ui={
                "type": "a2ui_processing_status",
                "data": {
                    "statusText": "AI đang chọn lọc mẫu đẹp nhất cho bạn...",
                    "progressPercent": 85,
                },
            }
        )

        stream_count = 0
        async for product in ranked_stream:
            stream_count += 1
            if first_prod is None:
                first_prod = product
                trace_print(
                    trace_id,
                    "handle_questionnaire",
                    "emit_first_product",
                    product=product_summary(first_prod),
                )
                yield A2UIChunk(
                    a2ui={
                        "type": "a2ui_processing_status",
                        "data": {"statusText": "Hoàn tất!", "progressPercent": 100},
                    }
                )
                yield build_interactive_product_chunk(first_prod)
                session["phase"] = "PRODUCT_SWIPE"
            else:
                session["pending_products"].append(product)
                trace_print(
                    trace_id,
                    "handle_questionnaire",
                    "buffer_product",
                    index=stream_count,
                    pendingCount=len(session["pending_products"]),
                    product=product_summary(product),
                )

        trace_print(
            trace_id,
            "handle_questionnaire",
            "ranked_stream_completed",
            receivedProducts=stream_count,
            pendingCount=len(session.get("pending_products", [])),
        )

    except Exception as exc:
        print(f"Lỗi khi tìm kiếm & xếp hạng: {exc}")
        traceback.print_exc()
        trace_print(
            trace_id,
            "handle_questionnaire",
            "error",
            errorType=type(exc).__name__,
            error=str(exc),
        )
        session["pending_products"] = []

    if first_prod is None:
        trace_print(trace_id, "handle_questionnaire", "no_products_found")
        yield MessageChunk(content="Rất tiếc mình không tìm thấy sản phẩm nào phù hợp yêu cầu.")
        session["phase"] = "DONE"

