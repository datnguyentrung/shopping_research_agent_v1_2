from concurrent.futures import ThreadPoolExecutor, as_completed

import pandas as pd
from llama_cpp import Llama
import re
from functools import lru_cache
from app.utils.load_instruction_from_file import load_instruction_from_file

MODEL_PATH = r"D:\Thực tập MB\Shopping_Research_Agent_V1_2\models\Qwen2.5\Qwen2.5-7B-Instruct-Q6_K.gguf"

PROMPT = r"D:\Thực tập MB\Shopping_Research_Agent_V1_2\app\prompts\translate_and_fix.md"
PROMPT_BATCH = r"D:\Thực tập MB\Shopping_Research_Agent_V1_2\app\prompts\translate_and_fix_batch.md"

llm = None
PROMPT_TEMPLATE = ""
PROMPT_BATCH_TEMPLATE = ""

# ── Regex constants ──────────────────────────────────────────────────────────
_VI_DIACRITIC = re.compile(
    r"[àáảãạăằắẳẵặâầấẩẫậèéẻẽẹêềếểễệ"
    r"ìíỉĩịòóỏõọôồốổỗộơờớởỡợùúủũụưừứửữự"
    r"ỳýỷỹỵđÀÁẢÃẠĂẰẮẲẴẶÂẦẤẨẪẬÈÉẺẼẸÊỀẾỂỄỆ"
    r"ÌÍỈĨỊÒÓỎÕỌÔỒỐỔỖỘƠỜỚỞỠỢÙÚỦŨỤƯỪỨỬỮỰỲÝỶỸỴĐ]"
)

_TELEX_PATTERN = re.compile(
    r"\bdd\w*"
    r"|\w*[wW]\w*"
    r"|\b\w+[fFrRxXjJ]\b"
    r"|\b(ao|quan|giay|tui|vay|dam|non|mu|dep|tat)\w*\b",
    re.IGNORECASE,
)

_EN_SHOPPING_VOCAB = {
    "shirt", "t-shirt", "tshirt", "pants", "jeans", "dress", "shoes",
    "jacket", "coat", "skirt", "blouse", "sneakers", "boots", "bag",
    "handbag", "hat", "cap", "men", "women", "unisex", "kids",
    "black", "white", "red", "blue", "size", "xl", "xxl", "s", "m", "l",
    "sport", "casual", "formal", "slim", "fit", "hoodie", "sweater",
    "shorts", "underwear", "socks", "scarf", "gloves", "belt", "wallet",
    "watch", "glasses", "sunglasses", "laptop", "phone", "backpack",
}

_BAD_PATTERNS = re.compile(
    r"\[unknown|\bunknown\]|error|\.\$|<\|",
    re.IGNORECASE,
)


# ── Init ─────────────────────────────────────────────────────────────────────
def init_qwen_model():
    global llm, PROMPT_TEMPLATE, PROMPT_BATCH_TEMPLATE
    print("🚀 Đang khởi động Qwen GGUF...")

    try:
        PROMPT_TEMPLATE = load_instruction_from_file(PROMPT)
        PROMPT_BATCH_TEMPLATE = load_instruction_from_file(PROMPT_BATCH)
        print("✅ Đã tải xong nội dung Prompt!")
    except Exception as e:
        print(f"❌ Lỗi tải file prompt: {e}")
        raise e
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
        print(f"❌ Lỗi tải mô hình: {e}")
        raise e


# ── Helpers: phát hiện ngôn ngữ ─────────────────────────────────────────────
def is_clean_english(text: str) -> bool:
    """True nếu text là tiếng Anh chuẩn, không cần qua LLM."""
    if _VI_DIACRITIC.search(text):
        return False
    if _TELEX_PATTERN.search(text):
        return False
    if not text.isascii():
        return False
    tokens = set(re.sub(r"[^a-z0-9\-]", " ", text.lower()).split())
    return bool(tokens) and tokens.issubset(_EN_SHOPPING_VOCAB)


# ── Helpers: validate output chống hallucination ─────────────────────────────
def _validate_output(vi: str, en: str, original: str) -> bool:
    """
    Validator nhẹ nhàng: Chỉ chặn lỗi syntax của LLM, độ dài quá lố.
    Tuyệt đối không dùng string-matching để bắt lỗi AI nữa.
    """
    if not vi or not en:
        return False

    # Chặn các token rác LLM hay đẻ ra
    if _BAD_PATTERNS.search(vi) or _BAD_PATTERNS.search(en):
        return False

    # Chặn word explosion (AI bịa ra câu dài gấp 4 lần input gốc)
    # Loại trừ trường hợp input quá ngắn (dưới 3 từ)
    input_word_count = max(len(original.split()), 1)
    vi_word_count = len(vi.split())
    if input_word_count > 3 and (vi_word_count / input_word_count > 4.0):
        print(f"⚠️ Word explosion chặn lại: {vi_word_count} từ.")
        return False

    return True


# ── Helpers: parse output ────────────────────────────────────────────────────
def _parse_output(raw: str) -> tuple[str, str]:
    """Tách output 'Tiếng Việt | English' thành 2 phần."""
    raw = raw.strip().strip('"').strip("'")
    raw = re.sub(r"<\|.*?\|>", "", raw).strip()
    raw = re.sub(r"^(Output|Kết quả|Keyword|Result)?\s*[:\-]\s*", "", raw,
                 flags=re.IGNORECASE).strip()

    if "|" in raw:
        parts = raw.split("|", 1)  # split tối đa 1 lần
        vi = parts[0].strip().lstrip(":- ")
        en = parts[1].strip().lstrip(":- ")
    else:
        vi = raw.lstrip(":- ")
        en = raw.lstrip(":- ")

    return vi, en


# ── LLM call ─────────────────────────────────────────────────────────────────
def _call_llm(prompt: str) -> str:
    output = llm(
        prompt,
        max_tokens=48,
        temperature=0.0,
        repeat_penalty=1.0,
        stop=["<|im_end|>", "\n\n", "Input:"],
        echo=False,
    )
    return output["choices"][0]["text"]


# ── Hàm chính ────────────────────────────────────────────────────────────────
@lru_cache(maxsize=2048)
def translate_and_fix(text: str) -> tuple[str, str]:
    if llm is None or PROMPT is None:
        raise RuntimeError("Chưa gọi init_qwen_model().")

    text = text.strip()

    # [QUAN TRỌNG] Tiền xử lý gộp các chữ xé lẻ (VD: "q u a n" -> "quan")
    text_clean = re.sub(r'(?<=\b\w)\s+(?=\w\b)', '', text)

    text_clean = text_clean.replace("&", "and")
    if not text_clean:
        return "", ""

    if is_clean_english(text_clean):
        return text_clean, text_clean

    prompt = PROMPT.replace("{input}", text_clean)
    raw = _call_llm(prompt)
    vi, en = _parse_output(raw)

    # Nếu Validator fail, trả về text_clean (đã gộp chữ) thay vì text rác ban đầu
    if not _validate_output(vi, en, text_clean):
        print(f"⚠️ Validation fail, fallback: '{text_clean}'")
        return text_clean, text_clean

    print(f"✅ {text!r:30s} → '{vi}' | '{en}'")
    return vi, en

# ── Test ─────────────────────────────────────────────────────────────────────
# if __name__ == "__main__":
#     init_qwen_model()
#     while True:
#         user_input = input("\nNhập keyword ('q' để thoát): ")
#         if user_input.lower() == "q":
#             break
#         vi, en = translate_and_fix(user_input)
#         print(f"  VI : {vi}")
#         print(f"  EN : {en}")
#     print(f"\n📊 Cache: {translate_and_fix.cache_info()}")

def chunk_list(lst, chunk_size):
    """Chia danh sách lớn thành các danh sách nhỏ."""
    for i in range(0, len(lst), chunk_size):
        yield lst[i:i + chunk_size]


def translate_batch_chunk(chunk_texts: list[str]) -> list[tuple[str, str]]:
    """Gửi một list khoảng 15-20 từ vào LLM cùng lúc."""
    # 1. Tạo chuỗi input có đánh số thứ tự
    input_str = "\n".join([f"{i + 1}. {text}" for i, text in enumerate(chunk_texts)])

    # 2. Đưa vào prompt
    prompt = PROMPT_BATCH_TEMPLATE.replace("{input}", input_str)

    # 3. Gọi LLM (Nhớ tăng max_tokens lên vì output giờ dài hơn)
    raw_output = llm(
        prompt,
        max_tokens=2048,  # Tăng lên để đủ chỗ chứa 20 dòng output
        temperature=0.0,
        stop=["<|im_end|>"],
        echo=False,
    )["choices"][0]["text"]

    # 4. Parse kết quả trả về
    results = []
    lines = raw_output.strip().split('\n')
    for line in lines:
        # Xóa số thứ tự ở đầu dòng (VD: "1. Áo thun | T-shirt" -> "Áo thun | T-shirt")
        clean_line = re.sub(r'^\d+\.\s*', '', line)
        vi, en = _parse_output(clean_line)
        results.append((vi, en))

    # Trả về kèm fallback nếu LLM bị lỡ mất dòng nào
    while len(results) < len(chunk_texts):
        results.append((chunk_texts[len(results)], chunk_texts[len(results)]))

    return results


# Tích hợp vào hàm Main
if __name__ == "__main__":
    init_qwen_model()
    df = pd.read_csv(r"D:\Thực tập MB\Shopping_Research_Agent_V1_2\data\category.csv")
    df = df[df['Depth'] == 5]
    test_inputs = df['Name'].tolist()

    print(f"🚀 Bắt đầu dịch batch {len(test_inputs)} từ...")

    all_results = []
    chunk_size = 20  # Xử lý 20 từ mỗi lần gọi AI

    # Chạy vòng lặp tuần tự từng chunk (rất nhanh, không cần đa luồng)
    for i, chunk in enumerate(chunk_list(test_inputs, chunk_size)):
        print(f"Đang xử lý Chunk {i + 1}...")
        chunk_res = translate_batch_chunk(chunk)
        all_results.extend(chunk_res)

        for (vi, en) in chunk_res:
            print(f"  '{vi}' | '{en}'")

    print(f"\n✅ Hoàn thành dịch batch! Tổng {len(all_results)} kết quả.")

    print("\n" + "=" * 50)
    for vi, en in all_results:
        print(f'"{vi}",')