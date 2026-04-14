import uuid

from app.schemas.entities import A2UIChunk, MessageChunk
from app.schemas.requests import ChatRequest
from app.core.shopping_flow.phase_utils import (
    build_attribute_questions,
    get_child_categories,
    search_and_rank_products,
)
from app.core.shopping_flow.ui_chunks import build_interactive_product_chunk, build_questionnaire_chunk


async def handle_category_drilldown(
    payload: ChatRequest,
    session: dict,
    action: str,
    data,
):
    """Handle iterative category narrowing until reaching a leaf category."""
    if action != "SUBMIT_SURVEY":
        return

    selected_name = data[0] if isinstance(data, list) and data else data
    cat_map = session.get("category_map", {})

    selected_cat_id = cat_map.get(selected_name, session.get("current_category_id"))
    session["current_category_id"] = selected_cat_id

    options, category_map, children = get_child_categories(selected_cat_id)

    if children:
        session["category_map"] = category_map
        next_question = {
            "id": "cat_drilldown_" + uuid.uuid4().hex,
            "name": "Chi tiết hơn một chút nhé, bạn muốn tìm loại nào?",
            "options": options,
        }
        yield A2UIChunk(
            a2ui={"type": "a2ui_processing_status", "data": {"statusText": f"Đã ghi nhận: {selected_name}"}}
        )
        yield build_questionnaire_chunk(next_question, allow_multiple=False)
        return

    session["leaf_category_name"] = selected_name
    session["attributes"] = build_attribute_questions(selected_cat_id)

    if session["attributes"]:
        session["phase"] = "QUESTIONNAIRE"
        first_attr = session["attributes"].pop(0)
        session["current_attribute_id"] = first_attr["id"]

        yield A2UIChunk(
            a2ui={"type": "a2ui_processing_status", "data": {"statusText": f"Đã chọn {selected_name}. Tiếp tục nào!"}}
        )
        yield build_questionnaire_chunk(first_attr, allow_multiple=True)
        return

    session["phase"] = "PRODUCT_SWIPE"
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

    raw_products, ranked_products = await search_and_rank_products(
        final_search_keyword=final_search_keyword,
        user_message=user_message,
        answers=[],
    )

    session["raw_products"] = raw_products
    session["pending_products"] = ranked_products

    if session["pending_products"]:
        first_prod = session["pending_products"].pop(0)
        yield A2UIChunk(
            a2ui={
                "type": "a2ui_processing_status",
                "data": {"statusText": "Hoàn tất!", "progressPercent": 100},
            }
        )
        yield build_interactive_product_chunk(first_prod)
    else:
        yield MessageChunk(content="Rất tiếc mình không tìm thấy sản phẩm nào phù hợp yêu cầu.")
        session["phase"] = "DONE"

