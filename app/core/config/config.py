from pydantic_settings import BaseSettings, SettingsConfigDict

ENV_FILE = r'D:\Code\Python\Shopping_Research_Agent\.env'

class Settings(BaseSettings):
    PROJECT_NAME: str = "Shopping Research Agent"
    API_V1: str = "/api/v1"
    DATABASE_URL: str = "postgresql+asyncpg://root:31102005@localhost:5433/version_4"
    GOOGLE_API_KEY: str = ""
    TAVILY_API_KEY: str = ""
    VEXTER_ENGINE_ID: str = ""
    PROJECT_ID: str = ""
    GOOGLE_APPLICATION_CREDENTIALS: str = ""
    ZAI_API_KEY: str = ""
    SERPER_API_KEY: str = ""

    model_config = SettingsConfigDict(env_file=ENV_FILE, extra="ignore")

# Khởi tạo một biến settings để import dùng ở mọi nơi
settings = Settings()