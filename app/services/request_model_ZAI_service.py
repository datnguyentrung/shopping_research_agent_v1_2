import json
from typing import Any, AsyncGenerator

import httpx
from openai import AsyncOpenAI

from app.core.config.llm_models import MODELS_ZAI_TO_TRY  # cập nhật list model (xem bước 3)
from app.core.config.config import settings
from app.utils.load_instruction_from_file import load_instruction_from_file

# ✅ Client dùng OpenAI SDK trỏ vào Z.AI
client = AsyncOpenAI(
    api_key=settings.ZAI_API_KEY,
    base_url="https://api.z.ai/api/paas/v4/",
    timeout=httpx.Timeout(connect=10.0, read=60.0, write=10.0, pool=5.0),  # ✅ thêm
)

def _build_messages(system: str | None, user_text: str) -> list[dict]:
    messages = []
    if system:
        messages.append({"role": "system", "content": system})
    messages.append({"role": "user", "content": user_text})
    return messages


def _safe_json_loads(text: str, default: Any) -> Any:
    try:
        return json.loads(text)
    except Exception:
        return default


async def _call_with_fallback(
    messages: list[dict],
    models: list[str],
    temperature: float = 0.2,
    json_mode: bool = False,
    thinking: bool = False,
) -> str:
    """
    Gọi Z.AI với fallback qua các model.
    - json_mode=True  → response_format=json_object
    - thinking=True   → bật extended reasoning (model hỗ trợ)
    """
    extra_body = {}
    if thinking:
        extra_body["thinking"] = {"type": "enabled"}

    for model in models:
        try:
            kwargs = dict(
                model=model,
                messages=messages,
                temperature=temperature,
                stream=False,
                extra_body=extra_body or None,
            )
            if json_mode:
                kwargs["response_format"] = {"type": "json_object"}

            response = await client.chat.completions.create(**kwargs)
            return response.choices[0].message.content or ""

        except Exception as e:
            error_msg = str(e)
            if any(err in error_msg for err in [
                "503", "429", "RESOURCE_EXHAUSTED", "overloaded",
                "timed out", "timeout", "ReadTimeout", "ConnectTimeout"  # ✅ thêm vào
            ]):
                print(f"[Warning] Model '{model}' timeout/quá tải. Chuyển tiếp...")
                continue
            print(f"[Error] Lỗi từ '{model}': {error_msg}")
            raise e

    raise RuntimeError("Tất cả model fallback đều quá tải.")


# ─────────────────────────────────────────────
# Các hàm public — interface giữ nguyên như cũ
# ─────────────────────────────────────────────

async def fix_and_translate(word: str) -> dict:
    system = load_instruction_from_file("prompts/fix_and_translate.md")

    # Few-shot examples nhúng vào system prompt (vì Z.AI không có multi-turn kiểu genai)
    few_shots = """
Ví dụ:
User: tôi muốn mua áo lôn g giá tẻ
Assistant: {"vi": "Áo lông giá rẻ", "en": "Cheap fleece jacket", "intent": "specific"}

User: bên shop có bán những sản phẩm gì thế?
Assistant: {"vi": "", "en": "", "intent": "vague"}

User: hello bạn, tư vấn cho mình với
Assistant: {"vi": "", "en": "", "intent": "greeting"}
"""
    messages = [
        {"role": "system", "content": system + "\n\n" + few_shots},
        {"role": "user", "content": word},
    ]

    try:
        response = await _call_with_fallback(
            messages=messages,
            models=MODELS_ZAI_TO_TRY,
            temperature=0.1,
            json_mode=True,
        )
        return _safe_json_loads(response, {"vi": "", "en": "", "intent": "vague"})
    except Exception as e:
        print(f"fix_and_translate thất bại: {e}")
        return {"vi": "", "en": "", "intent": "vague"}


async def generate_ranking_json(prompt: str) -> list:
    messages = [{"role": "user", "content": prompt}]
    try:
        response = await _call_with_fallback(
            messages=messages,
            models=MODELS_ZAI_TO_TRY,
            temperature=0.2,
            json_mode=True,
        )
        return _safe_json_loads(response, [])
    except Exception as e:
        print(f"generate_ranking_json thất bại: {e}")
        return []


async def analyze_dislike_reason(reason: str) -> list[str]:
    system = load_instruction_from_file("prompts/analyze_dislike_reason.md")
    messages = [
        {"role": "system", "content": system},
        {"role": "user", "content": reason},
    ]
    try:
        response = await _call_with_fallback(
            messages=messages,
            models=MODELS_ZAI_TO_TRY,
            temperature=0.1,
            json_mode=True,
        )
        return _safe_json_loads(response, [])
    except Exception as e:
        print(f"analyze_dislike_reason thất bại: {e}")
        return []


async def generate_final_summary_stream(prompt: str) -> AsyncGenerator[str, None]:
    system = load_instruction_from_file("prompts/interactive_agent.md")
    messages = [
        {"role": "system", "content": system},
        {"role": "user", "content": prompt},
    ]

    for model in MODELS_ZAI_TO_TRY:
        try:
            stream = await client.chat.completions.create(
                model=model,
                messages=messages,
                temperature=0.6,
                stream=True,
                extra_body={"thinking": {"type": "enabled"}},  # reasoning mode
            )
            async for chunk in stream:
                if text := chunk.choices[0].delta.content:
                    yield text
            return

        except Exception as e:
            error_msg = str(e)
            if any(err in error_msg for err in [
                "503", "429", "RESOURCE_EXHAUSTED", "overloaded",
                "timed out", "timeout", "ReadTimeout", "ConnectTimeout"  # ✅ thêm vào
            ]):
                print(f"[Warning] Model '{model}' timeout/quá tải. Chuyển tiếp...")
                continue
            print(f"[Error] '{model}': {error_msg}")
            raise e

    yield "\n\n*Hệ thống đang quá tải, vui lòng thử lại sau.*"

# if __name__ == "__main__":
#     import asyncio
#
#     async def _main():
#         test_query = "c ó đ ồ b ộ n à o c h o b é g á i k o s h o p"
#         result = await fix_and_translate(test_query)
#
#         print(f"Input: {test_query}")
#         print(f"VI Keyword: {result.get('vi')}")
#         print(f"EN Keyword: {result.get('en')}")
#
#     asyncio.run(_main())
#
#     import asyncio
#     import httpx
#
#     async def connection():
#         try:
#             async with httpx.AsyncClient(timeout=10.0) as c:
#                 r = await c.get("https://api.z.ai/api/paas/v4/models",
#                                 headers={"Authorization": f"Bearer {settings.ZAI_API_KEY}"})
#                 print(f"✅ Status: {r.status_code}")
#                 print(r.text)
#         except Exception as e:
#             print(f"❌ Lỗi kết nối: {e}")
#
#
#     asyncio.run(connection())

if __name__ == "__main__":
    import asyncio
    import httpx

    async def debug():
        # Test 1: POST thẳng bằng httpx, không qua openai SDK
        print("=== Test 1: Raw POST ===")
        try:
            async with httpx.AsyncClient(timeout=30.0) as c:
                r = await c.post(
                    "https://api.z.ai/api/paas/v4/chat/completions",
                    headers={
                        "Authorization": f"Bearer {settings.ZAI_API_KEY}",
                        "Content-Type": "application/json",
                    },
                    json={
                        "model": "glm-5.1",
                        "messages": [{"role": "user", "content": "Hi"}],
                        "temperature": 0.5,
                        "stream": False,
                        # Không có json_mode, không có extra_body
                    }
                )
                print(f"Status: {r.status_code}")
                print(f"Response: {r.text[:500]}")
        except Exception as e:
            print(f"❌ Test 1 thất bại: {e}")

        # Test 2: Thêm json_mode
        print("\n=== Test 2: Thêm response_format json_object ===")
        try:
            async with httpx.AsyncClient(timeout=30.0) as c:
                r = await c.post(
                    "https://api.z.ai/api/paas/v4/chat/completions",
                    headers={
                        "Authorization": f"Bearer {settings.ZAI_API_KEY}",
                        "Content-Type": "application/json",
                    },
                    json={
                        "model": "glm-4.7",
                        "messages": [
                            {"role": "system", "content": "Trả lời JSON"},
                            {"role": "user", "content": "Hi"},
                        ],
                        "temperature": 0.5,
                        "stream": False,
                        "response_format": {"type": "json_object"},
                    }
                )
                print(f"Status: {r.status_code}")
                print(f"Response: {r.text[:500]}")
        except Exception as e:
            print(f"❌ Test 2 thất bại: {e}")

    asyncio.run(debug())
