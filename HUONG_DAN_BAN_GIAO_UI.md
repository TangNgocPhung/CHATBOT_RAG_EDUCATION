# Chatbot RAG Giáo dục — Tài liệu bàn giao cho đội làm UI

> Tài liệu này mô tả phần **RAG backend** đã hoàn thiện và benchmark thật (không phải giả định). Người làm UI **không cần hiểu retrieval/embedding hoạt động bên trong ra sao** — chỉ cần đọc mục 4 (Cách chạy) và mục 6 (Hook cho UI) để nối vào giao diện.

---

## 1. Hệ thống này làm gì

Chatbot hỏi-đáp dựa trên kho tài liệu bao quát nhiều bậc và lĩnh vực giáo dục (mầm non, phổ thông, thường xuyên, nghề nghiệp, đại học, chính sách và quản lý giáo dục...), có khả năng:

- Trả lời câu hỏi dựa **CHỈ trên** nội dung tài liệu đã nạp (không bịa, có cơ chế từ chối khi không tìm thấy thông tin).
- Đọc trực tiếp 1 URL do người dùng dán trong câu hỏi (đọc ngay, không cần nạp trước vào kho).
- Trích dẫn nguồn (tên file/Chương/Điều) trong câu trả lời.

**Phạm vi ĐÃ làm** (mục 8 liệt kê rõ giới hạn CHƯA làm).

---

## 2. Yêu cầu để chạy

| Thành phần | Yêu cầu |
|---|---|
| Python | 3.11 (venv sẵn tại `Học Ai\.venv\`) |
| Ollama | Cài & chạy nền (`ollama serve`), có 2 model đã pull: `bge-m3` (embedding) và `llama3.2:3b` (LLM) |
| RAM | Đủ chạy 2 model Ollama cùng lúc (~4-5GB) |
| GPU | **Không bắt buộc** — hệ thống hiện chạy 100% CPU (đã đo và xác nhận, xem mục 7.5). Có GPU sẽ nhanh hơn nhưng không phải bắt buộc để chạy đúng. |
| Dữ liệu | Tài liệu nguồn tại `./ollama-rag-desktop/data_giao_duc`; FAISS index mới được lưu tại `./faiss_index_data_giao_duc`. |

Cài đặt:
```bash
cd Mr_Hai
pip install -r requirements.txt
ollama pull bge-m3
ollama pull llama3.2:3b
ollama serve
```

---

## 3. Cấu trúc file quan trọng

| File | Vai trò |
|---|---|
| `main.py` | Điểm chạy chính — khởi tạo embedding/LLM, load FAISS, vòng lặp hỏi-đáp qua terminal |
| `hybrid_retrieval.py` | Toàn bộ logic retrieval (FAISS + BM25 + RRF + dominance) |
| `chunking_utils.py` | Chunking theo cấu trúc Chương/Điều và theo phần tử (slide/sheet/đoạn phiên âm) |
| `document_loaders.py` | Loader từng định dạng: pdf (kèm số trang), docx, doc, pptx theo slide, excel/csv theo sheet, html, epub theo chương, ảnh rời qua OCR, video/âm thanh |
| `media_transcribe.py` | Phiên âm video/âm thanh bằng faster-whisper, cache theo hash, đọc phụ đề .srt/.vtt |
| `phien_am_video.py` | CLI phiên âm trước toàn bộ video trong kho, có tiến độ từng file |
| `drive_sync.py` | Đồng bộ kho tài liệu từ thư mục Google Drive dùng chung (API key hoặc manifest) |
| `kiem_tra_tra_loi.py` | Hậu kiểm câu trả lời: trích dẫn hợp lệ, số liệu có căn cứ, ngưỡng từ chối |
| `ocr_pdf.py` | OCR PDF bản scan bằng Tesseract, chạy song song nhiều trang, cache theo hash |
| `phan_loai_giao_duc.py` | Gắn nhãn môn học/cấp học/lớp/loại nội dung cho từng tài liệu và lọc phạm vi truy xuất |
| `van_ban_meta.py` | Hồ sơ văn bản (số hiệu, ngày, cơ quan) và quan hệ thay thế/sửa đổi giữa các văn bản trong kho |
| `api.py` + `rag_service.py` + `static/` | REST API (FastAPI, streaming NDJSON) và giao diện web |
| `bo_cau_hoi_benchmark.json` | Bộ câu hỏi chuẩn dùng để đo chất lượng, chạy bằng `benchmark_chatbot.py --bo` |
| `web_loader.py` | Đọc URL trực tiếp (độc lập với FAISS) + Web Context Compression |
| `capnhat_tailieu_moi.py` | Cập nhật kho tài liệu incremental (chạy riêng, không phải lúc hỏi-đáp) |
| `faiss_index_data_giao_duc/` | Vector store được build từ thư mục `data_giao_duc` |
| `data_giao_duc_da_xu_ly.json` | "Sổ ghi chép" hash + chunk_id từng file đã nạp (dùng cho incremental update) |

---

## 4. Cách chạy nhanh (để test trước khi nối UI)

```bash
cd Mr_Hai
"Học Ai/.venv/Scripts/python.exe" main.py
```

Gõ câu hỏi vào console, gõ `thoat` để dừng. Nếu chạy lần đầu và chưa có FAISS index, hệ thống sẽ tự build từ thư mục `ollama-rag-desktop/data_giao_duc` (`DATA_PATH` trong `main.py`).

---

## 5. Kiến trúc kỹ thuật (để ghi vào báo cáo/đề án)

| Thành phần | Lựa chọn | Vì sao |
|---|---|---|
| **Embedding model** | `bge-m3` (qua Ollama) | Đa ngôn ngữ, hỗ trợ tiếng Việt tốt, chạy local không cần API ngoài |
| **Vector store** | FAISS (CPU, local, thư viện `faiss-cpu`) | Local, miễn phí, đủ nhanh cho quy mô ~3.500 vector (search chỉ mất ~0.3-5s) |
| **LLM chính thức** | `llama3.2:3b` (qua Ollama) | Chọn qua A/B test thật với `llama3:latest` (8B): 3B cho accuracy gần bằng (17-18/30 vs 18/30) nhưng **hallucination ít hơn 2.7 lần** (3 vs 8/30) và **nhanh hơn 2.5 lần** (51s vs 126s/câu) |
| **Retrieval** | Hybrid: FAISS (dense) + BM25 (lexical, có structural tokenization cho "Điều N"/"Chương N") + Reciprocal Rank Fusion + evidence dominance có điều kiện | Qua 5 lần lặp (V1→V5), mỗi bản sửa đúng 1 lỗi phát hiện từ benchmark thật — xem mục 7 |
| **Chunking** | Structure-aware: tách theo Điều/Chương cho văn bản pháp lý, `RecursiveCharacterTextSplitter` (1200/150) cho phần còn lại | Giữ nguyên vẹn ngữ cảnh 1 Điều trong 1 chunk, tránh cắt giữa câu |
| **Metadata đặc biệt** | `context_label` (vd "Hình thức đào tạo: vừa làm vừa học") | Phân biệt 2 bảng số liệu khác nhau nằm trong CÙNG 1 Điều — lỗi thật gặp phải và đã sửa |
| **Prompt** | Format EVIDENCE có đánh số, 10 rule grounding (không bịa, không gộp evidence khác Điều, giữ nguyên số liệu...) | Đã thử "rule cấm cứng" ở V3, gây từ chối oan — rút kinh nghiệm, hiện dùng rule mềm |
| **Xử lý URL** | `requests` + `trafilatura` (trích nội dung chính) + BM25 nén context theo câu hỏi | Độc lập hoàn toàn với FAISS, không lưu trữ, không ảnh hưởng kho tài liệu chính |

---

## 6. Hook Python cấp thấp (REST API đã có sẵn ở `api.py`)

> Giao diện web và REST API đã hoàn thiện — xem `api.py` và mục 11. Phần dưới đây giữ lại cho ai muốn gọi thẳng từ Python (chạy batch, viết script đo đạc) thay vì qua HTTP:

```python
from main import tao_embeddings_va_llm, build_hoac_load_vector_store, tao_rag_chain
from hybrid_retrieval import xay_dung_bm25, truy_hoi, SO_KET_QUA_CUOI
from web_loader import tim_url_trong_cau_hoi, tai_va_trich_noi_dung, nen_ngu_canh_theo_cau_hoi, ket_qua_thanh_document

# Khởi tạo 1 LẦN khi server start (KHÔNG khởi tạo lại mỗi request - chậm)
embeddings, llm = tao_embeddings_va_llm()
vector_store, _ = build_hoac_load_vector_store(embeddings)   # load, không build lại
bm25_retriever = xay_dung_bm25(vector_store)
rag_chain, format_docs = tao_rag_chain(vector_store, llm)

# Mỗi request hỏi-đáp:
def tra_loi(cau_hoi: str) -> str:
    url = tim_url_trong_cau_hoi(cau_hoi)
    if url:
        ket_qua = tai_va_trich_noi_dung(url)
        if not ket_qua.thanh_cong:
            return f"Lỗi: {ket_qua.loi}"          # KHÔNG fallback sang FAISS
        noi_dung, _ = nen_ngu_canh_theo_cau_hoi(ket_qua.noi_dung, cau_hoi, so_doan=3)
        ket_qua.noi_dung = noi_dung
        tai_lieu = [ket_qua_thanh_document(ket_qua)]
    else:
        tai_lieu = truy_hoi(cau_hoi, vector_store, bm25_retriever, SO_KET_QUA_CUOI)

    ngu_canh = format_docs(tai_lieu)
    return rag_chain.invoke({"context": ngu_canh, "question": cau_hoi})  # dùng .invoke() thay .stream() nếu UI không cần streaming
```

**Lưu ý quan trọng khi bọc API**:
- `rag_chain.stream(...)` cho phép trả lời dần từng chữ (dùng cho UI kiểu streaming/typing effect) — xem `hoi_dap()` trong `main.py` để tham khảo cách dùng.
- Mỗi câu hỏi mất trung bình **~50 giây** (xem mục 7.5) — UI **bắt buộc phải có loading state rõ ràng**, không được để người dùng tưởng bị treo.
- Model được load 1 lần và giữ trong RAM suốt vòng đời server — không import/khởi tạo lại `embeddings`/`llm` mỗi request.

---

## 7. Test case đã chạy (số liệu thật, không phải ước lượng)

### 7.1. Pipeline nạp tài liệu (đo lại sau khi mở rộng định dạng + OCR + phiên âm)

| Mốc | File đọc được | Vector |
|---|---|---|
| Trước nâng cấp (chỉ PDF có sẵn lớp chữ) | 114/215 | 2.339 |
| Sau khi đồng bộ Drive và mở rộng định dạng (.doc, excel theo sheet, pptx theo slide, video) | 114/215 | 4.874 |
| Sau khi OCR 99 PDF bản scan | **211/215** | **8.827** |

OCR: 1.479 trang, thu được 2,86 triệu ký tự, 50 phút trên máy 8 lõi (6 trang song song), 0 file lỗi.
Phiên âm video: 5 file, 4 file có lời thoại (28 phút video, 10 phút xử lý).

4 file còn lại đều là vấn đề của dữ liệu nguồn, không phải của pipeline:
- 1 `.pptx` hỏng thật (đuôi file là trang HTML lỗi, không phải gói OpenXML) — cần export lại từ PowerPoint.
- 1 video không có lời thoại (video ngôn ngữ ký hiệu cho trẻ điếc).
- 2 file trùng nội dung với file khác.

### 7.2. Benchmark retrieval V1 → V5 (bộ 30 câu hỏi cố định, không đổi qua các bản)
| Bản | Thay đổi | Kết quả |
|---|---|---|
| V1 | Dense retrieval thuần | Phát hiện lỗi trích sai Điều (Điều 9 dân tộc thiểu số cho câu hỏi thời gian đào tạo) |
| V2 | Hybrid FAISS+BM25+RRF | Hallucination tăng vì đưa cả evidence yếu |
| V3 | Relevance filter + rule cấm cứng trong prompt | Giảm hallucination nhưng từ chối oan cả khi có evidence rõ ràng |
| V4 | Evidence dominance ở tầng retrieval | Sửa nhiều case nhưng cắt mất evidence bổ trợ cho câu multi-hop |
| **V5 (baseline chính thức)** | Phân loại câu hỏi đơn/đa đối tượng + context_label | Ổn định nhất — **18/30 đúng**, 3 hallucination |

### 7.3. A/B test LLM: `llama3.2:3b` vs `llama3:latest` (8B)
| | 3B (đã chọn) | 8B |
|---|---|---|
| Accuracy | 17-18/30 | 18/30 |
| Hallucination | 3 | 8 (+2 output hỏng hoàn toàn) |
| Latency/câu | 51s | 126s |

### 7.4. Thử dynamic context cap (V6/V6b) — KHÔNG áp dụng
Thử giảm số evidence gửi LLM theo loại câu hỏi để giảm latency. Kết quả: giảm TTFT 25-35% nhưng **accuracy tụt** (18→15→14/30), xác nhận là regression thật (không phải nhiễu, đã đo baseline-noise giữa 2 lần chạy y hệt code chỉ lệch 1/30 câu). → Giữ nguyên V5.

### 7.5. Latency profiling (V5, 30 câu)
| Tầng | Thời gian | Tỉ lệ |
|---|---|---|
| FAISS + BM25 + hậu xử lý | 0.38s | 0.7% |
| TTFT (chờ token đầu) | 34.9s | 66% |
| Sinh chữ sau token đầu | 17.3s | 33% |

Nguyên nhân TTFT cao: máy **không có GPU rời** (chỉ Intel UHD Graphics tích hợp), Ollama chạy 100% CPU, TTFT tỉ lệ thuận với độ dài context (Pearson r=0.84). → **Không cần tối ưu FAISS**, cần tối ưu context length/Ollama runtime nếu muốn nhanh hơn.

### 7.6. Nhánh URL + Web Context Compression
- 5 case end-to-end: URL HTML tĩnh ✅, URL nhúng trong câu tự nhiên ✅, URL 404 ✅ (không gọi LLM), URL PDF ✅ (báo lỗi rõ, không gọi LLM), câu hỏi không URL ✅ (giữ nguyên pipeline V5).
- Web Context Compression (BM25 top-3 đoạn liên quan câu hỏi): case Fibonacci (từ khóa ở 85% cuối trang 16.533 ký tự) → nén còn 647 ký tự, TTFT 85s→3.4s, **không mất thông tin**.
- Test thêm với 2 URL giáo dục thật: phát hiện case SSL certificate lỗi (`thsp.edu.vn`) → đã thêm xử lý lỗi rõ ràng; phát hiện 1 generation-miss trên trang dạng danh sách thông báo (`hcmue.edu.vn`) → ghi nhận là giới hạn đã biết, chưa sửa.

---

## 8. Giới hạn ĐÃ biết (quan trọng — đừng hứa với người dùng những gì chưa làm)

| Giới hạn | Chi tiết |
|---|---|
| Chất lượng OCR với tài liệu đóng dấu | PDF scan đã được OCR bằng Tesseract (gói tiếng Việt `tessdata_best`). Phần thân văn bản đọc tốt, nhưng vùng con dấu, chữ ký nháy và dấu công văn đến thường lẫn ký tự nhiễu |
| Video không có lời thoại | Phiên âm dựa trên tiếng nói. Video ngôn ngữ ký hiệu hoặc chỉ có nhạc nền sẽ cho 0 đoạn và được đánh dấu "Không có lời thoại" (bộ lọc VAD cố ý chặn, nếu tắt VAD thì Whisper bịa ra câu như "Hãy subscribe cho kênh...") |
| Chữ trong hình ảnh của slide/văn bản | Chỉ trích được text thật; chữ nằm trong ảnh chèn vào .docx/.pptx không đọc được. Ảnh rời (.jpg/.png) tải lên riêng thì có OCR |
| `.doc` đời cũ cần Word hoặc LibreOffice | Máy không có công cụ chuyển đổi thì báo lỗi rõ và hướng dẫn lưu lại thành .docx |
| Không đọc trang web JS-động | Trang React/Vue render nội dung bằng JavaScript → tải về sẽ rỗng, hệ thống báo lỗi rõ, không bịa |
| Không đọc PDF qua URL | Link PDF trực tiếp bị từ chối có thông báo rõ, cần tải file rồi dùng loader riêng |
| Không đọc YouTube / Google Drive private | Báo lỗi rõ, cần pipeline khác |
| Trang danh sách/thông báo (không phải bài viết) | Có thể tải đúng nhưng LLM đôi khi bỏ sót dữ kiện rời rạc (xem 7.6) |
| 1 file `.pptx` hỏng | Cần người dùng export lại từ PowerPoint |
| Chưa test đa người dùng đồng thời | Hiện tại thiết kế cho 1 phiên hỏi-đáp tại 1 thời điểm |

---

## 9. Gợi ý kiến trúc khi thêm tính năng "học sinh upload tài liệu riêng"

Đã thảo luận, khuyến nghị bản tối thiểu trước khi làm hệ thống multi-user đầy đủ:
- Tái sử dụng `tao_loader_cho_file()` + `chunking_utils` + `vector_store.add_documents()` đã có sẵn — không viết lại pipeline.
- Đánh dấu chunk upload bằng metadata (vd `metadata["nguon_upload"] = True`) để phân biệt với kho hệ thống, lọc SAU khi search (FAISS gốc không filter theo metadata lúc search).
- Chưa cần Django/multi-tenant/auth đầy đủ nếu mục tiêu là demo — 1 endpoint FastAPI đơn giản là đủ để chứng minh luồng "upload → xử lý → hỏi được ngay".

---

## 10. Câu hỏi thường gặp

**Đổi model LLM để test khác không cần sửa code?**
Có — set biến môi trường `RAG_LLM_MODEL` (mặc định `llama3.2:3b`).

**Đổi cấu hình retrieval để thử nghiệm?**
Set biến môi trường `RAG_RETRIEVAL_VARIANT` (mặc định `v5` — cấu hình chính thức; `v6b` là nhánh thực nghiệm dynamic-cap, không khuyến nghị dùng mặc định vì đã chứng minh gây regression).

**Cập nhật tài liệu mới vào kho?**
Chạy `capnhat_tailieu_moi.py` (không phải `main.py`) — tự động phát hiện file mới/sửa/xóa qua so sánh hash SHA-256, chỉ embedding lại phần thay đổi.

---

## 11. Phạm vi truy xuất — lọc theo môn / cấp học / lớp / loại tài liệu

### 11.1. Vấn đề cần giải

Kho trộn lẫn văn bản quy phạm, bài giảng nhiều môn và đề kiểm tra nhiều khối. Người đang học Tin học lớp 4 hỏi *"bài 2 nói về gì"* vẫn nhận về chunk **"Bài 2 Động năng Thế năng"** của Vật lí — xét theo từ khóa thì hai đoạn giống nhau thật, nên xếp hạng lại bao nhiêu lần cũng không sửa được. Cách sửa duy nhất là **thu hẹp phạm vi trước khi tìm**.

### 11.2. Cách gắn nhãn (`phan_loai_giao_duc.py`)

Chạy bằng quy tắc, **không gọi LLM** — 233 tài liệu nhân một lượt LLM là vài tiếng trên CPU máy này, trong khi dấu hiệu cần tìm chỉ là mấy chục từ khóa cố định (cùng lý do với `tinh_luong.py`).

| Nguyên tắc | Lý do |
|---|---|
| Suy từ **tên file trước**, nội dung sau | Tên file trong kho đặt khá kỷ luật; nội dung PDF scan qua OCR luôn có nhiễu |
| Mỗi trường là **danh sách**, không phải một giá trị | Một thông tư áp cho cả tiểu học lẫn THCS — ép về một cấp học là bịa |
| Nội dung chỉ **bổ sung** trường còn trống, không ghi đè tên file | Văn bản nào chẳng nhắc tên môn khác một lần ở phần căn cứ |
| Văn bản quy phạm chỉ được gắn môn khi có chữ "môn"/"chương trình" | Không chắn thì *"Thông tư quy định ứng dụng công nghệ trong giáo dục đại học"* thành môn Công nghệ |
| Không có dấu hiệu thì **để trống** | Thà nhận chưa phân loại còn hơn gắn nhầm — người dùng tin là đã lọc đúng |

Bảng nhãn được dựng lúc khởi động từ chính các chunk đã lập chỉ mục (không đọc lại file gốc, không embed lại), lưu ra `phan_loai_tai_lieu.json`, rồi chép xuống metadata từng chunk **trước khi dựng BM25** — dựng sau thì nhánh BM25 lọc hụt.

### 11.3. Kết quả trên kho thật (đo lúc kho có 241 tài liệu)

| | Số tài liệu |
|---|---|
| Đã gắn được ít nhất một nhãn | **185 / 241 (77%)** |
| Chưa phân loại | 56 |
| Văn bản quy phạm / Bài giảng / Học liệu khác / Đề kiểm tra | 137 / 62 / 29 / 13 |
| Môn nhiều nhất | Tin học 39, Khoa học 4, Công nghệ 3, Lí luận chính trị 3 |
| Cấp học | Đại học 73, Tiểu học 48, GDNN 43, Mầm non 27, GDTX 24, THPT 24, THCS 19 |
| Lớp | Lớp 5: 20, lớp 4: 5, lớp 3: 3, lớp 10-12: mỗi lớp 1 |

63 tài liệu có nhãn môn (31 suy từ tên file, 26 từ nội dung, 6 từ cả hai).
Nhãn **môn** ít hơn nhãn **cấp học** rất nhiều, và đó là chủ ý: kho này phần lớn
là văn bản quy phạm, mà văn bản quy phạm có phạm vi cấp học rõ ràng chứ hiếm
khi thuộc về một môn. Mỗi lần siết quy tắc (xem 11.2) đều làm số nhãn môn giảm
đi — phần giảm là các tài liệu trước đó bị gắn nhầm, kiểm tra từng cái một trên
kho thật chứ không phải ước lượng.

### 11.4. API

**`GET /api/bo-loc`** — danh sách lựa chọn kèm số tài liệu từng nhãn (chỉ liệt kê nhãn có tài liệu):

```json
{
  "tong_tai_lieu": 233, "chua_phan_loai": 48,
  "mon_hoc": [{"gia_tri": "Tin học", "nhan": "Tin học", "so_tai_lieu": 49}],
  "lop": [{"gia_tri": 4, "nhan": "Lớp 4", "so_tai_lieu": 5}],
  "cap_hoc": [...], "loai_noi_dung": [...]
}
```

**`POST /api/chat/stream`** — thêm trường `pham_vi` (bỏ trống = hỏi cả kho):

```json
{ "question": "Bài 2 nói về gì?", "pham_vi": { "mon_hoc": ["Tin học"], "lop": [4] } }
```

Giá trị lạ bị loại bỏ chứ không làm hỏng request: gửi môn không có thật sẽ rơi vào nhánh *"không lọc gì"*, **không** phải nhánh *"không tài liệu nào khớp"* — hai thứ này khiến người dùng hiểu hoàn toàn khác nhau.

### 11.5. Ba điểm đã xử lý riêng

1. **FAISS không lọc lúc tìm.** Lấy đúng 15 ứng viên rồi mới lọc thì phạm vi hẹp thường còn 0-1 đoạn dù kho có sẵn hàng chục đoạn đúng → khi có bộ lọc, rổ ứng viên dense nới ra 6 lần trước khi lọc (`HE_SO_MO_RONG_KHI_LOC`).
2. **Cache ngữ nghĩa bị tắt khi có lọc.** Cùng một câu hỏi nhưng khác phạm vi là hai câu hỏi khác nhau; phát lại câu trả lời dựng từ tài liệu ngoài phạm vi chính là thứ bộ lọc sinh ra để ngăn.
3. **Lời từ chối nói rõ nguyên nhân.** Đang lọc mà trả về *"không có trong tài liệu"* trống không thì người dùng kết luận nhầm là kho thiếu tài liệu — câu trả lời nêu đúng phạm vi đang lọc và gợi ý bỏ bớt bộ lọc.

### 11.6. Giới hạn của tầng này

| Giới hạn | Chi tiết |
|---|---|
| 48 tài liệu chưa phân loại | Tên file không nói gì (`Slide thuyet trinh.pptx`) và phần đầu nội dung cũng không. Bật bộ lọc thì các tài liệu này **không được xét** — có chủ đích, nhưng nghĩa là lọc hẹp có thể bỏ sót |
| Lớp chỉ nhận ra khi tên file nói rõ | `"lớp 4"`, `"khối 4"`, `"Tin4"`, `"GDCD 12"`. Cố tình **không** đọc `"Bài 4"` là lớp 4 |
| Nhãn dựa vào từ khóa, không hiểu nội dung | Tài liệu đặt tên sai sẽ gắn nhãn sai. `phan_loai_tai_lieu.json` mở ra sửa tay được, có trường `nguon` ghi rõ nhãn suy từ tên file hay từ nội dung |
| Chưa có CLO / độ khó / học kỳ | Mục 16 trong danh sách tính năng mới làm được phần môn/cấp/lớp/loại |
| Nhãn môn suy từ nội dung khá dè dặt | Nội dung chỉ được gắn môn khi nói tới **đúng một** môn; liệt kê nhiều môn (thời khóa biểu, bài học lấy môn khác làm ví dụ) thì bỏ qua hết. Thà để trống còn hơn để bộ lọc môn Toán trả về bài Tin học |
