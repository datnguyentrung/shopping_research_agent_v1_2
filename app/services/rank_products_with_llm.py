import json
from collections.abc import AsyncIterator

from app.services.request_model_service import stream_ranking_ids
from app.utils.trace_log import product_summary, trace_print


async def rank_products_with_llm_stream(
        filtered_products: list,
        user_message: str,
        answers: list,
        trace_id: str | None = None) -> AsyncIterator[dict]:
    trace_key = trace_id or "no-trace"
    trace_print(
        trace_key,
        "rank_products_with_llm_stream",
        "enter",
        filteredProducts=len(filtered_products),
        answersCount=len(answers),
        userMessagePreview=user_message[:160],
    )

    if not filtered_products:
        trace_print(trace_key, "rank_products_with_llm_stream", "no_filtered_products")
        return

    preferences_text = "Không có tiêu chí đặc biệt."
    if answers:
        prefs = [", ".join([str(opt) for opt in ans.get("selected_options", [])]) for ans in answers if
                 ans.get("selected_options")]
        if prefs:
            preferences_text = "Người dùng ưu tiên các tiêu chí sau: " + " | ".join(prefs)

    mini_products = []
    product_map = {}
    for prod in filtered_products:
        p_dict = prod.model_dump(by_alias=False) if hasattr(prod, "model_dump") else prod
        pid = str(p_dict.get("product_id") or p_dict.get("productId") or p_dict.get("id"))

        product_map[pid] = prod
        mini_products.append({
            "product_id": pid,
            "name": p_dict.get("name", ""),
            "price": p_dict.get("price_current", 0),
            "rating": p_dict.get("rating_star", 0),
            "sold": p_dict.get("sold_count", 0)
        })

    trace_print(
        trace_key,
        "rank_products_with_llm_stream",
        "prompt_prepared",
        candidateCount=len(mini_products),
    )

    prompt = f"""Hãy xếp hạng danh sách sản phẩm E-commerce dưới đây.
    [YÊU CẦU BAN ĐẦU CỦA KHÁCH]: "{user_message}"
    [CÁC TIÊU CHÍ KHÁCH ĐÃ CHỌN THÊM]: {preferences_text}
    [DANH SÁCH SẢN PHẨM ỨNG VIÊN]: {json.dumps(mini_products, ensure_ascii=False)}
    Nhiệm vụ: Chấm điểm (score từ 0-100)..."""

    yielded_ids = set()
    stream_idx = 0

    async for pid in stream_ranking_ids(prompt):
        stream_idx += 1
        trace_print(
            trace_key,
            "rank_products_with_llm_stream",
            "ranking_id_streamed",
            index=stream_idx,
            productId=pid,
            seenCount=len(yielded_ids),
        )
        if pid in product_map and pid not in yielded_ids:
            yielded_ids.add(pid)
            product = product_map[pid]
            trace_print(
                trace_key,
                "rank_products_with_llm_stream",
                "emit_ranked_product",
                product=product_summary(product),
            )
            yield product

    fallback_count = 0
    for pid, p in product_map.items():
        if pid not in yielded_ids:
            fallback_count += 1
            trace_print(
                trace_key,
                "rank_products_with_llm_stream",
                "emit_fallback_product",
                product=product_summary(p),
            )
            yield p

    trace_print(
        trace_key,
        "rank_products_with_llm_stream",
        "completed",
        rankedYielded=len(yielded_ids),
        fallbackYielded=fallback_count,
        totalYielded=len(yielded_ids) + fallback_count,
    )
