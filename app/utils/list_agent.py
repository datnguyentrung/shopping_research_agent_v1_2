from dotenv import load_dotenv
from google import genai

from app.core.config.config import settings

load_dotenv()


def list_my_models():
    # Khởi tạo client với API Key từ .env
    client = genai.Client(api_key=settings.GOOGLE_API_KEY)

    print("--- Các Model bạn có thể sử dụng ---")
    # Liệt kê các models
    for model in client.models.list():
        print(f"Model Name: {model.name}")
        print(f" > Display Name: {model.display_name}")
        print(f" > Supported Actions: {model.supported_actions}\n")


if __name__ == "__main__":
    list_my_models()
