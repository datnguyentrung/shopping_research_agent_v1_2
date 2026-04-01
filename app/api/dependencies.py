# Dependency injection (vd: check API key)

from app.core.database import SessionLocal

def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()