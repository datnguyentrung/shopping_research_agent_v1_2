# Trong luồng xử lý của _flow_runtime hoặc nơi bạn quản lý logic chính
import asyncio

from app.schemas.entities import A2UIChunk
from app.tools.query_category_classifier import classify_keyword_topk
from app.tools.transalte import translate_and_fix

from app.repositories.category_attribute_repository import CategoryAttributeRepository

async def handle_user_initial_query(text_input: str):
    # 1. Gọi model Qwen để lấy Tiếng Việt & Tiếng Anh (Chạy đồng bộ vì tốn ít tgian)
    vi_keyword, en_keyword = translate_and_fix(text_input)

    # 2. Lấy category_id từ query_category_classifier
    categories = classify_keyword_topk(en_keyword, k=3)
    category_ids = [c["category_id"] for c in categories]

    # 3. KÍCH HOẠT TÌM KIẾM NGẦM (BACKGROUND) - KHÔNG AWAIT Ở ĐÂY
    # Lưu task này vào session hoặc global dictionary để lấy kết quả sau
    search_task = asyncio.create_task(
        run_parallel_searches(vi_keyword, category_ids)
    )
    # Lưu search_task vào session_state (bạn cần có cơ chế lưu state theo session_id)
    # session_state[session_id]["search_task"] = search_task

    # 4. Lấy danh sách Attribute để hỏi User
    attributes = CategoryAttributeRepository.get_inherited_attributes_cte(category_ids)

    # 5. Yield trả về A2UI Questionnaires ngay lập tức cho FE
    for attr in attributes[:5]:  # Lấy 3-5 câu
        yield A2UIChunk(
            a2ui={
                "type": "a2ui_questionnaire",
                "data": {
                    "title": f"Bạn muốn {attr.name} như thế nào?",
                    "allowMultiple": True,
                    "options": attr.options,
                    "attribute_id": attr.id  # Để BE biết user đang trả lời cho cái gì
                }
            }
        )
        # Tạm dừng stream ở đây để chờ FE gửi hidden_events lên
        break  # Tạm thời break, xử lý từng câu một qua hidden event