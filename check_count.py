import os
import glob
import json

def count_crawled_data():
    base_dir = "data/raw/youtube"
    # Tìm tất cả file json trong mọi thư mục con của raw
    pattern = os.path.join(base_dir, "**", "*.json")
    files = glob.glob(pattern, recursive=True)
    
    print(f"📁 Tổng số file JSON raw đã cào: {len(files)}")
    
    total_records = 0
    for file_path in files:
        try:
            with open(file_path, "r", encoding="utf-8") as f:
                data = json.load(f)
                response = data.get("response", data)
                if isinstance(response, list):
                    total_records += len(response)
                elif isinstance(response, dict):
                    items = response.get("items", [response])
                    if isinstance(items, list):
                        total_records += len(items)
        except Exception:
            pass
            
    print(f"📊 Tổng số bản ghi video thô ước tính: {total_records}")

if __name__ == "__main__":
    count_crawled_data()