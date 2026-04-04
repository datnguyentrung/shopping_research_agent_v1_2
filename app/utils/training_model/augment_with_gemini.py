import json
import logging
from typing import Any, Dict, Iterable, List

import pandas as pd
from google import genai
from google.genai import Client, types

from app.core.config.config import settings

# Logger module-level
logger = logging.getLogger(__name__)

CATEGORY_MISSING_PATH = r'D:\Thực tập MB\Shopping_Research_Agent_V1_2\data\category_missing.csv'
CLEANNED_TRAINING_DATA_PATH = r'D:\Thực tập MB\Shopping_Research_Agent_V1_2\data\cleaned_training_data.csv'
ADDITIONAL_TRAINING_DATA_PATH = r'D:\Thực tập MB\Shopping_Research_Agent_V1_2\data\additional_training_data.csv'

# 1. Khởi tạo Client
client: Client = genai.Client(api_key=settings.GOOGLE_API_KEY)

# 2. CẤU HÌNH LẠI SCHEMA ĐỂ HỖ TRỢ NHIỀU CATEGORY CÙNG LÚC
# Cấu trúc: { "results": [ {"category_id": 123, "queries": ["...", "..."]} ] }
config = types.GenerateContentConfig(
    temperature=0.7,
    top_p=0.95,
    response_mime_type="application/json",
    response_schema={
        "type": "OBJECT",
        "properties": {
            "results": {
                "type": "ARRAY",
                "items": {
                    "type": "OBJECT",
                    "properties": {
                        "category_id": {"type": "INTEGER"},
                        "category_name": {"type": "STRING"},
                        "queries": {
                            "type": "ARRAY",
                            "items": {"type": "STRING"},
                        },
                    },
                    "required": ["category_id", "category_name", "queries"],
                },
            }
        },
        "required": ["results"],
    },
)


def original_data_preparation(missing_df: pd.DataFrame, cleaned_df: pd.DataFrame) -> Dict[int, List[str]]:
    """Chuẩn bị map: category_id -> list[search_query] từ dữ liệu gốc."""

    missing_categories: Iterable[int] = set(missing_df["id"].tolist())
    filtered_df = cleaned_df[cleaned_df["category_id"].isin(missing_categories)]
    grouped = filtered_df.groupby("category_id")["search_query"].apply(list)
    return grouped.to_dict()


def _build_prompt(
    batch_cat_map: Dict[Any, str],
    batch_orig_map: Dict[Any, List[str]],
    batch_need_map: Dict[Any, int],
    target_per_category: int,
) -> str:
    """Tạo prompt cho 1 batch category với số lượng query cần thêm cho từng category.

    Parameters
    ----------
    batch_cat_map: dict
        Map category_id -> category_name cho batch hiện tại.
    batch_orig_map: dict
        Map category_id -> danh sách search_query gốc cho batch hiện tại.
    batch_need_map: dict
        Map category_id -> số lượng query *tối thiểu* cần sinh thêm để tiệm cận target.
    target_per_category: int
        Ngưỡng mong muốn số lượng mẫu / category (ví dụ 300).
    """

    prompt = f"""
    You are an expert in e-commerce search data.

    Below is a map of category IDs to their category names:
    {json.dumps(batch_cat_map, ensure_ascii=False)}

    Here are some existing search queries for these categories (use these ONLY to understand the context/style, do NOT copy them exactly):
    {json.dumps(batch_orig_map, ensure_ascii=False)}

    For each category_id above, here is how many additional queries are still missing to reach the target of {target_per_category} queries:
    {json.dumps(batch_need_map, ensure_ascii=False)}

    TASK:
    For EVERY category_id present in the map above, generate AT LEAST the number of *new* queries specified in the map of missing counts.
    The queries MUST be:
    - written in natural English, as users would type on Amazon/Shopee;
    - highly diverse and realistic;
    - not trivial rewrites of the existing queries;
    - covering a wide range of attributes like size, color, material, use cases, and styles.

    Return the result as JSON following exactly this schema:
    {{
      "results": [
        {{
          "category_id": <int>,
          "category_name": <string>,
          "queries": [<string>, ...]
        }},
        ...
      ]
    }}
    """
    return prompt


def _extract_response_text(response: Any) -> str:
    """Trích nội dung text JSON từ response của Google GenAI."""

    text = getattr(response, "text", None)
    if isinstance(text, str) and text.strip():
        return text

    try:
        candidates = getattr(response, "candidates", None)
        if candidates:
            first = candidates[0]
            content = getattr(first, "content", None)
            parts = getattr(content, "parts", None)
            if parts:
                part0 = parts[0]
                part_text = getattr(part0, "text", None)
                if isinstance(part_text, str) and part_text.strip():
                    return part_text
    except Exception:  # defensive
        logger.exception("Failed to extract text from Gemini response structure.")

    raise ValueError("Unable to extract JSON text from Gemini response")


def _parse_gemini_json(raw_text: str) -> Dict[str, Any]:
    """Parse và validate JSON trả về từ Gemini."""

    try:
        data = json.loads(raw_text)
    except json.JSONDecodeError as exc:
        snippet = raw_text[:500] + ("... [TRUNCATED]" if len(raw_text) > 500 else "")
        logger.error("JSON decode error from Gemini response: %s | snippet=%s", exc, snippet)
        raise

    if not isinstance(data, dict):
        raise ValueError("Gemini response JSON must be an object at top level")

    results = data.get("results")
    if results is None or not isinstance(results, list):
        raise ValueError("Gemini response JSON must contain 'results' as a list")

    return data


def _collect_augmented_data(
    data: Dict[str, Any],
    category_map: Dict[Any, str],
) -> List[Dict[str, Any]]:
    """Chuyển dữ liệu đã parse thành list bản ghi để lưu CSV."""

    augmented: List[Dict[str, Any]] = []
    results = data.get("results", [])

    for idx, item in enumerate(results):
        if not isinstance(item, dict):
            logger.warning("Skip result index %s: not an object", idx)
            continue

        cat_id = item.get("category_id")
        queries = item.get("queries")

        if cat_id is None or not isinstance(queries, list):
            logger.warning(
                "Skip result index %s: missing/invalid category_id or queries (category_id=%r, type(queries)=%s)",
                idx,
                cat_id,
                type(queries).__name__,
            )
            continue

        cat_name = category_map.get(cat_id) or category_map.get(str(cat_id)) or item.get("category_name") or "Unknown"

        for q in queries:
            if not isinstance(q, str) or not q.strip():
                continue
            augmented.append(
                {
                    "category_id": cat_id,
                    "category_name": cat_name,
                    "search_query": q.strip(),
                }
            )

    return augmented


def augment_with_gemini(batch_size: int = 10, target_per_category: int = 300, min_new_per_category: int = 80) -> None:
    """Augment dữ liệu search query cho các category còn thiếu bằng Gemini.

    - Đọc `category_missing.csv` và `cleaned_training_data.csv` từ thư mục `data/`.
    - Dựa trên `query_count` trong `category_missing.csv`, tính số lượng query cần thêm cho từng category
      để tiệm cận `target_per_category`.
    - Gọi Gemini theo từng batch category (mỗi batch một request) để sinh query mới.
    - Ghi kết quả tổng hợp vào `additional_training_data.csv`.

    Parameters
    ----------
    batch_size: int
        Số lượng category mỗi batch gọi API.
    target_per_category: int
        Số mẫu mong muốn / category (mặc định 300).
    min_new_per_category: int
        Số lượng tối thiểu query mới yêu cầu models sinh cho mỗi category, ngay cả khi thiếu rất ít,
        để chống trùng lặp quá nhiều.
    """

    missing_df = pd.read_csv(CATEGORY_MISSING_PATH)
    cleaned_df = pd.read_csv(CLEANNED_TRAINING_DATA_PATH)

    if "query_count" not in missing_df.columns:
        raise ValueError("category_missing.csv must contain a 'query_count' column")

    logger.info(
        "Loaded %d missing categories. query_count in [min=%d, max=%d]",
        len(missing_df),
        missing_df["query_count"].min(),
        missing_df["query_count"].max(),
    )

    original_map = original_data_preparation(missing_df, cleaned_df)
    category_map: Dict[Any, str] = missing_df.set_index("id")["name"].to_dict()

    # id -> current count
    current_count_map: Dict[Any, int] = missing_df.set_index("id")["query_count"].to_dict()

    items = list(category_map.items())
    all_augmented: List[Dict[str, Any]] = []

    for start in range(0, len(items), batch_size):
        end = min(start + batch_size, len(items))
        batch_items = items[start:end]
        batch_cat_map = dict(batch_items)

        # Lọc original_map cho batch hiện tại
        batch_keys = {k for k in batch_cat_map.keys()}
        batch_keys_str = {str(k) for k in batch_cat_map.keys()}
        batch_orig_map = {
            k: v
            for k, v in original_map.items()
            if k in batch_keys or str(k) in batch_keys_str
        }

        # Tính số lượng cần thêm cho batch hiện tại
        batch_need_map: Dict[Any, int] = {}
        for cat_id, _ in batch_items:
            current = current_count_map.get(cat_id) or current_count_map.get(str(cat_id)) or 0
            need = max(target_per_category - int(current), 0)
            # Đặt ngưỡng tối thiểu để nâng xác suất nhận được đủ mẫu sau khi loại trùng
            if need > 0:
                need = max(need, min_new_per_category)
            batch_need_map[cat_id] = need

        logger.info(
            "Sending batch to Gemini: batch_index=%d, size=%d (categories %d-%d). Needs=%s",
            start // batch_size,
            len(batch_items),
            start,
            end - 1,
            batch_need_map,
        )

        prompt = _build_prompt(batch_cat_map, batch_orig_map, batch_need_map, target_per_category)

        try:
            response = client.models.generate_content(
                model="gemini-3.1-flash-lite-preview",
                contents=prompt,
                config=config,
            )

            raw_text = _extract_response_text(response)
            parsed = _parse_gemini_json(raw_text)
            batch_augmented = _collect_augmented_data(parsed, category_map)
            all_augmented.extend(batch_augmented)

            logger.info(
                "Batch finished: batch_index=%d, new_queries=%d, total_queries=%d",
                start // batch_size,
                len(batch_augmented),
                len(all_augmented),
            )
        except Exception:
            logger.exception("Failed to process batch starting at index %d", start)
            continue

    if all_augmented:
        augmented_df = pd.DataFrame(all_augmented)
        augmented_df.to_csv(ADDITIONAL_TRAINING_DATA_PATH, index=False)
        logger.info(
            "Saved %d augmented queries to %s", len(all_augmented), ADDITIONAL_TRAINING_DATA_PATH
        )
    else:
        logger.warning("No augmented data generated; CSV will not be written.")


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    augment_with_gemini()
