import gzip
import json
import os

# Xác định đường dẫn tuyệt đối tới file training_data.csv trong thư mục data
file_path = r'D:\Thực tập MB\Shopping_Research_Agent_V1_2\data\meta_Clothing_Shoes_and_Jewelry.json.gz'

with gzip.open(file_path, 'rt', encoding='utf-8') as f:
    for line in f:
        first_entry = json.loads(line)
        print(json.dumps(first_entry, indent=2))
        break  # Chỉ đọc 1 dòng rồi dừng để bảo vệ RAM