import asyncio
import urllib.parse
import logging
import json
import random
from playwright.sync_api import sync_playwright

logger = logging.getLogger(__name__)

OUTPUT_PATH = "tiki_products.jsonl"

async def fetch_tiki_data(keyword: str, limit: int = 30) -> list:
    keyword_encoded = urllib.parse.quote(keyword)
    search_url = f"https://tiki.vn/search?q={keyword_encoded}"
    extracted_data = []

    with sync_playwright() as p:
        browser = p.chromium.launch(
            headless=True,
            args=['--disable-blink-features=AutomationControlled']
        )
        context = browser.new_context(
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36",
            viewport={'width': 1920, 'height': 1080}
        )
        page = context.new_page()

        def handle_response(response):
            if "api/v2/products" in response.url and response.status == 200:
                try:
                    data = response.json()
                    items = data.get('data', []) if isinstance(data, dict) else []
                    for item in items[:limit]:
                        try:
                            product_id = str(item.get('id'))
                            mapped_item = {
                                "key": f"tiki_{product_id}",
                                "platform": "tiki",
                                "product_id": product_id,
                                "name": item.get('name'),
                                "price_current": float(item.get('price', 0)),
                                "price_original": float(item.get('list_price', 0)),
                                "currency": "VND",
                                "main_image": item.get('thumbnail_url'),
                                "rating_star": item.get('rating_average', 0),
                                "rating_count": item.get('review_count', 0),
                                "sold_count": item.get('quantity_sold', {}).get('value', 0),
                                "shop": {
                                    "shop_id": None,
                                    "shop_name": item.get('brand_name', 'Tiki'),
                                    "shop_location": None
                                },
                                "tier_variations": [],
                                "product_url": f"https://tiki.vn/{item.get('url_path')}"
                            }
                            extracted_data.append(mapped_item)
                        except Exception:
                            continue
                except Exception as e:
                    logger.warning(f"⚠️ Lỗi khi parse JSON Tiki cho '{keyword}': {e}")

        page.on("response", handle_response)

        try:
            # Chặn tài nguyên thừa để tăng tốc
            page.route("**/*.{png,jpg,jpeg,gif,webp,css,woff,svg}", lambda route: route.abort())

            logger.info(f"🚀 [TIKI] Đang tìm kiếm: {keyword}...")
            # Dùng domcontentloaded để giảm Timeout
            page.goto(search_url, wait_until="domcontentloaded", timeout=45000)
            # Đợi thêm 3s để API trả về hết
            page.wait_for_timeout(3000)
        except Exception as e:
            if len(extracted_data) == 0:
                logger.error(f"❌ [TIKI] Lỗi tải trang '{keyword}': {e}")
        finally:
            browser.close()

    return extracted_data

async def process_keyword(kw: str, semaphore: asyncio.Semaphore):
    async with semaphore:
        await asyncio.sleep(random.uniform(1.0, 2.5))
        try:
            products = await fetch_tiki_data(kw)

            if products:
                # GHI VÀO FILE NGAY LẬP TỨC
                with open(OUTPUT_PATH, 'a', encoding='utf-8') as f:
                    for item in products:
                        f.write(json.dumps(item, ensure_ascii=False) + '\n')
                print(f"✅ TIKI Xong: {kw} - Đã ghi {len(products)} SP")
            else:
                print(f"⚠️ TIKI: {kw} - Không lấy được dữ liệu.")

        except Exception as e:
            logger.error(f"🔥 Lỗi hệ thống khi xử lý '{kw}': {e}")


async def run_agent_research(keywords_list: list):
    # Loại bỏ trùng lặp để tiết kiệm thời gian
    unique_keywords = list(dict.fromkeys(keywords_list))
    print(f"📦 Tổng số từ khóa duy nhất: {len(unique_keywords)} (đã loại bỏ trùng lặp)")

    semaphore = asyncio.Semaphore(3)
    tasks = [asyncio.create_task(process_keyword(kw, semaphore)) for kw in unique_keywords]

    # Chờ tất cả hoàn thành
    await asyncio.gather(*tasks)
    print(f"🏁 TẤT CẢ ĐÃ HOÀN THÀNH. Dữ liệu nằm tại: {OUTPUT_PATH}")

if __name__ == '__main__':
    # Sử dụng danh sách Keywords tiếng Việt đã được làm sạch ở turn trước
    cleaned_keywords = [
        "Giày dép nữ",
        "Trang phục cho bé gái",
        "Kính râm & Phụ kiện kính mắt nam",
        "Giày cao gót nữ",
        "Áo thun, áo kiểu và áo sơ mi cho bé trai",
        "Quần áo nữ",
        "Giày dép nam",
        "Giày dép nữ",
        "Quần lót nam",
        "Giày lười & Giày búp bê nữ",
        "Trang phục nữ",
        "Trang phục thể thao nữ",
        "Quần áo khoác, áo vest nữ",
        "Trang phục độc lạ và nhiều hơn nữa",
        "Quần áo, Giày dép và Trang sức",
        "Giày dép nữ",
        "Đồng hồ nam",
        "Trang phục thể thao nam",
        "Trang phục bơi nam",
        "Áo khoác nam",
        "Áo hoodie và áo nỉ thời trang nữ",
        "Trang phục độc đáo",
        "Giày thể thao nữ",
        "Nón nam",
        "Trang phục và phụ kiện",
        "Thùng đồ du lịch",
        "Áo trang phục và đồ cosplay nữ",
        "Trang sức cưới & Đính hôn nữ",
        "Đồng hồ cài & Đinh nơ nữ",
        "Đồng hồ nữ",
        "Đồng hồ nữ",
        "Đồ trang sức nữ & Huy hiệu nữ",
        "Quần áo nam",
        "Áo len nữ",
        "Nhẫn nam",
        "Thùng đồ",
        "Giày thể thao nam",
        "Giày dép nữ",
        "Đồng hồ nam",
        "Áo trang phục và cosplay nam",
        "Quần áo cho bé trai sơ sinh",
        "Giày oxford nam",
        "Giày thể thao nữ",
        "Phụ kiện nữ",
        "Mũi vấn nữ",
        "Quần áo phong cách nam và hoodie",
        "Thời trang nam",
        "Giày bốt nam",
        "Đồng hồ nam",
        "Giày dép nam",
        "Giày dép nữ",
        "Kính râm & Phụ kiện kính mắt nữ",
        "Giày dép nữ",
        "Áo suit & Áo blazer nữ",
        "Đồng hồ cổ vũ nữ",
        "Trang sức nữ",
        "Trang phục độc lạ",
        "Quần áo đạp xe nam",
        "Giày mules & Clogs nữ",
        "Giày loafers & giày slip-on nam",
        "Giày thể thao nữ",
        "Balo ví & Organizer nữ",
        "Nón phụ nữ",
        "Ba lô",
        "Cà vạt, thắt lưng và khăn cài túi áo dành cho nam giới",
        "Quần lót & Áo lót nữ",
        "Đồng hồ nữ",
        "Trang phục nữ",
        "Quần áo chuyên dụng cho từng môn thể thao",
        "Giày leggings nữ",
        "Giày thể thao nam",
        "Giày bốt nữ",
        "Balo ví nam",
        "Trang sức khuyên nữ",
        "Đầm nữ",
        "Quần áo nam",
        "Hộp trang sức và tổ chức trang sức",
        "Quần jumpsuit, romper và overall nữ",
        "Trang sức body nữ",
        "Giày bệt nữ",
        "Áo trên người nữ",
        "Đồ bơi và áo khoác ngoài dành cho nữ",
        "Giày nam",
        "Giày tất nữ",
        "Quần nam",
        "Giày thể thao nam",
        "Áo suit & Áo khoác thể thao nam",
        "Quần jean nam",
        "Trang sức nữ",
        "Quần áo tập yoga nữ",
        "Trang phục giả tóc nữ",
        "Áo thể thao nam",
        "Phụ kiện trang phục nữ",
        "Áo len nam",
        "Quần short nam",
        "Giày đeo cổ chân nữ",
        "Giày dép slippers nam",
        "Giày thể thao nam",
        "Mũi nữ",
        "Quần lót nữ",
        "Quần áo nữ trẻ em",
        "Giày thể thao nam",
        "Giày dép bé gái",
        "Cinturoni uomo",
        "Quần áo nam trẻ em",
        "Quần áo gôn nam",
        "Túi xách tay",
        "Khuyên tai bé gái",
        "Balo trẻ em",
        "Xăng đan bé gái",
        "Phụ kiện bé gái sơ sinh",
        "Áo kiểu & Áo thun bé gái",
        "Giày ủng bé gái",
        "Giày búp bê bé gái",
        "Giày thể thao bé gái",
        "Bộ quần áo bé gái",
        "Đồ bơi bé gái",
        "Mặt nạ hóa trang nữ",
        "Giày dã ngoại nữ",
        "Thắt lưng nữ",
        "Khuy măng sét nam",
        "Vòng tay bé gái",
        "Khuyên tai nam",
        "Dây đồng hồ nam",
        "Thời trang bé gái",
        "Dây đồng hồ nữ",
        "Vali",
        "Mặt nạ hóa trang nam",
        "Thẻ tên & Bọc tay cầm hành lý",
        "Găng tay nam",
        "Phụ kiện hóa trang nam",
        "Đồ thể thao bé gái",
        "Túi tập gym",
        "Dây giày",
        "Áo khoác bé gái",
        "Đồ đạp xe nữ",
        "Phụ kiện trang trí giày (Jibbitz)",
        "Đồ bơi thể thao nữ",
        "Quần áo chơi gôn nữ",
        "Túi chia đồ du lịch",
        "Phụ kiện bé trai sơ sinh",
        "Giày bé trai sơ sinh",
        "Trang sức nữ",
        "Quần áo chạy bộ",
        "Giày Oxford nữ",
        "Áo khoác bé trai",
        "Nhẫn cưới nam",
        "Túi bao tử thời trang",
        "Bộ vali/hành lý",
        "Khăn quàng nam",
        "Bộ quần áo bé trai",
        "Phụ kiện dịp đặc biệt nữ",
        "Đá quý rời",
        "Trang phục nhảy múa bé gái",
        "Vũ khí & Giáp hóa trang",
        "Ô cán dài",
        "Móc khóa nam",
        "Nhẫn bé gái",
        "Trang phục nhảy múa nữ",
        "Tất & Quần tất bé gái",
        "Cặp táp công sở",
        "Đồ bơi bé trai",
        "Dây chuyền bé trai",
        "Thời trang bé trai",
        "Phụ kiện giữ ấm bé gái",
        "Phụ kiện túi xách nữ",
        "Túi rút tập gym",
        "Quần áo chạy bộ nam",
        "Dụng cụ sửa chữa đồng hồ",
        "Đồ lót bé gái",
        "Áo nỉ & Hoodie bé trai",
        "Quần áo tập Yoga",
        "Dây đai quần nam",
        "Xăng đan bé trai",
        "Mũ nón bé gái",
        "Ô gấp gọn",
        "Vòng tay bé trai",
        "Quần áo chạy bộ nữ",
        "Mũ nón bé trai",
        "Quần áo đạp xe",
        "Đồ lót bé trai",
        "Dép đi trong nhà bé gái",
        "Quần legging bé gái",
        "Ô đi mưa",
        "Đồ độc lạ & Khác",
        "Đồng hồ bỏ túi nam",
        "Tóc giả hóa trang nam",
        "Kẹp cà vạt",
        "Giày sục & Clogs nam",
        "Phụ kiện giữ ấm bé trai",
        "Áo nỉ & Hoodie bé gái",
        "Giày ủng bé trai",
        "Trang sức nam",
        "Trang sức cơ thể nam",
        "Quần dài bé trai",
        "Hộp & Tủ đựng đồng hồ",
        "Phụ kiện nam",
        "Ví đựng hộ chiếu",
        "Dây đai hành lý",
        "Dép đi trong nhà bé trai",
        "Ví du lịch",
        "Vỏ bọc hộ chiếu",
        "Giày Clogs & Giày sục bé gái",
        "Áo len bé gái",
        "Phụ kiện du lịch",
        "Đồ bơi thể thao nam",
        "Chân váy & Quần giả váy bé gái",
        "Comple & Áo khoác thể thao bé trai",
        "Túi đựng quần áo chống bụi",
        "Quần short bé trai",
        "Đồng phục dịch vụ thực phẩm",
        "Quần short bé gái",
        "Khăn tay nam",
        "Cây giữ form giày",
        "Hộp xoay đồng hồ cơ",
        "Đồ trượt tuyết nam",
        "Giày bé gái",
        "Đồng hồ nữ",
        "Mặt dây chuyền nam",
        "Kính râm bé gái",
        "Dụng cụ xỏ giày & tháo ủng",
        "Đồng hồ độc lạ",
        "Quần áo bóng rổ nam",
        "Giày lười bé trai",
        "Dung dịch chăm sóc & Nhuộm giày",
        "Phụ kiện & Chăm sóc giày",
        "Băng đô thể thao nữ",
        "Đồ đi mưa & Tuyết cho bé trai",
        "Quần jeans bé trai",
        "Đồ trượt tuyết nữ",
        "Tất bé trai",
        "Túi đựng giày",
        "Áo len bé trai",
        "Quần jeans bé gái",
        "Bộ áo liền quần bé gái",
        "Chụp tai giữ ấm nữ",
        "Quần áo bóng chày nam",
        "Quần dài & Quần lửng bé gái",
        "Đồ đi mưa & Tuyết cho bé gái",
        "Đồng phục y tế",
        "Quần áo chơi gôn",
        "Ghim cài cà vạt",
        "Đế đinh đi tuyết cho giày",
        "Giày Clogs & Giày sục bé trai",
        "Đồng hồ đeo tay bé gái",
        "Phụ kiện bé gái",
        "Bàn chải giày",
        "Trang phục quân đội",
        "Sản phẩm làm sạch trang sức",
        "Giày lười bé gái",
        "Giày hóa trang nữ",
        "Cân hành lý",
        "Võ phục Jiu-Jitsu",
        "Đồng hồ đeo tay bé trai",
        "Trang phục thể dục dụng cụ bé gái",
        "Râu giả hóa trang",
        "Đồng hồ bỏ túi nữ",
        "Khóa hành lý",
        "Băng đô thể thao nam",
        "Trang phục cổ vũ nữ",
        "Trang phục nhảy múa",
        "Kính râm bé trai",
        "Giày bé trai",
        "Hành lý trẻ em",
        "Giày dã ngoại bé trai",
        "Giày dã ngoại bé gái",
        "Dây đai quần bé trai",
        "Đồ bơi thể thao bé gái",
        "Cà vạt bé trai",
        "Giày Oxford bé trai",
        "Võ phục Karate",
        "Phụ kiện trang sức",
        "Giày hóa trang nam",
        "Quần áo & Giày sơ sinh"
    ]

    asyncio.run(run_agent_research(cleaned_keywords))