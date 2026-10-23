import pandas as pd
import matplotlib.pyplot as plt
import seaborn as sns
from sqlalchemy import create_engine

# 1. Kết nối tới PostgreSQL
# Thay đổi password/port nếu máy bạn cài đặt khác
DB_URL = "postgresql://postgres:postgres@localhost:5432/postgres"
engine = create_engine(DB_URL)

# Thiết lập phong cách biểu đồ
sns.set_theme(style="whitegrid")
plt.rcParams['font.sans-serif'] = 'DejaVu Sans'

# -------------------------------------------------------------
# Biểu đồ 1: Thống kê số lượng Video theo Thể loại (category_id)
# -------------------------------------------------------------
query_cat = """
    SELECT category_id, COUNT(*) AS total_videos
    FROM v_clean_videos
    GROUP BY category_id
    ORDER BY total_videos DESC;
"""
df_cat = pd.read_sql(query_cat, engine)

plt.figure(figsize=(10, 5))
ax = sns.barplot(data=df_cat, x='category_id', y='total_videos', palette='viridis')
plt.title('Phân bố Số lượng Video theo Thể loại (category_id)', fontsize=14, fontweight='bold')
plt.xlabel('Mã Thể loại (Category ID)', fontsize=12)
plt.ylabel('Số lượng Video', fontsize=12)

# Hiển thị số liệu trên đầu mỗi cột
for p in ax.patches:
    ax.annotate(f'{int(p.get_height())}', 
                (p.get_x() + p.get_width() / 2., p.get_height()), 
                ha='center', va='bottom', fontsize=10, xytext=(0, 3), 
                textcoords='offset points')

plt.tight_layout()
plt.savefig('category_distribution.png', dpi=300)
plt.show()
print("-> Đã lưu biểu đồ: category_distribution.png")

# -------------------------------------------------------------
# Biểu đồ 2: Mối tương quan giữa View Count và Like Count
# -------------------------------------------------------------
query_stats = """
    SELECT view_count, like_count, comment_count
    FROM fact_stats
    WHERE view_count > 0 AND like_count > 0
    LIMIT 5000;
"""
df_stats = pd.read_sql(query_stats, engine)

plt.figure(figsize=(8, 6))
sns.scatterplot(data=df_stats, x='view_count', y='like_count', alpha=0.5, color='crimson')
plt.title('Mối tương quan giữa Lượt xem (View) và Lượt thích (Like)', fontsize=14, fontweight='bold')
plt.xlabel('Lượt xem (View Count)', fontsize=12)
plt.ylabel('Lượt thích (Like Count)', fontsize=12)

plt.tight_layout()
plt.savefig('view_vs_like.png', dpi=300)
plt.show()
print("-> Đã lưu biểu đồ: view_vs_like.png")