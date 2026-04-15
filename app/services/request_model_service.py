import json
from typing import Any
from google import genai
from google.genai import types

from app.core.config.llm_models import MODELS_TO_TRY
from app.core.config.config import settings
from app.utils.load_instruction_from_file import load_instruction_from_file

client = genai.Client(
    api_key=settings.GOOGLE_API_KEY
)


def _build_user_contents(text: str) -> list[types.Content]:
    return [types.Content(role="user", parts=[types.Part.from_text(text=text)])]


def _safe_json_loads(response: Any, default: Any) -> Any:
    text_payload = ""
    if isinstance(response, str):
        text_payload = response
    elif response and getattr(response, "text", None):
        text_payload = response.text

    if text_payload:
        return json.loads(text_payload)
    return default


async def generate_with_fallback_async(
    client_instance: genai.Client,
    models: list[str],
    contents: list[types.Content],
    config: types.GenerateContentConfig
) -> str:
    """
    Ham goi API bat dong bo (Async) co che thu lai (fallback).
    """
    for model in models:
        try:
            chunks: list[str] = []
            stream = await client_instance.aio.models.generate_content_stream(
                model=model,
                contents=contents,
                config=config,
            )
            async for chunk in stream:
                if text := getattr(chunk, "text", None):
                    chunks.append(text)

            return "".join(chunks)

        except Exception as e:
            error_msg = str(e)

            # IN RA LỖI CHI TIẾT ĐỂ DEBUG
            print(f"-> [Chi tiết lỗi của {model}]: {error_msg}")

            if any(err in error_msg for err in ["503", "UNAVAILABLE", "529", "429", "RESOURCE_EXHAUSTED"]):
                print(f"[Warning] Model '{model}' loi (Qua tai/Het Quota). Dang chuyen sang model tiep theo...")
                continue
            print(f"[Error] Loi nghiem trong tu '{model}': {error_msg}")
            raise e

    raise RuntimeError("Tat ca cac model fallback deu qua tai.")


async def fix_and_translate(word: str) -> dict:
    system_instruction = load_instruction_from_file("prompts/fix_and_translate.md")

    contents = [
        types.Content(role="user", parts=[types.Part.from_text(text="tôi muốn mua áo lôn g giá tẻ")]),
        types.Content(role="model", parts=[
            types.Part.from_text(text='{"vi": "Áo lông giá rẻ", "en": "Cheap fleece jacket", "intent": "specific"}')]),
        types.Content(role="user", parts=[types.Part.from_text(
            text="c o' c a' i q u a n j e a n r a c h g o i n a m n a o m a u x a n h d d a m g i a r e k o")]),
        types.Content(role="model", parts=[types.Part.from_text(
            text='{"vi": "Quần jean nam rách gối xanh đậm giá rẻ", "en": "Cheap men\'s distressed dark blue jeans", "intent": "specific"}')]),
        types.Content(role="user", parts=[
            types.Part.from_text(text="tìm giúp em đôi s n e a k e r n i k e a i r f o r c e s i z e 4 2")]),
        types.Content(role="model", parts=[types.Part.from_text(
            text='{"vi": "Giày sneaker Nike Air Force size 42", "en": "Size 42 Nike Air Force sneakers", "intent": "specific"}')]),
        types.Content(role="user", parts=[types.Part.from_text(
            text="I a m l o o k i n g f o r b a b y b o y s \' b l o o m e r s , d i a p e r c o v e r s & u n d e r w e a r")]),
        types.Content(role="model", parts=[types.Part.from_text(
            text='{"vi": "Quần đùi, bọc tã và đồ lót bé trai", "en": "Baby boys\' bloomers, diaper covers and underwear", "intent": "specific"}')]),
        types.Content(role="user", parts=[types.Part.from_text(text="tôi muốn tìm ào phông cho nam dẹp")]),
        types.Content(role="model", parts=[types.Part.from_text(
            text='{"vi": "Áo phông nam đẹp", "en": "Beautiful men\'s t-shirt", "intent": "specific"}')]),
        types.Content(role="user", parts=[types.Part.from_text(text="bên shop có bán những sản phẩm gì thế?")]),
        types.Content(role="model", parts=[types.Part.from_text(text='{"vi": "", "en": "", "intent": "vague"}')]),
        types.Content(role="user", parts=[types.Part.from_text(text="hello bạn, tư vấn cho mình với")]),
        types.Content(role="model", parts=[types.Part.from_text(text='{"vi": "", "en": "", "intent": "greeting"}')]),
        types.Content(role="user", parts=[types.Part.from_text(text="sản phẩm")]),
        types.Content(role="model", parts=[types.Part.from_text(text='{"vi": "", "en": "", "intent": "vague"}')]),
        types.Content(role="user", parts=[types.Part.from_text(text=word)]),
    ]

    generate_content_config = types.GenerateContentConfig(
        system_instruction=system_instruction,
        # thinking_config=types.ThinkingConfig(
        #     thinking_level=types.ThinkingLevel.LOW,
        # ),
        temperature=0.1,
        response_mime_type="application/json",
        response_schema=genai.types.Schema(
            type=genai.types.Type.OBJECT,
            required=["vi", "en"],
            properties={
                "vi": genai.types.Schema(
                    type=genai.types.Type.STRING,
                    description="Từ khóa tìm kiếm rút gọn bằng Tiếng Việt"
                ),
                "en": genai.types.Schema(
                    type=genai.types.Type.STRING,
                    description="Từ khóa tìm kiếm chuẩn hóa bằng Tiếng Anh"
                ),
                "intent": genai.types.Schema(
                    type=genai.types.Type.STRING,
                    description="Phân loại câu hỏi của người dùng: 'specific' (đã nêu rõ tên sản phẩm), 'vague' (hỏi chung chung, thăm dò, ví dụ: 'có sản phẩm gì'), 'greeting' (câu chào hỏi)."
                )
            },
        ),
    )

    try:
        response = await generate_with_fallback_async(
            client_instance=client,
            models=MODELS_TO_TRY,
            contents=contents,
            config=generate_content_config,
        )
        return _safe_json_loads(response, {"vi": "", "en": ""})

    except Exception as e:
        print(f"Qua trinh trich xuat that bai: {e}")
        return {"vi": "", "en": ""}


async def generate_ranking_json(prompt: str) -> list:
    """
    Ham Ranking duoc cau hinh Schema tra ve MANG (ARRAY) cac id san pham da duoc AI cham diem.
    """
    try:
        contents = _build_user_contents(prompt)

        generate_content_config = types.GenerateContentConfig(
            # thinking_config=types.ThinkingConfig(
            #     thinking_level=types.ThinkingLevel.LOW,
            # ),
            temperature=0.2,
            response_mime_type="application/json",
            response_schema=genai.types.Schema(
                type=genai.types.Type.ARRAY,
                items=genai.types.Schema(
                    type=genai.types.Type.OBJECT,
                    properties={
                        "product_id": genai.types.Schema(type=genai.types.Type.STRING),
                        "score": genai.types.Schema(type=genai.types.Type.INTEGER, description="Diem danh gia tu 0-100"),
                    },
                    required=["product_id", "score"]
                )
            ),
        )

        response = await generate_with_fallback_async(
            client_instance=client,
            models=MODELS_TO_TRY,
            contents=contents,
            config=generate_content_config,
        )

        return _safe_json_loads(response, [])

    except Exception as e:
        print(f"[Runtime] Loi khi generate_ranking_json: {e}")
        return []


async def analyze_dislike_reason(reason: str) -> list[str]:
    """
    Ham nay nhan ly do khach hang khong thich mot san pham va tra ve danh sach tu khoa lien quan.
    """
    system_instruction = load_instruction_from_file("prompts/analyze_dislike_reason.md")

    contents = _build_user_contents(reason)

    generate_content_config = types.GenerateContentConfig(
        system_instruction=system_instruction,
        # thinking_config=types.ThinkingConfig(
        #     thinking_level=types.ThinkingLevel.LOW,
        # ),
        temperature=0.1,
        response_mime_type="application/json",
        response_schema=genai.types.Schema(
            type=genai.types.Type.ARRAY,
            items=genai.types.Schema(type=genai.types.Type.STRING)
        )
    )

    try:
        response = await generate_with_fallback_async(
            client_instance=client,
            models=MODELS_TO_TRY,
            contents=contents,
            config=generate_content_config,
        )

        return _safe_json_loads(response, [])

    except Exception as e:
        print(f"Qua trinh phan tich ly do khong thich that bai: {e}")
        return []

async def generate_final_summary_stream(prompt: str):
    """
    Async generator: stream Markdown report using genai.Client with model fallback.
    Used by final_summary.py and adk_client.py (replaces ADK Runner).
    """
    system_instruction = load_instruction_from_file("prompts/interactive_agent.md")
    contents = _build_user_contents(prompt)

    config = types.GenerateContentConfig(
        system_instruction=system_instruction,
        # thinking_config=types.ThinkingConfig(
        #     thinking_level=types.ThinkingLevel.HIGH,
        # ),
        temperature=0.6,
    )

    for model in MODELS_TO_TRY:
        try:
            stream = await client.aio.models.generate_content_stream(
                model=model,
                contents=contents,
                config=config,
            )
            async for chunk in stream:
                if text := getattr(chunk, "text", None):
                    yield text
            return  # success — exit generator

        except Exception as e:
            error_msg = str(e)

            # IN RA LỖI CHI TIẾT ĐỂ DEBUG
            print(f"-> [Chi tiết lỗi của {model}]: {error_msg}")

            if any(err in error_msg for err in ["503", "UNAVAILABLE", "529", "429", "RESOURCE_EXHAUSTED"]):
                print(f"[Warning] Model '{model}' loi (Qua tai/Het Quota). Dang chuyen sang model tiep theo...")
                continue
            print(f"[Error] Loi nghiem trong tu '{model}': {error_msg}")
            raise e

    # All models failed
    yield "\n\n*Hệ thống đang quá tải, không thể tạo báo cáo tóm tắt lúc này. Bạn vui lòng xem lại danh sách ở trên nhé!*"


if __name__ == "__main__":
    import asyncio

    async def _main():
        test_query = "c ó đ ồ b ộ n à o c h o b é g á i k o s h o p"
        result = await fix_and_translate(test_query)

        print(f"Input: {test_query}")
        print(f"VI Keyword: {result.get('vi')}")
        print(f"EN Keyword: {result.get('en')}")

    asyncio.run(_main())
