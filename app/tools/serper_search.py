import asyncio
import re
from typing import List

import httpx
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


async def serper_search(keyword: str, min_price: float = None, max_price: float = None) -> List[CapturedData]:
  url = "https://google.serper.dev/shopping"

  payload = {
    "q": keyword,
    "gl": "vn",
    "hl": "vi"
  }

  # --- TÍCH HỢP CẢ MIN VÀ MAX VÀO CÚ PHÁP LỌC GIÁ ---
  tbs_parts = ["mr:1", "price:1"]
  has_price_filter = False

  if min_price is not None and min_price > 0:
    tbs_parts.append(f"ppr_min:{int(min_price)}")
    has_price_filter = True

  if max_price is not None and max_price > 0:
    tbs_parts.append(f"ppr_max:{int(max_price)}")
    has_price_filter = True

  if has_price_filter:
    payload["tbs"] = ",".join(tbs_parts)  # Ví dụ kết quả: mr:1,price:1,ppr_min:300000,ppr_max:600000
  # ----------------------------------------------------

  headers = {
    'X-API-KEY': settings.SERPER_API_KEY,
    'Content-Type': 'application/json'
  }

  print(f"Đang gọi API Serper với payload: {payload}")

  loop = asyncio.get_event_loop()
  response = await loop.run_in_executor(
    None,
    lambda: requests.post(url, headers=headers, json=payload)
  )

  data = response.json()
  captured_list = map_serper_to_captured_data(data)

  return [item.model_dump() for item in captured_list]

if __name__ == "__main__":
    # Test hàm serper_search với một từ khóa mẫu
    test_keyword = "Áo thun nam đẹp"
    results = asyncio.run(serper_search(test_keyword))
    print(f"Tổng sản phẩm thu được từ Serper: {len(results)}")
    # In ra một vài sản phẩm đầu tiên để kiểm tra
    print(json.dumps(results, indent=3, ensure_ascii=False))