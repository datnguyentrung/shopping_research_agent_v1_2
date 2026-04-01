"""
train_model.py
==============
Fine-tune RoBERTa-base từ đầu cho bài toán phân loại danh mục sản phẩm.
Dùng với data mới từ Amazon metadata (product title → category).

Cải tiến so với v1:
  1. Train từ roberta-base sạch (không dùng lại v1 đã nhiễm review text)
  2. Stratified split đảm bảo phân phối nhãn đồng đều
  3. Dynamic class weights — chỉ bật nếu imbalance ratio > ngưỡng
  4. Early Stopping + load_best_model_at_end
  5. LR warmup (linear) + cosine decay
  6. Gradient Accumulation giả lập batch lớn
  7. Metrics: accuracy + F1-macro + F1-weighted + per-class F1 log
  8. Lưu metadata training để track experiment
"""

import os
import json
import joblib

import numpy as np
import pandas as pd
import torch
from sklearn.metrics import (
    accuracy_score, f1_score, classification_report
)
from sklearn.model_selection import train_test_split
from sklearn.preprocessing import LabelEncoder
from sklearn.utils.class_weight import compute_class_weight
from torch.nn import CrossEntropyLoss
from transformers import (
    AutoModelForSequenceClassification,
    AutoTokenizer,
    EarlyStoppingCallback,
    Trainer,
    TrainingArguments,
)

# ─────────────────────────────────────────────
# CẤU HÌNH
# ─────────────────────────────────────────────
MODEL_DIR      = r'D:\Thực tập MB\Shopping_Research_Agent_V1_2\models\query_category_classifier_v2'

CSV_PATH       = r'D:\Thực tập MB\Shopping_Research_Agent_V1_2\data\cleaned_training_data.csv'
OUTPUT_MODEL   = os.path.join(MODEL_DIR, 'query_category_classifier')
RESULTS_DIR    = os.path.join(MODEL_DIR, 'training_results')
LOG_DIR        = os.path.join(MODEL_DIR, 'logs')

os.makedirs(OUTPUT_MODEL, exist_ok=True)
os.makedirs(RESULTS_DIR,  exist_ok=True)
os.makedirs(LOG_DIR,      exist_ok=True)

# Model — luôn dùng roberta-base (train sạch từ đầu)
PRETRAINED_MODEL = "roberta-base"

# Hyperparams
PER_DEVICE_BATCH = 16     # roberta-base + 8GB VRAM
GRAD_ACCUM_STEPS = 2      # effective batch = 32
MAX_EPOCHS       = 10
LEARNING_RATE    = 3e-5   # standard cho fine-tune từ pretrained
WARMUP_RATIO     = 0.06   # ~6% đầu linear warmup
MAX_LENGTH       = 64     # title ngắn, 64 đủ — nhanh hơn 128 đáng kể

# Class weights — tự động bật nếu imbalance ratio > ngưỡng
AUTO_CLASS_WEIGHT_THRESHOLD = 10.0   # ratio > 10x thì bật

# Early stopping
EARLY_STOP_PATIENCE = 3

# ─────────────────────────────────────────────
# 1. LOAD DATA
# ─────────────────────────────────────────────
print("=" * 55)
print("  FINE-TUNE RoBERTa — Product Category Classifier v2")
print("=" * 55)

print(f"\n📂 Tải data: {CSV_PATH}")
df = pd.read_csv(CSV_PATH, dtype={'category_id': str})
df = df[["search_query", "category_id", "category_name"]].dropna()
print(f"   Tổng mẫu: {len(df):,} | Số nhãn: {df['category_id'].nunique()}")

# Kiểm tra imbalance
counts = df["category_id"].value_counts()
imbalance_ratio = counts.max() / counts.min()
print(f"   Imbalance ratio: {imbalance_ratio:.1f}x")

USE_CLASS_WEIGHTS = imbalance_ratio > AUTO_CLASS_WEIGHT_THRESHOLD
print(f"   Class weights: {'ON (auto)' if USE_CLASS_WEIGHTS else 'OFF'}")

# ─────────────────────────────────────────────
# 2. LABEL ENCODING
# ─────────────────────────────────────────────
label_encoder = LabelEncoder()
df["label"] = label_encoder.fit_transform(df["category_id"])
num_labels = len(label_encoder.classes_)

# Map id2label / label2id (dùng category_name thay vì ID thô)
cat_name_map = (
    df.drop_duplicates("category_id")
      .set_index("category_id")["category_name"]
      .to_dict()
)
id2label = {
    i: cat_name_map.get(label_encoder.classes_[i], str(label_encoder.classes_[i]))
    for i in range(num_labels)
}
label2id = {v: k for k, v in id2label.items()}

texts  = df["search_query"].tolist()
labels = df["label"].tolist()

# ─────────────────────────────────────────────
# 3. STRATIFIED SPLIT
# ─────────────────────────────────────────────
X_train, X_temp, y_train, y_temp = train_test_split(
    texts, labels, test_size=0.2, random_state=42, stratify=labels
)
X_val, X_test, y_val, y_test = train_test_split(
    X_temp, y_temp, test_size=0.5, random_state=42, stratify=y_temp
)
print(f"\n   Train: {len(X_train):,} | Val: {len(X_val):,} | Test: {len(X_test):,}")

# ─────────────────────────────────────────────
# 4. TOKENIZATION
# ─────────────────────────────────────────────
print(f"\n🔤 Tải tokenizer: {PRETRAINED_MODEL}")
tokenizer = AutoTokenizer.from_pretrained(PRETRAINED_MODEL)

def tokenize(texts_list):
    return tokenizer(
        texts_list,
        truncation=True,
        padding=True,
        max_length=MAX_LENGTH,
    )

print("   Tokenizing train...")
train_encodings = tokenize(X_train)
print("   Tokenizing val...")
val_encodings   = tokenize(X_val)
print("   Tokenizing test...")
test_encodings  = tokenize(X_test)
print("   ✓ Hoàn tất tokenization")

# ─────────────────────────────────────────────
# 5. PYTORCH DATASET
# ─────────────────────────────────────────────
class ShoppingDataset(torch.utils.data.Dataset):
    def __init__(self, encodings, labels):
        self.encodings = encodings
        self.labels    = labels

    def __getitem__(self, idx):
        item = {k: torch.tensor(v[idx]) for k, v in self.encodings.items()}
        item["labels"] = torch.tensor(self.labels[idx])
        return item

    def __len__(self):
        return len(self.labels)

train_dataset = ShoppingDataset(train_encodings, y_train)
val_dataset   = ShoppingDataset(val_encodings,   y_val)
test_dataset  = ShoppingDataset(test_encodings,  y_test)

# ─────────────────────────────────────────────
# 6. MODEL
# ─────────────────────────────────────────────
print(f"\n🤖 Khởi tạo {PRETRAINED_MODEL} ({num_labels} nhãn)...")
model = AutoModelForSequenceClassification.from_pretrained(
    PRETRAINED_MODEL,
    num_labels=num_labels,
    id2label=id2label,
    label2id=label2id,
)

# ─────────────────────────────────────────────
# 7. CLASS WEIGHTS
# ─────────────────────────────────────────────
device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
print(f"   Device: {device}")

weights_tensor = None
if USE_CLASS_WEIGHTS:
    class_weights = compute_class_weight(
        "balanced", classes=np.unique(y_train), y=y_train
    )
    # Clip weight cực cao để tránh gradient bùng nổ
    # Với imbalance 500x → weight 329 → clip xuống 10
    MAX_WEIGHT = 10.0
    class_weights = np.clip(class_weights, 0, MAX_WEIGHT)
    weights_tensor = torch.tensor(class_weights, dtype=torch.float).to(device)
    print(f"   Class weights clipped to max {MAX_WEIGHT} "
          f"(min={class_weights.min():.2f}, max={class_weights.max():.2f})")

# ─────────────────────────────────────────────
# 8. METRICS
# ─────────────────────────────────────────────
def compute_metrics(eval_pred):
    logits, labels = eval_pred
    preds = np.argmax(logits, axis=-1)
    return {
        "accuracy":    accuracy_score(labels, preds),
        "f1_macro":    f1_score(labels, preds, average="macro",    zero_division=0),
        "f1_weighted": f1_score(labels, preds, average="weighted", zero_division=0),
    }

# ─────────────────────────────────────────────
# 9. CUSTOM TRAINER
# ─────────────────────────────────────────────
class WeightedTrainer(Trainer):
    def compute_loss(self, model, inputs, return_outputs=False, **kwargs):
        labels  = inputs.pop("labels")
        outputs = model(**inputs)
        loss_fn = CrossEntropyLoss(weight=weights_tensor)
        loss    = loss_fn(outputs.logits, labels)
        return (loss, outputs) if return_outputs else loss

TrainerClass = WeightedTrainer if USE_CLASS_WEIGHTS else Trainer

# ─────────────────────────────────────────────
# 10. TRAINING ARGUMENTS
# ─────────────────────────────────────────────
training_args = TrainingArguments(
    output_dir=RESULTS_DIR,

    num_train_epochs              = MAX_EPOCHS,
    per_device_train_batch_size   = PER_DEVICE_BATCH,
    per_device_eval_batch_size    = PER_DEVICE_BATCH * 2,  # eval không cần gradient, batch lớn hơn được
    gradient_accumulation_steps   = GRAD_ACCUM_STEPS,

    learning_rate                 = LEARNING_RATE,
    warmup_ratio                  = WARMUP_RATIO,
    lr_scheduler_type             = "cosine",
    weight_decay                  = 0.01,

    eval_strategy                 = "epoch",
    save_strategy                 = "epoch",
    load_best_model_at_end        = True,
    metric_for_best_model         = "f1_macro",
    greater_is_better             = True,
    save_total_limit              = 2,          # chỉ giữ 2 checkpoint gần nhất

    logging_steps                 = 1000,
    report_to                     = "none",

    fp16                          = torch.cuda.is_available(),
    dataloader_num_workers        = 2,          # tăng tốc data loading
    dataloader_pin_memory         = torch.cuda.is_available(),
)

# ─────────────────────────────────────────────
# 11. TRAIN
# ─────────────────────────────────────────────
trainer = TrainerClass(
    model           = model,
    args            = training_args,
    train_dataset   = train_dataset,
    eval_dataset    = val_dataset,
    compute_metrics = compute_metrics,
    callbacks       = [
        EarlyStoppingCallback(early_stopping_patience=EARLY_STOP_PATIENCE),
    ],
)

print(f"\n{'='*55}")
print(f"  BẮT ĐẦU TRAINING")
print(f"{'='*55}")
print(f"  Model              : {PRETRAINED_MODEL}")
print(f"  Số nhãn            : {num_labels}")
print(f"  Effective batch    : {PER_DEVICE_BATCH * GRAD_ACCUM_STEPS}")
print(f"  Max epochs         : {MAX_EPOCHS} (early stop patience={EARLY_STOP_PATIENCE})")
print(f"  Learning rate      : {LEARNING_RATE} (warmup {WARMUP_RATIO*100:.0f}% + cosine)")
print(f"  Max seq length     : {MAX_LENGTH}")
print(f"  Class weights      : {'ON (clipped ≤10)' if USE_CLASS_WEIGHTS else 'OFF'}")
print(f"  Device             : {device}")
print(f"{'='*55}\n")

trainer.train()

# ─────────────────────────────────────────────
# 12. EVALUATE TRÊN TEST SET
# ─────────────────────────────────────────────
print("\n📊 Đánh giá trên tập Test...")
test_results = trainer.evaluate(test_dataset)
acc    = test_results.get('eval_accuracy', 0)
f1_mac = test_results.get('eval_f1_macro', 0)
f1_w   = test_results.get('eval_f1_weighted', 0)

print(f"\n  Accuracy    : {acc:.4f}")
print(f"  F1-macro    : {f1_mac:.4f}")
print(f"  F1-weighted : {f1_w:.4f}")

# Per-class F1 report (lưu vào file)
print("\n📝 Tạo per-class classification report...")
preds_output = trainer.predict(test_dataset)
preds = np.argmax(preds_output.predictions, axis=-1)
report = classification_report(
    y_test, preds,
    target_names=[id2label[i] for i in range(num_labels)],
    zero_division=0
)
report_path = os.path.join(OUTPUT_MODEL, "classification_report.txt")
with open(report_path, 'w', encoding='utf-8') as f:
    f.write(report)
print(f"   Lưu tại: {report_path}")

# ─────────────────────────────────────────────
# 13. LƯU MODEL
# ─────────────────────────────────────────────
print(f"\n💾 Lưu model → {OUTPUT_MODEL}")
trainer.save_model(OUTPUT_MODEL)
tokenizer.save_pretrained(OUTPUT_MODEL)
joblib.dump(label_encoder, os.path.join(OUTPUT_MODEL, "label_encoder.joblib"))

metadata = {
    "version":           "v2",
    "pretrained_model":  PRETRAINED_MODEL,
    "num_labels":        num_labels,
    "max_length":        MAX_LENGTH,
    "use_class_weights": USE_CLASS_WEIGHTS,
    "imbalance_ratio":   round(float(imbalance_ratio), 2),
    "train_samples":     len(X_train),
    "val_samples":       len(X_val),
    "test_samples":      len(X_test),
    "test_accuracy":     round(acc, 4),
    "test_f1_macro":     round(f1_mac, 4),
    "test_f1_weighted":  round(f1_w, 4),
}
meta_path = os.path.join(OUTPUT_MODEL, "training_metadata.json")
with open(meta_path, 'w', encoding='utf-8') as f:
    json.dump(metadata, f, indent=2, ensure_ascii=False)

print(f"\n{'='*55}")
print(f"  HOÀN TẤT!")
print(f"  Model lưu tại: {OUTPUT_MODEL}")
print(f"  Test F1-macro : {f1_mac:.4f}")
print(f"{'='*55}")