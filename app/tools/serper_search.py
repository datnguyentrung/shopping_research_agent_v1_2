import asyncio
import re
from typing import List

import requests
import json
from app.core.config.config import settings
from app.schemas.entities import ShopInfo, CapturedData


def map_serper_to_captured_data(serper_data: dict) -> list[CapturedData]:
  """
  Map dữ liệu JSON từ Google Serper Shopping sang List[CapturedData]
  """
  results = []
  shopping_items = serper_data.get("shopping", [])

  for item in shopping_items:
    # 1. Trích xuất thông tin Cửa hàng / Nền tảng
    source_name = item.get("source", "Unknown_Shop")
    product_link = item.get("link", "")

    shop_info = ShopInfo(
      shop_id=source_name.lower().replace(".vn", "").replace(".com", ""),  # Tạo ID giả dựa trên tên
      shop_name=source_name,
      shop_location=item.get("shop_location")
    )

    # 2. Tạo object CapturedData
    captured_item = CapturedData(
      platform="google_shopping",
      product_id=item.get("productId", str(item.get("position", 0))),  # Fallback về position nếu mất ID
      product_url=product_link,
      name=item.get("title", "No Name"),
      price_current=clean_vnd_price(item.get("price", "")),
      price_original=None,  # Serper thường không có giá gốc
      main_image=item.get("imageUrl", ""),
      rating_star=item.get("rating", 0.0),  # Lấy rating nếu Serper có trả về (đôi khi có)
      rating_count=item.get("ratingCount", 0),
      sold_count=None,
      shop=shop_info,
      tier_variations=[]
    )

    results.append(captured_item)

  return results

def clean_vnd_price(price_str: str) -> float:
  """
  Hàm làm sạch chuỗi giá tiền.
  VD: "275.000 ₫" -> 275000.0
  """
  if not price_str:
    return 0.0
  # Dùng regex loại bỏ tất cả các ký tự không phải là số (xóa cả dấu chấm, phẩy, ký hiệu tiền)
  cleaned = re.sub(r'[^\d]', '', price_str)
  return float(cleaned) if cleaned else 0.0



async def serper_search(keyword: str) -> List[CapturedData]:
  # 1. Dùng endpoint /search
  url = "https://google.serper.dev/shopping"

  # 2. Payload với từ khóa giao dịch trực tiếp
  payload = {
    "q": keyword,
    "gl": "vn",
    "hl": "vi"
  }

  headers = {
    'X-API-KEY': settings.SERPER_API_KEY,
    'Content-Type': 'application/json'
  }

  print("Đang gọi API Serper...")
  response = requests.post(url, headers=headers, json=payload)
  data = response.json()

  # print("data:", data)

  # Thực hiện Mapping
  captured_list = map_serper_to_captured_data(data)

  return [item.model_dump() for item in captured_list]

# # 3. Đường dẫn file JSON của bạn
# file_path = r'D:\Thực tập MB\Shopping_Research_Agent_V1_2\data\serper_ouput.json'
#
# # 4. Lưu response vào file JSON
# with open(file_path, 'w', encoding='utf-8') as f:
#     json.dump(data, f, ensure_ascii=False, indent=2)
#
# print(f"✅ Đã lưu kết quả thành công vào: {file_path}")

if __name__ == "__main__":
    # Test hàm serper_search với một từ khóa mẫu
    test_keyword = "Áo thun nam đẹp"
    results = asyncio.run(serper_search(test_keyword))
    print(f"Tổng sản phẩm thu được từ Serper: {len(results)}")
    # In ra một vài sản phẩm đầu tiên để kiểm tra
    print(json.dumps(results, indent=3, ensure_ascii=False))