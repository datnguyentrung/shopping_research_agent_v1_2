from sqlalchemy import Column, Integer, String, Float, ForeignKey, Boolean
from app.core.database import Base

class CategoryAttribute(Base):
    __tablename__ = "category_attribute"

    id = Column(Integer, primary_key=True, index=True)
    category_id = Column(String(255), ForeignKey("category.id"), nullable=False)
    attribute_id = Column(Integer, ForeignKey("attribute.id"), nullable=False)
    is_core = Column(Boolean, nullable=False, default=False)

    def __repr__(self):
        return f"<CategoryAttribute(id={self.id}, category_id={self.category_id}, attribute_id={self.attribute_id})>"