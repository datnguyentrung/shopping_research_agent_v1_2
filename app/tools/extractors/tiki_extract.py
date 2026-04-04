import requests
import logging

logger = logging.getLogger(__name__)


async def fetch_tiki_data(keyword: str, limit: int = 30) -> list:
    logger.info(f"[TIKI] Đang tìm kiếm: {keyword}")
    url = "https://tiki.vn/api/v2/products"
    params = {"q": keyword, "limit": limit}
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/120.0.0.0"
    }

    try:
        response = requests.get(url, params=params, headers=headers, timeout=10)
        if response.status_code == 200:
            data = response.json().get("data", [])
            results = []
            for item in data:
                # Bắt buộc phải có giá và ảnh mới lấy
                if item.get("price") and item.get("thumbnail_url"):
                    results.append({
                        "platform": "tiki",
                        "product_id": item.get("id"),
                        "name": item.get("name"),
                        "price_current": float(item.get("price")),
                        "main_image": item.get("thumbnail_url"),
                        "url": f"https://tiki.vn/{item.get('url_path')}",
                        # Tự tạo tags cơ bản từ title
                        "key_features": {"Thương hiệu": item.get("brand_name", "Khác")}
                    })
            logger.info(f"[TIKI] Đã lấy thành công {len(results)} sản phẩm")
            return results
    except Exception as e:
        logger.error(f"[TIKI] Lỗi: {e}")
    return []