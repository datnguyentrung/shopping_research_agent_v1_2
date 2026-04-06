import gzip
import json
import os

import pandas as pd
import networkx as nx
import matplotlib.pyplot as plt
import io

from app.utils.training_model.check_training_data import CLEANNED_TRAINING_DATA_PATH

# Xác định đường dẫn tuyệt đối tới file training_data.csv trong thư mục data
CATEGORY_PATH = r'D:\Thực tập MB\Shopping_Research_Agent_V1_2\data\category.csv'
META_DATA_PATH = r'D:\Thực tập MB\data\meta_Clothing_Shoes_and_Jewelry.jsonl.gz'
TRAINING_DATA_PATH = r'D:\Thực tập MB\Shopping_Research_Agent_V1_2\data\training_data.csv'

def read_file(file_path=META_DATA_PATH):
    count = 10
    with gzip.open(file_path, 'rt', encoding='utf-8') as f:
        for line in f:
            first_entry = json.loads(line)
            print(json.dumps(first_entry, indent=2))
            count -= 1
            if count == 0:
                break  # Chỉ đọc 1 dòng rồi dừng để bảo vệ RAM

def read_csv(file_path):
    with open(file_path, 'r', encoding='utf-8') as f:
        lines = f.readlines()
        print(f"Sự thật là file có: {len(lines):,} dòng")


# HÀM MỚI: Thuật toán xếp từ dưới lên chống đè node
def hierarchy_pos_horizontal(G, root):
    pos = {}

    # 1. Tìm tất cả các node lá theo thứ tự duyệt cây (DFS) để dây không bị chéo nhau
    dfs_nodes = list(nx.dfs_preorder_nodes(G, root))
    leaves = [n for n in dfs_nodes if G.out_degree(n) == 0]

    # 2. Xếp các node lá cách đều nhau 1 đơn vị theo chiều dọc (trục Y)
    leaf_y = {}
    y_current = 0
    for leaf in leaves:
        leaf_y[leaf] = y_current
        y_current -= 1  # Mỗi lá cách nhau 1 đơn vị xuống dưới

    # 3. Tính Y của cha bằng trung bình cộng Y của các con
    def get_y(node):
        if G.out_degree(node) == 0:
            return leaf_y[node]
        children = list(G.successors(node))
        return sum(get_y(child) for child in children) / len(children)

    # 4. Gắn tọa độ (X, Y) cho tất cả. X tăng theo chiều sâu (depth).
    def set_pos(node, current_x):
        pos[node] = (current_x, get_y(node))
        for child in G.successors(node):
            # Mỗi depth cách nhau 1 khoảng X
            set_pos(child, current_x + 10)  # Tăng khoảng cách X giữa các cấp

    set_pos(root, 0)
    return pos

def show_tree():
    df = pd.read_csv(CATEGORY_PATH)

    # Lọc dữ liệu: Chỉ lấy đến độ sâu 3
    df = df[df['Depth'] <= 6]

    G = nx.DiGraph()

    for _, row in df.iterrows():
        cat_id = str(row['Category ID'])
        parent_id = str(row['Parent ID'])

        G.add_node(cat_id, label=str(row['Name']), depth=row['Depth'])

        if parent_id and parent_id.lower() != 'nan':
            G.add_edge(parent_id, cat_id)

    root_node = 'root'

    if root_node not in G:
        print(f"Không tìm thấy nút '{root_node}' trong dữ liệu đã lọc.")
        return

    try:
        # Sử dụng hàm vẽ ngang mới
        pos = hierarchy_pos_horizontal(G, root_node)
    except Exception as e:
        print(f"Lỗi khi sắp xếp cây: {e}")
        return

    # Tùy chỉnh lại khung hình (nên để chiều rộng lớn hơn chiều cao khi vẽ ngang)
    plt.figure(figsize=(24, 120))
    labels = nx.get_node_attributes(G, 'label')

    nx.draw(G, pos, with_labels=True, labels=labels,
            node_size=100,
            node_color="lightblue",  # Bóng nhỏ lại
            font_size=7,
            font_weight="bold",  # Chữ bé lại 1 chút
            arrows=True,
            edge_color="gray",
            node_shape="s")  # "o" là hình tròn, bạn có thể đổi thành "s" nếu thích hình vuông

    plt.title("Sơ đồ phân cấp danh mục Amazon (Trái -> Phải, Depth <= 3)")

    # Căn chỉnh lề để chữ ở các node ngoài cùng bên phải không bị cắt xén
    plt.margins(0.1)
    plt.savefig("amazon_category_tree.pdf", format="pdf", bbox_inches="tight")
    plt.show()

if __name__ == "__main__":
    # read_csv(CLEANNED_TRAINING_DATA_PATH)
    # read_file()
    show_tree()