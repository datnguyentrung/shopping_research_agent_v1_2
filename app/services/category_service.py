from __future__ import annotations

from typing import Iterable, Optional

from sqlalchemy.orm import Session

from app.models.category import Category
from app.models.category_attribute import CategoryAttribute
from app.services.base import BaseService
from app.repositories import (
    CategoryRepository,
    AttributeRepository,
    CategoryAttributeRepository,
)


class CategoryService(BaseService):
    """Business logic related to Category and its attributes."""

    def __init__(self, db: Session):
        super().__init__(db)
        self._categories = CategoryRepository(db)
        self._attributes = AttributeRepository(db)
        self._category_attributes = CategoryAttributeRepository(db)

    # Basic CRUD wrappers -------------------------------------------------

    def get_category(self, id: int) -> Optional[Category]:
        return self._categories.get(id)

    def list_categories(
        self,
        *,
        parent_id: Optional[int] = None,
        level: Optional[int] = None,
        skip: int = 0,
        limit: int = 100,
    ) -> Iterable[Category]:
        return self._categories.list(
            parent_id=parent_id, level=level, skip=skip, limit=limit
        )

    def create_category(self, data: dict) -> Category:
        return self._categories.create(data)

    def update_category(self, id: int, data: dict) -> Optional[Category]:
        category = self._categories.get(id)
        if not category:
            return None
        return self._categories.update(category, data)

    def delete_category(self, id: int) -> bool:
        category = self._categories.get(id)
        if not category:
            return False
        self._categories.delete(category)
        return True

    # Attribute relations -------------------------------------------------

    def attach_attributes(
        self,
        category_id: int,
        attribute_ids: list[int],
        *,
        is_core: bool = False,
    ) -> None:
        """Attach multiple attributes to a category.

        Idempotent: existing pairs will be kept and not duplicated.
        """

        # Ensure category exists
        category = self._categories.get(category_id)
        if not category:
            raise ValueError("Category not found")

        for attr_id in attribute_ids:
            attr = self._attributes.get(attr_id)
            if not attr:
                continue  # or raise, depending on business rule

            pair = self._category_attributes.get_pair(category_id, attr_id)
            if pair:
                # Optionally update is_core flag
                if pair.is_core != is_core:
                    self._category_attributes.update(pair, {"is_core": is_core})
                continue

            self._category_attributes.create(
                {
                    "category_id": category_id,
                    "attribute_id": attr_id,
                    "is_core": is_core,
                }
            )

    def list_category_attributes(self, category_id: int) -> Iterable[CategoryAttribute]:
        return self._category_attributes.list_by_category(category_id)

