# Chatbot RAG Giáo dục

Ứng dụng hỏi đáp tài liệu giáo dục chạy cục bộ bằng FastAPI, Ollama, FAISS và giao diện web tiếng Việt. Hệ thống hỗ trợ tìm kiếm lai FAISS + BM25, trích dẫn nguồn, cập nhật chỉ mục tăng dần, OCR PDF scan, đọc tài liệu Office, tệp đính kèm và đồng bộ thư mục Google Drive.

## Yêu cầu

- Windows 10/11 và Python 3.11
- [Ollama](https://ollama.com/) đang chạy
- Model embedding `bge-m3`
- Một model hội thoại, mặc định `llama3.2:3b`
- Tesseract OCR nếu cần đọc PDF scan

## Cài đặt

```powershell
py -3.11 -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
ollama pull bge-m3
ollama pull llama3.2:3b
```

Đặt tài liệu vào thư mục:

```text
ollama-rag-desktop/data_giao_duc
```

Tạo chỉ mục lần đầu:

```powershell
.\.venv\Scripts\python.exe main.py
```

Khởi động giao diện:

```powershell
.\start_ui.bat
```

Ứng dụng sẽ chọn một cổng trống từ `8000` đến `8020` và mở trình duyệt tự động.

## Cập nhật tài liệu

Sau khi thêm, sửa hoặc xóa tài liệu trong kho, có thể cập nhật chỉ mục từ giao diện hoặc chạy:

```powershell
.\.venv\Scripts\python.exe capnhat_tailieu_moi.py
```

Kết quả OCR và sổ theo dõi giúp lần chạy tiếp theo tiếp tục mà không xử lý lại toàn bộ kho.

## Đo chất lượng hệ thống

Bộ câu hỏi chuẩn nằm ở `bo_cau_hoi_benchmark.json` (127 câu, trong đó 97 câu có nhãn nguồn đúng và 30 câu cố tình lạc đề).

```powershell
.\.venv\Scripts\python.exe benchmark_chatbot.py --ir
```

Chế độ `--ir` đo chất lượng **xếp hạng** của khối truy hồi bằng bộ chỉ số IR/QA kinh điển — MRR, Hit@K, Recall@K, nDCG@K, MAP (công thức nằm trong `chi_so_ir.py`). Không gọi LLM nên chạy vài phút, kết quả ghi ra `ket_qua_chi_so_ir.json` và bảng markdown `bang_chi_so_ir.md` để dán thẳng vào báo cáo.

Hai chế độ còn lại: `--nhanh` đo truy hồi kèm cổng chặn lạc đề, `--bo` gọi đủ LLM để đo thêm trích dẫn và số liệu (chậm, khoảng 150 giây/câu trên CPU).

## Cấu hình Google Drive

Sao chép `khoa_api.mau.bat` thành `khoa_api.bat`, sau đó điền khóa API của riêng bạn. `khoa_api.bat` đã được loại khỏi Git để tránh công khai khóa.

## Dữ liệu không nằm trong repository

Repository chỉ chứa mã nguồn. Tài liệu gốc, chỉ mục FAISS, cache OCR, bản phiên âm, lịch sử chat, khóa API và cấu hình riêng của máy không được commit vì có thể chứa dữ liệu riêng tư hoặc tệp dung lượng lớn.

Xem thêm [hướng dẫn chạy giao diện](HUONG_DAN_CHAY_GIAO_DIEN.md) và [tài liệu bàn giao](HUONG_DAN_BAN_GIAO_UI.md).
