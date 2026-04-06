import requests
import json
from app.core.config.config import settings

# 1. Dùng endpoint /search
url = "https://google.serper.dev/search"

# 2. Payload với từ khóa giao dịch trực tiếp
payload = {
  "q": "Áo len nam",
  "gl": "vn",
  "hl": "vi"
}

headers = {
  'X-API-KEY': settings.SERPER_API_KEY,
  'Content-Type': 'application/json'
}

print("Đang gọi API Serper...")
response = requests.post(url, headers=headers, json=payload)
data = response.json()

print("✅ API Serper đã trả về kết quả. Dữ liệu nhận được:")
print(json.dumps(data, ensure_ascii=False, indent=2))

# 3. Đường dẫn file JSON của bạn
file_path = r'D:\Thực tập MB\Shopping_Research_Agent_V1_2\data\serper_ouput.json'

# 4. Lưu response vào file JSON
with open(file_path, 'w', encoding='utf-8') as f:
    json.dump(data, f, ensure_ascii=False, indent=2)

print(f"✅ Đã lưu kết quả thành công vào: {file_path}")