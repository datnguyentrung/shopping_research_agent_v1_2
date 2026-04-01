from sqlalchemy import Column, Integer, String, Float, ForeignKey, JSON
from app.core.database import Base

class Attribute(Base):
    __tablename__ = 'attribute'

    id = Column(Integer, primary_key=True, index=True, autoincrement=True)
    name = Column(String(255), nullable=False)
    options = Column(JSON, nullable=False)  # Lưu trữ các lựa chọn dưới dạng list

    def __repr__(self):
        return f"<Attribute(id={self.id}, name='{self.name}', value='{self.value}')>"