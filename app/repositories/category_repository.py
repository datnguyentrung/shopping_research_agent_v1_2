from __future__ import annotations

from typing import Optional

from sqlalchemy.orm import Session

from app.models import Category
from app.models.category import Category
from .base import BaseRepository


class CategoryRepository(BaseRepository[Category]):
    """Repository for Category models."""

    def __init__(self, db: Session):
        super().__init__(db, Category)

    def get_by_name(self, name: str) -> Optional[Category]:
        return self.db.query(Category).filter(Category.name == name).first()

    def list(
        self,
        *,
        parent_id: Optional[int] = None,
        level: Optional[int] = None,
        skip: int = 0,
        limit: int = 100,
    ) -> list[type[Category]]:
        query = self.db.query(Category)
        if parent_id is not None:
            query = query.filter(Category.parent_id == parent_id)
        if level is not None:
            query = query.filter(Category.level == level)
        if skip:
            query = query.offset(skip)
        if limit:
            query = query.limit(limit)
        return query.all()

