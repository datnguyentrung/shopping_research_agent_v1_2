from llama_cpp import Llama
import re
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

# Từ tiếng Anh mua sắm: nếu toàn bộ token khớp danh sách này → bỏ qua LLM
_EN_SHOPPING_VOCAB = {
    "shirt", "t-shirt", "tshirt", "pants", "jeans", "dress", "shoes", "jacket",
    "coat", "skirt", "blouse", "sneakers", "boots", "bag", "handbag", "hat", "cap",
    "men", "women", "unisex", "kids", "black", "white", "red", "blue", "size", "xl",
    "xxl", "s", "m", "l", "sport", "casual", "formal", "slim", "fit", "hoodie",
    "sweater", "shorts", "underwear", "socks", "scarf", "gloves", "belt", "wallet",
    "watch", "glasses", "sunglasses", "laptop", "phone", "earphones", "charger",
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
            n_ctx=2048,
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


# ── Hàm chính ────────────────────────────────────────────────────────────────
def translate_and_fix(text: str) -> str | tuple[str, str]:
    """
    Nhận keyword tiếng Việt (có dấu / Telex / lẫn lộn) hoặc tiếng Anh,
    trả về tên sản phẩm tiếng Anh chuẩn dùng cho e-commerce search.
    """
    if llm is None or PROMPT_TEMPLATE is None:
        raise RuntimeError("Mô hình Qwen chưa được khởi tạo. Vui lòng cấu hình init_qwen_model() trong lifespan.")

    text = text.strip()
    if not text:
        return ""

    if is_clean_english(text):
        return text, text

    prompt = PROMPT_TEMPLATE.replace("{input}", text)

    output = llm(
        prompt,
        max_tokens=64,
        temperature=0.0,
        repeat_penalty=1.1,
        stop=["<|im_end|>", "\n\n"],
        echo=False,
    )

    raw: str = output["choices"][0]["text"]

    # Lấy cả 2 giá trị
    vi_keyword, en_keyword = _parse_output(raw)

    if not en_keyword or "unknown" in en_keyword.lower():
        return text, text

    return vi_keyword, en_keyword


# ── Test nội bộ (Chỉ chạy khi chạy trực tiếp file này) ──────────────────────
if __name__ == "__main__":
    # Tự động gọi init khi test trực tiếp file
    init_qwen_model()

    # test_cases = [
    #     "aosc khoacs gioos",
    #     "quafn jean nuwx",
    #     "black hoodie men",
    #     "áo khoác nữ màu đỏ",
    # ]

    print("\n✅ Hệ thống test sẵn sàng!\n" + "-" * 50)
    # for item in test_cases:
    #     print(f"  Input : {item}")
    #     print(f"  Output: {translate_and_fix(item)}")
    #     print("-" * 40)

    while True:
        user_input = input("\nNhập keyword (gõ 'q' để thoát): ")
        if user_input.lower() == 'q':
            print("👋 Tạm biệt!")
            break
        result = translate_and_fix(user_input)
        print(f"Output: {result}")