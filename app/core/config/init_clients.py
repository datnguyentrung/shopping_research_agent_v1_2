import os
from pathlib import Path

from dotenv import load_dotenv
from tavily import TavilyClient

PROJECT_ROOT = Path(__file__).resolve().parents[3]
ENV_FILE = PROJECT_ROOT / ".env"

# Always load env from project root, independent from current working directory.
load_dotenv(dotenv_path=ENV_FILE, override=False)

tavily_client = TavilyClient(api_key=os.getenv("TAVILY_API_KEY"))


def bootstrap_api_env() -> str | None:
    """Load env and normalize Google credentials path for all entry points."""
    load_dotenv(dotenv_path=ENV_FILE, override=False)

    api_key = os.getenv("GOOGLE_API_KEY") or os.getenv("GEMINI_API_KEY")
    if api_key and not os.getenv("GOOGLE_API_KEY"):
        os.environ["GOOGLE_API_KEY"] = api_key

    credentials = os.getenv("GOOGLE_APPLICATION_CREDENTIALS")
    if not credentials:
        raise ValueError("Thieu GOOGLE_APPLICATION_CREDENTIALS trong file .env")

    credentials_path = Path(credentials)
    if not credentials_path.is_absolute():
        credentials_path = (PROJECT_ROOT / credentials_path).resolve()

    if not credentials_path.exists():
        raise ValueError(
            f"Khong tim thay file credentials: {credentials_path} (cwd={Path.cwd()})"
        )

    os.environ["GOOGLE_APPLICATION_CREDENTIALS"] = str(credentials_path)

    return os.getenv("GOOGLE_API_KEY")


def ensure_api_key_configured() -> str:
    """Return configured API key or raise a clear startup error."""
    api_key = bootstrap_api_env()
    if not api_key:
        raise RuntimeError(
            "Missing Gemini API key. Set GOOGLE_API_KEY (or GEMINI_API_KEY) in .env or your shell."
        )
    return api_key


PROJECT_ID = os.getenv("PROJECT_ID", "default_project_id")
ENGINE_ID = os.getenv("ENGINE_ID") or os.getenv("VEXTER_ENGINE_ID", "default_engine_id")
GOOGLE_CREDENTIALS = os.getenv("GOOGLE_APPLICATION_CREDENTIALS")