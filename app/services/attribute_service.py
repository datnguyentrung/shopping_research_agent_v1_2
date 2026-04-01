from __future__ import annotations

from typing import Iterable, Optional

from sqlalchemy.orm import Session

from app.models.attribute import Attribute
from app.services.base import BaseService
from app.repositories import AttributeRepository


class AttributeService(BaseService):
    """Business logic related to Attribute."""

    def __init__(self, db: Session):
        super().__init__(db)
        self._attributes = AttributeRepository(db)

    def get_attribute(self, id: int) -> Optional[Attribute]:
        return self._attributes.get(id)

    def list_attributes(self, *, skip: int = 0, limit: int = 100) -> Iterable[Attribute]:
        return self._attributes.list(skip=skip, limit=limit)

    def create_attribute(self, data: dict) -> Attribute:
        return self._attributes.create(data)

    def update_attribute(self, id: int, data: dict) -> Optional[Attribute]:
        attribute = self._attributes.get(id)
        if not attribute:
            return None
        return self._attributes.update(attribute, data)

    def delete_attribute(self, id: int) -> bool:
        attribute = self._attributes.get(id)
        if not attribute:
            return False
        self._attributes.delete(attribute)
        return True

