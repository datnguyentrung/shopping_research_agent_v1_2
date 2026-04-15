"""Shared LLM model fallback order used by non-ADK generation paths."""

MODELS_TO_TRY = [
    "gemini-3.1-flash-lite-preview",
    "gemini-3-flash-preview",
    "gemini-3.1-pro-preview",
    "gemini-2.5-flash",
    "gemini-3.1-pro-preview",
    "gemini-flash-latest",
]

MODELS_ZAI_TO_TRY = [
    "glm-5.1",       # ✅ xác nhận có
    "glm-4.7",       # ✅ xác nhận có
    "glm-4.6",       # ✅ xác nhận có
    "glm-4.5-air",   # ✅ xác nhận có
    "glm-4.5",       # ✅ xác nhận có
]