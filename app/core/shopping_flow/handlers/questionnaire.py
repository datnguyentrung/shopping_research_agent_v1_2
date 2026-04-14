import traceback

from app.schemas.entities import A2UIChunk, MessageChunk
from app.schemas.requests import ChatRequest
from app.core.shopping_flow.phase_utils import search_and_rank_products
from app.core.shopping_flow.product_filters import parse_budget_bounds
from app.core.shopping_flow.ui_chunks import build_interactive_product_chunk, build_questionnaire_chunk


async def handle_questionnaire(payload: ChatRequest, session: dict, action: str, data):
    """Collect attribute answers then trigger search + ranking pipeline."""
    if action not in ["SUBMIT_SURVEY", "SKIP_SURVEY"]:
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

    if session["attributes"]:
        next_attr = session["attributes"].pop(0)
        session["current_attribute_id"] = next_attr["id"]
        if last_options_text:
            yield A2UIChunk(a2ui={"type": "a2ui_processing_status", "data": {"statusText": last_options_text}})
        yield build_questionnaire_chunk(next_attr, allow_multiple=True)
        return

    session["phase"] = "PRODUCT_SWIPE"
    yield A2UIChunk(
        a2ui={
            "type": "a2ui_processing_status",
            "data": {"statusText": "Đang tìm kiếm dựa trên sở thích của bạn...", "progressPercent": 60},
        }
    )

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
        raw_products, ranked_products = await search_and_rank_products(
            final_search_keyword=final_search_keyword,
            user_message=user_message,
            answers=session.get("answers", []),
            min_price_filter=min_price_filter,
            max_price_filter=max_price_filter,
        )
        session["raw_products"] = raw_products

        yield A2UIChunk(
            a2ui={
                "type": "a2ui_processing_status",
                "data": {
                    "statusText": "AI đang chọn lọc mẫu đẹp nhất cho bạn...",
                    "progressPercent": 85,
                },
            }
        )

        session["pending_products"] = ranked_products
    except Exception as exc:
        print(f"Lỗi khi tìm kiếm & xếp hạng: {exc}")
        traceback.print_exc()
        session["pending_products"] = []

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

