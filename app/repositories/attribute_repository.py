from __future__ import annotations

from typing import Iterable, Optional

from sqlalchemy.orm import Session

from app.models import Attribute
from app.models.attribute import Attribute
from .base import BaseRepository


class AttributeRepository(BaseRepository[Attribute]):
    """Repository for Attribute model."""

    def __init__(self, db: Session):
        super().__init__(db, Attribute)

    def get_by_name(self, name: str) -> Optional[Attribute]:
        return self.db.query(Attribute).filter(Attribute.name == name).first()

    def list(self, *, skip: int = 0, limit: int = 100) -> list[type[Attribute]]:
        query = self.db.query(Attribute)
        if skip:
            query = query.offset(skip)
        if limit:
            query = query.limit(limit)
        return query.all()

