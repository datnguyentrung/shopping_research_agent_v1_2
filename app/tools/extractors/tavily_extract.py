import logging
import re
from typing import Any, Dict, Optional

from app.core.config.config import settings  # dùng Settings.settings instance
from app.tools.extractors.base import BaseExtractor

try:
    from tavily import TavilyClient  # type: ignore
except Exception:  # pragma: no cover - optional dependency
    TavilyClient = None  # type: ignore


logger = logging.getLogger(__name__)
_MAX_PRICE_DIGITS = 11  # ~99 tỷ VND, đủ cho mọi sản phẩm thực tế
# Các từ context báo hiệu đây LÀ giá
_PRICE_CONTEXT_RE = re.compile(
    r'(giá|price|₫|đ\b|vnd|discount|sale|thành\s*tiền)',
    re.IGNORECASE
)

def _get_tavily_client() -> Optional["TavilyClient"]:
    """Lấy Tavily client nếu có API key, ngược lại trả về None.

    Hàm tách riêng để dễ test/mocking.
    """

    api_key = getattr(settings, "TAVILY_API_KEY", None)
    if not api_key:
        logger.warning("[TAVILY] Thiếu TAVILY_API_KEY trong cấu hình")
        return None

    if TavilyClient is None:
        logger.warning("[TAVILY] Thư viện tavily chưa được cài đặt")
        return None

    return TavilyClient(api_key=api_key)


def extract_price_from_text(text: str) -> Optional[float]:
    """Rất đơn giản: cố gắng trích giá từ text.

    Ở đây chỉ là ví dụ: tìm số có dấu chấm / phẩy, sau đó convert về float.
    Bạn có thể thay bằng logic regex phức tạp hơn nếu cần.
    """
    if not text:
        return None

    # Tìm các pattern như 1.234.000 hoặc 1,234,000 hoặc 1234000
    candidates: list[tuple[int, float]] = []  # (vị_trí, giá_trị)

    for m in re.finditer(r'\b(\d{1,3}(?:[.,]\d{3})+|\d{4,})\b', text):
        raw = m.group(1)
        # Chuẩn hóa: bỏ dấu phân cách nghìn
        normalized = raw.replace('.', '').replace(',', '')
        if len(normalized) > _MAX_PRICE_DIGITS:
            continue  # Quá lớn → chắc là ID kỹ thuật
        try:
            value = float(normalized)
        except ValueError:
            continue
        if value < 1_000:  # Dưới 1k VND vô lý
            continue
        candidates.append((m.start(), value))

    if not candidates:
        return None

    # Tìm đoạn text xung quanh để score theo context
    def context_score(pos: int) -> int:
        window = text[max(0, pos - 80): pos + 30]
        return 1 if _PRICE_CONTEXT_RE.search(window) else 0

    # Ưu tiên: có context giá → giá trị nhỏ nhất (tránh bắt tổng/gộp)
    with_context = [(pos, val) for pos, val in candidates if context_score(pos)]
    pool = with_context if with_context else candidates

    # Lấy giá trị nhỏ nhất trong pool (giá sản phẩm thường là số nhỏ nhất có nghĩa)
    _, best = min(pool, key=lambda x: x[1])
    return best


class TavilyExtractor(BaseExtractor):
    """Extractor dùng Tavily API, fallback chung nếu không có extractor chuyên biệt.

    domains = ["*"] để cho phép match mọi domain, nhưng BaseExtractor.matches
    có thể implement ưu tiên extractor chuyên biệt trước (Shopee, Tiki, ...).
    """

    domains = ["*"]

    @classmethod
    def matches(cls, url: str) -> bool:
        return True  # Luôn bắt các URL lọt qua được Shopee và Tiki

    async def extract(self, url: str) -> Dict[str, Any] | None:
        logger.info("[TAVILY] Đang trích xuất dữ liệu từ: %s", url)

        client = _get_tavily_client()
        if client is None:
            return None

        try:
            response: Dict[str, Any] = client.extract(urls=[url])  # type: ignore[call-arg]
        except Exception as exc:  # noqa: BLE001
            logger.error("[TAVILY] Lỗi khi gọi API: %s", exc, exc_info=True)
            return None

        results = response.get("results") if isinstance(response, dict) else None
        if not results:
            logger.warning("[TAVILY] Không có kết quả trả về")
            return None

        data: Dict[str, Any] = results[0]
        raw_text = data.get("raw_content") or data.get("content") or ""

        price: Optional[float] = None
        if isinstance(raw_text, str) and raw_text:
            price = extract_price_from_text(raw_text)

        enriched: Dict[str, Any] = {**data, "source": "tavily"}
        if price is not None:
            enriched["price"] = price
            logger.info("[TAVILY] Trích xuất được giá: %s", price)
        else:
            logger.info("[TAVILY] Không trích xuất được giá từ nội dung, caller có thể fallback")

        return enriched


# Giữ lại API cũ nếu có code nơi khác đang gọi trực tiếp
async def extract(url: str) -> Dict[str, Any] | None:  # type: ignore[override]
    extractor = TavilyExtractor()
    return await extractor.extract(url)
