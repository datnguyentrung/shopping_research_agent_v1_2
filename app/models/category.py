from sqlalchemy import Column, Integer, String, Float, ForeignKey
from sqlalchemy.orm import relationship

from app.core.database import Base

class Category(Base):
    __tablename__ = "category"

    id = Column(String(255), primary_key=True, index=True, autoincrement=True)
    name = Column(String(255), unique=True, nullable=False)
    parent_id = Column(Integer, ForeignKey("category.id"))
    level = Column(Integer, nullable=False)

    # Quan hệ N-N với Attribute thông qua bảng trung gian
    attributes = relationship("Attribute", secondary="category_attribute")

    def __repr__(self):
        return f"<Category(id={self.id}, name='{self.name}', parent_id={self.parent_id}, level={self.level})>"