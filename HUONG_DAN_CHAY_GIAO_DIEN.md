# Hướng dẫn chạy giao diện Chatbot RAG Giáo dục

## Chạy nhanh trên Windows

1. Mở Ollama và bảo đảm đã có hai model:

   ```powershell
   ollama pull bge-m3
   ollama pull qwen3.5:4b
   ```

   Muốn câu trả lời chắc tay hơn thì tải thêm bậc 9B rồi chọn ở nút model
   trên giao diện. Nặng khoảng 6.6 GB, cần máy từ 12 GB RAM trở lên:

   ```powershell
   ollama pull qwen3.5:9b
   ```

2. Nhấp đúp `start_ui.bat`.

3. Trình duyệt tự mở tại `http://127.0.0.1:8000`. Nếu cổng 8000 đang bận,
   ứng dụng tự chọn cổng tiếp theo (8001, 8002...) và mở đúng địa chỉ đó.

Nếu chưa có `.venv`, tạo môi trường và cài thư viện một lần:

```powershell
py -3.11 -m venv .venv
.venv\Scripts\python.exe -m pip install -r requirements.txt
```

## Cấu hình tùy chọn

Thiết lập biến môi trường trước khi chạy nếu cấu hình máy khác mặc định:

| Biến | Mặc định | Ý nghĩa |
|---|---|---|
| `RAG_LLM_MODEL` | `qwen3.5:4b` | Model tạo câu trả lời và suy luận |
| `RAG_EMBEDDING_MODEL` | `bge-m3` | Model embedding, phải khớp model dùng để build index |
| `RAG_REASONING` | `0` | Đặt `1` để bật suy luận sâu; trên máy chỉ có CPU sẽ chậm hơn nhiều |
| `RAG_CONTEXT_LENGTH` | `4096` | Cửa sổ ngữ cảnh dùng cho một câu hỏi; chạy được trên GPU thì nới lên `8192` |
| `RAG_MAX_OUTPUT_TOKENS` | `420` | Độ dài tối đa của câu trả lời |
| `RAG_MAX_OUTPUT_TOKENS_TOM_TAT` | `700` | Hạn mức riêng cho bản tóm tắt tệp đính kèm |
| `RAG_SO_BANG_CHUNG` | `4` | Số đoạn tài liệu đưa vào prompt mỗi câu hỏi |
| `RAG_KY_TU_MOI_BANG_CHUNG` | `900` | Cắt bớt mỗi đoạn còn bấy nhiêu ký tự; `0` = không cắt |
| `RAG_SO_DOAN_TOM_TAT` | `6` | Số đoạn trích để tóm tắt một tệp |
| `RAG_KY_TU_TOM_TAT` | `5000` | Ngân sách ký tự tài liệu khi tóm tắt |
| `RAG_KEEP_ALIVE` | `2h` | Giữ model trong RAM bao lâu sau câu hỏi cuối |
| `OLLAMA_BASE_URL` | `http://localhost:11434` | Địa chỉ Ollama |
| `RAG_INDEX_PATH` | `faiss_index_data_giao_duc` trong dự án | Đường dẫn FAISS index |
| `RAG_DATA_PATH` | `ollama-rag-desktop/data_giao_duc` | Kho tài liệu giáo dục dùng để build/cập nhật index |
| `RAG_HOST` | `127.0.0.1` | IP lắng nghe của web server |
| `RAG_PORT` | `8000` | Cổng web server |
| `RAG_OPEN_BROWSER` | `1` | Đặt `0` nếu không muốn tự mở trình duyệt |
| `RAG_DRIVE_API_KEY` | *(trống)* | API key Google Drive; có key thì hệ thống tự phát hiện file mới trên Drive |
| `RAG_DRIVE_FOLDER_ID` | thư mục đề án | ID thư mục Drive dùng chung |
| `RAG_DRIVE_AUTO_SYNC_PHUT` | `15` | Chu kỳ tự kiểm tra Drive; đặt `0` để tắt |
| `RAG_DRIVE_MAX_MB` | `2048` | Bỏ qua file lớn hơn ngưỡng này khi đồng bộ |
| `RAG_LUU_TEP_DINH_KEM` | `1` | Tệp đính kèm trong chat tự được thêm vào kho tài liệu; đặt `0` để tắt |
| `RAG_THU_MUC_TEP_DINH_KEM_TRONG_KHO` | `tai_lieu_dinh_kem` | Thư mục con trong kho dùng chứa tệp đính kèm |
| `RAG_CHO_NAP_TEP_GIAY` | `90` | Đợi bao lâu sau câu hỏi cuối mới nạp tệp mới vào chỉ mục |
| `RAG_WHISPER_MODEL` | `small` | Model phiên âm video: tiny/base/small/medium/large-v3 |
| `RAG_TRANSCRIBE_ON_INDEX` | `1` | Đặt `0` nếu chỉ nạp video đã phiên âm sẵn |
| `RAG_TU_CHOI_KHI_LAC_DE` | `1` | Tự trả lời "không tìm thấy" khi truy hồi lạc đề |
| `RAG_OCR_ON_INDEX` | `1` | Đặt `0` nếu chỉ nạp PDF đã OCR sẵn |
| `RAG_OCR_DPI` | `300` | Độ phân giải render trang PDF trước khi OCR |
| `RAG_OCR_LUONG` | số lõi − 2 | Số trang OCR song song |

### Nếu câu trả lời quá lâu

Máy chỉ có CPU xử lý prompt khoảng 26 token/giây và sinh chữ khoảng 6 token/giây,
nên thời gian chờ tỉ lệ thẳng với độ dài prompt + độ dài câu trả lời. Theo thứ tự
hiệu quả:

1. Giảm `RAG_SO_BANG_CHUNG` (4 → 3) và `RAG_KY_TU_MOI_BANG_CHUNG` (900 → 700):
   mỗi đoạn bỏ đi tiết kiệm khoảng 15 giây chờ.
2. Giảm `RAG_MAX_OUTPUT_TOKENS` (420 → 300): câu trả lời ngắn hơn, nhanh hơn
   khoảng 20 giây.
3. Đổi sang model nhỏ hơn ngay trên giao diện (`qwen2.5:3b-instruct`,
   `llama3.2:3b`): nhanh gần gấp đôi, đổi lại chất lượng trích dẫn giảm - nên
   chạy `benchmark_chatbot.py` để đối chiếu trước khi dùng lâu dài.
4. Chỉ khi thật cần chi tiết mới đặt `RAG_REASONING=1`; suy luận ẩn làm chậm
   gấp nhiều lần trên CPU.
| `RAG_TESSERACT_PATH` | tự dò | Đường dẫn `tesseract.exe` nếu cài chỗ khác |

Ví dụ PowerShell:

```powershell
$env:RAG_LLM_MODEL = "qwen3.5:4b"
$env:RAG_PORT = "8080"
.venv\Scripts\python.exe run_ui.py
```

## API

- `GET /api/status`: trạng thái model và kho tri thức.
- `GET /api/documents`: danh sách tài liệu và tình trạng lập chỉ mục.
- `GET /api/goi-y?so_luong=6`: mẻ câu hỏi gợi ý cho màn hình chào.
- `POST /api/chat/stream`: nhận câu hỏi và trả NDJSON streaming.
- `GET /api/source?name=...`: mở tệp nguồn đã được kiểm tra trong kho dữ liệu.
- `POST /api/reinitialize`: thử kết nối lại sau khi mở Ollama.
- `POST /api/index/update`: cập nhật tăng dần chỉ mục sau khi thêm, sửa hoặc xóa tài liệu.
- `POST /api/drive/sync`: kéo tài liệu mới từ Google Drive rồi tự cập nhật chỉ mục.
- `GET /api/models`: danh sách model Ollama đang có trên máy.
- `POST /api/model`: đổi model trả lời ngay lúc đang chạy.
- `GET /api/docs`: tài liệu OpenAPI tương tác.

Payload cho endpoint chat:

```json
{
  "question": "Còn giảng viên thì sao?",
  "history": [
    {"role": "user", "content": "Quy định đối với sinh viên là gì?"},
    {"role": "assistant", "content": "Các quy định gồm..."}
  ]
}
```

Ứng dụng thiết kế cho một lượt sinh câu trả lời tại một thời điểm vì Ollama chạy CPU. Câu hỏi đến sau sẽ chờ lượt hiện tại kết thúc. Lịch sử chat lưu trong `localStorage` của trình duyệt; tối đa sáu tin nhắn gần nhất được gửi kèm câu hỏi để hiểu câu hỏi nối tiếp và không được thêm vào kho tài liệu.

Trong giao diện, câu trả lời hỗ trợ tiêu đề, danh sách, chữ đậm, mã ngắn và liên kết trích dẫn. Nhấp vào nguồn tham khảo để mở tài liệu gốc. Nếu chủ động dừng giữa chừng, phần nội dung đã nhận vẫn được lưu vào lịch sử.

Dưới bốn thẻ chủ đề ở màn hình chào có hàng **Gợi ý khác từ kho tài liệu**: câu hỏi dựng theo tên văn bản đang có trong kho, bấm **Đổi gợi ý** để lấy mẻ khác. Cuối mỗi câu trả lời có hàng **Hỏi tiếp** dựng từ chính nguồn vừa trích - văn bản đã bị thay thế hay còn là dự thảo thì gợi ý hỏi ngay về chỗ đó, nguồn trích theo Điều thì gợi ý đọc sâu vào Điều đó. Khác với bốn thẻ chủ đề (chỉ điền vào khung hỏi để sửa lại), gợi ý dạng chip đã là câu hỏi trọn vẹn nên bấm là gửi luôn. Cả hai hàng gợi ý đều dựng bằng dữ liệu có sẵn, không gọi thêm model nên không làm chậm câu trả lời.

Nút **Kho tài liệu** mở danh sách nguồn, cho phép tìm theo tên hoặc thư mục và hiển thị trạng thái đã lập chỉ mục, cần OCR, tệp trùng hoặc chờ cập nhật.

Khi kho tài liệu thay đổi, thẻ trạng thái sẽ hiện nút **Cập nhật kho tri thức**. Quá trình chạy nền và tạm khóa gửi câu hỏi để không đọc chỉ mục giữa lúc đang thay đổi. Không đóng cửa sổ chạy ứng dụng cho tới khi trạng thái trở lại **Sẵn sàng**.

Để đo một model bằng toàn bộ pipeline truy hồi, sinh câu trả lời và kiểm tra số trích dẫn:

```powershell
.venv\Scripts\python.exe benchmark_chatbot.py "Câu hỏi cần kiểm tra"
```

Chạy cả bộ 15 câu hỏi chuẩn (có chấm điểm truy hồi đúng nguồn, trích dẫn hợp lệ, số liệu có căn cứ và từ chối đúng chỗ), kết quả ghi ra `ket_qua_benchmark.json`:

```powershell
.venv\Scripts\python.exe benchmark_chatbot.py --bo
```

## Chọn mô hình trả lời

Bấm vào tên model ở góc trên bên phải để mở danh sách. Menu hiện mọi model Ollama đang có trên máy kèm số tham số và dung lượng; model đang dùng có dấu tích.

Đổi model **không phải nạp lại chỉ mục**: vector đã embed bằng `bge-m3`, chỉ chuỗi sinh câu trả lời được dựng lại nên chuyển gần như tức thì. Lựa chọn được ghi vào `cai_dat.json` để lần mở sau vẫn giữ nguyên.

Vài điểm cần biết:

- Model nhúng (`bge-m3`, `nomic-embed-text`) bị lọc khỏi danh sách vì chúng chỉ sinh vector, không trò chuyện được.
- Không đổi được giữa lúc đang trả lời dở; hệ thống báo chờ câu hiện tại xong.
- Đặt biến `RAG_LLM_MODEL` sẽ ép cứng model và bỏ qua lựa chọn đã lưu.
- Thêm model mới bằng `ollama pull <tên model>`, menu tự thấy ở lần mở sau.

## Tài liệu trên Google Drive

Thư mục Drive dùng chung là nguồn dữ liệu chính thức; người phụ trách chỉ cần upload lên đó. Máy chạy chatbot tự tải phần thay đổi về `data_giao_duc` rồi tự nạp vào chỉ mục — mặc định kiểm tra mỗi 15 phút, hoặc bấm **Đồng bộ Google Drive** trên thanh bên để làm ngay.

Vì embedding và tìm kiếm chạy 100% cục bộ nên nội dung vẫn phải nằm trên máy; điều khác biệt là không ai phải tải tay hay chạy lại script nào.

Hai chế độ hoạt động:

| Chế độ | Cấu hình cần | Phát hiện file mới trên Drive |
|---|---|---|
| API key *(khuyến nghị)* | đặt `RAG_DRIVE_API_KEY` | Tự động, kể cả file và thư mục con mới thêm |
| Manifest | dùng `drive_manifest.json` có sẵn | Chỉ các file đã có trong manifest |

Tạo API key một lần (khoảng 5 phút, miễn phí, không cần màn hình xin quyền vì thư mục đã chia sẻ công khai theo liên kết):

1. Vào [console.cloud.google.com](https://console.cloud.google.com) → tạo project mới.
2. **APIs & Services → Library** → tìm *Google Drive API* → **Enable**.
3. **APIs & Services → Credentials → Create credentials → API key** → sao chép key.
4. Đặt biến môi trường rồi chạy lại ứng dụng:

```powershell
setx RAG_DRIVE_API_KEY "AIza...key-cua-ban"
```

Sau khi có key, xuất lại danh sách file dự phòng bất cứ lúc nào:

```powershell
.venv\Scripts\python.exe drive_sync.py --xuat-manifest
```

Các lệnh đồng bộ chạy tay:

```powershell
.venv\Scripts\python.exe drive_sync.py --thu
.venv\Scripts\python.exe drive_sync.py
```

## Video và âm thanh

Video được phiên âm offline bằng faster-whisper, cắt đoạn theo mốc thời gian, nên câu trả lời trích dẫn được đúng phút trong video và giao diện phát ngay tại đoạn đó.

Nên phiên âm trước khi lập chỉ mục để xem được tiến độ từng file (bản phiên âm lưu cache theo nội dung file, lần sau không làm lại):

```powershell
.venv\Scripts\python.exe phien_am_video.py
```

Tốc độ đo trên máy chỉ có CPU: nhanh hơn khoảng 4 lần thời gian thực với model `small` (video 1 phút 45 giây mất 24 giây). Muốn chính xác hơn thì dùng `--model medium`, đổi lại chậm hơn khoảng 3 lần. Nếu file media có sẵn phụ đề `.srt`/`.vtt` cùng tên đặt cạnh nó, hệ thống dùng phụ đề và bỏ qua bước phiên âm.

## PDF bản scan (OCR)

Phần lớn văn bản quy phạm trong kho là bản scan ảnh: mỗi trang chỉ có một tấm ảnh, không có lớp chữ nào để trích xuất. Những file này được nhận diện tự động và đưa qua Tesseract OCR, kết quả lưu cache theo hash nội dung nên chỉ chạy một lần cho mỗi tài liệu.

Cài một lần:

```powershell
winget install --id UB-Mannheim.TesseractOCR -e
```

Gói ngôn ngữ tiếng Việt `vie.traineddata` đã có sẵn trong thư mục `tessdata/` của dự án (bản `tessdata_best`, cho dấu tiếng Việt chính xác hơn bản thường).

OCR trước toàn bộ PDF scan, có tiến độ từng trang:

```powershell
.venv\Scripts\python.exe ocr_pdf.py
```

Tốc độ đo thực tế trên máy 8 lõi: khoảng 2,8 giây/trang khi chạy 6 trang song song (so với 12 giây/trang nếu chạy tuần tự). Văn bản in ra sạch, riêng phần con dấu và chữ ký nháy có thể lẫn ký tự nhiễu — đây là giới hạn chung của OCR với tài liệu hành chính đã đóng dấu.

## Hồ sơ văn bản và cảnh báo hiệu lực

Kho chứa cả văn bản cũ lẫn văn bản mới thay thế nó. Hai văn bản đó gần như giống hệt nhau về mặt ngữ nghĩa, nên một chatbot chỉ so khớp nội dung sẽ trích dẫn bản đã hết hiệu lực mà không hề biết.

Khi nạp chỉ mục, hệ thống đọc chính nội dung đã lập chỉ mục để rút ra:

- **Hồ sơ từng văn bản**: số hiệu, loại, cơ quan ban hành, ngày ban hành.
- **Quan hệ giữa các văn bản**: A thay thế / bãi bỏ / sửa đổi B.

Kết quả dùng vào ba việc: hiện số hiệu ngay trên mỗi nguồn trích dẫn, cảnh báo khi câu trả lời dựa trên văn bản đã bị thay thế hoặc sửa đổi bởi văn bản khác **có trong kho**, và hạ bậc văn bản hết hiệu lực khi xếp hạng truy hồi.

Dựng lại hồ sơ và xem thống kê:

```powershell
.venv\Scripts\python.exe van_ban_meta.py
```

Kết quả lưu ở `ho_so_van_ban.json`. Số hiệu nào hệ thống không chắc (số trong tên file khác số OCR được, hoặc bản dự thảo chưa điền số) sẽ hiện kèm dấu `(?)` thay vì khẳng định.

Ba quy tắc giúp tránh kết luận sai — đều rút ra từ dữ liệu thật của kho:

| Bẫy | Cách xử lý |
|---|---|
| Thông tư nào cũng "Căn cứ Nghị định 37/2025/NĐ-CP" | Chỉ đọc số hiệu trong khối tiêu đề, cắt trước chữ "Căn cứ" |
| Bản hợp nhất chú thích "Điều này **được** sửa đổi **theo quy định tại** Nghị định 311/2025" | Nhận ra thể bị động để không kết luận ngược chiều |
| "Nghị định số 311/2025/NĐ-CP thay thế Nghị định 71/2020" nằm trong văn bản khác | Bỏ qua khi chủ ngữ là một văn bản khác, không phải văn bản đang đọc |

## Kiểm tra câu trả lời tự động

Sau mỗi câu trả lời, hệ thống đối chiếu lại bằng chuỗi (không gọi thêm mô hình):

- Mọi số trích dẫn `[n]` phải ứng với một khối EVIDENCE có thật.
- Mọi con số trong câu trả lời phải xuất hiện trong đoạn tài liệu được đưa vào.

Nếu lệch, giao diện hiện dải cảnh báo vàng ngay dưới câu trả lời để người đọc đối chiếu lại, thay vì để thông tin sai trôi qua.
