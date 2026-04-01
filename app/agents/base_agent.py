# Class base chứa cấu hình chung (model, temperature...)
from google.adk.agents import LlmAgent

from app.utils.load_instruction_from_file import load_instruction_from_file

interactive_agent = LlmAgent(
    name="InteractiveAgent",
    model="gemini-3.1-flash-lite-preview",
    instruction=load_instruction_from_file("prompts/interactive_agent.md"),
)