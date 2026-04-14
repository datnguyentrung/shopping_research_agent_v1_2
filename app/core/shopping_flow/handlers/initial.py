import traceback
import uuid

from app.schemas.entities import A2UIChunk, MessageChunk
from app.schemas.requests import ChatRequest
from app.services.request_model_service import fix_and_translate
from app.tools.query_category_classifier import classify_keyword_topk
from app.core.shopping_flow.phase_utils import (
    build_attribute_questions,
    get_child_categories,
    search_and_rank_products,
)
from app.core.shopping_flow.ui_chunks import build_interactive_product_chunk, build_questionnaire_chunk


async def handle_initial_phase(payload: ChatRequest, session: dict):
    """Handle very first user message and decide the first UI step.

    This function is the entrypoint of the state machine (phase INIT).
    """
    user_message = payload.message.strip()
    session["whitelist"] = []
    session["blacklist"] = []

    yield A2UIChunk(
        a2ui={
            "type": "a2ui_processing_status",
            "data": {
                "statusText": f"Đợi mình một chút, mình đang phân tích nhu cầu '{user_message}' của bạn nhé...",
            },
        }
    )

    try:
        result = await fix_and_translate(user_message)
        intent = result.get("intent", "vague")
        vi_keyword, en_keyword = result.get("vi"), result.get("en")

        if intent == "greeting":
            yield MessageChunk(
                content="Chào bạn! Mình là Trợ lý Mua sắm thông minh. Bạn đang cần tìm mua sản phẩm gì hôm nay để mình hỗ trợ nhé?"
            )
            session["phase"] = "INIT"
            return

        # =====================================================================
        # [CẬP NHẬT Ở ĐÂY] Rẽ nhánh logic phân loại danh mục
        # =====================================================================
        if intent == "vague" or not en_keyword:
            vi_keyword = "Thời trang và Phụ kiện"
            yield MessageChunk(
                content="Do bạn chưa nêu tên sản phẩm cụ thể, mình sẽ mở danh mục tổng hợp 'Thời trang & Phụ kiện' để bạn tham khảo nhé. Bạn có thể gõ tên món đồ (vd: 'áo phông', 'giày thể thao') bất cứ lúc nào để mình tìm chính xác hơn!"
            )

            # Gán cứng danh mục Gốc luôn, không gọi classifier nữa
            top_cat = {
                "category_id": "fashion",
                "category_name": "Clothing, Shoes & Jewelry"
            }
        else:
            # Nếu có từ khóa cụ thể thì mới tốn công gọi classifier
            categories = classify_keyword_topk(en_keyword, k=1)
            top_cat = categories[0] if categories else None
        # =====================================================================

        session["original_keyword"] = vi_keyword
        session["vi_keyword"] = vi_keyword

        if not top_cat:
            yield MessageChunk(content="Xin lỗi, mình không tìm thấy danh mục phù hợp cho từ khóa này.")
            session["phase"] = "ERROR"
            return

        session["current_category_id"] = top_cat["category_id"]
        options, category_map, children = get_child_categories(top_cat["category_id"])

        if children:
            session["category_map"] = category_map
            session["phase"] = "CATEGORY_DRILLDOWN"
            first_question = {
                "id": "cat_drilldown_" + uuid.uuid4().hex,
                "name": "Bạn đang tìm kiếm loại mặt hàng nào dưới đây?",
                "options": options,
            }
            yield build_questionnaire_chunk(first_question, allow_multiple=False)
            return

        session["leaf_category_name"] = top_cat.get("category_name", "")
        session["attributes"] = build_attribute_questions(top_cat["category_id"])

        if session["attributes"]:
            session["phase"] = "QUESTIONNAIRE"
            first_attr = session["attributes"].pop(0)
            session["current_attribute_id"] = first_attr["id"]
            yield build_questionnaire_chunk(first_attr, allow_multiple=True)
            return

        yield A2UIChunk(
            a2ui={
                "type": "a2ui_processing_status",
                "data": {"statusText": "Đang tìm kiếm sản phẩm...", "progressPercent": 60},
            }
        )
        final_search_keyword = f"{session.get('original_keyword', '')} {session.get('leaf_category_name', '')}".strip()
        raw_products, ranked_products = await search_and_rank_products(
            final_search_keyword=final_search_keyword,
            user_message=user_message,
            answers=[],
        )
        session["raw_products"] = raw_products
        session["pending_products"] = ranked_products

        if session.get("pending_products"):
            first_prod = session["pending_products"].pop(0)
            yield A2UIChunk(
                a2ui={
                    "type": "a2ui_processing_status",
                    "data": {"statusText": "Hoàn tất!", "progressPercent": 100},
                }
            )
            yield build_interactive_product_chunk(first_prod)
            session["phase"] = "PRODUCT_SWIPE"
        else:
            yield MessageChunk(content="Rất tiếc mình không tìm thấy sản phẩm nào phù hợp yêu cầu.")
            session["phase"] = "DONE"

    except Exception as exc:
        print(f"Error in initial phase: {exc}")
        traceback.print_exc()
        yield MessageChunk(content="Xin lỗi, có lỗi xảy ra khi xử lý yêu cầu của bạn.")
        session["phase"] = "ERROR"

