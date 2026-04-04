# extractors/base.py
import re
from abc import ABC, abstractmethod

class BaseExtractor(ABC):
    """Mỗi extractor đăng ký domain nó xử lý"""
    domains: list[str] = []  # Override ở subclass

    @abstractmethod
    async def extract(self, url: str) -> dict | list | None:
        pass

    @classmethod
    def matches(cls, url: str) -> bool:
        return any(d in url for d in cls.domains)

    @staticmethod
    def normalize_url(url: str) -> str:
        """Đảm bảo URL luôn có scheme. Không có https:// → thêm vào."""
        url = url.strip()
        if url and not re.match(r'^https?://', url):
            url = 'https://' + url
        return url