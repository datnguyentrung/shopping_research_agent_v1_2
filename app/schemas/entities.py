# Schema chuẩn hóa dữ liệu cào được (CapturedData)

from typing import Any, List, Optional, Union, Literal
from pydantic import BaseModel, ConfigDict
from pydantic.alias_generators import to_camel


# 1. Định nghĩa kiểu dữ liệu cho phân loại (màu sắc, kích thước,...)
class TierVariation(BaseModel):
    model_config = ConfigDict(populate_by_name=True, alias_generator=to_camel)  # ← thêm
    name: str  # Tên phân loại (VD: "Màu sắc", "Size")
    options: List[str]  # Các lựa chọn (VD: ["Đen", "Xanh"], ["M", "L"])

# 2. Định nghĩa thông tin cửa hàng
class ShopInfo(BaseModel):
    model_config = ConfigDict(populate_by_name=True, alias_generator=to_camel)  # ← thêm
    shop_id: Optional[str] = "Unknown"
    shop_name: Optional[str] = "Unknown"
    shop_location: Optional[str] = None  # Vị trí/Khu vực của shop

# 3. Định nghĩa Schema chính CapturedData
class CapturedData(BaseModel):
    model_config = ConfigDict(populate_by_name=True, alias_generator=to_camel)  # ← thêm
    platform: str # Tên nền tảng (VD: "shopee", "lazada", "tiki")
    product_id: Union[str, int]
    product_url: str # URL dẫn đến sản phẩm trên nền tảng
    name: str

    # -- Giá cả --
    price_current: float  # Giá bán hiện tại
    price_original: Optional[float] = None  # Giá gốc trước khi giảm
    currency: str = "VND"  # Mặc định là VND

    # -- Hình ảnh --
    main_image: str  # URL ảnh chính

    # -- Đánh giá & Bán hàng --
    rating_star: float  # Số sao đánh giá trung bình
    rating_count: int  # Tổng số lượt đánh giá
    sold_count: Optional[int] = None  # Số lượng đã bán

    # -- Cửa hàng --
    shop: Optional[ShopInfo] = None  # Chứa object ShopInfo ở trên

    # -- Phân loại hàng --
    tier_variations: List[TierVariation] = []  # Danh sách các biến thể

class ProductList(BaseModel):
    model_config = ConfigDict(populate_by_name=True, alias_generator=to_camel)  # ← thêm
    products: List[CapturedData]  # Danh sách sản phẩm đã trích xuất


class MessageChunk(BaseModel):
    model_config = ConfigDict(populate_by_name=True, alias_generator=to_camel)  # ← thêm
    type: Literal["message"] = "message"
    content: str


class A2UIChunk(BaseModel):
    model_config = ConfigDict(populate_by_name=True, alias_generator=to_camel)  # ← thêm
    type: Literal["a2ui"] = "a2ui"
    a2ui: dict[str, Any]


class DoneChunk(BaseModel):
    model_config = ConfigDict(populate_by_name=True, alias_generator=to_camel)  # ← thêm
    type: Literal["done"] = "done"


class ErrorChunk(BaseModel):
    model_config = ConfigDict(populate_by_name=True, alias_generator=to_camel)  # ← thêm
    type: Literal["error"] = "error"
    error: str


ChatStreamChunk = Union[MessageChunk, A2UIChunk, DoneChunk, ErrorChunk]
