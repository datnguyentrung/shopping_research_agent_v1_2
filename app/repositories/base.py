from __future__ import annotations

from typing import Generic, Iterable, Optional, Type, TypeVar

from sqlalchemy.orm import Session

from app.core.database import Base

ModelType = TypeVar("ModelType", bound=Base)


class BaseRepository(Generic[ModelType]):
    """Generic repository base class with common CRUD helpers.

    This layer should stay thin and focus on pure DB access using SQLAlchemy.
    Business rules should live in the service layer.
    """

    def __init__(self, db: Session, model: Type[ModelType]):
        self.db = db
        self.model = model

    def get(self, id: int) -> Optional[ModelType]:
        return self.db.get(self.model, id)

    def list(self, *, skip: int = 0, limit: int = 100) -> Iterable[ModelType]:
        query = self.db.query(self.model)
        if skip:
            query = query.offset(skip)
        if limit:
            query = query.limit(limit)
        return query.all()

    def create(self, obj_in: dict) -> ModelType:
        db_obj = self.model(**obj_in)
        self.db.add(db_obj)
        self.db.commit()
        self.db.refresh(db_obj)
        return db_obj

    def update(self, db_obj: ModelType, obj_in: dict) -> ModelType:
        for field, value in obj_in.items():
            if hasattr(db_obj, field):
                setattr(db_obj, field, value)
        self.db.add(db_obj)
        self.db.commit()
        self.db.refresh(db_obj)
        return db_obj

    def delete(self, db_obj: ModelType) -> None:
        self.db.delete(db_obj)
        self.db.commit()

