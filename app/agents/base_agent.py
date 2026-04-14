# Class base chứa cấu hình chung (models, temperature...)
import os

from google.adk.agents import LlmAgent

from app.core.config.config import settings
from app.utils.load_instruction_from_file import load_instruction_from_file

# Override môi trường cục bộ để LiteLLM trỏ luồng API sang Z.AI
# os.environ["OPENAI_API_BASE"] = "https://api.z.ai/api/paas/v4/"
# os.environ["OPENAI_API_KEY"] = settings.ZAI_API_KEY

MODELS_TO_TRY = [
    "gemini-3-flash-preview",        # Fallback 1
    "gemini-3.1-flash-lite-preview", # Primary model
    "gemini-2.5-flash",              # Fallback 2
    "gemini-3.1-pro-preview",
    "gemini-flash-latest"            # Fallback 3
]

interactive_agent = LlmAgent(
    name="InteractiveAgent",
    model="gemini-3.1-flash-lite-preview", # model glm-5.1 nếu dùng Z.AI
    instruction=load_instruction_from_file("prompts/interactive_agent.md"),
)

ranking_agent = LlmAgent(
    name="RankingAgent",
    model="gemini-3.1-flash-lite-preview",  # Model nhỏ, siêu tốc độ
    instruction="""
    Bạn là một công cụ AI xử lý dữ liệu ngầm (Backend Data Processor).
    NHIỆM VỤ CỦA BẠN: Sắp xếp mức độ ưu tiên của các sản phẩm dựa trên nhu cầu của khách hàng.

    RÀNG BUỘC CỰC KỲ QUAN TRỌNG:
    - Bạn KHÔNG được phép giao tiếp với người dùng.
    - Bạn KHÔNG được dùng Markdown, KHÔNG dùng bảng biểu.
    - Kết quả trả về của bạn TUYỆT ĐỐI CHỈ LÀ MỘT MẢNG JSON HỢP LỆ chứa các chuỗi ID sản phẩm.
    - Đừng thêm bất kỳ ký tự nào như ```json hay ``` ở đầu/cuối.
    - Ví dụ đầu ra mong muốn: ["id_1", "id_2", "id_3"]
    """
)

translation_agent = LlmAgent(
    name="TranslationAgent",
    model="gemini-3.1-flash-lite-preview", # Dùng Flash-Lite cho tốc độ chớp nhoáng
    instruction=load_instruction_from_file("prompts/translate_and_fix.md"),
)



