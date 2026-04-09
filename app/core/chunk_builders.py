import asyncio
import traceback
import uuid
import json

from app.core.orchestrator_runtime import get_flow_runtime
from app.memory.session_store import get_or_create_session, clear_session
from app.repositories.category_attribute_repository import CategoryAttributeRepository
from app.schemas.entities import A2UIChunk, ChatStreamChunk, MessageChunk, CapturedData
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
            categories = classify_keyword_topk(en_keyword, k=2)
            category_ids = [c["category_id"] for c in categories]

            # 3. KÍCH HOẠT TÌM KIẾM NGẦM
            session["search_task"] = asyncio.create_task(run_parallel_searches(vi_keyword))

            # 4. Lấy câu hỏi thuộc tính (Attribute) từ DB
            db = SessionLocal()
            try:
                category_repo = CategoryAttributeRepository(db)
                attributes = category_repo.get_inherited_attributes_cte(category_ids)

                # Convert SQLAlchemy objects to dicts for serialization
                attributes_data = [
                    {
                        'id': attr.id,
                        'name': attr.name,
                        'options': attr.options if attr.options else []
                    }
                    for attr in attributes[:5]  # Lấy tối đa 5 phần tử
                ]
                session["attributes"] = attributes_data
                session["phase"] = "QUESTIONNAIRE"
            finally:
                db.close()

            # 5. Đẩy câu hỏi đầu tiên xuống FE
            if session["attributes"]:
                first_attr = session["attributes"].pop(0)
                session["current_attribute_id"] = first_attr['id']  # THÊM DÒNG NÀY
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
            if action in ["SUBMIT_SURVEY", "SKIP_SURVEY"]:
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
                    decision = data.get("decision", "").lower()
                    if decision == "like":
                        session["whitelist"].append(data)
                    elif decision == "dislike":
                        session["blacklist"].append(data)

                total_swipes = len(session.get("whitelist", [])) + len(session.get("blacklist", []))

                # KIỂM TRA ĐIỀU KIỆN DỪNG
                # Điều kiện dừng:
                # 1. Đã "Phù hợp" đủ 5 cái
                # 2. HOẶC tổng số lần quẹt (thích + không thích) đạt tối đa 10 cái
                # 3. HOẶC đã cạn kho sản phẩm
                if len(session["whitelist"]) >= 5 or total_swipes >= 10 or len(session["pending_products"]) < 1:

                    # Góc độ Edge Case: Nếu user quẹt 10 cái mà chê cả 10 (whitelist rỗng)
                    if not session["whitelist"]:
                        yield MessageChunk(
                            content="Có vẻ bạn chưa ưng ý sản phẩm nào trong lô này. Hãy thử ấn Bắt đầu mới và mô tả lại nhu cầu cụ thể hơn (ví dụ: đổi tầm giá, màu sắc) nhé!")
                        yield A2UIChunk(a2ui={"type": "a2ui_done", "data": {}})
                        clear_session(session_id)
                        return

                    session["phase"] = "FINAL_SUMMARY"
                    yield A2UIChunk(a2ui={"type": "a2ui_processing_status",
                                          "data": {"statusText": "Đang tổng hợp các mẫu bạn thích để viết báo cáo...",
                                                   "progressPercent": 100}})

                    # Gọi LLM để sinh kết quả cuối cùng
                    final_chunks = generate_final_summary_with_llm(session["whitelist"],
                                                                   session.get("raw_products", []))
                    async for chunk in final_chunks:
                        yield chunk

                    # Đánh dấu hoàn tất UI
                    yield A2UIChunk(a2ui={"type": "a2ui_done", "data": {}})

                    # DỌN RÁC RAM SAU KHI XONG VIỆC
                    clear_session(session_id)
                    return

                else:
                    # Chưa đủ điều kiện -> Push thẻ quẹt tiếp theo
                    next_prod = session["pending_products"].pop(0)
                    yield _build_interactive_product_chunk(next_prod)

    except Exception as e:
        print(f"Error in hidden event processing: {e}")
        import traceback
        traceback.print_exc()
        yield MessageChunk(content=f"Có lỗi xảy ra: {str(e)}")
        session["phase"] = "ERROR"

# ---------------------------------------------------------
# ------------- CÁC HÀM HELPER ĐỂ BUILD UI CHUNK ----------
# ---------------------------------------------------------
def _build_questionnaire_chunk(attr: dict) -> A2UIChunk:
    return A2UIChunk(
        a2ui={
            "type": "a2ui_questionnaire",
            "data": {
                "title": f"{attr['name']}",
                "allowMultiple": True,  # Gõ thẳng camelCase vì đây là dict thủ công
                "options": attr["options"],
                "attributeId": attr["id"]  # camelCase
            }
        }
    )

def _build_interactive_product_chunk(product_data: dict) -> A2UIChunk:
    if isinstance(product_data, dict):
        product_model = CapturedData(**product_data)
    else:
        product_model = product_data

    return A2UIChunk(
        a2ui={
            "type": "a2ui_interactive_product",
            "data": {
                # 2. Ép Pydantic dump model này ra dict bằng camelCase
                "product": product_model.model_dump(by_alias=True, exclude_none=True),
                "reasonsToReject": [
                    "Giá quá cao",
                    "Không hợp phong cách",
                    "Thương hiệu",
                    "Tính năng",
                    "Khác"
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
        return products[:10]  # Giới hạn 50 sản phẩm nếu không có filter

    filtered = products
    # Ở đây bạn có thể implement logic lọc phức tạp hơn
    # Hiện tại trả về tối đa 50 sản phẩm
    return filtered[:10]


async def generate_final_summary_with_llm(whitelist: list, all_products: list, blacklist: list = None):
    if blacklist is None:
        blacklist = []

    selected_products = []
    whitelist_ids = [str(item.get("productId") or item.get("product_id")) for item in whitelist]
    blacklist_ids = [str(item.get("productId") or item.get("product_id")) for item in blacklist]
    interacted_ids = set(whitelist_ids + blacklist_ids)

    # 1. Trích xuất thông tin sản phẩm User đã thích (Sở thích/Gu)
    for prod in all_products:
        prod_dict = prod.model_dump(by_alias=False) if hasattr(prod, "model_dump") else prod
        if str(prod_dict.get("product_id")) in whitelist_ids:
            selected_products.append({
                "Tên": prod_dict.get("name", "N/A"),
                "Giá": f"{int(prod_dict.get('price_current', 0)):,} {prod_dict.get('currency', 'VND')}",
                "Đánh giá": f"{prod_dict.get('rating_star', 0)} ⭐",
                "Link": prod_dict.get("product_url", "")
            })

    # ========================================================
    # GIAI ĐOẠN 1: PYTHON LỌC THÔ (RETRIEVAL) -> Tôn trọng Relevance
    # ========================================================
    candidates = []
    for prod in all_products:
        prod_dict = prod.model_dump(by_alias=False) if hasattr(prod, "model_dump") else prod
        current_id = str(prod_dict.get("product_id"))

        # Bỏ qua những cái đã quẹt (Whitelist/Blacklist)
        if current_id not in interacted_ids:
            # Chỉ lấy những sản phẩm có rating ổn (>= 4.0) hoặc hàng mới lên kệ (0 sao)
            rating = float(prod_dict.get('rating_star', 0))
            if rating == 0.0 or rating >= 4.0:
                candidates.append(prod_dict)

    rough_top_40 = candidates[:40]

    # Chuẩn bị data siêu nhẹ cho AI đọc
    ai_candidates = []
    for c in rough_top_40:
        ai_candidates.append({
            "Tên": c.get("name", "N/A"),
            "Giá": f"{int(c.get('price_current', 0)):,} VND",
            "Đánh giá": f"{c.get('rating_star', 0)} ⭐ | Đã bán: {c.get('sold_count', 0)}",
            "Shop": c.get("shop", {}).get("shop_name", "N/A"),
            "Link": c.get("product_url", "")
        })

        # ========================================================
        # GIAI ĐOẠN 2: GOOGLE ADK ĐÁNH GIÁ & CHỌN TOP 10 (RANKING)
        # ========================================================
        prompt = f"""Hãy viết báo cáo phân tích mua sắm dựa trên dữ liệu sau:
        [Sản phẩm người dùng đã chọn]: {json.dumps(selected_products, ensure_ascii=False)}
        [10 Ứng viên tiềm năng nhất để gợi ý thêm]: {json.dumps(ai_candidates[:10], ensure_ascii=False)}

    [Danh sách 40 ứng viên thô]:
    {json.dumps(ai_candidates, ensure_ascii=False, indent=2)}

    RÀNG BUỘC CỐT LÕI (TUYỆT ĐỐI TUÂN THỦ):
    - BẮT BUỘC chỉ đề xuất các mặt hàng ĐÚNG CÙNG LOẠI với "Sở thích của tôi". Ví dụ: Nếu tôi chọn "Quần âu/Quần tây", bạn CHỈ ĐƯỢC gợi ý Quần âu/Quần tây. TUYỆT ĐỐI KHÔNG gợi ý Áo, Thắt lưng, Túi xách, Giày, Quần lót, hoặc các loại quần khác (như Jean/Jogger) trừ khi có sự tương đồng cực kỳ lớn.

    Yêu cầu xuất Báo cáo bằng Tiếng Việt gồm 4 phần:
    ### 1. Phân tích chân dung nhu cầu
    (Dựa vào sở thích của tôi, hãy tóm tắt tôi đang tìm kiếm phong cách gì, tầm giá bao nhiêu).
    ### 2. Danh sách sản phẩm tôi đã chốt
    (Liệt kê lại các sản phẩm tôi đã chọn kèm Link).
    ### 3. Đề xuất TOP 10 tốt nhất cùng danh mục
    (Liệt kê Top 10 sản phẩm TƯƠNG ĐỒNG NHẤT VỀ LOẠI HÀNG VÀ PHONG CÁCH từ 40 ứng viên. Nêu rõ lý do chọn kèm Link).
    ### 4. Bảng tổng hợp so sánh
    (Gộp chung danh sách đã chốt và Top 10 đề xuất vào 1 bảng Markdown duy nhất).
    """

    try:
        runtime = get_flow_runtime()
        async for text_chunk in runtime.stream_text(prompt):
            if text_chunk:
                yield MessageChunk(content=text_chunk)

    except Exception as e:
        print(f"Error generating final summary: {e}")
        traceback.print_exc()
        yield MessageChunk(
            content="\n\n*Hệ thống đang quá tải, không thể tạo báo cáo tóm tắt lúc này. Bạn vui lòng xem lại danh sách ở trên nhé!*")


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