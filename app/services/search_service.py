# app/services/search_service.py
import asyncio

from app.schemas.entities import CapturedData
from app.schemas.requests import SearchRequest
from app.tools.serper_search import serper_search
from app.tools.vertex_search import perform_search


# Import các hàm bạn đã có: perform_search (Vertex), classify_keyword_topk, serper_search...

async def run_parallel_searches(keyword_vi: str) -> list[CapturedData]:
    """Chạy đồng thời các nguồn search và gom kết quả"""
    print(f"🔍 [Background] Đang tìm kiếm ngầm cho: {keyword_vi}")

    # Giả sử bạn bọc API Serper vào một hàm async get_serper_results
    task_vertex = asyncio.create_task(perform_search(SearchRequest(keyword=keyword_vi)))
    task_serper = asyncio.create_task(serper_search(keyword_vi))

    # Chờ cả 2 hoàn thành (có thể thêm timeout để tránh treo)
    vertex_res = await task_vertex
    serper_res = await task_serper

    # Gom và chuẩn hóa dữ liệu về cùng chuẩn CapturedData (dict)
    combined_results = []
    if vertex_res:
        combined_results.extend(vertex_res)

    if serper_res:
        combined_results.extend(serper_res)

    print(f"✅ [Background] Đã tìm xong. Tổng: {len(combined_results)} sản phẩm.")
    return combined_results

### OUTPUT MẪU:
# 🔍 [Background] Đang tìm kiếm ngầm cho: Áo thun nam đẹp
# Đang gọi API Serper...
# ✅ [Background] Đã tìm xong. Tổng: 1265 sản phẩm.
# Tổng sản phẩm thu được: 1265
# Product 1: {'platform': 'tiki', 'product_id': '1e205daf37c8dec74045db57d1688526', 'product_url': 'https://tiki.vn/ao-thun-nam-ao-phong-nam-co-tron-khong-co-out-of-control-thoi-trang-sieu-hot-hang-dep-bao-dep-m190-p113052442.html?spid=113052553', 'name': 'Áo thun nam Áo phông nam cổ tròn - không cổ Out of control thời trang siêu hot hàng đẹp bao đẹp-M190', 'price_current': 203950.0, 'price_original': 0.0, 'currency': 'VND', 'main_image': 'https://salt.tikicdn.com/cache/280x280/ts/product/65/b0/6a/f1ee6d7d015f77132ab74eb4cce0e59d.jpg', 'rating_star': 4.0, 'rating_count': 4, 'sold_count': None, 'shop': {'shop_id': 'Unknown', 'shop_name': 'Unknown', 'shop_location': None}, 'tier_variations': []}
# Product 2: {'platform': 'tiki', 'product_id': '580bf07fa652b4212640308d9a59778f', 'product_url': 'https://tiki.vn/ao-thun-nam-nhieu-mau-p55424651.html?spid=113224948', 'name': 'Áo Thun Nam Nhiều Mẫu', 'price_current': 371950.0, 'price_original': 0.0, 'currency': 'VND', 'main_image': 'https://salt.tikicdn.com/cache/280x280/ts/product/5a/b8/a2/10ed2a18a7190bd8fa225998df12488b.jpg', 'rating_star': 0.0, 'rating_count': 0, 'sold_count': None, 'shop': {'shop_id': 'Unknown', 'shop_name': 'Unknown', 'shop_location': None}, 'tier_variations': []}
# Product 3: {'platform': 'tiki', 'product_id': '263484608', 'product_url': 'https://tiki.vn/ao-thun-nam-nhat-tuan-thoi-trang-p263484608.html?spid=263484644', 'name': 'Áo thun nam Nhật Tuấn thời trang', 'price_current': 310000.0, 'price_original': 0.0, 'currency': 'VND', 'main_image': 'https://salt.tikicdn.com/cache/280x280/ts/product/01/8a/26/7cf35d12d7d47198e0e6ad9342fb048e.jpg', 'rating_star': 0.0, 'rating_count': 0, 'sold_count': 1, 'shop': {'shop_id': 'Unknown', 'shop_name': 'OEM', 'shop_location': None}, 'tier_variations': []}
# Product 4: {'platform': 'tiki', 'product_id': '55424651', 'product_url': 'https://tiki.vn/ao-thun-nam-nhieu-mau-p55424651.html?spid=113224948', 'name': 'Áo Thun Nam Nhiều Mẫu', 'price_current': 371950.0, 'price_original': 0.0, 'currency': 'VND', 'main_image': 'https://salt.tikicdn.com/cache/280x280/ts/product/5a/b8/a2/10ed2a18a7190bd8fa225998df12488b.jpg', 'rating_star': 0.0, 'rating_count': 0, 'sold_count': 0, 'shop': {'shop_id': 'Unknown', 'shop_name': 'OEM', 'shop_location': None}, 'tier_variations': []}
# Product 5: {'platform': 'tiki', 'product_id': 'cf76d26531586eae1ee1b6c6a685bf54', 'product_url': 'https://tiki.vn/ao-thun-nam-the-thao-phoi-vien-vai-co-gian-tot-p81928420.html?spid=113225938', 'name': 'ÁO THUN NAM THỂ THAO PHỐI VIỀN VAI CO GIÃN TỐT', 'price_current': 298450.0, 'price_original': 0.0, 'currency': 'VND', 'main_image': 'https://salt.tikicdn.com/cache/280x280/ts/product/73/62/7e/3eb12298fe6b30ef5e8de253836011a7.jpg', 'rating_star': 0.0, 'rating_count': 0, 'sold_count': None, 'shop': {'shop_id': 'Unknown', 'shop_name': 'Unknown', 'shop_location': None}, 'tier_variations': []}
if __name__ == "__main__":
    # Test chạy song song
    test_keyword = "Áo thun nam đẹp"
    results = asyncio.run(run_parallel_searches(test_keyword))
    print(f"Tổng sản phẩm thu được: {len(results)}")
    # In ra một vài sản phẩm đầu tiên để kiểm tra
    for i, product in enumerate(results[:5]):
        print(f"Product {i+1}: {product}")