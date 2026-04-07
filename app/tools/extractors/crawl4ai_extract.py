import json
from urllib.parse import urlparse
from bs4 import BeautifulSoup
from crawl4ai import AsyncWebCrawler, BrowserConfig, CrawlerRunConfig, CacheMode, LLMExtractionStrategy, LLMConfig

from app.core.config import ensure_api_key_configured
from app.core.config.config import settings
from app.schemas.entities import CapturedData
from app.tools.extractors.base import BaseExtractor

# --- DANH SÁCH CÁC TRANG SPA CẦN CẤU HÌNH NẶNG ---
SPA_DOMAINS = [
    "shopee.vn",
    "lazada.vn",
    "tiktok.com",
    "tiki.vn",
    "fado.vn"
]


def is_spa_website(url: str) -> bool:
    """Hàm kiểm tra xem URL có thuộc danh sách SPA cần chờ JS render không"""
    domain = urlparse(url).netloc.lower()
    for spa_domain in SPA_DOMAINS:
        if spa_domain in domain:
            return True
    return False


# --- HÀM CẤU HÌNH ĐỘNG ---
def get_crawl4ai_config(is_spa: bool):
    """Trả về cấu hình crawler tùy thuộc vào loại website"""

    if is_spa:
        # CẤU HÌNH CHO SHOPEE / SPA (Chậm nhưng chắc)
        print("⚙️ Kích hoạt cấu hình tải nặng cho trang SPA (chờ JS render)...")
        browser_config = BrowserConfig(
            headless=True,
            light_mode=False,  # Phải tắt để JS chạy
            verbose=False
        )
        run_config = CrawlerRunConfig(
            cache_mode=CacheMode.BYPASS,
            magic=True,
            delay_before_return_html=5.0,  # Chờ 5 giây
            page_timeout=30000
        )
    else:
        # CẤU HÌNH CHO TRANG BÌNH THƯỜNG (Siêu tốc)
        print("⚙️ Kích hoạt cấu hình siêu tốc cho trang tiêu chuẩn...")
        browser_config = BrowserConfig(
            headless=True,
            light_mode=True,  # Bật để giảm tải CSS/JS thừa
            verbose=False
        )
        run_config = CrawlerRunConfig(
            cache_mode=CacheMode.BYPASS,
            magic=True,
            wait_for="js:() => document.readyState === 'complete'",
            page_timeout=20000
        )

    return browser_config, run_config


def extract_schema_org_data(html_content: str):
    soup = BeautifulSoup(html_content, "html.parser")
    ld_json_tags = soup.find_all("script", type="application/ld+json")

    for tag in ld_json_tags:
        if not tag.string: continue
        try:
            data = json.loads(tag.string)
            if isinstance(data, dict) and data.get("@type") == "Product":
                return data
            elif isinstance(data, list):
                for item in data:
                    if item.get("@type") == "Product":
                        return item
        except json.JSONDecodeError:
            continue
    return None


async def extract_by_llm(target_url: str, is_spa: bool):
    """Hàm fallback sử dụng LLM để bóc tách, nhận thêm cờ is_spa"""

    extraction_strategy = LLMExtractionStrategy(
        llm_config=LLMConfig(
            provider="gemini/gemini-3.1-flash-lite-preview",
            api_token=settings.GOOGLE_API_KEY
        ),
        schema=CapturedData.model_json_schema(),
        instruction="Hãy trích xuất thông tin sản phẩm (tên, giá, link, ảnh...) từ nội dung trang web thương mại điện tử Shopee sau. Bỏ qua các sản phẩm rác."
    )

    browser_config, run_config = get_crawl4ai_config(is_spa)
    run_config.extraction_strategy = extraction_strategy

    # QUAN TRỌNG: Phải dùng BYPASS để ép crawler cào lại từ đầu, chờ đủ 5s
    run_config.cache_mode = CacheMode.BYPASS

    async with AsyncWebCrawler(config=browser_config) as crawler:
        result = await crawler.arun(url=target_url, config=run_config)

        if not result.success:
            raise Exception(f"Lỗi khi crawl bằng LLM: {result.error_message}")

        # --- ĐOẠN DEBUG QUAN TRỌNG ---
        # In ra tiêu đề trang web để xem có bị Shopee chặn (bắt đăng nhập/captcha) không
        soup = BeautifulSoup(result.html, "html.parser")
        page_title = soup.title.text if soup.title else 'Không có'
        print(f"📌 Crawler đang nhìn thấy trang có tiêu đề: '{page_title}'")

        if "đăng nhập" in page_title.lower() or "xác minh" in page_title.lower() or "captcha" in page_title.lower():
            print("🚨 BÁO ĐỘNG: Shopee đã phát hiện bot và chặn quyền truy cập (bắt đăng nhập/giải Captcha).")
            return {"error": "Bị Anti-bot của Shopee chặn."}
        # ------------------------------

        return json.loads(result.extracted_content)


class Crawl4AIExtractor(BaseExtractor):
    domains = []

    @classmethod
    def matches(cls, url: str) -> bool:
        return True

    async def extract(self, url: str):
        print(f"🚀 Khởi động cào dữ liệu: {url}")

        # Phân tích URL ngay từ đầu
        is_spa = is_spa_website(url)

        # Lấy cấu hình tương ứng
        browser_config, run_config = get_crawl4ai_config(is_spa)

        async with AsyncWebCrawler(config=browser_config) as crawler:
            result = await crawler.arun(url=url, config=run_config)

            if not result.success:
                return {"error": result.error_message}

            raw_html = result.html

            # --- ƯU TIÊN 1: Chuẩn SEO Quốc tế (JSON-LD) ---
            print("🔍 Đang tìm kiếm dữ liệu chuẩn SEO (JSON-LD)...")
            schema_data = extract_schema_org_data(raw_html)
            if schema_data:
                print("✅ Trích xuất THÀNH CÔNG bằng JSON-LD!")
                return schema_data

            # --- ƯU TIÊN 2: Chuẩn Next.js (__NEXT_DATA__) ---
            print("⚠️ Không có JSON-LD, đang tìm kiếm __NEXT_DATA__...")
            soup = BeautifulSoup(raw_html, "html.parser")
            next_data_script = soup.find("script", id="__NEXT_DATA__", type="application/json")
            if next_data_script:
                try:
                    next_data_json = json.loads(next_data_script.string)
                    print("✅ Trích xuất THÀNH CÔNG từ __NEXT_DATA__!")
                    return next_data_json
                except Exception as e:
                    print(f"⚠️ Lỗi parse JSON từ __NEXT_DATA__: {e}")

        # --- ƯU TIÊN 3: Fallback bằng AI Agent ---
        print("🤖 Các phương pháp tĩnh thất bại. Kích hoạt AI Agent (LLM Extraction)...")
        try:
            # Truyền cờ is_spa vào LLM fallback
            llm_data = await extract_by_llm(url, is_spa)
            print("✅ Trích xuất THÀNH CÔNG bằng mô hình AI!")
            return llm_data
        except Exception as e:
            return {"error": f"Quá trình trích xuất hoàn toàn thất bại: {e}"}


if __name__ == "__main__":
    # Test với Shopee (SPA)
    test_url = "https://www.facebook.com/TokyoLifeNow/videos/top-5-%C3%A1o-len-m%E1%BB%81m-%E1%BA%A5m-tokyolife-%C4%91%C6%B0%E1%BB%A3c-%C6%B0a-chu%E1%BB%99ng-nh%E1%BA%A5t-m%C3%B9a/1186824340186549/"

    # Test với web thường (Uniqlo/Routine/IconDenim...)
    # test_url = "https://icondenim.com/collections/quan-jean?srsltid=AfmBOopjs_9nWcI3YiBYm3uzqzt0Qwy1I17olNXxXVeioANZG2d_LXJA"

    extractor = Crawl4AIExtractor()
    import asyncio

    result = asyncio.run(extractor.extract(test_url))
    print("\n--- KẾT QUẢ TRÍCH XUẤT ---")
    print(json.dumps(result, indent=2, ensure_ascii=False))