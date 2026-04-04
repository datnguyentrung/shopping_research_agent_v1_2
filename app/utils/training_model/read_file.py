import gzip
import json
import os

# Xác định đường dẫn tuyệt đối tới file training_data.csv trong thư mục data
file_path = r'D:\Thực tập MB\Shopping_Research_Agent_V1_2\data\meta_Clothing_Shoes_and_Jewelry.json.gz'

def read_file():
    count = 10
    with gzip.open(file_path, 'rt', encoding='utf-8') as f:
        for line in f:
            first_entry = json.loads(line)
            print(json.dumps(first_entry, indent=2))
            count -= 1
            if count == 0:
                break  # Chỉ đọc 1 dòng rồi dừng để bảo vệ RAM

def read_csv():
    with open(r'D:\Thực tập MB\Shopping_Research_Agent_V1_2\data\training_data.csv', 'r', encoding='utf-8') as f:
        lines = f.readlines()
        print(f"Sự thật là file có: {len(lines):,} dòng")

if __name__ == "__main__":
    read_file()