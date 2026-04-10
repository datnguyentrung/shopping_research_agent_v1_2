import json

# 1. Đọc dữ liệu từ file JSON
file_path = r'/data/vertex_product.jsonl'

try:
    with open(file_path, 'r', encoding='utf-8') as file:
        data = json.load(file)
except FileNotFoundError:
    print(f"❌ Không tìm thấy file tại đường dẫn: {file_path}")
    exit()

# 2. Trích xuất mảng 'shopping' (chứa băng chuyền quảng cáo sản phẩm)
shopping_results = data.get("shopping", [])

if not shopping_results:
    print("⚠️ Không tìm thấy mảng 'shopping'. Hãy kiểm tra lại file JSON xem Google có trả về băng chuyền sản phẩm không!")
else:
    # Cắt lấy 10 sản phẩm đầu tiên
    top_10 = shopping_results[:10]
    print(f"--- ĐANG HIỂN THỊ {len(top_10)} SẢN PHẨM CÓ LINK THẬT ---\n")

    for index, item in enumerate(top_10, start=1):
        title = item.get("title", "Không có tiêu đề")
        source = item.get("source", "Không rõ nguồn")
        price = item.get("price", "Đang cập nhật")
        link = item.get("link", "Không có link")
        image_url = item.get("imageUrl", "Không có ảnh")

        print(f"Sản phẩm #{index}:")
        print(f"  - Title  : {title}")
        print(f"  - Source : {source}")
        print(f"  - Price  : {price}")

        # Rút gọn ảnh base64 nếu có
        if image_url.startswith("data:image"):
            print(f"  - Image  : {image_url[:50]}... (Đã rút gọn base64)")
        else:
            print(f"  - Image  : {image_url}")

        print(f"  - Link   : {link}")
        print("-" * 60)