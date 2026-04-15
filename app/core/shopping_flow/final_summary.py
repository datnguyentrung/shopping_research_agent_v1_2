import json
import traceback

from app.services.request_model_service import generate_final_summary_stream
from app.schemas.entities import MessageChunk


async def generate_final_summary_with_llm(
    whitelist: list,
    all_products: list,
    original_keyword: str = "",
    pending_products: list | None = None,
    blacklist: list | None = None,
):
    """Build a final recommendation report from user likes/dislikes and candidates."""
    if blacklist is None:
        blacklist = []
    if pending_products is None:
        pending_products = []

    selected_products = []
    rejected_products = []

    whitelist_ids = [str(item.get("productId") or item.get("product_id")) for item in whitelist]
    blacklist_ids = [str(item.get("productId") or item.get("product_id")) for item in blacklist]
    interacted_ids = set(whitelist_ids + blacklist_ids)

    for prod in all_products:
        prod_dict = prod.model_dump(by_alias=False) if hasattr(prod, "model_dump") else prod
        current_id = str(prod_dict.get("product_id"))

        if current_id in whitelist_ids:
            selected_products.append(
                {
                    "Tên": prod_dict.get("name", "N/A"),
                    "Giá": f"{int(prod_dict.get('price_current', 0)):,} {prod_dict.get('currency', 'VND')}",
                    "Đánh giá": f"{prod_dict.get('rating_star', 0)} ⭐",
                    "Đã bán": prod_dict.get("sold_count", "Không có dữ liệu"),
                    "Shop": prod_dict.get("shop", {}).get("shop_name", "N/A"),
                    "Ảnh": prod_dict.get("main_image", ""),
                    "Link": prod_dict.get("product_url", ""),
                }
            )
        elif current_id in blacklist_ids:
            rejected_products.append(
                {
                    "Tên": prod_dict.get("name", "N/A"),
                    "Giá": f"{int(prod_dict.get('price_current', 0)):,} VND",
                }
            )

    candidates = []
    pending_dicts = [p.model_dump(by_alias=False) if hasattr(p, "model_dump") else p for p in pending_products]

    for prod_dict in pending_dicts:
        current_id = str(prod_dict.get("product_id"))
        if current_id not in interacted_ids:
            candidates.append(prod_dict)
            if len(candidates) >= 20:
                break

    existing_candidate_ids = {str(c.get("product_id")) for c in candidates}
    for prod in all_products:
        if len(candidates) >= 40:
            break

        prod_dict = prod.model_dump(by_alias=False) if hasattr(prod, "model_dump") else prod
        current_id = str(prod_dict.get("product_id"))

        if current_id not in interacted_ids and current_id not in existing_candidate_ids:
            rating = float(prod_dict.get("rating_star", 0))
            if rating == 0.0 or rating >= 4.0:
                candidates.append(prod_dict)

    ai_candidates = []
    for candidate in candidates:
        ai_candidates.append(
            {
                "Tên": candidate.get("name", "N/A"),
                "Giá": f"{int(candidate.get('price_current', 0)):,} VND",
                "Đánh giá": f"{candidate.get('rating_star', 0)} ⭐",
                "Đã bán": candidate.get("sold_count", "Không có dữ liệu"),
                "Shop": candidate.get("shop", {}).get("shop_name", "N/A"),
                "Ảnh": candidate.get("main_image", ""),
                "Link": candidate.get("product_url", ""),
            }
        )

    prompt = f"""Hãy đóng vai một Chuyên gia Phân tích Mua sắm. Dựa trên dữ liệu dưới đây:

    [TỪ KHÓA TÌM KIẾM GỐC CỦA KHÁCH HÀNG]: \"{original_keyword}\"
    [Sản phẩm khách hàng đã bấm THÍCH (Đại diện cho gu của khách)]: {json.dumps(selected_products, ensure_ascii=False)}
    [Sản phẩm khách hàng KHÔNG THÍCH (Tuyệt đối NÉ các phong cách/mức giá tương tự)]: {json.dumps(rejected_products, ensure_ascii=False)}
    [Danh sách ứng viên]: {json.dumps(ai_candidates, ensure_ascii=False)}

    NHIỆM VỤ:
    Viết một báo cáo tư vấn mua sắm chuyên sâu bằng Tiếng Việt.

    RÀNG BUỘC CỐT LÕI (TUYỆT ĐỐI TUÂN THỦ):
    1. Chỉ được phép chọn các sản phẩm bám sát và đúng nghĩa với [TỪ KHÓA TÌM KIẾM GỐC].
    2. Nếu \"Sản phẩm khách hàng đã bấm Thích\" lạc quẻ với từ khóa gốc, hãy ƯU TIÊN TỪ KHÓA GỐC để chọn 10 sản phẩm. Không đề xuất sai mặt hàng.
    3. Phân tích [Sản phẩm khách hàng KHÔNG THÍCH] để LOẠI BỎ triệt để các phong cách, thiết kế hoặc tầm giá tương tự khỏi TOP 10 đề xuất.

    YÊU CẦU ĐỊNH DẠNG:
    1. Tóm tắt nhanh: Đánh giá chung về gu của khách.
    2. Danh sách đã chọn: Liệt kê ngắn gọn.
    3. TOP 10 đề xuất: Với mỗi sản phẩm, dùng đúng cấu trúc Markdown sau:

    #### [Số thứ tự]. [Tên sản phẩm]
    ![Ảnh sản phẩm](Link_Ảnh_Của_Sản_Phẩm)
    - **Giá tham khảo:** [Giá]
    - **Đánh giá & Lượt bán:** [Đánh giá] / [Đã bán]
    - **Ưu điểm:** [Phân tích]
    - **Khuyết điểm:** [Điểm cần cân nhắc]
    - **Đánh giá chuyên gia:** [Lời khuyên]
    - [Mua ngay tại đây](Link_Sản_Phẩm)

    4. Bảng So Sánh Tổng Hợp:
    | Tên sản phẩm | Giá | Đánh giá | Đã bán | Điểm nổi bật |

    - Không dùng dấu ngoặc nhọn '{{ }}' ngoài cấu trúc Markdown.
    - Nếu ghi \"Không có dữ liệu\", hãy bỏ qua hoặc ghi \"Đang cập nhật\".
    """

    try:
        async for text_chunk in generate_final_summary_stream(prompt):
            if text_chunk:
                yield MessageChunk(content=text_chunk)
    except Exception as exc:
        print(f"Error generating final summary: {exc}")
        traceback.print_exc()
        yield MessageChunk(
            content="\n\n*Hệ thống đang quá tải, không thể tạo báo cáo tóm tắt lúc này. Bạn vui lòng xem lại danh sách ở trên nhé!*"
        )

