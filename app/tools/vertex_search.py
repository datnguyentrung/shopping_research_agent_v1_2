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

        search_filter = request.category_filter if request.category_filter else None

        search_req = discoveryengine.SearchRequest(
            serving_config=serving_config,
            query=search_keyword,
            filter=search_filter,  # Truyền thẳng vào đây
            page_size=50,
        )

        response = await client.search(search_req)

        results_list = []

        # Vì dùng AsyncClient, response trả về có thể cần lặp bất đồng bộ (async for)
        async for result in response:
            # 2. Kiểm tra nếu đã đủ 50 sản phẩm hợp lệ thì dừng lại ngay
            if len(results_list) >= 50:
                break

            # 1. Gỡ Protobuf thành Dictionary
            clean_product_dict = parse_protobuf_data(result.document.struct_data)

            # CỨU CÁNH CHO PRODUCT_ID:
            # Nếu trong struct_data không có product_id, lấy ID của document đắp vào
            if "product_id" not in clean_product_dict:
                clean_product_dict["product_id"] = result.document.id

            # Đảm bảo có object shop (dù rỗng) để đưa vào Pydantic
            if "shop" not in clean_product_dict:
                clean_product_dict["shop"] = {}
            else:
                if "shop_id" in clean_product_dict["shop"] and clean_product_dict["shop"]["shop_id"] is not None:
                    shop_id_val = clean_product_dict["shop"]["shop_id"]
                    if isinstance(shop_id_val, float):
                        clean_product_dict["shop"]["shop_id"] = int(shop_id_val)
                    clean_product_dict["shop"]["shop_id"] = str(shop_id_val)

            # 2. Map dict vào thẳng Pydantic Model
            try:
                captured_item = CapturedData(**clean_product_dict)
                results_list.append(captured_item.model_dump())
            except Exception as validation_error:
                # Lúc này nếu vẫn lỗi, nghĩa là thiếu những trường BẮT BUỘC khác
                print(f"⚠️ Bỏ qua sản phẩm: {validation_error}")
                continue

        return results_list

    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc))

if __name__ == "__main__":
    # Thay category_filter thành None hoặc bỏ hẳn đi
    test_request = SearchRequest(keyword="áo sơ mi trắng", category_filter=None)
    search_results = asyncio.run(perform_search(test_request))
    print(json.dumps(search_results, indent=2, ensure_ascii=False))