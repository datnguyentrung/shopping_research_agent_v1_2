from __future__ import annotations

from typing import Optional

from sqlalchemy.orm import Session

from app.models.category_attribute import CategoryAttribute
from .base import BaseRepository


class CategoryAttributeRepository(BaseRepository[CategoryAttribute]):
    """Repository for CategoryAttribute models (join table)."""

    def __init__(self, db: Session):
        super().__init__(db, CategoryAttribute)

    def list_by_category(self, category_id: int) -> list[type[CategoryAttribute]]:
        return (
            self.db.query(CategoryAttribute)
            .filter(CategoryAttribute.category_id == category_id)
            .all()
        )

    def list_by_attribute(self, attribute_id: int) -> list[type[CategoryAttribute]]:
        return (
            self.db.query(CategoryAttribute)
            .filter(CategoryAttribute.attribute_id == attribute_id)
            .all()
        )

    def get_pair(self, category_id: int, attribute_id: int) -> Optional[CategoryAttribute]:
        return (
            self.db.query(CategoryAttribute)
            .filter(
                CategoryAttribute.category_id == category_id,
                CategoryAttribute.attribute_id == attribute_id,
            )
            .first()
        )

