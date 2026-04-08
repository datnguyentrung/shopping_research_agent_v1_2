# Lưu trữ memory (có thể dùng Redis hoặc in-memory)

import asyncio
from typing import Any, Dict, List

from cachetools import TTLCache

# Quản lý session đơn giản bằng Dictionary (Memory).
SESSION_STORE = TTLCache(maxsize=1000, ttl=3600)

def get_or_create_session(session_id: str) -> dict:
    if session_id not in SESSION_STORE:
        # Khởi tạo state mặc định cho một user mới
        SESSION_STORE[session_id] = {
            "phase": "INIT",
            "attributes": [],
            "answers": [],
            "raw_products": [],
            "pending_products": [],
            "whitelist": [],
            "blacklist": [],
            "search_task": None
        }
    return SESSION_STORE[session_id]

def clear_session(session_id: str):
    """Gọi hàm này khi user hoàn tất luồng để dọn rác RAM ngay lập tức"""
    if session_id in SESSION_STORE:
        del SESSION_STORE[session_id]