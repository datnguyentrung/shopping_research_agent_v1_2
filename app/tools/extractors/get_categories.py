import json
from patchright.sync_api import sync_playwright


def fetch_shopee_categories():
    print("🚀 Đang dùng Playwright lách tường lửa lấy danh mục...")
    url = "https://shopee.vn/api/v4/pages/get_category_tree"

    with sync_playwright() as p:
        # Khởi tạo trình duyệt với các tham số chống nhận diện bot
        browser = p.chromium.launch(
            headless=True,
            args=['--disable-blink-features=AutomationControlled']
        )
        context = browser.new_context(
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36"
        )
        page = context.new_page()

        try:
            # Bước 1: Ghé thăm trang chủ Shopee để lấy Cookies và Session thật
            print("⏳ 1. Truy cập trang chủ để tạo session hợp lệ...")
            page.goto("https://shopee.vn/", wait_until="domcontentloaded", timeout=30000)
            page.wait_for_timeout(3000)  # Đợi 3s cho các script bảo mật của Shopee chạy xong

            # Bước 2: Dùng chính trình duyệt đó để gọi API (Sẽ mang theo toàn bộ cookie vừa nhận)
            print("📡 2. Gọi API lấy Cây danh mục gốc...")
            response = page.request.get(url)

            if response.ok:
                data = response.json()
                category_list = data.get("data", {}).get("category_list", [])

                # Trích xuất Level 1 và Level 2
                extracted_categories = []
                for cat in category_list:
                    level_1_name = cat.get("display_name")
                    children = cat.get("children", [])

                    for child in children:
                        extracted_categories.append({
                            "catid": child.get("catid"),
                            "name": f"{level_1_name} > {child.get('display_name')}"
                        })

                # Lưu ra file
                with open("shopee_categories.json", "w", encoding="utf-8") as f:
                    json.dump(extracted_categories, f, ensure_ascii=False, indent=2)

                print(f"\n✅ THÀNH CÔNG! Đã lưu {len(extracted_categories)} danh mục vào shopee_categories.json")
            else:
                print(f"\n❌ Vẫn bị chặn. Trạng thái: {response.status} - {response.status_text}")

        except Exception as e:
            print(f"\n❌ Có lỗi xảy ra: {e}")
        finally:
            browser.close()


if __name__ == "__main__":
    fetch_shopee_categories()