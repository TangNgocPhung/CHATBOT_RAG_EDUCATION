"""
Worker script chạy trong subprocess riêng (gọi qua subprocess.run, KHÔNG qua
multiprocessing.Process - multiprocessing "spawn" trên Windows tương tác lỗi
với venv launcher, gây ra tiến trình con "ma" chạy nhầm interpreter hệ thống).

Nhận đường dẫn file qua argv[1], in kết quả dạng JSON ra stdout:
  {"ok": true, "docs": [{"page_content": ..., "metadata": {...}}, ...]}
  {"ok": false, "error": "..."}
"""

import sys
import os
import json

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from chunking_utils import tao_loader_cho_file


def main():
    duong_dan = sys.argv[1]
    try:
        loader = tao_loader_cho_file(duong_dan)
        docs = loader.load()
        ket_qua = {
            "ok": True,
            "docs": [{"page_content": d.page_content, "metadata": d.metadata} for d in docs],
        }
    except Exception as e:
        ket_qua = {"ok": False, "error": str(e)}

    sys.stdout.write(json.dumps(ket_qua, ensure_ascii=False))


if __name__ == "__main__":
    main()
