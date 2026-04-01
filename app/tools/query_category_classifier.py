import os

import joblib
import torch
from transformers import AutoTokenizer, AutoModelForSequenceClassification

BASE_DIR = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
MODEL_PATH = os.path.join(BASE_DIR, "model\query_category_classifier_v1\query_category_classifier")

print("⏳ Đang thức tỉnh AI Classifier, đợi chút...")

try:
    tokenizer = AutoTokenizer.from_pretrained(MODEL_PATH)
    model = AutoModelForSequenceClassification.from_pretrained(MODEL_PATH)
except Exception as e:
    print(f"❌ Lỗi tải mô hình. Bạn kiểm tra lại đường dẫn {MODEL_PATH} nhé!")
    print(f"Chi tiết: {e}")
    exit()

device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
model.to(device)

model.eval()  # Đặt model vào chế độ đánh giá (inference mode)

label_encoder_path = os.path.join(MODEL_PATH, "label_encoder.joblib")
try:
    with open(label_encoder_path, 'rb') as f:
        label_encoder = joblib.load(f)
except FileNotFoundError:
    label_encoder = None
    print("⚠️ Chú ý: Không tìm thấy file label_encoder.pkl. Sẽ trả về ID nội bộ thay vì ID gốc.")


def classify_keyword(text):
    """Hàm nhận text và trả về danh mục dự đoán cùng độ tự tin"""

    # Bước A: Tiền xử lý văn bản (Mã hóa text thành số để model hiểu)
    inputs = tokenizer(
        text,
        return_tensors="pt",  # Trả về Pytorch Tensors
        truncation=True,  # Cắt bớt nếu quá dài
        padding="max_length",  # Bù thêm số 0 nếu quá ngắn
        max_length=128  # Phải giống hệt con số lúc train
    ).to(device)

    # Bước B: Đưa vào mô hình dự đoán
    # Dùng torch.no_grad() để tắt tính toán đạo hàm -> Chạy nhanh và đỡ tốn RAM
    with torch.no_grad():
        outputs = model(**inputs)
        logits = outputs.logits

    # Bước C: Tính xác suất (phần trăm % tự tin)
    probabilities = torch.nn.functional.softmax(logits, dim=1)

    # Lấy ra class có điểm cao nhất
    confidence, predicted_class = torch.max(probabilities, dim=1)

    pred_internal_id = predicted_class.item()
    conf_score = confidence.item()

    # Bước D: Dịch ngược từ ID nội bộ ra Category ID gốc
    if label_encoder:
        # Nếu dùng sklearn.preprocessing.LabelEncoder
        final_category_id = label_encoder.inverse_transform([pred_internal_id])[0]
        final_name = model.config.id2label.get(pred_internal_id, "Unknown")
    else:
        # Cách fallback dự phòng nếu model có lưu id2label trong file config.json
        final_category_id = model.config.id2label.get(pred_internal_id, pred_internal_id)
        final_name = model.config.id2label.get(pred_internal_id, "Unknown")

    return final_category_id, final_name, conf_score


# ==========================================
# 4. CHẠY THỬ VỚI NGƯỜI DÙNG
# ==========================================
if __name__ == "__main__":
    print(f"✅ Tải thành công! Đang chạy trên: {device}")
    print("-" * 50)

    while True:
        user_input = input("\n🛒 Nhập từ khóa sản phẩm (hoặc gõ 'q' để thoát): ")

        if user_input.lower() in ['q', 'quit', 'exit']:
            print("👋 Tạm biệt!")
            break

        if not user_input.strip():
            continue

        # Gọi hàm dự đoán
        category_id, category_name ,score = classify_keyword(user_input)

        print(f"🎯 Kết quả dự đoán:")
        print(f"   - Nhãn Category ID : {category_id}")
        print(f"   - Tên danh mục: {category_name}")
        print(f"   - Độ tự tin (Score): {score:.2%}")