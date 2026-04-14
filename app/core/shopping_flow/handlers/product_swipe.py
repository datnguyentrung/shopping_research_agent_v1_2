from app.memory.session_store import clear_session
from app.schemas.entities import A2UIChunk, MessageChunk

from app.core.shopping_flow.final_summary import generate_final_summary_with_llm
from app.core.shopping_flow.ui_chunks import build_interactive_product_chunk
from app.services.request_model_service import analyze_dislike_reason


async def handle_product_swipe(session: dict, session_id: str, action: str, data):
    """Consume swipe feedback and decide whether to continue or finalize."""
    if action != "PRODUCT_FEEDBACK":
        return

    if isinstance(data, dict):
        decision = data.get("decision", "").lower()
        if decision == "like":
            session["whitelist"].append(data)
        elif decision == "dislike":
            session["blacklist"].append(data)

            # --- BỘ LỌC ĐỘNG TỪ FEEDBACK ---
            reason = data.get("reason", "")
            rejected_product = data.get("product", {})

            if reason and session.get("pending_products"):
                yield A2UIChunk(
                    a2ui={
                        "type": "a2ui_processing_status",
                        "data": {
                            "statusText": f"Đang điều chỉnh kết quả để loại bỏ sản phẩm '{reason}'...",
                            "progressPercent": 85
                        }
                    }
                )

                filtered_products = []

                # 1. Xử lý Hard Filter (Các lý do có sẵn từ UI)
                if reason == "Giá quá cao":
                    current_price = float(rejected_product.get("price_current", 0)) if rejected_product else 0
                    for p in session["pending_products"]:
                        p_dict = p.model_dump(by_alias=False) if hasattr(p, "model_dump") else p
                        # Giữ lại các sản phẩm có giá RẺ HƠN
                        if current_price == 0 or float(p_dict.get("price_current", 0)) < current_price:
                            filtered_products.append(p)

                elif reason == "Thương hiệu":
                    bad_brand = rejected_product.get("brand", "").lower() if rejected_product else ""
                    for p in session["pending_products"]:
                        p_dict = p.model_dump(by_alias=False) if hasattr(p, "model_dump") else p
                        # Loại bỏ sản phẩm cùng thương hiệu
                        if not bad_brand or p_dict.get("brand", "").lower() != bad_brand:
                            filtered_products.append(p)

                elif reason == "Khác" or reason not in ["Không hợp phong cách", "Tính năng"]:
                    # 2. Xử lý Soft Filter bằng LLM (Lý do nhập tay)
                    banned_keywords = await analyze_dislike_reason(reason)

                    for p in session["pending_products"]:
                        p_dict = p.model_dump(by_alias=False) if hasattr(p, "model_dump") else p
                        # Nối các trường thông tin quan trọng để search keyword
                        p_text = f"{p_dict.get('name', '')} {p_dict.get('description', '')}".lower()

                        # Giữ lại nếu KHÔNG chứa bất kỳ keyword bị cấm nào
                        is_banned = any(kw.lower() in p_text for kw in banned_keywords if kw.strip())
                        if not is_banned:
                            filtered_products.append(p)
                else:
                    # Nếu là lý do chung chung không định lượng được, bỏ qua bước lọc bổ sung
                    filtered_products = session["pending_products"]

                # Cập nhật lại mảng chờ (chỉ cập nhật nếu sau khi lọc vẫn còn sản phẩm)
                if filtered_products:
                    session["pending_products"] = filtered_products

    total_swipes = len(session.get("whitelist", [])) + len(session.get("blacklist", []))

    if len(session["whitelist"]) >= 5 or total_swipes >= 10 or len(session["pending_products"]) < 1:
        if not session["whitelist"]:
            yield MessageChunk(
                content="Có vẻ bạn chưa ưng ý sản phẩm nào trong lô này. Hãy thử ấn Bắt đầu mới và mô tả lại nhu cầu cụ thể hơn nhé!"
            )
            yield A2UIChunk(a2ui={"type": "a2ui_done", "data": {}})
            clear_session(session_id)
            return

        session["phase"] = "FINAL_SUMMARY"
        yield A2UIChunk(
            a2ui={
                "type": "a2ui_processing_status",
                "data": {
                    "statusText": "Đang tổng hợp các mẫu bạn thích để viết báo cáo...",
                    "progressPercent": 100,
                },
            }
        )

        final_chunks = generate_final_summary_with_llm(
            whitelist=session["whitelist"],
            all_products=session.get("raw_products", []),
            original_keyword=session.get("vi_keyword", ""),
            pending_products=session.get("pending_products", []),
            blacklist=session["blacklist"],
        )
        async for chunk in final_chunks:
            yield chunk

        yield A2UIChunk(a2ui={"type": "a2ui_done", "data": {}})
        clear_session(session_id)
        return

    next_prod = session["pending_products"].pop(0)
    yield build_interactive_product_chunk(next_prod)

