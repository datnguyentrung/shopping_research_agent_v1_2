import json

from bs4 import BeautifulSoup
from crawl4ai import AsyncWebCrawler, BrowserConfig, CrawlerRunConfig, CacheMode, LLMExtractionStrategy

from app.tools.extractors.base import BaseExtractor
# 1. Đổi thành hàm đồng bộ bình thường (bỏ async)
def get_crawl4ai_config():
    browser_config = BrowserConfig(
        headless=True,
        light_mode=True, # Chỉ tải HTML, bỏ qua CSS/JS để tăng tốc độ và giảm tài nguyên, phù hợp với mục đích chỉ lấy dữ liệu JSON trong __NEXT_DATA__
        verbose=False # Tắt log chi tiết của crawl4ai để terminal gọn hơn, chỉ in kết quả cuối thôi
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
    # Quét tất cả các thẻ script chuẩn SEO
    ld_json_tags = soup.find_all("script", type="application/ld+json")

    for tag in ld_json_tags:
        if not tag.string: continue
        try:
            data = json.loads(tag.string)
            # Schema.org có thể trả về list hoặc dict
            if isinstance(data, dict) and data.get("@type") == "Product":
                return data
            elif isinstance(data, list):
                for item in data:
                    if item.get("@type") == "Product":
                        return item
        except json.JSONDecodeError:
            continue
    return None



class Crawl4AIExtractor(BaseExtractor):
    domains = []

    @classmethod
    def matches(cls, url: str) -> bool:
        # Crawl4AI có thể xử lý mọi URL nên luôn trả về True
        return True

    async def extract(self, url: str):
        print(f"🚀 Khởi động cào dữ liệu: {url}")

        # Lấy cấu hình từ hàm đồng bộ
        browser_config, run_config = get_crawl4ai_config()

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
            return None

        # --- ƯU TIÊN 3: Fallback bằng AI Agent (Chậm hơn, tốn token nhưng cân mọi web) ---
        # print("🤖 Các phương pháp tĩnh thất bại. Kích hoạt AI Agent (LLM Extraction)...")
        # try:
        #     llm_data = await extract_by_llm(target_url)
        #     print("✅ Trích xuất THÀNH CÔNG bằng mô hình AI!")
        #     return llm_data
        # except Exception as e:
        #     return {"error": f"Quá trình trích xuất hoàn toàn thất bại: {e}"}
