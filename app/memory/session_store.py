# Lưu trữ memory (có thể dùng Redis hoặc in-memory)

import asyncio
from typing import Any, Dict, List

# Quản lý session đơn giản bằng Dictionary (Memory).
# Nếu sau này có nhiều user thực tế, bạn có thể chuyển sang Redis.
session_store: Dict[str, Dict[str, Any]] = {}

def get_or_create_session(session_id: str) -> Dict[str, Any]:
    if session_id not in session_store:
        session_store[session_id] = {
            "phase": "INIT", # INIT -> QUESTIONNAIRE -> PRODUCT_SWIPE -> DONE
            "search_task": None, # Chứa asyncio.Task của việc tìm kiếm ngầm
            "attributes": [], # Danh sách câu hỏi lấy từ Database
            "answers": {}, # Câu trả lời của user
            "raw_products": [], # Sản phẩm cào được từ Serper + Vertex
            "pending_products": [], # Sản phẩm chờ được quẹt
            "whitelist": [], # Sản phẩm User Thích
            "blacklist": [] # Sản phẩm User Bỏ qua
        }
    return session_store[session_id]