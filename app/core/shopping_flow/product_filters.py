import re


def parse_vnd_amount(raw: str, unit: str | None) -> int:
    """Convert textual amount to VND integer.

    Supports shorthand like 300k, 1.5tr and plain grouped numbers like 1.200.000.
    """
    raw = (raw or "").strip()
    unit = (unit or "").lower().strip()

    if unit:
        value = float(raw.replace(",", "."))
        if unit in {"k", "nghin", "nghìn", "ngan", "ngàn"}:
            return int(value * 1_000)
        if unit in {"tr", "trieu", "triệu", "m"}:
            return int(value * 1_000_000)

    cleaned = re.sub(r"[.,\s]", "", raw)
    return int(cleaned) if cleaned.isdigit() else 0


def parse_budget_bounds(option_text: str) -> tuple[int | None, int | None]:
    """Infer min/max budget from Vietnamese free text options."""
    text = (option_text or "").strip().lower()
    if not text or not re.search(r"\d", text):
        return None, None

    matches = re.findall(r"(\d+(?:[.,]\d+)*)\s*(k|nghin|nghìn|ngan|ngàn|tr|trieu|triệu|m)?", text)
    values = [
        parse_vnd_amount(amount, unit)
        for amount, unit in matches
        if parse_vnd_amount(amount, unit) > 0
    ]

    if not values:
        return None, None

    if "-" in text and len(values) >= 2:
        return min(values[0], values[1]), max(values[0], values[1])

    if any(token in text for token in ["dưới", "duoi", "<=", "toi da", "tối đa"]):
        return None, values[0]

    if any(token in text for token in ["trên", "tren", "từ", "tu", ">="]):
        return values[0], None

    return None, None


def apply_product_filters(products: list, answers: list) -> list:
    """Apply deterministic hard filters before LLM ranking.

    Current hard filter is price only, intentionally simple to avoid false negatives.
    """
    if not answers or not products:
        return products[:100]

    max_price = float("inf")
    min_price = 0

    for ans in answers:
        options = ans.get("selected_options", [])
        for option in options:
            parsed_min, parsed_max = parse_budget_bounds(str(option))
            if parsed_min is not None or parsed_max is not None:
                if parsed_min is not None:
                    min_price = max(min_price, parsed_min)
                if parsed_max is not None:
                    max_price = min(max_price, parsed_max)

    filtered_products = []
    for prod in products:
        p_dict = prod.model_dump(by_alias=False) if hasattr(prod, "model_dump") else prod
        price = float(p_dict.get("price_current", 0))

        if min_price <= price <= max_price:
            filtered_products.append(prod)

    filtered_products.sort(
        key=lambda x: float((x.model_dump(by_alias=False) if hasattr(x, "model_dump") else x).get("price_current", 0)),
        reverse=True,
    )

    return filtered_products[:50]

