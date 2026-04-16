# app/services/search_service.py
import asyncio

from app.schemas.entities import CapturedData
from app.schemas.requests import SearchRequest
from app.tools.serper_search import serper_search
from app.tools.vertex_search import perform_search
from app.utils.trace_log import trace_plain, trace_print


# Import các hàm bạn đã có: perform_search (Vertex), classify_keyword_topk, serper_search...

def _get_value(item, key: str):
    if isinstance(item, dict):
        return item.get(key)
    return getattr(item, key, None)


def _dedupe_by_platform_product_id(*sources):
    """Giữ thứ tự xuất hiện đầu tiên, unique theo (platform, product_id)."""
    seen: set[tuple[str, str]] = set()
    merged = []

    for source in sources:
        if not source:
            continue

        for item in source:
            platform = str(_get_value(item, "platform") or "").strip().lower()
            product_id = str(_get_value(item, "product_id") or "").strip()

            # Nếu thiếu 1 trong 2 trường khóa thì vẫn giữ lại để tránh mất dữ liệu.
            if not platform or not product_id:
                merged.append(item)
                continue

            key = (platform, product_id)
            if key in seen:
                continue

            seen.add(key)
            merged.append(item)

    return merged


async def run_parallel_searches(
    keyword_vi: str,
    min_price: float = None,
    max_price: float = None,
    trace_id: str | None = None,
) -> list[CapturedData]:
    """Chạy đồng thời các nguồn search và gom kết quả"""
    trace_key = trace_id or "no-trace"
    trace_print(
        trace_key,
        "run_parallel_searches",
        "enter",
        keyword=keyword_vi,
        minPrice=min_price,
        maxPrice=max_price,
    )

    trace_plain(f"🔍 [Background] Đang tìm kiếm ngầm cho: {keyword_vi} | Min: {min_price} | Max: {max_price}")

    # 1. Xây dựng chuỗi truy vấn chuẩn cho Vertex AI
    vertex_filters = []
    if min_price is not None:
        vertex_filters.append(f"price_current >= {min_price}")
    if max_price is not None:
        vertex_filters.append(f"price_current <= {max_price}")

    final_vertex_filter = " AND ".join(vertex_filters) if vertex_filters else None

    # Gắn chuỗi filter vào SearchRequest
    search_req = SearchRequest(
        keyword=keyword_vi,
        category_filter=final_vertex_filter  # Đẩy nguyên chuỗi vào đây
    )

    task_vertex = asyncio.create_task(perform_search(search_req))

    # Truyền cả min và max vào Serper
    task_serper = asyncio.create_task(serper_search(keyword_vi, min_price, max_price))

    # Chờ cả 2 hoàn thành
    vertex_res = await task_vertex
    serper_res = await task_serper

    trace_print(
        trace_key,
        "run_parallel_searches",
        "sources_completed",
        vertexCount=len(vertex_res) if vertex_res else 0,
        serperCount=len(serper_res) if serper_res else 0,
    )

    combined_results = _dedupe_by_platform_product_id(vertex_res, serper_res)

    trace_plain(f"✅ [Background] Đã tìm xong. Tổng sau dedupe: {len(combined_results)} sản phẩm.")
    trace_print(
        trace_key,
        "run_parallel_searches",
        "exit",
        dedupedCount=len(combined_results),
    )
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
    trace_plain(f"Tổng sản phẩm thu được: {len(results)}")
    # In ra một vài sản phẩm đầu tiên để kiểm tra
    for i, product in enumerate(results[:5]):
        trace_plain(f"Product {i+1}: {product}")
