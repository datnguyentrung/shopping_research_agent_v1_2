# Schema chuẩn hóa dữ liệu cào được (CapturedData)

from typing import Any, List, Optional, Union, Literal
from pydantic import BaseModel


# 1. Định nghĩa kiểu dữ liệu cho phân loại (màu sắc, kích thước,...)
class TierVariation(BaseModel):
    name: str  # Tên phân loại (VD: "Màu sắc", "Size")
    options: List[str]  # Các lựa chọn (VD: ["Đen", "Xanh"], ["M", "L"])

# 2. Định nghĩa thông tin cửa hàng
class ShopInfo(BaseModel):
    shop_id: Union[str, int]  # ID của shop (hỗ trợ cả dạng số và chuỗi)
    shop_name: str  # Tên shop
    shop_location: Optional[str] = None  # Vị trí/Khu vực của shop


# 3. Định nghĩa Schema chính CapturedData
class CapturedData(BaseModel):
    platform: str # Tên nền tảng (VD: "shopee", "lazada", "tiki")
    product_id: Union[str, int]
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
    shop: ShopInfo  # Chứa object ShopInfo ở trên

    # -- Phân loại hàng --
    tier_variations: List[TierVariation] = []  # Danh sách các biến thể

class ProductList(BaseModel):
    products: List[CapturedData]  # Danh sách sản phẩm đã trích xuất


class MessageChunk(BaseModel):
    type: Literal["message"] = "message"
    content: str


class A2UIChunk(BaseModel):
    type: Literal["a2ui"] = "a2ui"
    a2ui: dict[str, Any]


class DoneChunk(BaseModel):
    type: Literal["done"] = "done"


class ErrorChunk(BaseModel):
    type: Literal["error"] = "error"
    error: str


ChatStreamChunk = Union[MessageChunk, A2UIChunk, DoneChunk, ErrorChunk]
