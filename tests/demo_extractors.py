import asyncio
import json
import logging
import secrets

# Chỉnh sửa đường dẫn import nếu cần thiết để khớp với project của bạn
from app.tools.extractors.registry import extract
from app.tools.extractors.shopee_extract import fetch_shopee_data
from app.tools.extractors.tiki_extract import fetch_tiki_data

# Tắt bớt log rác của thư viện bên thứ 3 để console sạch sẽ
logging.getLogger("httpx").setLevel(logging.WARNING)
logging.basicConfig(level=logging.INFO, format="%(levelname)s - %(message)s")
logger = logging.getLogger(__name__)

# ==========================================
# 1. QUẢN LÝ TRẠNG THÁI TOÀN CỤC (GLOBAL STATE)
# ==========================================
class AppState:
    def __init__(self):
        self.big_data = []  # Chứa các sản phẩm đã cào thành công
        self.temp_data = []  # Chứa các sản phẩm đang được cào, chưa lọc
        self.filter_map = {}  # dict: map<thuộc tính> = [giá trị]
        self.whitelist = set()
        self.blacklist = set()
        self.is_extracting = True  # Cờ báo hiệu quá trình cào nền còn chạy không
        self.ui_phase_1_done = False  # Cờ báo hiệu người dùng đã chọn xong filter sơ bộ chưa


state = AppState()

# ==========================================
# 2. CÁC HÀM CÀO DỮ LIỆU NỀN (BACKGROUND WORKERS)
# ==========================================

async def worker_fast_apis(keyword: str):
    """Worker này chạy cực nhanh, lấy data từ Shopee/Tiki ném ngay vào big_data"""
    logger.info("[WORKER] Đang chạy API siêu tốc (Tiki/Shopee)...")

    loop = asyncio.get_running_loop()

    # 1. Ném cả 2 hàm vào ThreadPool để nó chạy nền NGAY LẬP TỨC
    task_tiki = fetch_tiki_data(keyword, 10)

    # 2. Shopee của bạn ĐÃ LÀ hàm async -> Gọi thẳng
    # task_shopee = fetch_shopee_data(keyword)

    # 3. GATHER: Chạy đua song song cả 2 sàn!
    # return_exceptions=True giúp hệ thống KHÔNG BỊ SẬP nếu 1 trong 2 trang web bị lỗi mạng
    results = await asyncio.gather(
        task_tiki,
        # task_shopee,
        return_exceptions=True
    )

    tiki_data = results[0]
    # shopee_data = results[1]

    # 4. Kiểm tra và bơm data vào kho chứa (State)
    # if isinstance(shopee_data, list):
    #     logger.info(f"[WORKER] Nhận được {len(shopee_data)} sản phẩm từ Shopee.")
    #     for item in shopee_data:
    #         add_to_big_data_if_valid(item)
    # else:
    #     logger.error(f"[WORKER] Lỗi luồng Shopee: {shopee_data}")

    if isinstance(tiki_data, list):
        logger.info(f"[WORKER] Nhận được {len(tiki_data)} sản phẩm từ Tiki.")
        for item in tiki_data:
            add_to_big_data_if_valid(item)
    else:
        logger.error(f"[WORKER] Lỗi luồng Tiki: {tiki_data}")

    logger.info(f"[WORKER] Đã gom xong! Hiện kho big_data đang có {len(state.big_data)} sản phẩm hợp lệ.")

# ==========================================
# 3. LOGIC CẬP NHẬT TRẠNG THÁI VÀ BỘ LỌC
# ==========================================

def add_to_big_data_if_valid(product: dict):
    """Kiểm tra whitelist/blacklist trước khi nhét vào kho"""
    # # 1. Kiểm tra tồn tại ảnh và giá
    # if not product.get("price_current") or not product.get("main_image"):
    #     return

    # 2. Thuật toán Blacklist: Nếu tên chứa từ khóa blacklist -> Vứt
    product_str = json.dumps(product).lower()
    for bad_word in state.blacklist:
        if bad_word.lower() in product_str:
            return  # Bỏ qua sản phẩm này

    # 3. Thêm vào Big Data
    state.big_data.append(product)

    # 4. Cập nhật Filter Map (Map<biến> = []) để UI hiển thị cho User
    features = product.get("key_features", {})
    for key, value in features.items():
        if key not in state.filter_map:
            state.filter_map[key] = set()
        state.filter_map[key].add(value)


async def work_deep():
    # Giả lập luồng ra quyết định của Agent:
    # Nó sinh ra các URL tùy thuộc vào mục đích (Search sản phẩm hoặc Đọc chi tiết web)
    agent_requests = [
        # # 1. Tình huống tìm kiếm (Search): Sẽ lọt vào ShopeeExtractor
        # "shopee.vn/Áo-khoác-bomber-nỉ-nam-nữ-form-rộng-kiểu-dáng-bóng-chày-màu-xám-đen-LAVADO12-nhiều-mẫu-mới-đẹp-i.362579679.14879238823",
        # "shopee.vn/Áo-Khoác-Bomber-KingKong-Unisex-Nam-Nữ-Thể-Thao-Basic-Local-Brand-TB-KINGKONG-SPORT-WEAR-i.751079589.23665543559",
        #
        # # 2. Tình huống tìm kiếm (Search): Sẽ lọt vào TikiExtractor
        # "https://tiki.vn/ao-khoac-bomber-nam-nu-theu-rong-p66607818.html",
        # "https://tiki.vn/ao-khoac-du-nam-nu-unisex-kieu-bomber-form-rong-2-lop-day-dan-p110692795.html",

        # 3. Tình huống cào data (Scrape): Một link thật, sẽ lọt qua Tavily hoặc Crawl4AI
        "https://canifa.com/ao-khoac-nam-8ot24w019-se384",
        "https://torano.vn/products/ao-khoac-bomber-lot-long-theu-logo-nguc-5-gwcu051",
        "https://www.uniqlo.com/vn/vi/products/E474936-000/00?colorDisplayCode=53&sizeDisplayCode=004"
    ]

    print("🤖 Khởi động module Extractors...\n" + "=" * 60)

    for url in agent_requests:
        print(f"\n▶️ BẮT ĐẦU XỬ LÝ: {url}")
        try:
            # Chỉ cần 1 dòng gọi hàm duy nhất cho mọi trường hợp
            result = await extract(url)

            if not result:
                print("⚠️ Cảnh báo: Không lấy được dữ liệu.")
                continue

            # Xử lý hiển thị dựa trên kiểu dữ liệu trả về
            if isinstance(result, list):
                print(f"✅ THÀNH CÔNG: Lấy được danh sách {len(result)} sản phẩm.")
                if result:
                    # In thử thông tin cơ bản của sản phẩm đầu tiên để check kết quả map dữ liệu
                    top_item = result[0]
                    print(f"   🏆 Top 1: {top_item.get('name')[:60]}...")
                    print(f"   💰 Giá: {top_item.get('price_current', 0):,.0f} VND - Nền tảng: {top_item.get('platform')}")
                    print(f"   🔗 Link gốc: {top_item.get('product_url')}")

                # BƠM VÀO STATE
                for item in result:
                    add_to_big_data_if_valid(item)

            elif isinstance(result, dict):
                print(f"✅ THÀNH CÔNG: Cào được dữ liệu trang web.")
                # In ra một số key quan trọng cào được
                keys = list(result.keys())
                print(f"   📄 Các trường dữ liệu lấy được: {keys}")

                # BƠM VÀO STATE
                add_to_big_data_if_valid(result)

        except ValueError as ve:
            print(f"❌ LỖI REGISTRY: {ve}")
        except Exception as e:
            print(f"❌ LỖI KHÔNG XÁC ĐỊNH: {e}")

        print("-" * 60)


async def main_orchestrator(keyword: str):
    logger.info("=== KHỞI ĐỘNG SHOPPING RESEARCH AGENT ===")

    # Tạo các task chạy nền
    task_fast = asyncio.create_task(worker_fast_apis(keyword))
    task_slow = asyncio.create_task(work_deep())

    # Đợi task UI hoàn thành là kết thúc phiên làm việc
    # await task_ui
    await asyncio.gather(task_fast, task_slow)

    # IN KẾT QUẢ RA MÀN HÌNH SAU KHI CÀO XONG
    logger.info("==================================================")
    logger.info(f"🎉 TỔNG KẾT: Đã thu thập được {len(state.big_data)} sản phẩm vào Big Data")
    logger.info("==================================================")

    # In JSON đẹp mắt
    print(json.dumps(state.big_data, indent=2, ensure_ascii=False))

    # Dọn dẹp
    # task_fast.cancel()
    # task_slow.cancel()


if __name__ == "__main__":
    asyncio.run(main_orchestrator("áo khoác nam bomber"))