# file: app/tools/query_category_classifier.py
import os
import joblib
import torch
from transformers import AutoTokenizer, AutoModelForSequenceClassification

MODEL_PATH = r'D:\Thực tập MB\Shopping_Research_Agent_V1_2\models\query_category_classifier_v4\query_category_classifier'

# Khai báo các biến global nhưng chưa khởi tạo
tokenizer = None
model = None
device = None
label_encoder = None


def init_classifier_model():
    """Hàm này sẽ được gọi 1 lần duy nhất khi khởi động FastAPI"""
    global tokenizer, model, device, label_encoder

    print("⏳ Đang thức tỉnh AI Classifier, đợi chút...")

    try:
        tokenizer = AutoTokenizer.from_pretrained(MODEL_PATH)
        model = AutoModelForSequenceClassification.from_pretrained(MODEL_PATH)
    except Exception as e:
        print(f"❌ Lỗi tải mô hình. Bạn kiểm tra lại đường dẫn {MODEL_PATH} nhé!")
        print(f"Chi tiết: {e}")
        raise e  # Dừng app nếu không load được model

    device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
    model.to(device)
    model.eval()  # Đặt models vào chế độ đánh giá (inference mode)

    label_encoder_path = os.path.join(MODEL_PATH, "label_encoder.joblib")
    try:
        with open(label_encoder_path, 'rb') as f:
            label_encoder = joblib.load(f)
    except FileNotFoundError:
        label_encoder = None
        print("⚠️ Chú ý: Không tìm thấy file label_encoder.pkl. Sẽ trả về ID nội bộ thay vì ID gốc.")

    print(f"✅ Tải thành công Classifier! Đang chạy trên: {device}")


def classify_keyword_topk(text, k=3):
    """Hàm nhận text và trả về Top K danh mục dự đoán cùng độ tự tin"""
    # Đảm bảo model đã được load
    if model is None or tokenizer is None:
        raise RuntimeError("Model chưa được khởi tạo. Vui lòng kiểm tra lại quá trình startup.")

    inputs = tokenizer(
        text,
        return_tensors="pt",
        truncation=True,
        padding="max_length",
        max_length=128
    ).to(device)

    with torch.no_grad():
        outputs = model(**inputs)
        logits = outputs.logits

    probabilities = torch.nn.functional.softmax(logits, dim=1)
    top_probs, top_indices = torch.topk(probabilities, k=k, dim=1)

    results = []
    for i in range(k):
        pred_internal_id = top_indices[0][i].item()
        conf_score = top_probs[0][i].item()

        if label_encoder:
            final_category_id = label_encoder.inverse_transform([pred_internal_id])[0]
            final_name = model.config.id2label.get(pred_internal_id, "Unknown")
        else:
            final_category_id = model.config.id2label.get(pred_internal_id, pred_internal_id)
            final_name = model.config.id2label.get(pred_internal_id, "Unknown")

        results.append({
            "category_id": final_category_id,
            "category_name": final_name,
            "score": conf_score
        })

    print(f"🔍 Dự đoán Top {k} cho '{text}':")
    for rank, res in enumerate(results, 1):
        print(f"   - Top {rank}: {res['category_name']} (ID: {res['category_id']}, Score: {res['score']:.2%})")

    return results

# ==========================================
# CÁCH GỌI HÀM MỚI
# ==========================================
# user_input = "I want to buy high-quality trousers for over 1 million VND."
# top_results = classify_keyword_topk(user_input, k=2)
# for rank, res in enumerate(top_results, 1):
#     print(f"Top {rank}: {res['category_name']} ({res['score']:.2%})")


# ==========================================
# 4. CHẠY THỬ VỚI NGƯỜI DÙNG
# ==========================================
if __name__ == "__main__":
    init_classifier_model()
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
        top_results = classify_keyword_topk(user_input, k=2)

        print(f"🎯 Kết quả dự đoán:")
        for rank, res in enumerate(top_results, 1):
            category_id = res['category_id']
            category_name = res['category_name']
            score = res['score']
            print(f"   - Nhãn Category ID : {category_id}")
            print(f"   - Tên danh mục: {category_name}")
            print(f"   - Độ tự tin (Score): {score:.2%}")