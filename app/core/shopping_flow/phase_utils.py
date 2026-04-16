import random

from app.repositories import CategoryRepository
from app.repositories.category_attribute_repository import CategoryAttributeRepository
from app.services.rank_products_with_llm import rank_products_with_llm_stream
from app.services.search_service import run_parallel_searches
from app.core.database import SessionLocal
from app.utils.trace_log import trace_print


def build_attribute_questions(category_id: int, trace_id: str | None = None) -> list[dict]:
    """Load inherited attributes and keep a compact randomized subset for UI questions."""
    trace_key = trace_id or "no-trace"
    trace_print(trace_key, "build_attribute_questions", "enter", categoryId=category_id)

    db = SessionLocal()
    try:
        category_attribute_repo = CategoryAttributeRepository(db)
        db_attributes = category_attribute_repo.get_inherited_attributes_cte([str(category_id)])

        attributes_data = []
        if db_attributes:
            selected_attributes = [db_attributes[0]]
            remaining_attributes = db_attributes[1:]
            num_samples = min(4, len(remaining_attributes))

            if num_samples > 0:
                selected_attributes.extend(random.sample(remaining_attributes, num_samples))

            for attr in selected_attributes:
                attributes_data.append(
                    {
                        "id": attr.id,
                        "name": attr.name,
                        "options": attr.options if attr.options else [],
                    }
                )

        trace_print(
            trace_key,
            "build_attribute_questions",
            "exit",
            sourceAttributes=len(db_attributes) if db_attributes else 0,
            selectedAttributes=len(attributes_data),
        )
        return attributes_data
    finally:
        db.close()


def get_child_categories(category_id: int, trace_id: str | None = None) -> tuple[list[str], dict[str, int], list]:
    """Load direct children for category drill-down and provide FE-ready option list."""
    trace_key = trace_id or "no-trace"
    trace_print(trace_key, "get_child_categories", "enter", categoryId=category_id)

    db = SessionLocal()
    try:
        category_repo = CategoryRepository(db)
        cat_children = category_repo.get_by_parent_id(category_id)
        options = [getattr(child, "name_vi", child.name) or child.name for child in cat_children]
        mapping = {(getattr(child, "name_vi", child.name) or child.name): child.id for child in cat_children}

        trace_print(
            trace_key,
            "get_child_categories",
            "exit",
            childrenCount=len(cat_children),
            optionsCount=len(options),
        )
        return options, mapping, cat_children
    finally:
        db.close()


# async def search_and_rank_products(
#     final_search_keyword: str,
#     user_message: str,
#     answers: list,
#     min_price_filter: int | None = None,
#     max_price_filter: int | None = None,
# ):
#     """Centralized search + ranking pipeline used by multiple phases."""
#     raw_products = await run_parallel_searches(final_search_keyword, min_price_filter, max_price_filter)
#
#     from app.core.shopping_flow.product_filters import apply_product_filters
#
#     filtered_products = apply_product_filters(raw_products, answers)
#     ranked_products = await rank_products_with_llm_stream(filtered_products, user_message, answers)
#     return raw_products, ranked_products

async def search_and_prepare_stream(
        final_search_keyword: str,
        user_message: str,
        answers: list,
        min_price_filter: int | None = None,
        max_price_filter: int | None = None,
        trace_id: str | None = None,
):
    trace_key = trace_id or "no-trace"
    trace_print(
        trace_key,
        "search_and_prepare_stream",
        "enter",
        finalSearchKeyword=final_search_keyword,
        answersCount=len(answers),
        minPrice=min_price_filter,
        maxPrice=max_price_filter,
    )

    raw_products = await run_parallel_searches(
        final_search_keyword,
        min_price_filter,
        max_price_filter,
        trace_id=trace_key,
    )
    from app.core.shopping_flow.product_filters import apply_product_filters

    filtered_products = apply_product_filters(raw_products, answers)
    ranked_stream = rank_products_with_llm_stream(filtered_products, user_message, answers, trace_id=trace_key)

    trace_print(
        trace_key,
        "search_and_prepare_stream",
        "prepared",
        rawProducts=len(raw_products),
        filteredProducts=len(filtered_products),
    )
    return raw_products, ranked_stream