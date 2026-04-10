from concurrent.futures import ThreadPoolExecutor, as_completed
from llama_cpp import Llama
import re
from functools import lru_cache
from app.utils.load_instruction_from_file import load_instruction_from_file

MODEL_PATH = r"D:\Thực tập MB\Shopping_Research_Agent_V1_2\models\Qwen2.5\Qwen2.5-7B-Instruct-Q6_K.gguf"

llm = None
PROMPT_TEMPLATE = None

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
    global llm, PROMPT_TEMPLATE
    print("🚀 Đang khởi động Qwen GGUF...")
    try:
        PROMPT_TEMPLATE = load_instruction_from_file("prompts/translate_and_fix.md")
    except Exception as e:
        print("❌ Lỗi tải file prompt!")
        raise e
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
    if llm is None or PROMPT_TEMPLATE is None:
        raise RuntimeError("Chưa gọi init_qwen_model().")

    text = text.strip()

    # [QUAN TRỌNG] Tiền xử lý gộp các chữ xé lẻ (VD: "q u a n" -> "quan")
    text_clean = re.sub(r'(?<=\b\w)\s+(?=\w\b)', '', text)

    text_clean = text_clean.replace("&", "and")
    if not text_clean:
        return "", ""

    if is_clean_english(text_clean):
        return text_clean, text_clean

    prompt = PROMPT_TEMPLATE.replace("{input}", text_clean)
    raw = _call_llm(prompt)
    vi, en = _parse_output(raw)

    # Nếu Validator fail, trả về text_clean (đã gộp chữ) thay vì text rác ban đầu
    if not _validate_output(vi, en, text_clean):
        print(f"⚠️ Validation fail, fallback: '{text_clean}'")
        return text_clean, text_clean

    print(f"✅ {text!r:30s} → '{vi}' | '{en}'")
    return vi, en


# ── Batch ────────────────────────────────────────────────────────────────────
def translate_and_fix_batch(
        texts: list[str],
        max_workers: int = 4,
) -> list[tuple[str, str]]:
    results: list[tuple[str, str] | None] = [None] * len(texts)
    with ThreadPoolExecutor(max_workers=max_workers) as executor:
        future_to_index = {
            executor.submit(translate_and_fix, t): i
            for i, t in enumerate(texts)
        }
        for future in as_completed(future_to_index):
            i = future_to_index[future]
            try:
                results[i] = future.result()
            except Exception as e:
                print(f"⚠️  Lỗi index {i} ({texts[i]!r}): {e}")
                results[i] = (texts[i], texts[i])
    return results  # type: ignore[return-value]


# ── Test ─────────────────────────────────────────────────────────────────────
if __name__ == "__main__":
    init_qwen_model()
    while True:
        user_input = input("\nNhập keyword ('q' để thoát): ")
        if user_input.lower() == "q":
            break
        vi, en = translate_and_fix(user_input)
        print(f"  VI : {vi}")
        print(f"  EN : {en}")
    print(f"\n📊 Cache: {translate_and_fix.cache_info()}")