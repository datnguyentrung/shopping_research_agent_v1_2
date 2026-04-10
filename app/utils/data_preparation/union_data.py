import os
import json

# Gom thư mục gốc vào một chỗ
DATA_DIR = r"D:\Thực tập MB\Shopping_Research_Agent_V1_2\data"

# Đường dẫn file
SHOPEE_PATH = os.path.join(DATA_DIR, "shopee_data.jsonl")
TIKI_PATH = os.path.join(DATA_DIR, "tiki_products_data.jsonl")
VERTEX_PATH = os.path.join(DATA_DIR, "vertex_data.jsonl")


def union_data(file_paths: list[str], output_path: str):
    """
    Hợp nhất nhiều file JSONL, lọc trùng theo 'key' và ghi ra file mới.
    Tối ưu hóa: Đọc/Ghi từng dòng để không bị tràn RAM.
    """
    seen_keys = set()  # Chỉ lưu danh sách các key đã gặp để tiết kiệm RAM
    written_count = 0

    print(f"🚀 Bắt đầu gộp dữ liệu vào: {output_path}...")

    # Mở file đích ở chế độ ghi ('w')
    with open(output_path, 'w', encoding='utf-8') as outfile:

        for file_path in file_paths:
            if not os.path.exists(file_path):
                print(f"⚠️ Bỏ qua file không tồn tại: {file_path}")
                continue

            print(f"📂 Đang đọc file: {os.path.basename(file_path)}")

            # Mở từng file nguồn ở chế độ đọc
            with open(file_path, 'r', encoding='utf-8') as infile:
                for line in infile:
                    line = line.strip()
                    if not line:
                        continue

                    try:
                        # Parse thử JSON để lấy key
                        raw_data = json.loads(line)
                        product_key = raw_data.get("key")

                        if not product_key:
                            continue

                        # Nếu là key mới -> Lưu vào set và ghi thẳng dòng text gốc ra file
                        if product_key not in seen_keys:
                            seen_keys.add(product_key)
                            outfile.write(line + "\n")  # Ghi dòng JSON gốc kèm ký tự xuống dòng
                            written_count += 1

                    except json.JSONDecodeError:
                        # Bỏ qua các dòng bị đứt/hỏng trong quá trình crawl
                        continue

    print(f"✅ Đã gộp thành công! Tổng số sản phẩm unique: {written_count}")


# Chạy thử hàm
if __name__ == "__main__":
    files_to_merge = [SHOPEE_PATH, TIKI_PATH]
    union_data(files_to_merge, VERTEX_PATH)