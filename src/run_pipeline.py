import subprocess
import sys


def run_step(module_name, description):
  print(f"\n==================================================")
  print(f"🚀 BẮT ĐẦU: {description}")
  print(f"==================================================")

  # Gọi module python dưới dạng subprocess
  result = subprocess.run([sys.executable, "-m", module_name])

  if result.returncode != 0:
    print(f"❌ Lỗi xảy ra tại bước: {description}")
    sys.exit(1)

  print(f"✅ HOÀN TẤT: {description}")


if __name__ == "__main__":
  print("🔄 BẮT ĐẦU CHẠY TOÀN BỘ PIPELINE ETL YOUTUBE...")

  # Bước 1: Quét, làm sạch dữ liệu thô và xuất ra file CSV đã xử lý
  run_step("src.processing.clean_data", "Làm sạch dữ liệu (Data Cleaning & Processing)")

  # Bước 2: Đọc file CSV đã làm sạch và nạp vào các bảng Fact/Dim trong PostgreSQL
  run_step("src.processing.load_all_jobs", "Nạp dữ liệu vào PostgreSQL (Database Loading)")

  print(
      "\n🎉🎉 CHÚC MỪNG! Toàn bộ pipeline ETL đã chạy thành công rực rỡ từ đầu"
      " tới cuối!"
  )