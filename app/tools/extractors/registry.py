# extractors/registry.py
import logging

from app.tools.extractors.base import BaseExtractor
from app.tools.extractors.crawl4ai_extract import Crawl4AIExtractor
from app.tools.extractors.tavily_extract import TavilyExtractor

logger = logging.getLogger(__name__)

# Thứ tự = ưu tiên
EXTRACTORS: list[type[BaseExtractor]] = [
    # ShopeeExtractor,   # Phương án 3
    # TikiExtractor,     # Phương án 3
    TavilyExtractor,   # Phương án 2
    Crawl4AIExtractor, # Phương án 1 (fallback cuối)
]

async def extract(url: str) -> dict | list | None:
    url = BaseExtractor.normalize_url(url)
    logger.info("[REGISTRY] Xử lý URL: %s", url)

    for extractor_cls in EXTRACTORS:
        if not extractor_cls.matches(url):
            continue
        try:
            result = await extractor_cls().extract(url)
            if result:  # None, [], {} đều bị skip
                logger.info("[REGISTRY] Thành công với %s", extractor_cls.__name__)
                return result
            logger.debug("[REGISTRY] %s trả về rỗng, thử tiếp...", extractor_cls.__name__)
        except Exception as e:
            logger.warning("[REGISTRY] %s lỗi: %s, thử tiếp...", extractor_cls.__name__, e)
    raise ValueError(f"Không extractor nào xử lý được: {url}")