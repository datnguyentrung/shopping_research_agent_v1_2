import random

from app.repositories import CategoryRepository
from app.repositories.category_attribute_repository import CategoryAttributeRepository
from app.services.rank_products_with_llm import rank_products_with_llm
from app.services.search_service import run_parallel_searches
from app.core.database import SessionLocal


def build_attribute_questions(category_id: int) -> list[dict]:
    """Load inherited attributes and keep a compact randomized subset for UI questions."""
    db = SessionLocal()
    try:
        category_attribute_repo = CategoryAttributeRepository(db)
        # Repository signature expects list[str], keep conversion local.
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

        return attributes_data
    finally:
        db.close()


def get_child_categories(category_id: int) -> tuple[list[str], dict[str, int], list]:
    """Load direct children for category drill-down and provide FE-ready option list."""
    db = SessionLocal()
    try:
        category_repo = CategoryRepository(db)
        cat_children = category_repo.get_by_parent_id(category_id)
        options = [getattr(child, "name_vi", child.name) or child.name for child in cat_children]
        mapping = {(getattr(child, "name_vi", child.name) or child.name): child.id for child in cat_children}
        return options, mapping, cat_children
    finally:
        db.close()


async def search_and_rank_products(
    final_search_keyword: str,
    user_message: str,
    answers: list,
    min_price_filter: int | None = None,
    max_price_filter: int | None = None,
):
    """Centralized search + ranking pipeline used by multiple phases."""
    raw_products = await run_parallel_searches(final_search_keyword, min_price_filter, max_price_filter)

    from app.core.shopping_flow.product_filters import apply_product_filters

    filtered_products = apply_product_filters(raw_products, answers)
    ranked_products = await rank_products_with_llm(filtered_products, user_message, answers)
    return raw_products, ranked_products
