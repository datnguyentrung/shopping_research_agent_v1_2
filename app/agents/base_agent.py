# Class base chứa cấu hình chung (models, temperature...)
import os

from google.adk.agents import LlmAgent

from app.core.config.config import settings
from app.tools.query_category_classifier import classify_keyword
from app.utils.load_instruction_from_file import load_instruction_from_file

# Override môi trường cục bộ để LiteLLM trỏ luồng API sang Z.AI
# os.environ["OPENAI_API_BASE"] = "https://api.z.ai/api/paas/v4/"
# os.environ["OPENAI_API_KEY"] = settings.ZAI_API_KEY

interactive_agent = LlmAgent(
    name="InteractiveAgent",
    model="gemini-3.1-flash-lite-preview", # model openai/glm-5 nếu dùng Z.AI
    instruction=load_instruction_from_file("prompts/interactive_agent.md"),
)