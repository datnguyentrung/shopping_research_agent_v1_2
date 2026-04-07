from concurrent.futures import ThreadPoolExecutor, as_completed

from llama_cpp import Llama
import re

from functools import lru_cache

from app.utils.load_instruction_from_file import load_instruction_from_file

MODEL_PATH = r"D:\Thực tập MB\Shopping_Research_Agent_V1_2\models\Qwen2.5-1.5B-Instruct-GGUF\Qwen2.5-7B-Instruct-Q4_K_M.gguf"

# ── Khai báo biến global chưa khởi tạo ──────────────────────────────────────
llm = None
PROMPT_TEMPLATE = None

# ── Hằng số (Constants) ─────────────────────────────────────────────────────
# Ký tự có dấu tiếng Việt
_VI_DIACRITIC = re.compile(
    r"[àáảãạăằắẳẵặâầấẩẫậèéẻẽẹêềếểễệ"
    r"ìíỉĩịòóỏõọôồốổỗộơờớởỡợùúủũụưừứửữự"
    r"ỳýỷỹỵđÀÁẢÃẠĂẰẮẲẴẶÂẦẤẨẪẬÈÉẺẼẸÊỀẾỂỄỆ"
    r"ÌÍỈĨỊÒÓỎÕỌÔỒỐỔỖỘƠỜỚỞỠỢÙÚỦŨỤƯỪỨỬỮỰỲÝỶỸỴĐ]"
)

# Telex marker: dd (đ), các combo nguyên âm+tone cờ điển hình
_TELEX_PATTERN = re.compile(
    r"\bdd\w*"  # dd → đ
    r"|\w*[wW]\w*"  # w  → ư/ơ
    r"|\b\w+[fFrRxXjJ]\b"  # tone cuối từ: f à, r ả, x ã, j ị
    r"|\b(ao|quan|giay|tui|vay|dam|non|mu|dep|tat|ao)\w*\b",  # gốc VN không dấu
    re.IGNORECASE,
)

_JUNK_PATTERN = re.compile(r"[^\w\s\u00C0-\u024F|,&'\-]")  # ký tự rác

# Từ tiếng Anh mua sắm: nếu toàn bộ token khớp danh sách này → bỏ qua LLM
_EN_SHOPPING_VOCAB = {
    "shirt", "t-shirt", "tshirt", "pants", "jeans", "dress", "shoes", "jacket",
    "coat", "skirt", "blouse", "sneakers", "boots", "bag", "handbag", "hat", "cap",
    "men", "women", "unisex", "kids", "black", "white", "red", "blue", "size", "xl",
    "xxl", "s", "m", "l", "sport", "casual", "formal", "slim", "fit", "hoodie",
    "sweater", "shorts", "underwear", "socks", "scarf", "gloves", "belt", "wallet",
    "watch", "glasses", "sunglasses", "laptop", "phone", "earphones", "charger",
}

# Thêm vào đầu file
_EN_CATEGORY_STOPWORDS = {
    "women", "men", "girls", "boys", "baby", "kids", "unisex",
    "and", "for", "the", "of", "with", "or", "in", "s",  # possessive 's
}

# ── Hàm Khởi Tạo (Gọi 1 lần ở Lifespan) ────────────────────────────────────
def init_qwen_model():
    """Hàm này sẽ được gọi 1 lần duy nhất khi khởi động FastAPI"""
    global llm, PROMPT_TEMPLATE

    print("🚀 Đang khởi động Qwen GGUF...")

    # Load prompt template
    try:
        PROMPT_TEMPLATE = load_instruction_from_file("prompts/translate_and_fix.md")
    except Exception as e:
        print("❌ Lỗi tải file prompt translate_and_fix.md!")
        raise e

    # Khởi tạo mô hình Llama
    try:
        llm = Llama(
            model_path=MODEL_PATH,
            n_gpu_layers=-1,
            n_ctx=1024,
            n_threads=4,
            verbose=False,
        )
        print("✅ Tải thành công mô hình Qwen!")
    except Exception as e:
        print(f"❌ Lỗi tải mô hình Qwen. Bạn kiểm tra lại đường dẫn {MODEL_PATH} nhé!")
        print(f"Chi tiết: {e}")
        raise e


# ── Helpers ─────────────────────────────────────────────────────────────────
def _looks_like_telex(text: str) -> bool:
    """True nếu text chứa dấu hiệu Telex / tiếng Việt không dấu."""
    return bool(_TELEX_PATTERN.search(text))

def is_vietnamese_or_telex(text: str) -> bool:
    """Phát hiện nhanh input có phải tiếng Việt / Telex không."""
    if _VI_DIACRITIC.search(text):
        return True
    if _looks_like_telex(text):
        return True
    if not text.isascii():
        return True
    return False


def is_clean_english(text: str) -> bool:
    """
    True nếu text đã là tiếng Anh chuẩn, không cần qua LLM.
    Logic ưu tiên an toàn: nghi ngờ → False → để LLM xử lý.
    """
    if _VI_DIACRITIC.search(text): return False
    if _looks_like_telex(text): return False
    if not text.isascii(): return False

    tokens = set(re.sub(r"[^a-z0-9\-]", " ", text.lower()).split())
    if tokens and tokens.issubset(_EN_SHOPPING_VOCAB):
        return True

    return False


def _parse_output(raw: str) -> tuple[str, str]:
    """
    Tách và lấy CẢ Tiếng Việt và Tiếng Anh từ output dạng:
      'Standard Vietnamese | Professional English Name'
    """
    # Dọn dẹp token thừa, khoảng trắng và ngoặc kép
    raw = raw.strip().strip('"').strip("'")
    raw = re.sub(r"<\|.*?\|>", "", raw).strip()

    # Dọn sạch các tiền tố LLM hay tự thêm vào như "Output:", "Kết quả:", hoặc dấu ":"
    raw = re.sub(r"^(Output|Kết quả|Keyword)?\s*[:\-]\s*", "", raw, flags=re.IGNORECASE).strip()

    if "|" in raw:
        parts = raw.split("|")
        # lstrip(":- ") giúp dọn sạch dấu hai chấm hoặc gạch ngang nếu nó bị kẹt lại ở đầu chuỗi
        vietnamese = parts[0].strip().lstrip(":- ")
        english = parts[-1].strip().lstrip(":- ")
    else:
        # Fallback nếu LLM quên sinh dấu |
        vietnamese = raw.lstrip(":- ")
        english = raw.lstrip(":- ")

    return vietnamese, english

def _call_llm(prompt: str) -> str:
    """Tách riêng lời gọi LLM để dễ mock khi test."""
    output = llm(
        prompt,
        max_tokens=48,       # ✅ Giảm từ 64 → 48: output thực tế < 40 token
        temperature=0.0,
        repeat_penalty=1.0,
        stop=["<|im_end|>", "\n\n", "Input:"],
        echo=False,
    )
    return output["choices"][0]["text"]

# ── Hàm chính ────────────────────────────────────────────────────────────────
@lru_cache(maxsize=2048)
def translate_and_fix(text: str) -> tuple[str, str]:
    """
    Nhận keyword tiếng Việt (có dấu / Telex / lẫn lộn) hoặc tiếng Anh,
    trả về tên sản phẩm tiếng Anh chuẩn dùng cho e-commerce search.
    """
    if llm is None or PROMPT_TEMPLATE is None:
        raise RuntimeError("Mô hình Qwen chưa được khởi tạo. Vui lòng cấu hình init_qwen_model() trong lifespan.")

    text = text.strip()
    text_clean = text.replace("&", "and")  # Đổi & thành and giúp model dễ hiểu hơn
    if not text_clean:
        return "", ""

    if is_clean_english(text_clean):
        return text, text

    prompt = PROMPT_TEMPLATE.replace("{input}", text_clean)

    # 2. Gọi Model
    output = llm(
        prompt,
        max_tokens=64,
        temperature=0.0,
        repeat_penalty=1.0,
        stop=["<|im_end|>", "\n\n", "Input:"],
        echo=False,
    )

    raw: str = output["choices"][0]["text"]
    vi_keyword, en_keyword = _parse_output(raw)

    # 3. Hậu xử lý & Fallback chặt chẽ hơn
    # Nếu kết quả có chứa Unknown, ký tự rác, hoặc vi_keyword bị rỗng
    invalid_patterns = ["[unknown", "unknown]", ".$", "error"]
    is_invalid = any(p in raw.lower() for p in invalid_patterns)

    # Kểm tra xem đầu ra có bị dính ký tự đặc biệt kỳ lạ không (ngoại trừ chữ cái, số, dấu cách, phẩy, &)
    if is_invalid or not vi_keyword or not en_keyword:
        return text, text  # Trả về nguyên bản gốc thay vì sinh rác

    return vi_keyword, en_keyword

def translate_and_fix_batch(
    texts: list[str],
    max_workers: int = 4,
) -> list[tuple[str, str]]:
    """
    Xử lý song song. lru_cache bên trong translate_and_fix
    tự lo cache hit — batch không cần check riêng.
    """
    results: list[tuple[str, str] | None] = [None] * len(texts)

    with ThreadPoolExecutor(max_workers=max_workers) as executor:
        future_to_index = {
            executor.submit(translate_and_fix, text): i
            for i, text in enumerate(texts)
        }
        for future in as_completed(future_to_index):
            i = future_to_index[future]
            try:
                results[i] = future.result()
            except Exception as e:
                print(f"⚠️ Lỗi index {i} ({texts[i]}): {e}")
                results[i] = (texts[i], texts[i])

    return results  # type: ignore[return-value]

# ── Test nội bộ (Chỉ chạy khi chạy trực tiếp file này) ──────────────────────
if __name__ == "__main__":
    # Tự động gọi init khi test trực tiếp file
    init_qwen_model()

    while True:
        user_input = input("\nNhập keyword (gõ 'q' để thoát): ")
        if user_input.lower() == 'q':
            print("👋 Tạm biệt!")
            break
        result = translate_and_fix(user_input)
        print(f"Output: {result}")

    # test_cases = [
    #   "Women's Sandals",
    #   "Baby Girls' Clothing",
    #   "Men's Sunglasses & Eyewear Accessories",
    #   "Women's Pumps",
    #   "Boys' Tops, Tees & Shirts",
    #   "Women's Clothing",
    #   "Men's Socks & Hosiery",
    #   "Women's Jeans",
    #   "Men's Underwear",
    #   "Women's Loafers & Slip-Ons",
    #   "Girls' Dresses",
    #   "Women's Activewear",
    #   "Women's Coats, Jackets & Vests",
    #   "Novelty Clothing & More",
    #   "Clothing, Shoes & Jewelry",
    #   "Women's Skirts",
    #   "Men's Bracelets",
    #   "Men's Activewear",
    #   "Men's Swimwear",
    #   "Men's Outerwear Jackets & Coats",
    #   "Women's Fashion Hoodies & Sweatshirts",
    #   "Novelty Clothing",
    #   "Women's Athletic Shoes",
    #   "Men's Hats & Caps",
    #   "Costumes & Accessories",
    #   "Luggage & Travel Gear",
    #   "Women's Costumes & Cosplay Apparel",
    #   "Women's Wedding & Engagement Rings",
    #   "Women's Brooches & Pins",
    #   "Women's Wrist Watches",
    #   "Women's Rings",
    #   "Women's Pendants & Coins",
    #   "Men's Clothing",
    #   "Women's Sweaters",
    #   "Men's Rings",
    #   "Luggage",
    #   "Men's Fashion Sneakers",
    #   "Women's Shoes",
    #   "Men's Necklaces",
    #   "Men's Costumes & Cosplay Apparel",
    #   "Baby Boy's Clothing",
    #   "Men's Oxfords",
    #   "Girls' Sneakers",
    #   "Women's Accessories",
    #   "Women's Scarves & Wraps",
    #   "Men's Fashion Hoodies & Sweatshirts",
    #   "Men's Fashion",
    #   "Men's Boots",
    #   "Men's Wrist Watches",
    #   "Men's Sandals",
    #   "Women's Slippers",
    #   "Women's Sunglasses & Eyewear Accessories",
    #   "Women's Pants",
    #   "Women's Suiting & Blazers",
    #   "Women's Necklaces",
    #   "Women's Jewelry Sets",
    #   "Exotic Apparel",
    #   "Men's Cycling Clothing",
    #   "Women's Mules & Clogs",
    #   "Men's Loafers & Slip-Ons",
    #   "Women's Fashion Sneakers",
    #   "Women's Wallets, Card Cases & Money Organizers",
    #   "Women's Hats & Caps",
    #   "Backpacks",
    #   "Men's Ties, Cummerbunds & Pocket Squares",
    #   "Women's Lingerie, Sleep & Lounge",
    #   "Women's Bracelets",
    #   "Women's Fashion",
    #   "Sport Specific Clothing",
    #   "Women's Leggings",
    #   "Men's Athletic Shoes",
    #   "Women's Boots",
    #   "Men's Wallets, Card Cases & Money Organizers",
    #   "Women's Earrings",
    #   "Women's Dresses",
    #   "Men's Shirts",
    #   "Jewelry Boxes & Organizers",
    #   "Women's Jumpsuits, Rompers & Overalls",
    #   "Women's Body Jewelry",
    #   "Women's Flats",
    #   "Women's Tops, Tees & Blouses",
    #   "Women's Swimsuits & Cover Ups",
    #   "Men's Shoes",
    #   "Women's Socks & Hosiery",
    #   "Men's Pants",
    #   "Men's Outdoor Shoes",
    #   "Men's Suits & Sport Coats",
    #   "Men's Jeans",
    #   "Girls' Jewelry",
    #   "Women's Yoga Clothing",
    #   "Women's Costume Wigs",
    #   "Boys' Activewear",
    #   "Women's Costume Accessories",
    #   "Men's Sweaters",
    #   "Men's Shorts",
    #   "Women's Anklets",
    #   "Men's Slippers",
    #   "Boys' Sneakers",
    #   "Women's Gloves & Mittens",
    #   "Women's Shorts",
    #   "Girls' Clothing",
    #   "Boys' Athletic Shoes",
    #   "Baby Girls' Shoes",
    #   "Men's Belts",
    #   "Boys' Clothing",
    #   "Men's Golf Clothing",
    #   "Messenger Bags",
    #   "Girls' Earrings",
    #   "Kids' Backpacks",
    #   "Girls' Sandals",
    #   "Baby Girls' Accessories",
    #   "Girls' Tops, Tees & Blouses",
    #   "Girls' Boots",
    #   "Girls' Flats",
    #   "Girls' Athletic Shoes",
    #   "Girls' Clothing Sets",
    #   "Girls' Swimwear",
    #   "Women's Costume Masks",
    #   "Women's Outdoor Shoes",
    #   "Women's Belts",
    #   "Men's Cuff Links",
    #   "Girls' Bracelets",
    #   "Men's Earrings",
    #   "Men's Watch Bands",
    #   "Girls' Fashion",
    #   "Women's Watch Bands",
    #   "Suitcases",
    #   "Men's Costume Masks",
    #   "Luggage Tags & Handle Wraps",
    #   "Men's Gloves & Mittens",
    #   "Men's Costume Accessories",
    #   "Girls' Activewear",
    #   "Gym Bags",
    #   "Shoelaces",
    #   "Girls' Outerwear Jackets & Coats",
    #   "Women's Cycling Clothing",
    #   "Shoe Decoration Charms",
    #   "Women's Athletic Swimwear",
    #   "Women's Golf Clothing",
    #   "Travel Packing Organizers",
    #   "Baby Boys' Accessories",
    #   "Baby Boys' Shoes",
    #   "Women's Jewelry",
    #   "Running Clothing",
    #   "Women's Oxfords",
    #   "Boys' Outerwear Jackets & Coats",
    #   "Men's Wedding Rings",
    #   "Fashion Waist Packs",
    #   "Luggage Sets",
    #   "Men's Scarves",
    #   "Boys' Clothing Sets",
    #   "Women's Special Occasion Accessories",
    #   "Loose Gemstones",
    #   "Girls' Dance Clothing",
    #   "Costume Weapons & Armor",
    #   "Stick Umbrellas",
    #   "Men's Keyrings & Keychains",
    #   "Girls' Rings",
    #   "Women's Dance Clothing",
    #   "Girls' Socks & Tights",
    #   "Briefcases",
    #   "Boys' Swimwear",
    #   "Boys' Necklaces",
    #   "Boys' Fashion",
    #   "Girls' Cold Weather Accessories",
    #   "Women's Handbag Accessories",
    #   "Gym Drawstring Bags",
    #   "Men's Running Clothing",
    #   "Watch Repair Tools & Kits",
    #   "Girls' Underwear",
    #   "Boys' Fashion Hoodies & Sweatshirts",
    #   "Yoga Clothing",
    #   "Men's Suspenders",
    #   "Boys' Sandals",
    #   "Girls' Hats & Caps",
    #   "Folding Umbrellas",
    #   "Boys' Bracelets",
    #   "Women's Running Clothing",
    #   "Boys' Hats & Caps",
    #   "Cycling Clothing",
    #   "Boys' Underwear",
    #   "Girls' Slippers",
    #   "Girls' Leggings",
    #   "Rain Umbrellas",
    #   "Novelty & More",
    #   "Men's Pocket Watches",
    #   "Men's Costume Wigs",
    #   "Tie Clips",
    #   "Men's Mules & Clogs",
    #   "Boys' Cold Weather Accessories",
    #   "Girls' Fashion Hoodies & Sweatshirts",
    #   "Boys' Boots",
    #   "Men's Jewelry",
    #   "Men's Body Jewelry",
    #   "Boys' Pants",
    #   "Watch Cabinets & Cases",
    #   "Men's Accessories",
    #   "Passport Wallets",
    #   "Luggage Straps",
    #   "Boys' Slippers",
    #   "Travel Wallets",
    #   "Passport Covers",
    #   "Girls' Clogs & Mules",
    #   "Girls' Sweaters",
    #   "Travel Accessories",
    #   "Men's Athletic Swimwear",
    #   "Girls' Skirts & Skorts",
    #   "Boys' Suits & Sport Coats",
    #   "Garment Bags",
    #   "Boys' Shorts",
    #   "Food Service Uniforms",
    #   "Girls' Shorts",
    #   "Men's Handkerchiefs",
    #   "Shoe & Boot Trees",
    #   "Watch Winders",
    #   "Men's Snowboarding Clothing",
    #   "Girls' Shoes",
    #   "Women's Watches",
    #   "Men's Pendants",
    #   "Girls' Sunglasses",
    #   "Shoe Horns & Boot Jacks",
    #   "Novelty Watches",
    #   "Men's Basketball Clothing",
    #   "Boys' Loafers",
    #   "Shoe Care Treatments & Dyes",
    #   "Shoe Care & Accessories",
    #   "Women's Sport Headbands",
    #   "Boys' Snow & Rainwear",
    #   "Boys' Jeans",
    #   "Women's Snowboarding Clothing",
    #   "Boys' Socks & Hosiery",
    #   "Shoe Bags",
    #   "Boys' Sweaters",
    #   "Girls' Jeans",
    #   "Girls' Jumpsuits & Rompers",
    #   "Women's Earmuffs",
    #   "Men's Baseball Clothing",
    #   "Girls' Pants & Capris",
    #   "Girls' Snow & Rainwear",
    #   "Medical Uniforms & Scrubs",
    #   "Golf Clothing",
    #   "Tie Pins",
    #   "Shoe Ice & Snow Grips",
    #   "Boys' Clogs & Mules",
    #   "Girls' Wrist Watches",
    #   "Girls' Accessories",
    #   "Shoe Brushes",
    #   "Military Clothing",
    #   "Jewelry Cleaning & Care Products",
    #   "Girls' Loafers",
    #   "Women's Costume Footwear",
    #   "Luggage Scales",
    #   "Jiu-Jitsu Suits",
    #   "Boys' Wrist Watches",
    #   "Girls' Gymnastics Clothing",
    #   "Costume Facial Hair",
    #   "Women's Pocket Watches",
    #   "Luggage Locks",
    #   "Men's Sport Headbands",
    #   "Women's Cheerleading Apparel",
    #   "Dance Apparel",
    #   "Boys' Sunglasses",
    #   "Boys' Shoes",
    #   "Kids' Luggage",
    #   "Boys' Outdoor Shoes",
    #   "Girls' Outdoor Shoes",
    #   "Boys' Suspenders",
    #   "Girls' Athletic Swimwear",
    #   "Boys' Neckties",
    #   "Boys' Oxfords",
    #   "Karate Suits",
    #   "Jewelry Accessories",
    #   "Men's Costume Footwear",
    #   "Baby Clothing & Shoes"
    # ]
    #
    # print("\n--- Single ---")
    # for item in test_cases:
    #     vi, en = translate_and_fix(item)
    #     print(f"  Input : {item}\n  VI    : {vi}\n  EN    : {en}")
    #     print("-" * 40)
    #
    # # Xem thống kê cache
    # print(f"\n📊 Cache: {translate_and_fix.cache_info()}")
    #
    # print("\n--- Batch ---")
    # batch_results = translate_and_fix_batch(test_cases * 3)
    # for text, (vi, en) in zip(test_cases * 3, batch_results):
    #     print(f"  {text:40s} → {vi} | {en}")
    #
    # print(f"\n📊 Cache sau batch: {translate_and_fix.cache_info()}")

