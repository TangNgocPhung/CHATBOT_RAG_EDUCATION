"""
CẬP NHẬT TÀI LIỆU MỚI TỪ KHO DỮ LIỆU CỤC BỘ (hash-based incremental update)
=======================================================================
Chạy file này SAU KHI đã thêm/sửa/xóa tài liệu trong data_giao_duc.
So sánh SHA-256 hash của từng file với "sổ ghi chép" để phân loại:
  - NEW       -> chunk + embed + add vào FAISS
  - MODIFIED  -> xóa vector cũ của file đó (theo chunk_id đã lưu) rồi embed lại
  - DELETED   -> xóa vector khỏi FAISS
  - UNCHANGED -> bỏ qua
"""

import os
import json
from langchain_ollama import OllamaEmbeddings
from langchain_community.vectorstores import FAISS
from tqdm import tqdm

from chunking_utils import (
    DINH_DANG_HO_TRO, chunk_theo_cau_truc, suy_metadata, tao_text_splitter_fallback,
    tinh_hash_file, load_file_an_toan_neu_can,
)


# ============================================================
# CẤU HÌNH - PHẢI KHỚP VỚI main.py
# ============================================================
THU_MUC_DU_AN = os.path.dirname(os.path.abspath(__file__))
DATA_PATH = os.path.abspath(os.getenv(
    "RAG_DATA_PATH",
    os.path.join(THU_MUC_DU_AN, "ollama-rag-desktop", "data_giao_duc"),
))
DUONG_DAN_LUU_INDEX = os.getenv(
    "RAG_INDEX_PATH", os.path.join(THU_MUC_DU_AN, "faiss_index_data_giao_duc")
)
DUONG_DAN_SO_GHI_CHEP = os.getenv(
    "RAG_LEDGER_PATH", os.path.join(THU_MUC_DU_AN, "data_giao_duc_da_xu_ly.json")
)  # "sổ" ghi nhớ hash + chunk_id của từng file



def doc_so_ghi_chep() -> dict:
    """
    Đọc sổ ghi chép. Hỗ trợ tự nâng cấp từ định dạng cũ (list đường dẫn)
    lên định dạng mới: {duong_dan: {"hash": ..., "chunk_ids": [...], "status": "processed"}}.
    Các file từ sổ cũ chưa có "chunk_ids" -> để rỗng (không xóa được vector cũ
    của chúng một cách chính xác nếu sau này bị sửa nội dung).
    """
    if not os.path.exists(DUONG_DAN_SO_GHI_CHEP):
        return {}

    with open(DUONG_DAN_SO_GHI_CHEP, "r", encoding="utf-8") as f:
        du_lieu = json.load(f)

    if isinstance(du_lieu, list):
        print("⚠️  Sổ ghi chép đang ở định dạng cũ (danh sách đường dẫn).")
        print("   Đang nâng cấp lên định dạng mới có hash + chunk_id...")
        so_moi = {}
        for duong_dan in du_lieu:
            ban_ghi = {"status": "processed", "chunk_ids": []}
            if os.path.exists(duong_dan):
                ban_ghi["hash"] = tinh_hash_file(duong_dan)
            else:
                ban_ghi["hash"] = None
            so_moi[duong_dan] = ban_ghi
        return so_moi

    return du_lieu


def luu_so_ghi_chep(so_ghi_chep: dict):
    with open(DUONG_DAN_SO_GHI_CHEP, "w", encoding="utf-8") as f:
        json.dump(so_ghi_chep, f, ensure_ascii=False, indent=2)


def doc_va_chunk_file(duong_dan: str, text_splitter, bao_tien_do_ocr=None):
    """
    .pdf/.docx load trực tiếp (nhanh, đã kiểm chứng an toàn); .pptx/.html/.txt
    load qua subprocess cô lập (chống segfault từ UnstructuredFileLoader).
    Sau đó chunk theo cấu trúc Chương/Điều (chunking_utils.chunk_theo_cau_truc).
    """
    docs, loi = load_file_an_toan_neu_can(
        duong_dan, bao_tien_do_ocr=bao_tien_do_ocr
    )
    if loi is not None:
        raise RuntimeError(loi)
    for d in docs:
        d.metadata.update(suy_metadata(duong_dan, DATA_PATH))
    return chunk_theo_cau_truc(docs, text_splitter)


def _bat_utf8_cho_console() -> None:
    """Console Windows mặc định là cp1252 nên in tiếng Việt sẽ ném UnicodeEncodeError."""
    import sys

    for luong in (sys.stdout, sys.stderr):
        if hasattr(luong, "reconfigure"):
            luong.reconfigure(encoding="utf-8", errors="replace")


def main(bao_tien_do=None):
    _bat_utf8_cho_console()

    def bao(**du_lieu):
        """Không để lỗi hiển thị tiến độ làm hỏng việc lập chỉ mục."""
        if bao_tien_do is not None:
            try:
                bao_tien_do(du_lieu)
            except Exception:
                pass

    if not os.path.exists(DATA_PATH):
        raise FileNotFoundError(f"Không tìm thấy: {DATA_PATH}")

    if not os.path.exists(DUONG_DAN_LUU_INDEX):
        raise FileNotFoundError(
            f"Chưa có vector store tại {DUONG_DAN_LUU_INDEX}. "
            f"Hãy chạy main.py trước để tạo vector store ban đầu."
        )

    # --- Bước 1: Quét toàn bộ file hiện có trong kho dữ liệu ---
    bao(
        stage="scanning", label="Đang quét kho tài liệu...", percent=1,
        completed=0, total=0, unit="tệp", current_file="", detail="",
    )
    tat_ca_file_hien_co = []
    for root, dirs, files in os.walk(DATA_PATH):
        for f in files:
            if os.path.splitext(f)[1].lower() in DINH_DANG_HO_TRO:
                tat_ca_file_hien_co.append(os.path.join(root, f))

    print(f"Tổng số file văn bản trong kho dữ liệu: {len(tat_ca_file_hien_co)}")

    # --- Bước 2: Tính hash hiện tại + phân loại NEW / MODIFIED / UNCHANGED / DELETED ---
    so_ghi_chep = doc_so_ghi_chep()

    print("Đang tính hash để so sánh với sổ ghi chép...")
    hash_hien_tai = {}
    tong_file = len(tat_ca_file_hien_co)
    for thu_tu, duong_dan in enumerate(
        tqdm(tat_ca_file_hien_co, desc="Tính hash", unit="file"), 1
    ):
        bao(
            stage="hashing", label="Đang kiểm tra thay đổi...",
            percent=round(1 + 4 * (thu_tu - 1) / max(1, tong_file), 1),
            completed=thu_tu - 1, total=tong_file, unit="tệp",
            current_file=os.path.basename(duong_dan), detail="Đang tính dấu vân tay",
        )
        try:
            hash_hien_tai[duong_dan] = tinh_hash_file(duong_dan)
        except Exception as e:
            print(f"\n  ⚠️  Không đọc được '{os.path.basename(duong_dan)}' để tính hash: {e}")

    file_moi = []
    file_sua_doi = []
    file_khong_doi = []
    for duong_dan, h in hash_hien_tai.items():
        ban_ghi_cu = so_ghi_chep.get(duong_dan)
        if ban_ghi_cu is None:
            file_moi.append(duong_dan)
        elif ban_ghi_cu.get("hash") != h:
            file_sua_doi.append(duong_dan)
        elif ban_ghi_cu.get("status") == "no_text":
            # File từng không rút được chữ nào (PDF scan, video chưa phiên âm).
            # Nay có thể đã có bản OCR/phiên âm nên thử lại - chúng không có
            # chunk nào trong chỉ mục nên thử lại không tạo dữ liệu trùng.
            # Riêng status "error" thì không thử lại: file hỏng thật, chỉ xử lý
            # khi người dùng upload bản sửa (lúc đó hash đổi).
            file_moi.append(duong_dan)
        else:
            file_khong_doi.append(duong_dan)

    file_bi_xoa = [d for d in so_ghi_chep.keys() if d not in hash_hien_tai]

    print(f"\n🆕 File mới:      {len(file_moi)}")
    print(f"✏️  File bị sửa:   {len(file_sua_doi)}")
    print(f"🗑️  File bị xóa:   {len(file_bi_xoa)}")
    print(f"✅ File không đổi: {len(file_khong_doi)}")

    if not file_moi and not file_sua_doi and not file_bi_xoa:
        print("\n✅ Không có thay đổi nào. Kho tri thức đã cập nhật đầy đủ.")
        bao(
            stage="complete", label="Kho tri thức đã cập nhật", percent=100,
            completed=0, total=0, unit="tệp", current_file="",
            detail="Không có tệp thay đổi",
        )
        return

    # --- Bước 3: Load vector store ---
    print("\nĐang load vector store hiện có...")
    # Máy này 8 luồng CPU: mặc định Ollama chỉ lấy số lõi vật lý nên nhúng chậm
    # hơn ~15%. RAG_EMBED_THREADS=8 ép dùng hết luồng; để trống thì giữ mặc định.
    so_luong_nhung = int(os.getenv("RAG_EMBED_THREADS", "0")) or None
    embeddings = OllamaEmbeddings(
        model=os.getenv("RAG_EMBEDDING_MODEL", "bge-m3"),
        base_url=os.getenv("OLLAMA_BASE_URL", "http://localhost:11434"),
        num_thread=so_luong_nhung,
    )
    vector_store = FAISS.load_local(
        DUONG_DAN_LUU_INDEX, embeddings, allow_dangerous_deserialization=True
    )
    print(f"Vector store hiện có: {vector_store.index.ntotal} vectors.")

    # --- Bước 4: Xóa vector cũ của file bị XÓA hoặc bị SỬA ---
    file_can_xoa_vector = file_bi_xoa + file_sua_doi
    canh_bao_khong_xoa_duoc = []
    if file_can_xoa_vector:
        ids_can_xoa = []
        for duong_dan in file_can_xoa_vector:
            chunk_ids = so_ghi_chep.get(duong_dan, {}).get("chunk_ids") or []
            if chunk_ids:
                ids_can_xoa.extend(chunk_ids)
            else:
                canh_bao_khong_xoa_duoc.append(duong_dan)

        if ids_can_xoa:
            print(f"\nĐang xóa {len(ids_can_xoa)} vector cũ (file bị sửa/xóa)...")
            vector_store.delete(ids=ids_can_xoa)

        if canh_bao_khong_xoa_duoc:
            print(f"\n⚠️  {len(canh_bao_khong_xoa_duoc)} file không có chunk_id đã lưu "
                  f"(được xử lý từ sổ ghi chép định dạng cũ) nên KHÔNG xóa được vector cũ:")
            for d in canh_bao_khong_xoa_duoc:
                print(f"   - {os.path.basename(d)}")
            print("   -> Vector cũ của các file này vẫn còn trong FAISS (dữ liệu trùng lặp).")
            print("   -> Nếu cần chính xác tuyệt đối, hãy xóa faiss_index_data_giao_duc và "
                  "chạy lại main.py để build lại từ đầu.")

    # Bỏ file đã xóa khỏi sổ ngay tại đây: có vậy mốc lưu giữa chừng ở bước 6
    # mới nhất quán - vector đã gỡ thì sổ cũng không còn tham chiếu tới nó.
    for duong_dan in file_bi_xoa:
        so_ghi_chep.pop(duong_dan, None)

    # --- Bước 5: Đọc + chunk file MỚI và file SỬA ĐỔI ---
    file_can_embed = file_moi + file_sua_doi
    print(f"\nĐang đọc và chunk {len(file_can_embed)} file (mới + sửa đổi)...")
    text_splitter = tao_text_splitter_fallback()

    chunks_theo_file = {}
    file_loi = []
    tong_file_can_embed = len(file_can_embed)
    for thu_tu, duong_dan in enumerate(
        tqdm(file_can_embed, desc="Xử lý file", unit="file"), 1
    ):
        ten_file = os.path.basename(duong_dan)

        def bao_ocr(da_xong, tong_trang, *, _thu_tu=thu_tu, _ten=ten_file):
            ty_le_file = da_xong / max(1, tong_trang)
            ty_le_doc = ((_thu_tu - 1) + ty_le_file) / max(1, tong_file_can_embed)
            bao(
                stage="reading", label="Đang đọc và OCR tài liệu...",
                percent=round(5 + 45 * ty_le_doc, 1),
                completed=_thu_tu - 1, total=tong_file_can_embed, unit="tệp",
                current_file=_ten, detail=f"OCR trang {da_xong}/{tong_trang}",
            )

        bao(
            stage="reading", label="Đang đọc và tách nội dung...",
            percent=round(5 + 45 * (thu_tu - 1) / max(1, tong_file_can_embed), 1),
            completed=thu_tu - 1, total=tong_file_can_embed, unit="tệp",
            current_file=ten_file, detail="Đang mở tài liệu",
        )
        try:
            chunks_theo_file[duong_dan] = doc_va_chunk_file(
                duong_dan, text_splitter, bao_tien_do_ocr=bao_ocr
            )
        except Exception as e:
            print(f"\n  ⚠️  Lỗi khi đọc '{os.path.basename(duong_dan)}': {e}")
            file_loi.append(duong_dan)
            # Ghi nhận cả file lỗi vào sổ: nếu không, mỗi lần chạy đều coi nó là
            # "file mới", kho luôn bị báo lệch chỉ mục và lần nào cũng thử đọc
            # lại một file hỏng. Hash được lưu nên khi người dùng upload bản sửa,
            # hash đổi và hệ thống tự thử lại.
            so_ghi_chep[duong_dan] = {
                "hash": hash_hien_tai[duong_dan],
                "chunk_ids": [],
                "status": "error",
                "loi": str(e)[:300],
                "size": os.path.getsize(duong_dan),
                "modified_ns": os.stat(duong_dan).st_mtime_ns,
            }

    tong_chunks = sum(len(c) for c in chunks_theo_file.values())
    if tong_chunks == 0 and not file_bi_xoa:
        print("Không tách được chunk nào từ file mới/sửa đổi, và không có file bị xóa. Dừng lại.")
        vector_store.save_local(DUONG_DAN_LUU_INDEX)
        # Vẫn phải lưu sổ: các file vừa bị đánh dấu lỗi nằm trong đó, không lưu
        # thì lần chạy sau lại coi chúng là file mới và thử đọc lại vô ích.
        luu_so_ghi_chep(so_ghi_chep)
        return

    print(f"\n✅ Đã tách được {tong_chunks} chunks từ {len(chunks_theo_file)} file.")

    # --- Bước 6: Embedding theo batch, add vào FAISS, ghi nhận chunk_id mới cho từng file ---
    # Batch nhỏ thì đỉnh bộ nhớ thấp hơn - máy ít RAM hạ số này xuống.
    KICH_THUOC_BATCH = int(os.getenv("RAG_INDEX_BATCH", "20"))
    # Máy 15 GB chạy CPU: runner Ollama có thể sập giữa một job hai tiếng và
    # save_local chỉ chạy ở cuối, nghĩa là mất sạch. Lưu theo mốc để lần chạy
    # lại đọc sổ và tiếp tục từ đó. 0 = tắt.
    MOC_LUU_MOI = int(os.getenv("RAG_INDEX_MOC_LUU", "10"))
    so_file_da_xong = 0
    file_loi_embed = []
    print(f"\nĐang embedding bằng Ollama...")
    tong_file_embedding = len(chunks_theo_file)
    for thu_tu, (duong_dan, chunks) in enumerate(
        tqdm(chunks_theo_file.items(), desc="Embedding theo file", unit="file"), 1
    ):
        bao(
            stage="embedding", label="Đang tạo vector tìm kiếm...",
            percent=round(50 + 45 * (thu_tu - 1) / max(1, tong_file_embedding), 1),
            completed=thu_tu - 1, total=tong_file_embedding, unit="tệp",
            current_file=os.path.basename(duong_dan),
            detail=f"Đang nhúng {len(chunks)} đoạn văn bản",
        )
        chunk_ids_moi = []
        loi_embed = None
        for i in range(0, len(chunks), KICH_THUOC_BATCH):
            batch = chunks[i: i + KICH_THUOC_BATCH]
            try:
                ids_batch = vector_store.add_documents(batch)
            except Exception as e:
                # Máy ít RAM: runner Ollama có thể chết giữa job. Trước đây lỗi
                # này giết cả lần chạy và mất sạch công. Bỏ file, đi tiếp.
                loi_embed = str(e)[:300]
                if chunk_ids_moi:
                    vector_store.delete(ids=chunk_ids_moi)
                    chunk_ids_moi = []
                break
            chunk_ids_moi.extend(ids_batch)

        if loi_embed:
            # KHÔNG ghi vào sổ: lỗi hạ tầng là tạm thời, không ghi thì lần chạy
            # sau vẫn coi đây là file mới và tự thử lại. Khác với file đọc hỏng
            # ở bước 5 - cái đó ghi vào sổ để khỏi thử lại vô ích.
            file_loi_embed.append((duong_dan, loi_embed))
            continue

        so_ghi_chep[duong_dan] = {
            "hash": hash_hien_tai[duong_dan],
            "chunk_ids": chunk_ids_moi,
            "status": "processed" if chunk_ids_moi else "no_text",
            "size": os.path.getsize(duong_dan),
            "modified_ns": os.stat(duong_dan).st_mtime_ns,
        }

        so_file_da_xong += 1
        if MOC_LUU_MOI and so_file_da_xong % MOC_LUU_MOI == 0:
            vector_store.save_local(DUONG_DAN_LUU_INDEX)
            luu_so_ghi_chep(so_ghi_chep)

    bao(
        stage="saving", label="Đang lưu chỉ mục...", percent=96,
        completed=tong_file_embedding, total=tong_file_embedding, unit="tệp",
        current_file="", detail="Đang ghi FAISS xuống đĩa",
    )
    vector_store.save_local(DUONG_DAN_LUU_INDEX)
    print(f"✅ Đã lưu vector store cập nhật ({vector_store.index.ntotal} vectors).")

    luu_so_ghi_chep(so_ghi_chep)
    bao(
        stage="reloading", label="Đang nạp lại kho tri thức...", percent=98,
        completed=tong_file_embedding, total=tong_file_embedding, unit="tệp",
        current_file="", detail="Chỉ mục đã lưu, đang chuẩn bị tìm kiếm",
    )

    if file_loi_embed:
        print(f"{chr(10)}⚠️  {len(file_loi_embed)} file embedding thất bại (lần chạy sau tự thử lại):")
        for d, e in file_loi_embed:
            print(f"   - {os.path.basename(d)}: {e[:120]}")

    print(f"\n🎉 HOÀN TẤT!")
    print(f"   - Mới:      {len(file_moi) - len([f for f in file_moi if f in file_loi])}")
    print(f"   - Sửa lại:  {len(file_sua_doi) - len([f for f in file_sua_doi if f in file_loi])}")
    print(f"   - Đã xóa:   {len(file_bi_xoa)}")
    if file_loi:
        print(f"⚠️  {len(file_loi)} file bị lỗi, chưa xử lý được: "
              f"{[os.path.basename(f) for f in file_loi]}")
        print("   (Những file này sẽ được thử lại ở lần chạy sau)")


if __name__ == "__main__":
    main()
