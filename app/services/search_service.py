# app/services/search_service.py
import asyncio
from app.schemas.requests import SearchRequest
from app.tools.serper_search import serper_search
from app.tools.vexter_search import perform_search


# Import các hàm bạn đã có: perform_search (Vertex), classify_keyword_topk, serper_search...

async def run_parallel_searches(keyword_vi: str) -> list[dict]:
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
    if vertex_res and "data" in vertex_res:
        combined_results.extend(vertex_res["data"])

    if serper_res and "products" in serper_res:
        combined_results.extend(serper_res["products"])

    print(f"✅ [Background] Đã tìm xong. Tổng: {len(combined_results)} sản phẩm.")
    return combined_results