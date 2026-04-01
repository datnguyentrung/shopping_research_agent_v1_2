from dotenv import load_dotenv
from google import genai

load_dotenv()


def list_my_models():
    # Khởi tạo client với API Key từ .env
    client = genai.Client(api_key="AIzaSyBiFeiHxt4Jm80rZLm4T9JMYcgSAvpRp60")

    print("--- Các Model bạn có thể sử dụng ---")
    # Liệt kê các model
    for model in client.models.list():
        print(f"Model Name: {model.name}")
        print(f" > Display Name: {model.display_name}")
        print(f" > Supported Actions: {model.supported_actions}\n")


if __name__ == "__main__":
    list_my_models()
