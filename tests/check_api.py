from dotenv import load_dotenv
import os
from zai import ZaiClient

from app.core.config.config import settings

def check_api():
    try:
        # 2. Khởi tạo ZaiClient chuẩn theo Docs
        client = ZaiClient(api_key=settings.ZAI_API_KEY)

        print("Đang gửi request lên Z.AI...")

        # 3. Tạo request gọi model glm-5
        response = client.chat.completions.create(
            model="glm-5",
            messages=[
                {
                    "role": "user",
                    "content": "Xin chào, hãy giới thiệu ngắn gọn về bạn."
                }
            ],
            stream=False  # Để False cho dễ test lần đầu
        )

        # 4. In kết quả trả về
        print("\n✅ THÀNH CÔNG! Phản hồi từ AI:")
        print(response.choices[0].message.content)

    except Exception as e:
        # Bắt mọi lỗi từ server Z.AI và in ra
        print("\n❌ LỖI RỒI:")
        print(e)

if __name__ == "__main__":
    check_api()