import random
import uuid

from app.schemas.entities import A2UIChunk, MessageChunk
from app.schemas.requests import ChatRequest
from app.core.shopping_flow.phase_utils import (
    build_attribute_questions,
    get_child_categories,
    search_and_prepare_stream,
)
from app.core.shopping_flow.ui_chunks import build_interactive_product_chunk, build_questionnaire_chunk
from app.utils.trace_log import product_summary, short_preview, trace_print


async def handle_category_drilldown(
    payload: ChatRequest,
    session: dict,
    action: str,
    data,
):
    """Handle iterative category narrowing until reaching a leaf category."""
    trace_id = session.get("_trace_id", "unknown")
    trace_print(
        trace_id,
        "handle_category_drilldown",
        "enter",
        action=action,
        dataPreview=short_preview(data),
        currentCategoryId=session.get("current_category_id"),
    )

    if action != "SUBMIT_SURVEY":
        trace_print(trace_id, "handle_category_drilldown", "skip_unsupported_action", action=action)
        return

    selected_name = data[0] if isinstance(data, list) and data else data
    cat_map = session.get("category_map", {})

    selected_cat_id = cat_map.get(selected_name, session.get("current_category_id"))
    session["current_category_id"] = selected_cat_id
    trace_print(
        trace_id,
        "handle_category_drilldown",
        "category_selected",
        selectedName=selected_name,
        selectedCategoryId=selected_cat_id,
    )

    options, category_map, children = get_child_categories(selected_cat_id, trace_id)

    if len(options) > 4:
        options = random.sample(options, 4)

    if children:
        session["category_map"] = category_map
        next_question = {
            "id": "cat_drilldown_" + uuid.uuid4().hex,
            "name": "Chi tiết hơn một chút nhé, bạn muốn tìm loại nào?",
            "options": options,
        }
        trace_print(
            trace_id,
            "handle_category_drilldown",
            "emit_next_category_question",
            questionId=next_question["id"],
            optionCount=len(options),
        )
        yield A2UIChunk(
            a2ui={"type": "a2ui_processing_status", "data": {"statusText": f"Đã ghi nhận: {selected_name}"}}
        )
        yield build_questionnaire_chunk(next_question, allow_multiple=False)
        return

    session["leaf_category_name"] = selected_name
    session["attributes"] = build_attribute_questions(selected_cat_id, trace_id)
    trace_print(
        trace_id,
        "handle_category_drilldown",
        "leaf_category_reached",
        leafCategoryName=selected_name,
        attributesCount=len(session["attributes"]),
    )

    if session["attributes"]:
        session["phase"] = "QUESTIONNAIRE"
        first_attr = session["attributes"].pop(0)
        session["current_attribute_id"] = first_attr["id"]

        trace_print(
            trace_id,
            "handle_category_drilldown",
            "emit_first_attribute_question",
            attributeId=first_attr["id"],
            remaining=len(session["attributes"]),
        )
        yield A2UIChunk(
            a2ui={"type": "a2ui_processing_status", "data": {"statusText": f"Đã chọn {selected_name}. Tiếp tục nào!"}}
        )
        yield build_questionnaire_chunk(first_attr, allow_multiple=True)
        return

    yield A2UIChunk(
        a2ui={
            "type": "a2ui_processing_status",
            "data": {
                "statusText": "Đang tìm kiếm dựa trên sở thích của bạn...",
                "progressPercent": 60,
            },
        }
    )

    final_search_keyword = f"{session.get('original_keyword', '')} {session.get('leaf_category_name', '')}".strip()
    user_message = payload.message.strip() if hasattr(payload, "message") and payload.message else ""
    trace_print(
        trace_id,
        "handle_category_drilldown",
        "search_pipeline_start",
        finalSearchKeyword=final_search_keyword,
        userMessagePreview=short_preview(user_message),
    )

    raw_products, ranked_stream = await search_and_prepare_stream(
        final_search_keyword=final_search_keyword,
        user_message=user_message,
        answers=[],
        min_price_filter=None,
        max_price_filter=None,
        trace_id=trace_id,
    )

    session["raw_products"] = raw_products
    session["pending_products"] = []
    first_prod = None
    stream_count = 0

    async for product in ranked_stream:
        stream_count += 1
        if first_prod is None:
            first_prod = product
            trace_print(
                trace_id,
                "handle_category_drilldown",
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
                "handle_category_drilldown",
                "buffer_product",
                index=stream_count,
                pendingCount=len(session["pending_products"]),
                product=product_summary(product),
            )

    trace_print(
        trace_id,
        "handle_category_drilldown",
        "ranked_stream_completed",
        receivedProducts=stream_count,
        pendingCount=len(session.get("pending_products", [])),
    )

    if first_prod is None:
        trace_print(trace_id, "handle_category_drilldown", "no_products_found")
        yield MessageChunk(content="Rất tiếc mình không tìm thấy sản phẩm nào phù hợp yêu cầu.")
        session["phase"] = "DONE"

