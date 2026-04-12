import json
import logging
import random
import os
import time
import re

from patchright.sync_api import sync_playwright

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

# =======================================================
# CẤU HÌNH ĐƯỜNG DẪN DỮ LIỆU
# =======================================================
SHOPEE_CATEGORY_TREE = r"D:\Thực tập MB\Shopping_Research_Agent_V1_2\data\shopee_category_tree.json"
SHOPEE_DATA = r"D:\Thực tập MB\Shopping_Research_Agent_V1_2\data\shopee_data.jsonl"

os.makedirs(os.path.dirname(SHOPEE_DATA), exist_ok=True)


# =======================================================
# HÀM TẠO URL CHUẨN SHOPEE (SLUGIFY)
# =======================================================
def generate_shopee_url(display_name, catid, page_num=0):
    """Tạo URL chuẩn của Shopee dạng: /Ten-Danh-Muc-cat.ID?page=X"""
    # Thay thế & thành khoảng trắng
    name = display_name.replace("&", " ")
    # Loại bỏ ký tự đặc biệt, giữ lại chữ, số, tiếng Việt và khoảng trắng
    name = re.sub(r'[^\w\s-]', '', name)
    # Thay nhiều khoảng trắng thành 1 dấu gạch ngang
    name = re.sub(r'\s+', '-', name).strip('-')

    # Nếu tên bị rỗng sau khi lọc, fallback về 'a' (như shopee.vn/a-cat.123)
    if not name:
        name = 'a'

    return f"https://shopee.vn/{name}-cat.{catid}?page={page_num}"


# =======================================================
# 1. HÀM MAP DỮ LIỆU CHUẨN SCHEMA (Đã mở rộng lưới)
# =======================================================
def extract_and_map_data(response, extracted_data):
    if response.request.resource_type in ["image", "stylesheet", "font", "media", "script"]:
        return True

    url = response.url

    # Bắt cả search_items (Cũ) và recommend_v2 (Mới)
    if "api/v4/search/search_items" in url or "api/v4/recommend/recommend_v2" in url:
        if response.status == 403:
            return "CAPTCHA_DETECTED"

        try:
            res_text = response.text()
            if "90309999" in res_text:
                return "CAPTCHA_DETECTED"

            data = json.loads(res_text)
            items = []

            # --- LUỒNG 1: XỬ LÝ CHUẨN CŨ (Trang Search) ---
            if 'items' in data:
                for i in data['items']:
                    items.append({"source": "search", "data": i})

            # --- LUỒNG 2: XỬ LÝ CHUẨN MỚI (Trang Danh Mục recommend_v2) ---
            elif 'data' in data and 'units' in data['data']:
                for unit in data['data']['units']:
                    # Chỉ lấy những unit có chứa 'item'
                    if unit.get('data_type') == 'item' and 'item' in unit:
                        items.append({"source": "recommend_v2", "data": unit['item']})

            if not items:
                return "EMPTY"

            logger.info(f"🔥 BẮT TRÚNG MẠCH! Hốt trọn {len(items)} sản phẩm.")

            # --- MAP VÀO SCHEMA ---
            for item_wrapper in items:
                source = item_wrapper["source"]
                item = item_wrapper["data"]

                # Khởi tạo biến trống
                itemid, shopid, name, raw_price, raw_price_before = None, None, "", 0, 0
                raw_image, shop_location, sold_count = "", "", 0
                item_rating, raw_variations = {}, []

                if source == "search":
                    item_basic = item.get('item_basic', {})
                    itemid = item_basic.get('itemid')
                    shopid = item_basic.get('shopid')
                    name = item_basic.get('name', "")
                    raw_price = item_basic.get('price', 0)
                    raw_price_before = item_basic.get('price_before_discount', 0)
                    raw_image = item_basic.get('image', '')
                    item_rating = item_basic.get('item_rating', {})
                    raw_variations = item_basic.get('tier_variations', [])
                    sold_count = item_basic.get('historical_sold', 0)
                    shop_location = item_basic.get('shop_location', "")

                elif source == "recommend_v2":
                    item_data = item.get('item_data', {})
                    item_asset = item.get('item_card_displayed_asset', {})

                    itemid = item_data.get('itemid')
                    shopid = item_data.get('shopid')
                    name = item_asset.get('name', "")

                    price_info = item_data.get('item_card_display_price', {})
                    raw_price = price_info.get('price', 0)
                    raw_price_before = price_info.get('strikethrough_price', 0)

                    raw_image = item_asset.get('image', '')
                    item_rating = item_data.get('item_rating', {})
                    raw_variations = item_data.get('tier_variations', [])

                    shop_data = item_data.get('shop_data', {})
                    shop_location = shop_data.get('shop_location', "")

                    # API mới ẩn số sold_count tuyệt đối, thường trả text "Đã bán 10k+".
                    # Tạm gán 0 để không bị lỗi schema.
                    sold_count = 0

                    # Bỏ qua nếu thiếu ID
                if not itemid or not shopid:
                    continue

                # --- CHUẨN HOÁ DỮ LIỆU CUỐI CÙNG ---
                price_current = float(raw_price) / 100000 if raw_price else 0.0
                price_original = float(raw_price_before) / 100000 if raw_price_before else None
                main_image = f"https://down-vn.img.susercontent.com/file/{raw_image}" if raw_image else ""
                product_url = f"https://shopee.vn/product/{shopid}/{itemid}"

                rating_count_raw = item_rating.get('rating_count', [0])
                rating_count = rating_count_raw[0] if isinstance(rating_count_raw, list) and len(
                    rating_count_raw) > 0 else 0

                clean_variations = [{"name": v.get("name", ""), "options": v.get("options", [])} for v in
                                    raw_variations]

                mapped_item = {
                    "key": f"shopee_{itemid}",
                    "platform": "shopee",
                    "product_id": str(itemid),
                    "product_url": product_url,
                    "name": name,
                    "price_current": price_current,
                    "price_original": price_original,
                    "currency": "VND",
                    "main_image": main_image,
                    "rating_star": float(item_rating.get('rating_star', 0.0)) if isinstance(item_rating, dict) else 0.0,
                    "rating_count": int(rating_count),
                    "sold_count": int(sold_count),
                    "shop": {
                        "shop_id": str(shopid),
                        "shop_name": "",
                        "shop_location": shop_location
                    },
                    "tier_variations": clean_variations
                }
                extracted_data.append(mapped_item)
            return True

        except Exception as e:
            logger.error(f"❌ Lỗi parse JSON: {e}")
            return True

    return True

# =======================================================
# 2. LOGIC QUÉT 1 CATEGORY ID
# =======================================================
def scrape_category_sync(context, catid, full_name, slug_name, max_pages=5):
    """Quét sản phẩm bằng cách Click UI để ép gọi API"""
    extracted_data = []
    page = context.pages[0] if context.pages else context.new_page()

    has_more_data = True
    captcha_detected = False

    def handle_response(res):
        nonlocal has_more_data, captcha_detected
        result = extract_and_map_data(res, extracted_data)
        if result == "EMPTY":
            pass  # Bỏ qua, vì khi click UI có thể có lúc API trả rỗng giả
        elif result == "CAPTCHA_DETECTED":
            captcha_detected = True

    # Xóa và gắn lại listener để chống trùng lặp event
    page.remove_listener("response", handle_response)
    page.on("response", handle_response)

    try:
        # 1. GOTO ĐÚNG 1 LẦN VÀO TRANG ĐẦU TIÊN
        target_url = generate_shopee_url(slug_name, catid, page_num=0)
        logger.info(f"🚀 Mở danh mục [ {full_name} ]...")

        try:
            page.goto(target_url, wait_until="domcontentloaded", timeout=60000)
        except Exception as e:
            logger.warning(f"⚠️ Load trang hơi chậm: {e}. Vẫn tiếp tục...")

        if captcha_detected:
            logger.warning("⚠️ TẠM DỪNG: Vui lòng giải Captcha.")
            input("👉 Click vào 1 chỗ trống trên web rồi nhấn ENTER tại đây...")
            captcha_detected = False
            page.reload(wait_until="domcontentloaded")

        # 2. BẮT ĐẦU VÒNG LẶP CUỘN CHUỘT VÀ CLICK NEXT
        for page_num in range(max_pages):
            if not has_more_data or captcha_detected:
                break

            logger.info(f"🔄 Đang nghe ngóng data [ {full_name} ] - Trang {page_num}...")

            # Cuộn chuột sâu xuống để Shopee bung API lấy 30 sản phẩm cuối của trang hiện tại
            page.mouse.wheel(0, 2500)
            page.wait_for_timeout(2000)
            page.mouse.wheel(0, 3500)
            page.wait_for_timeout(3000)

            # 3. CLICK NÚT SANG TRANG (Bỏ qua nếu đang ở trang cuối cùng của vòng lặp)
            if page_num < max_pages - 1:
                try:
                    # Nút > (Next Page) của Shopee thường nằm trong class shopee-icon-button--right
                    next_button = page.locator('.shopee-icon-button--right').first

                    if next_button.is_visible() and not next_button.is_disabled():
                        logger.info("👉 Click sang trang tiếp theo...")
                        next_button.click()
                        page.wait_for_timeout(4000)  # Đứng chờ 4s cho API nhả data về
                    else:
                        logger.info("⚠️ Nút chuyển trang bị mờ hoặc không tìm thấy (Đã hết SP).")
                        break
                except Exception as e:
                    logger.error(f"Lỗi khi click nút sang trang: {e}")
                    break

    except Exception as e:
        logger.error(f"❌ Lỗi ở danh mục {full_name}: {e}")
    finally:
        # Nhớ tháo thính sau khi câu xong
        page.remove_listener("response", handle_response)

    return extracted_data

# =======================================================
# 3. HÀM CHÍNH (MAIN)
# =======================================================
def main():
    target_categories = []
    try:
        with open(SHOPEE_CATEGORY_TREE, "r", encoding="utf-8") as f:
            tree_data = json.load(f)
            category_list = tree_data.get("data", {}).get("category_list", [])

            for cat in category_list:
                level_1_name = cat.get("display_name")
                children = cat.get("children", [])

                if children:
                    for child in children:
                        target_categories.append({
                            "catid": child.get("catid"),
                            "full_name": f"{level_1_name} > {child.get('display_name')}",
                            "slug_name": child.get('display_name')  # Lấy tên ngắn để tạo URL
                        })
                else:
                    target_categories.append({
                        "catid": cat.get("catid"),
                        "full_name": level_1_name,
                        "slug_name": level_1_name
                    })
    except FileNotFoundError:
        logger.error(f"❌ Không tìm thấy file: {SHOPEE_CATEGORY_TREE}")
        return

    logger.info(f"📁 Tìm thấy {len(target_categories)} danh mục mục tiêu.")

    # Lấy 5 danh mục đầu tiên để chạy thử nghiệm
    test_categories = target_categories[5:]
    total_scraped = 0

    with sync_playwright() as p:
        user_data_dir = os.path.join(os.getcwd(), "shopee_chrome_profile")

        context = p.chromium.launch_persistent_context(
            user_data_dir=user_data_dir,
            headless=False,
            ignore_default_args=["--enable-automation"],  # Xóa thanh cảnh báo test software
            args=[
                '--disable-blink-features=AutomationControlled',
                '--no-sandbox'
            ],
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36",
            viewport={'width': 1920, 'height': 1080}
        )

        for cat in test_categories:
            catid = cat['catid']
            full_name = cat['full_name']
            slug_name = cat['slug_name']

            # Gọi hàm quét truyền cả full_name (để log) và slug_name (để tạo URL)
            res = scrape_category_sync(context, catid, full_name, slug_name, max_pages=5)

            if res:
                total_scraped += len(res)
                with open(SHOPEE_DATA, "a", encoding="utf-8") as f:
                    for item in res:
                        f.write(json.dumps(item, ensure_ascii=False) + '\n')
                logger.info(f"✅ Đã lưu {len(res)} SP từ [{full_name}] vào file.")
            else:
                logger.info(f"⚠️ Không lấy được SP nào từ [{full_name}]")

            delay = random.uniform(8.0, 15.0)
            logger.info(f"⏳ Nghỉ {delay:.1f}s...\n")
            time.sleep(delay)

        context.close()

    logger.info(f"🎉 HOÀN THÀNH! Tổng số sản phẩm lấy được phiên này: {total_scraped}")


if __name__ == "__main__":
    main()