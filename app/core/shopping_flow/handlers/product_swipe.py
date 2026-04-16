from app.memory.session_store import clear_session
from app.schemas.entities import A2UIChunk, MessageChunk

from app.core.shopping_flow.final_summary import generate_final_summary_with_llm
from app.core.shopping_flow.ui_chunks import build_interactive_product_chunk
from app.services.request_model_service import analyze_dislike_reason
from app.utils.trace_log import product_summary, short_preview, trace_plain, trace_print


async def handle_product_swipe(session: dict, session_id: str, action: str, data):
    """Consume swipe feedback and decide whether to continue or finalize."""
    trace_print(
        session_id,
        "handle_product_swipe",
        "enter",
        action=action,
        dataPreview=short_preview(data),
        whitelistCount=len(session.get("whitelist", [])),
        blacklistCount=len(session.get("blacklist", [])),
        pendingCount=len(session.get("pending_products", [])),
    )

    if action != "PRODUCT_FEEDBACK":
        trace_print(session_id, "handle_product_swipe", "skip_unsupported_action", action=action)
        return

    if isinstance(data, dict):
        decision = data.get("decision", "").lower()
        trace_print(session_id, "handle_product_swipe", "feedback_received", decision=decision)
        if decision == "like":
            session["whitelist"].append(data)
            trace_print(
                session_id,
                "handle_product_swipe",
                "like_recorded",
                whitelistCount=len(session["whitelist"]),
                product=data.get("product") or data,
            )
        elif decision == "dislike":
            session["blacklist"].append(data)

            reason = data.get("reason", "")
            rejected_product = data.get("product", {})
            trace_print(
                session_id,
                "handle_product_swipe",
                "dislike_recorded",
                reason=reason,
                blacklistCount=len(session["blacklist"]),
                rejectedProduct=short_preview(rejected_product),
            )

            if reason and session.get("pending_products"):
                yield A2UIChunk(
                    a2ui={
                        "type": "a2ui_processing_status",
                        "data": {
                            "statusText": f"Đang điều chỉnh kết quả để loại bỏ sản phẩm '{reason}'...",
                            "progressPercent": 85
                        }
                    }
                )

                filtered_products = []
                original_count = len(session["pending_products"])

                if reason == "Giá quá cao":
                    current_price = float(rejected_product.get("price_current", 0)) if rejected_product else 0
                    for p in session["pending_products"]:
                        p_dict = p.model_dump(by_alias=False) if hasattr(p, "model_dump") else p
                        if current_price == 0 or float(p_dict.get("price_current", 0)) < current_price:
                            filtered_products.append(p)
                    trace_print(
                        session_id,
                        "handle_product_swipe",
                        "hard_filter_price",
                        basePrice=current_price,
                        before=original_count,
                        after=len(filtered_products),
                    )

                elif reason == "Thương hiệu":
                    bad_brand = rejected_product.get("brand", "").lower() if rejected_product else ""
                    for p in session["pending_products"]:
                        p_dict = p.model_dump(by_alias=False) if hasattr(p, "model_dump") else p
                        if not bad_brand or p_dict.get("brand", "").lower() != bad_brand:
                            filtered_products.append(p)
                    trace_print(
                        session_id,
                        "handle_product_swipe",
                        "hard_filter_brand",
                        blockedBrand=bad_brand,
                        before=original_count,
                        after=len(filtered_products),
                    )

                elif reason == "Khác" or reason not in ["Không hợp phong cách", "Tính năng"]:
                    banned_keywords = await analyze_dislike_reason(reason)
                    trace_print(
                        session_id,
                        "handle_product_swipe",
                        "soft_filter_keywords",
                        reason=reason,
                        bannedKeywords=banned_keywords,
                    )

                    for p in session["pending_products"]:
                        p_dict = p.model_dump(by_alias=False) if hasattr(p, "model_dump") else p
                        p_text = f"{p_dict.get('name', '')} {p_dict.get('description', '')}".lower()
                        is_banned = any(kw.lower() in p_text for kw in banned_keywords if kw.strip())
                        if not is_banned:
                            filtered_products.append(p)

                    trace_print(
                        session_id,
                        "handle_product_swipe",
                        "soft_filter_result",
                        before=original_count,
                        after=len(filtered_products),
                    )
                else:
                    filtered_products = session["pending_products"]
                    trace_print(
                        session_id,
                        "handle_product_swipe",
                        "skip_additional_filter",
                        reason=reason,
                        pendingCount=len(filtered_products),
                    )

                if filtered_products:
                    session["pending_products"] = filtered_products
                trace_print(
                    session_id,
                    "handle_product_swipe",
                    "pending_products_updated",
                    before=original_count,
                    after=len(session.get("pending_products", [])),
                )

    total_swipes = len(session.get("whitelist", [])) + len(session.get("blacklist", []))
    trace_print(
        session_id,
        "handle_product_swipe",
        "swipe_state",
        whitelistCount=len(session.get("whitelist", [])),
        blacklistCount=len(session.get("blacklist", [])),
        totalSwipes=total_swipes,
        pendingCount=len(session.get("pending_products", [])),
    )

    if len(session["whitelist"]) >= 5 or total_swipes >= 10 or len(session["pending_products"]) < 1:
        if not session["whitelist"]:
            trace_print(session_id, "handle_product_swipe", "done_without_like")
            yield MessageChunk(
                content="Có vẻ bạn chưa ưng ý sản phẩm nào trong lô này. Hãy thử ấn Bắt đầu mới và mô tả lại nhu cầu cụ thể hơn nhé!"
            )
            yield A2UIChunk(a2ui={"type": "a2ui_done", "data": {}})
            clear_session(session_id)
            trace_print(session_id, "handle_product_swipe", "session_cleared")
            return

        session["phase"] = "FINAL_SUMMARY"
        trace_print(
            session_id,
            "handle_product_swipe",
            "start_final_summary",
            whitelistCount=len(session["whitelist"]),
            blacklistCount=len(session.get("blacklist", [])),
            rawProducts=len(session.get("raw_products", [])),
            pendingProducts=len(session.get("pending_products", [])),
        )
        yield A2UIChunk(
            a2ui={
                "type": "a2ui_processing_status",
                "data": {
                    "statusText": "Đang tổng hợp các mẫu bạn thích để viết báo cáo...",
                    "progressPercent": 100,
                },
            }
        )

        final_chunks = generate_final_summary_with_llm(
            whitelist=session["whitelist"],
            all_products=session.get("raw_products", []),
            original_keyword=session.get("vi_keyword", ""),
            pending_products=session.get("pending_products", []),
            blacklist=session["blacklist"],
        )
        chunk_count = 0
        async for chunk in final_chunks:
            chunk_count += 1
            trace_print(
                session_id,
                "handle_product_swipe",
                "yield_final_summary_chunk",
                index=chunk_count,
                chunkType=type(chunk).__name__,
            )
            yield chunk

        yield A2UIChunk(a2ui={"type": "a2ui_done", "data": {}})
        clear_session(session_id)
        trace_print(session_id, "handle_product_swipe", "final_summary_completed", yieldedChunks=chunk_count)
        return

    next_prod = session["pending_products"].pop(0)
    trace_print(
        session_id,
        "handle_product_swipe",
        "emit_next_product",
        nextProduct=product_summary(next_prod),
        remainingPending=len(session.get("pending_products", [])),
    )
    trace_plain(f"Next product to swipe: {getattr(next_prod, 'name', str(next_prod))}")
    yield build_interactive_product_chunk(next_prod)
