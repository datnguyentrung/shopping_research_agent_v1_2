import re

def extract_price_from_text(text: str) -> str | None:
    """
    Tìm giá sản phẩm từ text, bỏ qua giá trong các cụm không liên quan.
    """
    # Loại bỏ các dòng chứa context không phải giá sản phẩm
    NOISE_PATTERNS = [
        r'.{0,50}(miễn phí|free shipping|phí giao|vận chuyển|giao hàng|tối thiểu|trở lên|discount|giảm|coupon|voucher).{0,100}',
        r'.{0,50}(thanh toán|payment|order|đơn hàng).{0,100}',
    ]

    cleaned_text = text
    for noise in NOISE_PATTERNS:
        cleaned_text = re.sub(noise, '', cleaned_text, flags=re.IGNORECASE)

    # Tìm giá trong text đã làm sạch
    price_patterns = [
        # VND: 588.000 VNĐ / 588,000đ / 588.000 ₫
        r'[\d]{1,3}(?:[.,]\d{3})+\s*(?:VNĐ|VND|vnđ|đ|₫)',
        # USD
        r'(?:USD|\$)\s*[\d]{1,3}(?:[.,]\d{3})*(?:[.,]\d{2})?',
    ]

    candidates = []
    for pattern in price_patterns:
        matches = re.findall(pattern, cleaned_text)
        candidates.extend(matches)

    if not candidates:
        return None

    # Ưu tiên giá lớn nhất (giá sản phẩm thường lớn hơn ngưỡng shipping)
    def parse_value(price_str: str) -> int:
        digits = re.sub(r'[^\d]', '', price_str)
        return int(digits) if digits else 0

    candidates.sort(key=parse_value, reverse=True)
    return candidates[0].strip()