import traceback
import uuid

from app.schemas.entities import A2UIChunk, MessageChunk
from app.schemas.requests import ChatRequest
from app.services.request_model_service import fix_and_translate
from app.tools.query_category_classifier import classify_keyword_topk
from app.core.shopping_flow.phase_utils import (
    build_attribute_questions,
    get_child_categories,
    search_and_prepare_stream,
)
from app.core.shopping_flow.ui_chunks import build_interactive_product_chunk, build_questionnaire_chunk
from app.utils.trace_log import product_summary, short_preview, trace_print


async def handle_initial_phase(payload: ChatRequest, session: dict):
    """Handle very first user message and decide the first UI step.

    This function is the entrypoint of the state machine (phase INIT).
    """
    trace_id = session.get("_trace_id", "unknown")
    user_message = payload.message.strip()
    trace_print(
        trace_id,
        "handle_initial_phase",
        "enter",
        messagePreview=short_preview(user_message),
        incomingPhase=session.get("phase"),
    )

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
        trace_print(
            trace_id,
            "handle_initial_phase",
            "fix_and_translate_result",
            intent=intent,
            viKeyword=vi_keyword,
            enKeyword=en_keyword,
        )

        if intent == "greeting":
            trace_print(trace_id, "handle_initial_phase", "branch_greeting")
            yield MessageChunk(
                content="Chào bạn! Mình là Trợ lý Mua sắm thông minh. Bạn đang cần tìm mua sản phẩm gì hôm nay để mình hỗ trợ nhé?"
            )
            session["phase"] = "INIT"
            return

        if intent == "vague" or not en_keyword:
            vi_keyword = "Thời trang và Phụ kiện"
            trace_print(
                trace_id,
                "handle_initial_phase",
                "branch_vague",
                fallbackCategory="fashion",
            )
            yield MessageChunk(
                content="Do bạn chưa nêu tên sản phẩm cụ thể, mình sẽ mở danh mục tổng hợp 'Thời trang & Phụ kiện' để bạn tham khảo nhé. Bạn có thể gõ tên món đồ (vd: 'áo phông', 'giày thể thao') bất cứ lúc nào để mình tìm chính xác hơn!"
            )

            top_cat = {
                "category_id": "fashion",
                "category_name": "Clothing, Shoes & Jewelry"
            }
        else:
            categories = classify_keyword_topk(en_keyword, k=1)
            top_cat = categories[0] if categories else None
            trace_print(
                trace_id,
                "handle_initial_phase",
                "classifier_result",
                resultCount=len(categories) if categories else 0,
                topCategory=top_cat,
            )

        session["original_keyword"] = vi_keyword
        session["vi_keyword"] = vi_keyword

        if not top_cat:
            trace_print(trace_id, "handle_initial_phase", "no_category_found")
            yield MessageChunk(content="Xin lỗi, mình không tìm thấy danh mục phù hợp cho từ khóa này.")
            session["phase"] = "ERROR"
            return

        session["current_category_id"] = top_cat["category_id"]
        options, category_map, children = get_child_categories(top_cat["category_id"], trace_id)
        trace_print(
            trace_id,
            "handle_initial_phase",
            "child_categories_loaded",
            categoryId=top_cat["category_id"],
            childrenCount=len(children),
            optionsCount=len(options),
        )

        if children:
            session["category_map"] = category_map
            session["phase"] = "CATEGORY_DRILLDOWN"
            first_question = {
                "id": "cat_drilldown_" + uuid.uuid4().hex,
                "name": "Bạn đang tìm kiếm loại mặt hàng nào dưới đây?",
                "options": options,
            }
            trace_print(trace_id, "handle_initial_phase", "emit_category_question", questionId=first_question["id"])
            yield build_questionnaire_chunk(first_question, allow_multiple=False)
            return

        session["leaf_category_name"] = top_cat.get("category_name", "")
        session["attributes"] = build_attribute_questions(top_cat["category_id"], trace_id)
        trace_print(
            trace_id,
            "handle_initial_phase",
            "attributes_loaded",
            count=len(session["attributes"]),
        )

        if session["attributes"]:
            session["phase"] = "QUESTIONNAIRE"
            first_attr = session["attributes"].pop(0)
            session["current_attribute_id"] = first_attr["id"]
            trace_print(
                trace_id,
                "handle_initial_phase",
                "emit_first_attribute_question",
                attributeId=first_attr["id"],
                remaining=len(session["attributes"]),
            )
            yield build_questionnaire_chunk(first_attr, allow_multiple=True)
            return

        yield A2UIChunk(
            a2ui={
                "type": "a2ui_processing_status",
                "data": {"statusText": "Đang tìm kiếm sản phẩm...", "progressPercent": 60},
            }
        )
        final_search_keyword = f"{session.get('original_keyword', '')} {session.get('leaf_category_name', '')}".strip()
        trace_print(
            trace_id,
            "handle_initial_phase",
            "search_pipeline_start",
            finalSearchKeyword=final_search_keyword,
            answersCount=0,
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
            session["pending_products"].append(product)
            trace_print(
                trace_id,
                "handle_initial_phase",
                "ranked_product_received",
                index=stream_count,
                pendingCount=len(session["pending_products"]),
                product=product_summary(product),
            )

            if first_prod is None:
                first_prod = product
                yield A2UIChunk(
                    a2ui={
                        "type": "a2ui_processing_status",
                        "data": {"statusText": "Hoàn tất!", "progressPercent": 100},
                    }
                )
                trace_print(
                    trace_id,
                    "handle_initial_phase",
                    "emit_first_product",
                    product=product_summary(first_prod),
                )
                yield build_interactive_product_chunk(first_prod)
                session["phase"] = "PRODUCT_SWIPE"

        trace_print(
            trace_id,
            "handle_initial_phase",
            "ranked_stream_completed",
            receivedProducts=stream_count,
            pendingCount=len(session.get("pending_products", [])),
        )

        if first_prod is None:
            trace_print(trace_id, "handle_initial_phase", "no_products_found")
            yield MessageChunk(content="Rất tiếc mình không tìm thấy sản phẩm nào phù hợp yêu cầu.")
            session["phase"] = "DONE"

    except Exception as exc:
        print(f"Error in initial phase: {exc}")
        traceback.print_exc()
        trace_print(
            trace_id,
            "handle_initial_phase",
            "error",
            errorType=type(exc).__name__,
            error=str(exc),
        )
        yield MessageChunk(content="Xin lỗi, có lỗi xảy ra khi xử lý yêu cầu của bạn.")
        session["phase"] = "ERROR"
