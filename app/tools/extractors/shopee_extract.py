import asyncio
import logging
import urllib

from patchright.sync_api import sync_playwright

logger = logging.getLogger(__name__)

def _run_shopee_logic(keyword: str, limit: int = 30) -> list:
    """
    Logic chính của Playwright chạy ở chế độ ĐỒNG BỘ (Sync)
    để tránh xung đột Event Loop trên Windows.
    """
    keyword_encoded = urllib.parse.quote(keyword)
    search_url = f"https://shopee.vn/search?keyword={keyword_encoded}"
    extracted_data = []

    # Sử dụng sync_playwright
    with sync_playwright() as p:
        # Khởi chạy trình duyệt
        browser = p.chromium.launch(
            headless=True,
            args=['--disable-blink-features=AutomationControlled']
        )

        context = browser.new_context(
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36",
            viewport={'width': 1920, 'height': 1080}
        )
        page = context.new_page()

        # ==========================================
        # HÀM LẮNG NGHE & MAP DỮ LIỆU
        # ==========================================
        def handle_response(response):
            if "api/v4/search/search_items" in response.url and response.status == 200:
                try:
                    data = response.json()
                    items = data.get('items', [])
                    if items:
                        for item in items[:limit]:
                            item_basic = item.get('item_basic', {})

                            shopid = item_basic.get('shopid')
                            itemid = item_basic.get('itemid')

                            # 1. Ghép URL sản phẩm
                            product_url = f"https://shopee.vn/product/{shopid}/{itemid}" if shopid and itemid else ""

                            # 2. Xử lý chia giá (loại bỏ phần nghìn tỷ của Shopee)
                            raw_price = item_basic.get('price', 0)
                            price_current = float(raw_price) / 100000 if raw_price else 0

                            raw_price_before = item_basic.get('price_before_discount', 0)
                            price_original = float(raw_price_before) / 100000 if raw_price_before else 0

                            # 3. Ghép link ảnh chính
                            raw_image = item_basic.get('image', '')
                            main_image = f"https://down-vn.img.susercontent.com/file/{raw_image}" if raw_image else ""

                            # 4. Xử lý Rating Count (Shopee trả về mảng, index [0] là tổng)
                            item_rating = item_basic.get('item_rating', {})
                            rating_count_raw = item_rating.get('rating_count')
                            if isinstance(rating_count_raw, list) and len(rating_count_raw) > 0:
                                rating_count = rating_count_raw[0]
                            else:
                                rating_count = rating_count_raw if isinstance(rating_count_raw, (int, float)) else 0

                            # 5. Xử lý tier_variations: Loại bỏ 'images', chỉ giữ 'name' và 'options'
                            raw_variations = item_basic.get('tier_variations', [])
                            clean_variations = []
                            for v in raw_variations:
                                clean_variations.append({
                                    "name": v.get("name", ""),
                                    "options": v.get("options", [])
                                })

                            # 6. Map vào Object chuẩn
                            mapped_item = {
                                "platform": "shopee",
                                "product_id": itemid,
                                "name": item_basic.get('name'),
                                "price_current": price_current,
                                "price_original": price_original,
                                "currency": "VND",
                                "main_image": main_image,
                                "rating_star": item_rating.get('rating_star', 0),
                                "rating_count": rating_count,
                                "sold_count": item_basic.get('historical_sold', 0),
                                "shop": {
                                    "shop_id": shopid,
                                    "shop_name": "",  # Search API Shopee thường không có tên shop ở đây
                                    "shop_location": item_basic.get('shop_location')
                                },
                                "tier_variations": clean_variations,
                                "product_url": product_url
                            }
                            extracted_data.append(mapped_item)
                except Exception as e:
                    logger.warning(f"⚠️ Lỗi khi đọc/map JSON: {e}")

        page.on("response", handle_response)

        try:
            logger.info(f"🚀 Đang truy cập Shopee để tìm: {keyword}...")
            # Chờ networkidle ở bản sync
            page.goto(search_url, wait_until="networkidle", timeout=30000)
            # Nghỉ thêm một chút để đảm bảo intercept kịp
            page.wait_for_timeout(3000)
        except Exception as e:
            logger.error(f"❌ Lỗi khi tải trang: {e}")
        finally:
            browser.close()

    return extracted_data

async def fetch_shopee_data(keyword: str, limit: int = 30) -> list:
    """
    Tool tìm kiếm sản phẩm Shopee thông qua kỹ thuật Network Interception.
    Đã được tối ưu để chạy trên Windows.
    """
    # CHÌA KHÓA: Đẩy logic sync vào một thread riêng để né lỗi Event Loop của ADK
    return await asyncio.to_thread(_run_shopee_logic, keyword, limit)  # Giới hạn 10 sản phẩm
