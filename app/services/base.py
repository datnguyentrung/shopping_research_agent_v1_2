from __future__ import annotations

from sqlalchemy.orm import Session


class BaseService:
    """Base class for services.

    Holds a SQLAlchemy session and can be extended with
    cross-cutting concerns (logging, metrics, error mapping,...).
    """

    def __init__(self, db: Session):
        self.db = db

