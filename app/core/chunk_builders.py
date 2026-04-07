import asyncio
import uuid
from typing import Dict, Any

from app.memory.session_store import get_or_create_session
from app.repositories.category_attribute_repository import CategoryAttributeRepository
from app.schemas.entities import A2UIChunk, ChatStreamChunk, MessageChunk
from app.schemas.requests import ChatRequest
from app.services.search_service import run_parallel_searches
from app.tools.query_category_classifier import classify_keyword_topk
from app.tools.transalte import translate_and_fix
from app.core.database import SessionLocal


async def stream_shopping_agent(payload: ChatRequest):
    # Lấy session_id từ frontend (FE cần gửi kèm sessionId trong ChatRequest)
    # Nếu không có, tự sinh 1 cái (chỉ dùng cho tin nhắn đầu tiên)
    session_id = getattr(payload, 'sessionId', str(uuid.uuid4()))
    session = get_or_create_session(session_id)

    # ---------------------------------------------------------
    # TRƯỜNG HỢP 1: TIN NHẮN MỚI (PHASE: INIT)
    # ---------------------------------------------------------
    if not payload.hidden_events:
        user_message = payload.message.strip()
        yield MessageChunk(content=f"Đợi mình một chút, mình đang phân tích nhu cầu '{user_message}' của bạn nhé...")

        try:
            # 1. Dịch & Phân tích (Chạy đồng bộ vì model cục bộ chạy khá nhanh)
            vi_keyword, en_keyword = translate_and_fix(user_message)

            # 2. Phân loại danh mục
            categories = classify_keyword_topk(en_keyword, k=3)
            category_ids = [c["category_id"] for c in categories]

            # 3. KÍCH HOẠT TÌM KIẾM NGẦM
            session["search_task"] = asyncio.create_task(run_parallel_searches(vi_keyword))

            # 4. Lấy câu hỏi thuộc tính (Attribute) từ DB
            db = SessionLocal()
            try:
                category_repo = CategoryAttributeRepository(db)
                attributes = category_repo.get_inherited_attributes_cte(category_ids)

                # Convert SQLAlchemy objects to dicts for serialization
                attributes_data = []
                for attr in attributes:
                    attributes_data.append({
                        'id': attr.id,
                        'name': attr.name,
                        'options': attr.options if attr.options else []
                    })

                session["attributes"] = attributes_data
                session["phase"] = "QUESTIONNAIRE"
            finally:
                db.close()

            # 5. Đẩy câu hỏi đầu tiên xuống FE
            if session["attributes"]:
                first_attr = session["attributes"].pop(0)
                yield _build_questionnaire_chunk(first_attr)
            else:
                # Nếu không có câu hỏi nào, nhảy thẳng sang chờ lấy sản phẩm
                yield MessageChunk(content="Đang thu thập sản phẩm phù hợp nhất...")
                session["phase"] = "WAITING_PRODUCTS"

        except Exception as e:
            print(f"Error in initial phase: {e}")
            import traceback
            traceback.print_exc()
            yield MessageChunk(content="Xin lỗi, có lỗi xảy ra khi xử lý yêu cầu của bạn.")
            session["phase"] = "ERROR"

        return  # Kết thúc stream của request đầu tiên

    # ---------------------------------------------------------
    # TRƯỜNG HỢP 2: FE GỬI HIDDEN EVENTS (XỬ LÝ STATE)
    # ---------------------------------------------------------
    action = payload.hidden_events.action
    data = payload.hidden_events.payload

    try:
        if session["phase"] == "QUESTIONNAIRE":
            if action in ["SUBMIT_SURVEY", "SKIP_QUESTION"]:
                # Lưu câu trả lời nếu có
                if action == "SUBMIT_SURVEY":
                    # data lúc này là list các option ID được chọn
                    if "answers" not in session:
                        session["answers"] = []
                    session["answers"].append({
                        "attribute_id": session.get("current_attribute_id"),
                        "selected_options": data
                    })

                # Nếu vẫn còn câu hỏi -> Push câu tiếp theo
                if session["attributes"]:
                    next_attr = session["attributes"].pop(0)
                    session["current_attribute_id"] = next_attr['id']
                    yield _build_questionnaire_chunk(next_attr)
                else:
                    # Hết câu hỏi -> Chuyển phase chờ sản phẩm
                    session["phase"] = "PRODUCT_SWIPE"
                    yield A2UIChunk(a2ui={"type": "a2ui_processing_status",
                                          "data": {"statusText": "Đang lọc sản phẩm dựa trên sở thích của bạn...",
                                                   "progressPercent": 80}})

                    # CHỜ BACKGROUND TASK XONG ĐỂ LẤY SẢN PHẨM
                    if session["search_task"]:
                        try:
                            raw_products = await session["search_task"]
                            session["raw_products"] = raw_products
                            # Lọc sản phẩm dựa trên câu trả lời
                            filtered_products = apply_product_filters(raw_products, session.get("answers", []))
                            session["pending_products"] = filtered_products
                        except Exception as e:
                            print(f"Lỗi search task: {e}")
                            session["pending_products"] = []
                    else:
                        session["pending_products"] = []

                    # Bắn thẻ sản phẩm đầu tiên
                    if session["pending_products"]:
                        first_prod = session["pending_products"].pop(0)
                        yield _build_interactive_product_chunk(first_prod)
                    else:
                        yield MessageChunk(content="Rất tiếc mình không tìm thấy sản phẩm nào phù hợp yêu cầu.")
                        session["phase"] = "DONE"

        elif session["phase"] == "PRODUCT_SWIPE":
            if action == "PRODUCT_FEEDBACK":
                # data là payload: { product_id: "...", feedback: "LIKE"/"DISLIKE", reasons: ["..."] }
                if isinstance(data, dict):
                    if data.get("feedback") == "LIKE":
                        session["whitelist"].append(data)
                    else:
                        session["blacklist"].append(data)

                # KIỂM TRA ĐIỀU KIỆN DỪNG
                # Dừng nếu đã thích >= 5 sản phẩm hoặc giỏ chờ < 1 sản phẩm
                if len(session["whitelist"]) >= 5 or len(session["pending_products"]) < 1:
                    session["phase"] = "FINAL_SUMMARY"
                    yield A2UIChunk(a2ui={"type": "a2ui_processing_status",
                                          "data": {"statusText": "Đang viết báo cáo tóm tắt...", "progressPercent": 100}})

                    # Gọi LLM để sinh kết quả cuối cùng
                    final_chunks = await generate_final_summary_with_llm(session["whitelist"], session.get("raw_products", []))
                    for chunk in final_chunks:
                        yield chunk

                    yield A2UIChunk(a2ui={"type": "a2ui_done", "data": {}})
                    session["phase"] = "DONE"

                else:
                    # Push thẻ quẹt tiếp theo
                    next_prod = session["pending_products"].pop(0)
                    yield _build_interactive_product_chunk(next_prod)

    except Exception as e:
        print(f"Error in hidden event processing: {e}")
        import traceback
        traceback.print_exc()
        yield MessageChunk(content=f"Có lỗi xảy ra: {str(e)}")
        session["phase"] = "ERROR"

# --- CÁC HÀM HELPER ĐỂ BUILD UI CHUNK ---

def _build_questionnaire_chunk(attr: dict) -> A2UIChunk:
    return A2UIChunk(
        a2ui={
            "type": "a2ui_questionnaire",
            "data": {
                "title": f"Bạn ưu tiên {attr['name'].lower()} như thế nào?",
                "allowMultiple": True,
                "options": attr["options"],
                "attribute_id": attr["id"]
            }
        }
    )

def _build_interactive_product_chunk(product_data: dict) -> A2UIChunk:
    # Chuẩn hóa dữ liệu sản phẩm cho frontend
    return A2UIChunk(
        a2ui={
            "type": "a2ui_interactive_product",
            "data": {
                "product": product_data,
                "reasonsToReject": [
                    {"id": "price", "label": "Giá quá cao"},
                    {"id": "style", "label": "Không hợp phong cách"},
                    {"id": "brand", "label": "Thương hiệu"},
                    {"id": "features", "label": "Tính năng"},
                    {"id": "other", "label": "Khác"}
                ]
            }
        }
    )

def apply_product_filters(products: list, answers: list) -> list:
    """
    Lọc sản phẩm dựa trên câu trả lời của người dùng.
    Đây là logic lọc cơ bản - bạn có thể nâng cấp sau.
    """
    if not answers:
        return products[:50]  # Giới hạn 50 sản phẩm nếu không có filter

    filtered = products
    # Ở đây bạn có thể implement logic lọc phức tạp hơn
    # Hiện tại trả về tối đa 50 sản phẩm
    return filtered[:50]

async def generate_final_summary_with_llm(whitelist: list, all_products: list) -> list:
    """
    Gọi LLM để sinh text tóm tắt cuối cùng với 3 phần:
    1. Summary
    2. Product Listing (Name, link, price, pros, cons, target audience)
    3. Comparison Table
    """
    from app.agents.base_agent import interactive_agent
    import json

    # Chuẩn bị dữ liệu sản phẩm đã chọn
    selected_products = []
    for item in whitelist:
        product_data = item.get("product", {})
        selected_products.append({
            "name": product_data.get("name", "N/A"),
            "price": product_data.get("price_current", "N/A"),
            "currency": product_data.get("currency", "VND"),
            "rating": product_data.get("rating_star", "N/A"),
            "sold_count": product_data.get("sold_count", "N/A"),
            "shop": product_data.get("shop", {}).get("shop_name", "N/A"),
            "link": product_data.get("link", ""),
        })

    # Tạo prompt cho LLM
    prompt = f"""Dựa trên các sản phẩm người dùng đã chọn below, hãy tạo ra một báo cáo tóm tắt với 3 phần:

## Dữ liệu sản phẩm đã chọn:
{json.dumps(selected_products, ensure_ascii=False, indent=2)}

## Yêu cầu:
Hãy viết một báo cáo bao gồm:

### 1. Tóm tắt
Tóm tắt ngắn gọn về nhu cầu và những gì người dùng tìm được.

### 2. Danh sách sản phẩm chi tiết
Với mỗi sản phẩm, bao gồm:
- Tên sản phẩm
- Link (nếu có)
- Giá
- Ưu điểm (2-3 điểm)
- Nhược điểm (1-2 điểm, nếu có)
- Đối tượng phù hợp nhất

### 3. Bảng so sánh
Bảng so sánh các sản phẩm theo các tiêu chí:
- Tên
- Giá
- Đánh giá
- Số lượng đã bán
- Điểm nổi bật

Hãy viết bằng tiếng Việt, ngắn gọn và súc tích."""

    try:
        # Gọi LLM và stream kết quả
        response_content = ""

        # Sử dụng interactive_agent để tạo response
        # Lưu ý: Cần check cách gọi agent API của bạn
        # Đây là mock implementation - bạn cần điều chỉnh theo API thực tế

        # Mock response for now
        response_content = f"""### Tóm tắt
Dựa trên lựa chọn của bạn, mình đã tìm thấy {len(selected_products)} sản phẩm phù hợp với nhu cầu.

### Danh sách sản phẩm nổi bật

"""
        for idx, product in enumerate(selected_products, 1):
            response_content += f"""#### {idx}. {product['name']}
- **Giá:** {product['price']:,} {product['currency']}
- **Đánh giá:** {product['rating']} ⭐ | Đã bán: {product.get('sold_count', 'N/A')}
- **Ưu điểm:** Chất lượng tốt, giá cả hợp lý
- **Nhược điểm:** Cần kiểm tra thêm thông tin
- **Đối tượng phù hợp:** Người dùng phổ thông
- **Link:** {product.get('link', 'N/A')}

"""

        response_content += """### Bảng so sánh chi tiết

| Tên sản phẩm | Giá | Đánh giá | Đã bán | Điểm nổi bật |
|--------------|-----|----------|--------|--------------|
"""
        for product in selected_products:
            response_content += f"| {product['name']} | {product['price']:,} {product['currency']} | {product['rating']} ⭐ | {product.get('sold_count', 'N/A')} | Chất lượng tốt |\n"

        # Return as chunks
        yield MessageChunk(content=response_content)

    except Exception as e:
        print(f"Error generating final summary: {e}")
        import traceback
        traceback.print_exc()
        yield MessageChunk(content="Xin lỗi, có lỗi xảy ra khi tạo báo cáo tóm tắt.")

# Legacy functions - kept for compatibility but deprecated
def build_hidden_event_chunks(payload: ChatRequest) -> list[ChatStreamChunk]:
    """Deprecated: Hidden events are now handled directly in stream_shopping_agent"""
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