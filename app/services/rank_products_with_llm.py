import json

from app.services.request_model_service import generate_ranking_json


async def rank_products_with_llm(filtered_products: list, user_message: str, answers: list) -> list:
    """
    Hàm xử lý business logic: Đóng gói thông tin, gọi LLM, và map dữ liệu trả về.
    """
    if not filtered_products:
        return []

    # 1. Chuẩn bị text sở thích từ danh sách answers của người dùng
    preferences_text = "Không có tiêu chí đặc biệt."
    if answers:
        prefs = []
        for ans in answers:
            options = ans.get("selected_options", [])
            if options:
                # Ép kiểu sang string và nối lại
                prefs.append(", ".join([str(opt) for opt in options]))
        if prefs:
            preferences_text = "Người dùng ưu tiên các tiêu chí sau: " + " | ".join(prefs)

    # 2. Tạo payload siêu nhẹ gửi lên LLM (Tiết kiệm token & tăng tốc độ)
    mini_products = []
    for prod in filtered_products:
        # Xử lý tương thích cả Pydantic Model lẫn Dictionary
        p_dict = prod.model_dump(by_alias=False) if hasattr(prod, "model_dump") else prod

        # Lấy ID (cover các trường hợp key khác nhau)
        pid = str(p_dict.get("product_id") or p_dict.get("productId") or p_dict.get("id"))

        mini_products.append({
            "product_id": pid,
            "name": p_dict.get("name", ""),
            "price": p_dict.get("price_current", 0),
            "rating": p_dict.get("rating_star", 0),
            "sold": p_dict.get("sold_count", 0)
        })

    # 3. Khởi tạo Prompt
    prompt = f"""
        Hãy xếp hạng danh sách sản phẩm E-commerce dưới đây.

        [YÊU CẦU BAN ĐẦU CỦA KHÁCH]: "{user_message}"
        [CÁC TIÊU CHÍ KHÁCH ĐÃ CHỌN THÊM]: {preferences_text}

        [DANH SÁCH SẢN PHẨM ỨNG VIÊN]:
        {json.dumps(mini_products, ensure_ascii=False)}

        Nhiệm vụ: Chấm điểm (score từ 0-100) dựa trên độ phù hợp với tổng hợp yêu cầu và sở thích của khách. Trả về danh sách được xếp hạng từ điểm cao nhất xuống thấp nhất.
    """

    # 4. Gọi LLM
    ranked_result = await generate_ranking_json(prompt)

    # 5. Nếu LLM lỗi hoặc trả mảng rỗng, fallback về danh sách gốc
    if not ranked_result:
        return filtered_products

    # 6. Map kết quả JSON (chứa ID) về lại Object gốc để giữ nguyên thông tin hiển thị UI
    product_map = {}
    for p in filtered_products:
        p_dict = p.model_dump(by_alias=False) if hasattr(p, "model_dump") else p
        pid = str(p_dict.get("product_id") or p_dict.get("productId") or p_dict.get("id"))
        product_map[pid] = p

    final_sorted_products = []
    ranked_ids = set()

    # Đưa các sản phẩm được LLM chấm điểm vào trước (đã sort)
    for item in ranked_result:
        pid = str(item.get("product_id"))
        if pid in product_map:
            final_sorted_products.append(product_map[pid])
            ranked_ids.add(pid)

    # Fallback an toàn: Thêm những sản phẩm LLM lỡ bỏ sót xuống cuối mảng
    for p in filtered_products:
        p_dict = p.model_dump(by_alias=False) if hasattr(p, "model_dump") else p
        pid = str(p_dict.get("product_id") or p_dict.get("productId") or p_dict.get("id"))
        if pid not in ranked_ids:
            final_sorted_products.append(p)

    return final_sorted_products