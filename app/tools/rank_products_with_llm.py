import json

# Import trực tiếp hàm độc lập
from app.services.request_model_service import generate_ranking_json


async def rank_products_with_llm(filtered_products: list, user_message: str, answers: list) -> list:
    """
    Hàm này gọi LLM để sắp xếp sản phẩm dựa trên nhu cầu ngữ nghĩa của user.
    """
    if len(filtered_products) <= 1:
        return filtered_products

    # 1. Chuẩn bị data siêu nhẹ (chỉ gửi ID, Tên, Giá, Đặc điểm nổi bật để tiết kiệm Token)
    ai_candidates = []
    product_map = {}  # Dùng để map lại object gốc sau khi LLM trả về ID

    for prod in filtered_products:
        p_dict = prod.model_dump(by_alias=False) if hasattr(prod, "model_dump") else prod

        # Đảm bảo ép kiểu string an toàn, phòng trường hợp ID là số
        pid = str(p_dict.get("product_id") or p_dict.get("productId") or p_dict.get("id"))

        product_map[pid] = prod

        ai_candidates.append({
            "id": pid,
            "name": p_dict.get("name", ""),
            "price": p_dict.get("price_current", 0),
            "rating": p_dict.get("rating_star", 0)
        })

    # 2. Thiết kế Prompt (Không bắt AI format JSON bằng chữ, vì Config của generate_ranking_json đã lo việc đó)
    prompt = f"""
        Hãy xếp hạng danh sách sản phẩm E-commerce dưới đây.
        
        [Nhu cầu gốc của khách]: "{user_message}"
        [Các tiêu chí khách đã chọn thêm]: {json.dumps(answers, ensure_ascii=False)}
        
        [Sản phẩm ứng viên]: 
        {json.dumps(ai_candidates, ensure_ascii=False)}
        
        Nhiệm vụ của bạn:
        1. Đọc tên sản phẩm và đánh giá độ phù hợp với nhu cầu và tiêu chí của khách.
        2. Trả về danh sách chứa ID và Score (từ 0-100) của các sản phẩm.
    """

    try:
        # GỌI TRỰC TIẾP HÀM ĐỘC LẬP
        # Vì generate_ranking_json đã trả về mảng (list of dicts) nên không cần json.loads nữa
        ranked_result = await generate_ranking_json(prompt)

        # Nếu AI trả về rỗng do lỗi
        if not ranked_result:
            return filtered_products

        # 3. Map kết quả trả về từ dạng list[dict] sang mảng object sản phẩm gốc
        ranked_products = []
        ranked_ids = set()

        for item in ranked_result:
            # Lấy id từ object trả về (vì Schema của bạn đang yêu cầu AI trả về mảng chứa key 'product_id' và 'score')
            pid = str(item.get("product_id"))
            if pid in product_map:
                ranked_products.append(product_map[pid])
                ranked_ids.add(pid)

        # Bổ sung những sản phẩm LLM bỏ sót (đề phòng AI thiếu sót)
        for prod in filtered_products:
            p_dict = prod.model_dump(by_alias=False) if hasattr(prod, "model_dump") else prod
            pid = str(p_dict.get("product_id") or p_dict.get("productId") or p_dict.get("id"))

            if pid not in ranked_ids:
                ranked_products.append(prod)

        return ranked_products

    except Exception as e:
        print(f"Lỗi khi LLM ranking: {e}")
        # Nếu LLM lỗi, fallback về danh sách ban đầu
        return filtered_products