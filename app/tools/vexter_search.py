import json
from typing import List

from fastapi import HTTPException
from google.cloud import discoveryengine

from app.core.config.config import settings
from app.schemas.entities import CapturedData
from app.schemas.requests import SearchRequest
import asyncio

# Thêm hàm helper này để đệ quy gỡ toàn bộ Google Protobuf objects thành cấu trúc Python chuẩn
def parse_protobuf_data(data):
    if hasattr(data, 'items'):  # Xử lý MapComposite (tương đương Dict)
        return {k: parse_protobuf_data(v) for k, v in data.items()}
    elif hasattr(data, '__iter__') and not isinstance(data, (str, bytes)):  # Xử lý RepeatedComposite (tương đương List)
        return [parse_protobuf_data(i) for i in data]
    else:
        return data

async def perform_search(request: SearchRequest) -> List[CapturedData]:
    try:
        client = discoveryengine.SearchServiceAsyncClient()

        serving_config = f"projects/{settings.PROJECT_ID}/locations/global/collections/default_collection/engines/{settings.VEXTER_ENGINE_ID}/servingConfigs/default_search"

        search_keyword = request.keyword

        search_filter = ""
        if request.category_filter:
            try:
                # Đảm bảo filter truyền vào là con số hợp lệ
                max_price = float(request.category_filter)
                search_filter = f'price_current <= {max_price}'
            except ValueError:
                # Nếu không phải số thì bỏ qua filter hoặc xử lý lỗi
                search_filter = ""

        search_req = discoveryengine.SearchRequest(
            serving_config=serving_config,
            query=search_keyword,
            filter=search_filter if search_filter else None,
            page_size=1000,  # Thử tăng lên 1000
        )

        response = await client.search(search_req)

        results_list = []

        # Vì dùng AsyncClient, response trả về có thể cần lặp bất đồng bộ (async for)
        async for result in response:
            # 1. Gỡ Protobuf thành Dictionary thông thường
            clean_product_dict = parse_protobuf_data(result.document.struct_data)

            # 2. Map dict vào thẳng Pydantic Model (CapturedData)
            # Dùng ** để unpack dict. Pydantic sẽ tự động bắt các field trùng tên
            # và bỏ qua các field thừa (như _vertex_document_id, product_url)
            try:
                captured_item = CapturedData(**clean_product_dict)
                results_list.append(captured_item)
            except Exception as validation_error:
                # Catch lỗi nếu có 1 doc bị thiếu trường bắt buộc để không làm sập cả list
                print(f"⚠️ Bỏ qua sản phẩm lỗi map data: {validation_error}")
                continue

        return results_list

    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc))

if __name__ == "__main__":
    # Thay category_filter thành None hoặc bỏ hẳn đi
    test_request = SearchRequest(keyword="ao khoac bomber nam chinh hang", category_filter=None)
    search_results = asyncio.run(perform_search(test_request))
    print(json.dumps(search_results, indent=2, ensure_ascii=False))