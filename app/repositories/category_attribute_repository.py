from __future__ import annotations

from typing import List, Set, Optional
from sqlalchemy import select, func
from sqlalchemy.orm import aliased

from sqlalchemy.orm import Session
from sqlalchemy.testing import db

from app.core.database import SessionLocal
from app.models.category_attribute import CategoryAttribute
from app.repositories.base import BaseRepository
from app.models import Category, Attribute


class CategoryAttributeRepository(BaseRepository[CategoryAttribute]):
    """Repository for CategoryAttribute models (join table)."""

    def __init__(self, db: Session):
        super().__init__(db, CategoryAttribute)

    def list_by_category(self, category_id: int) -> list[type[CategoryAttribute]]:
        return (
            self.db.query(CategoryAttribute)
            .filter(CategoryAttribute.category_id == category_id)
            .all()
        )

    def list_by_attribute(self, attribute_id: int) -> list[type[CategoryAttribute]]:
        return (
            self.db.query(CategoryAttribute)
            .filter(CategoryAttribute.attribute_id == attribute_id)
            .all()
        )

    def get_pair(self, category_id: int, attribute_id: int) -> Optional[CategoryAttribute]:
        return (
            self.db.query(CategoryAttribute)
            .filter(
                CategoryAttribute.category_id == category_id,
                CategoryAttribute.attribute_id == attribute_id,
            )
            .first()
        )

    def get_inherited_attributes_cte(self, category_ids: List[str]) -> List[type[Attribute]]:
        """
        Lấy toàn bộ model Attribute của một list categories và các category cha.
        Đã tối ưu: Dùng Subquery để tính MAX(is_core) kết hợp với Index (category_id, is_core).
        """
        if not category_ids:
            return []

        # 1. Base Query: Lấy các category ban đầu
        base_q = (
            select(Category.id, Category.parent_id)
            .where(Category.id.in_(category_ids))
            .cte(name="category_hierarchy", recursive=True)
        )

        # 2. Recursive Part: Alias model Category để tự join lên cha
        parent_alias = aliased(Category)
        hierarchy_q = base_q.union_all(
            select(parent_alias.id, parent_alias.parent_id)
            .where(parent_alias.id == base_q.c.parent_id)
        )

        # 3. TỐI ƯU MỚI: Gom nhóm và lấy Max(is_core) TỪ BẢNG CategoryAttribute TRƯỚC
        # Database sẽ Scan index idx_category_core cực nhanh ở bước này (Vì chỉ xử lý ID và Boolean)
        attr_subq = (
            select(
                CategoryAttribute.attribute_id,
                func.max(CategoryAttribute.is_core).label("max_core")
            )
            .join(hierarchy_q, CategoryAttribute.category_id == hierarchy_q.c.id)
            .group_by(CategoryAttribute.attribute_id)
            .subquery()
        )

        # 4. Query cuối: Chỉ việc Join 1-1 bảng Attribute với subquery đã gom nhóm
        # Lúc này attr_subq chỉ chứa các attribute_id DUY NHẤT -> Không cần tốn kém group_by ở bảng Attribute nữa!
        final_q = (
            select(Attribute)
            .join(attr_subq, Attribute.id == attr_subq.c.attribute_id)
            .order_by(attr_subq.c.max_core.desc())
        )

        # Trả về list các object Attribute
        result = self.db.execute(final_q).scalars().all()
        return list(result)

if __name__ == "__main__":
    db = SessionLocal()
    cateogory_repo = CategoryAttributeRepository(db)
    result = attributes = cateogory_repo.get_inherited_attributes_cte(['1045830', '2419343011'])
    print("🚀 Kết quả Attribute kế thừa:")
    print(result)

