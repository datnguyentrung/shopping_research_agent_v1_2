from sqlalchemy import Column, Integer, String, Float, ForeignKey, PrimaryKeyConstraint
from sqlalchemy.orm import relationship

from app.core.database import Base

class Category(Base):
    __tablename__ = 'category'

    id = Column(String(255), nullable=False)
    name = Column(String(255), nullable=False)
    name_vi = Column(String(255), nullable=False)
    parent_id = Column(String(255), nullable=False)
    depth = Column(Integer, nullable=False)

    # Khai báo Khóa chính kép (Composite Primary Key)
    __table_args__ = (
        PrimaryKeyConstraint('id', 'parent_id', name='category_pk'),
        # Các constraint khác như UNIQUE (name, parent_id) nếu bạn có map trong code
    )

    def __repr__(self):
        return f"<Category(id={self.id}, name='{self.name}', parent_id={self.parent_id}, level={self.depth})>"