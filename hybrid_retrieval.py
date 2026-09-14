"""
HYBRID RETRIEVAL: FAISS (dense) + BM25 (lexical) + Reciprocal Rank Fusion
============================================================================
Thay cho similarity_search_with_relevance_scores + score_threshold cứng.

Benchmark 30 câu (xem benchmark_output.txt) cho thấy score_threshold=0.5
chặn hoàn toàn ~30% câu hỏi dù nội dung tồn tại trong kho - chủ yếu câu hỏi
ngắn/từ khóa chính xác ("Điều 58 quy định gì?", "Bài 6 nói về gì?") mà dense
embedding (bge-m3) không tính đủ tương đồng, trong khi đây lại đúng là điểm
mạnh của tìm kiếm từ khóa (BM25). Không có threshold cứng nào cắt đúng ranh
giới đúng/sai vì bản chất dense similarity không tuyến tính với độ liên quan.

Cũng xử lý riêng "balanced retrieval" cho câu hỏi so sánh 2 thực thể (2 Điều,
hoặc "A và B") - benchmark cho thấy nếu để top-k toàn cục, 1 thực thể có thể
chiếm hết chunk, khiến LLM chỉ thấy 1 phía hoặc trộn lẫn số liệu của cả hai.
"""

import hashlib
import os
import re
import unicodedata

from langchain_community.retrievers import BM25Retriever
from langchain_core.documents import Document

SO_UNG_VIEN_MOI_RETRIEVER = 15  # top-k lấy từ mỗi retriever trước khi fuse
SO_KET_QUA_CUOI = int(os.getenv("RAG_SO_BANG_CHUNG", "4"))  # chunk đưa vào prompt
# 4 thay vì 5: chunk thứ 5 hiếm khi đổi được câu trả lời nhưng luôn cộng thêm
# ~400 token prompt, tức khoảng 15 giây chờ trên CPU.
RRF_K = 60                       # hằng số chuẩn trong công thức RRF
SO_CHUNK_TOI_DA_MOI_NGUON = 2
# Khi có lọc phạm vi thì rổ ứng viên phải rộng ra trước khi lọc (xem
# truy_hoi_hybrid). 6 lần là mức đủ để một môn hẹp vẫn còn ứng viên mà tìm
# dense vẫn dưới một giây trên kho ~8.800 vector.
HE_SO_MO_RONG_KHI_LOC = 6

TU_DUNG = {
    "ai", "bao", "các", "cái", "cho", "có", "của", "đang", "được", "gì",
    "hay", "hiện", "hỏi", "không", "là", "làm", "một", "nào", "những",
    "ra", "sao", "theo", "thế", "thì", "trong", "từ", "và", "về", "với",
}


# Kho tài liệu giáo dục dùng viết tắt dày đặc trong TÊN FILE và tiêu đề bảng
# ("TKB-du-kien...", "PPCT-5.docx", "KHBD tiết 02"), trong khi người dùng lại hỏi
# bằng cụm đầy đủ. BM25 chấm theo từ nên không nối được hai cách viết này; mở
# rộng truy vấn hai chiều rẻ hơn nhiều so với chạy thêm một mô hình rerank.
TU_DONG_NGHIA = {
    "tkb": ["thời", "khóa", "biểu"],
    "ppct": ["phân", "phối", "chương", "trình"],
    "khbd": ["kế", "hoạch", "bài", "dạy"],
    "gdpt": ["giáo", "dục", "phổ", "thông"],
    "gdtx": ["giáo", "dục", "thường", "xuyên"],
    "gdnn": ["giáo", "dục", "nghề", "nghiệp"],
    "gdmn": ["giáo", "dục", "mầm", "non"],
    "bgddt": ["bộ", "giáo", "dục", "đào", "tạo"],
    "hs": ["học", "sinh"],
    "gv": ["giáo", "viên"],
    "sgk": ["sách", "giáo", "khoa"],
    "hk": ["học", "kỳ"],
    "cntt": ["công", "nghệ", "thông", "tin"],
    "nls": ["năng", "lực", "số"],
    "ai": ["trí", "tuệ", "nhân", "tạo"],
    "vtvl": ["vị", "trí", "việc", "làm"],
    "tt": ["thông", "tư"],
    "nd": ["nghị", "định"],
    "cv": ["công", "văn"],
}
# Chiều ngược lại: hỏi "thời khóa biểu" thì cũng tìm được file đặt tên "TKB".
CUM_THANH_VIET_TAT = {
    tuple(cum): viet_tat for viet_tat, cum in TU_DONG_NGHIA.items() if len(cum) > 1
}


def mo_rong_truy_van(tokens: list[str], cau_hoi_goc: str = "") -> list[str]:
    """Thêm dạng viết tắt/đầy đủ tương ứng vào cuối danh sách token của truy vấn."""
    mo_rong = list(tokens)
    for tu in tokens:
        mo_rong.extend(TU_DONG_NGHIA.get(tu, []))
    for cum, viet_tat in CUM_THANH_VIET_TAT.items():
        if all(tu in tokens for tu in cum) and viet_tat not in mo_rong:
            mo_rong.append(viet_tat)
    # "AI" viết hoa là công nghệ, còn "ai" viết thường là từ để hỏi - từ để hỏi
    # nằm trong TU_DUNG nên đã bị loại trước khi tới đây. Chỉ bung nghĩa công
    # nghệ khi người dùng thực sự viết hoa, nhờ vậy "ai được miễn học phí" không
    # bị kéo về nhóm tài liệu tích hợp AI.
    if re.search(r"\bAI\b", cau_hoi_goc):
        mo_rong.extend(["ai", "trí", "tuệ", "nhân", "tạo"])
    return mo_rong


def tach_tu_tieng_viet(van_ban: str) -> list[str]:
    """Chuẩn hóa Unicode, chữ hoa/thường và dấu câu trước khi chấm BM25."""
    van_ban = unicodedata.normalize("NFC", van_ban or "").lower()
    # [^\W_] = chữ và số nhưng KHÔNG gồm dấu gạch dưới: tên file trong kho dùng
    # "_" làm dấu ngăn từ ("Bai1_TinHoc5"), coi nó là ký tự từ sẽ dính "1_tin".
    return [
        tu for tu in re.findall(r"[^\W_]+", van_ban, flags=re.UNICODE)
        if len(tu) > 1 and tu not in TU_DUNG
    ]


def bo_dau(van_ban: str) -> str:
    """'Tin học' -> 'tin hoc'. Tên file trong kho hầu hết viết không dấu."""
    tach_roi = unicodedata.normalize("NFD", van_ban or "")
    khong_dau = "".join(c for c in tach_roi if not unicodedata.combining(c))
    return khong_dau.replace("đ", "d").replace("Đ", "D")


def tach_camel_va_so(van_ban: str) -> str:
    """
    "Bai1_TinHoc5.pptx" -> "Bai 1 Tin Hoc 5", "PhanPhoi-ChuongTrinh-Tin4" -> từng từ.

    Cố tình dùng isupper()/isdigit() thay cho regex dải ký tự: dải "À-Ỹ" trong
    Unicode có xen cả chữ thường tiếng Việt (ọ, ộ, ế...), nên regex kiểu
    (?<=[a-z])(?=[A-ZÀ-Ỹ]) sẽ cắt ngay giữa từ - "học" thành "h" + "ọc".
    """
    ket_qua = []
    truoc = ""
    for ky_tu in van_ban or "":
        chu_hoa_sau_chu_thuong = ky_tu.isupper() and truoc.islower()
        ranh_gioi_so = (
            (ky_tu.isdigit() and truoc.isalpha())
            or (ky_tu.isalpha() and truoc.isdigit())
        )
        if chu_hoa_sau_chu_thuong or ranh_gioi_so:
            ket_qua.append(" ")
        ket_qua.append(ky_tu)
        truoc = ky_tu
    return "".join(ket_qua)


def tach_tu_mo_rong(van_ban: str) -> list[str]:
    """
    Bản tách từ dùng cho BM25, sinh thêm hai biến thể để nối được cách viết
    của người dùng với cách đặt tên file trong kho:

      "Bài 1 môn Tin học lớp 5"  -> bài, môn, tin, học, lớp + bai, tin, hoc, lop
      "Bai1_TinHoc5.pptx"        -> bai, tin, hoc + 1, 5

    Nếu không tách chữ hoa và không bỏ dấu thì hai chuỗi trên KHÔNG có một
    token chung nào, dù cùng nói về một bài học - đúng lỗi đo được ở benchmark.
    Dạng có dấu vẫn được giữ nguyên nên phân biệt dấu vẫn có trọng số.
    """
    tokens = tach_tu_tieng_viet(tach_camel_va_so(van_ban))
    da_co = set(tokens)
    them = []
    for tu in tokens:
        khong_dau = bo_dau(tu)
        if khong_dau != tu and khong_dau not in da_co:
            da_co.add(khong_dau)
            them.append(khong_dau)
    return tokens + them


def _khoa_chunk(doc) -> str:
    khoa = doc.metadata.get("_chunk_key")
    if khoa:
        return khoa
    du_lieu = "\x1f".join([
        doc.metadata.get("source_file", ""),
        doc.metadata.get("chapter", "") or "",
        doc.metadata.get("article", "") or "",
        doc.page_content,
    ])
    khoa = hashlib.sha1(du_lieu.encode("utf-8")).hexdigest()
    doc.metadata["_chunk_key"] = khoa
    return khoa


def xay_dung_bm25(vector_store):
    """Dựng BM25 có chuẩn hóa tiếng Việt và lập chỉ mục cả tên nguồn."""
    tat_ca_docs = list(vector_store.docstore._dict.values())
    docs_bm25 = []
    for doc in tat_ca_docs:
        khoa = _khoa_chunk(doc)
        tieu_de = " ".join(filter(None, [
            doc.metadata.get("source_file"),
            doc.metadata.get("chapter"),
            doc.metadata.get("article"),
            doc.metadata.get("context_label"),
        ]))
        metadata = dict(doc.metadata)
        metadata["_chunk_key"] = khoa
        metadata["_noi_dung_goc"] = doc.page_content
        docs_bm25.append(Document(
            page_content=f"{tieu_de}\n{doc.page_content}",
            metadata=metadata,
        ))
    bm25 = BM25Retriever.from_documents(
        docs_bm25, preprocess_func=tach_tu_mo_rong
    )
    bm25.k = SO_UNG_VIEN_MOI_RETRIEVER
    return bm25


def _ket_qua_bm25_co_diem(cau_hoi, bm25_retriever, so_ung_vien=SO_UNG_VIEN_MOI_RETRIEVER,
                          bo_loc=None):
    """Không đưa các tài liệu BM25 điểm 0 vào RRF như retriever mặc định."""
    tokens = mo_rong_truy_van(bm25_retriever.preprocess_func(cau_hoi), cau_hoi)
    if not tokens:
        return []
    scores = bm25_retriever.vectorizer.get_scores(tokens)
    thu_tu = sorted(range(len(scores)), key=lambda i: scores[i], reverse=True)
    ket_qua = []
    for vi_tri in thu_tu:
        score = float(scores[vi_tri])
        if score <= 0:
            break
        doc = bm25_retriever.docs[vi_tri]
        if bo_loc is not None and not bo_loc(doc):
            continue
        doc.metadata["_bm25_score"] = score
        ket_qua.append(doc)
        if len(ket_qua) >= so_ung_vien:
            break
    return ket_qua


def rrf_fusion(*danh_sach_ket_qua, k=RRF_K):
    """
    Reciprocal Rank Fusion: hợp nhất nhiều danh sách xếp hạng (dense, bm25...)
    thành một xếp hạng duy nhất, không phụ thuộc thang điểm gốc của từng
    retriever (dense similarity và BM25 score không so sánh trực tiếp được).
    danh_sach_ket_qua: các tuple (ten_retriever, [Document,...]).
    Dùng khóa ổn định theo nguồn + nội dung để nhận diện cùng một chunk giữa
    dense và BM25 (BM25 có thêm tiêu đề nguồn vào văn bản lập chỉ mục).
    """
    diem = {}
    tai_lieu = {}
    nguon_dong_gop = {}
    for ten_retriever, ket_qua in danh_sach_ket_qua:
        for hang, doc in enumerate(ket_qua):
            khoa = _khoa_chunk(doc)
            diem[khoa] = diem.get(khoa, 0.0) + 1.0 / (k + hang + 1)
            tai_lieu.setdefault(khoa, doc)
            nguon_dong_gop.setdefault(khoa, set()).add(ten_retriever)

    xep_hang = sorted(diem.items(), key=lambda x: -x[1])
    ket_qua_cuoi = []
    for khoa, diem_rrf in xep_hang:
        doc = tai_lieu[khoa]
        if doc.metadata.get("_noi_dung_goc") is not None:
            metadata = dict(doc.metadata)
            noi_dung_goc = metadata.pop("_noi_dung_goc")
            doc = Document(page_content=noi_dung_goc, metadata=metadata)
        doc.metadata["_rrf_score"] = diem_rrf
        doc.metadata["_nguon"] = "+".join(sorted(nguon_dong_gop[khoa]))
        ket_qua_cuoi.append(doc)
    return ket_qua_cuoi


def xep_hang_theo_lien_quan(cau_hoi, documents, so_ket_qua):
    """Rerank theo độ phủ từ khóa, tiêu đề và đa dạng nguồn."""
    tu_cau_hoi = set(mo_rong_truy_van(tach_tu_mo_rong(cau_hoi), cau_hoi))
    cau_hoi_chuan = " ".join(tach_tu_tieng_viet(cau_hoi))
    for doc in documents:
        tu_noi_dung = set(tach_tu_mo_rong(doc.page_content))
        ten_nguon = doc.metadata.get("source_file", "")
        tieu_de_day_du = " ".join(filter(None, [
            ten_nguon,
            doc.metadata.get("chapter"),
            doc.metadata.get("article"),
            doc.metadata.get("context_label"),
        ]))
        tu_tieu_de = set(tach_tu_mo_rong(tieu_de_day_du))
        do_phu = len(tu_cau_hoi & tu_noi_dung) / max(1, len(tu_cau_hoi))
        do_phu_tieu_de = len(tu_cau_hoi & tu_tieu_de) / max(1, len(tu_cau_hoi))
        dong_thuan = 1.0 if doc.metadata.get("_nguon") == "bm25+dense" else 0.0
        ma_khoa = set(re.findall(r"\bk\d+\b", " ".join(tu_tieu_de)))
        phat_lech_pham_vi = 0.012 if any(ma not in cau_hoi_chuan for ma in ma_khoa) else 0.0
        # Văn bản đã bị một văn bản khác trong kho thay thế thì hạ bậc, nhưng
        # không loại hẳn: người dùng vẫn có quyền hỏi về quy định cũ, và câu trả
        # lời sẽ kèm cảnh báo hiệu lực. Mức phạt đặt ngang một bậc RRF.
        phat_het_hieu_luc = 0.015 if doc.metadata.get("_het_hieu_luc") else 0.0
        doc.metadata["_lexical_coverage"] = round(do_phu, 4)
        doc.metadata["_retrieval_score"] = (
            doc.metadata.get("_rrf_score", 0.0)
            + 0.025 * do_phu
            + 0.035 * do_phu_tieu_de
            + 0.004 * dong_thuan
            - phat_lech_pham_vi
            - phat_het_hieu_luc
        )

    xep_hang = sorted(
        documents, key=lambda d: d.metadata.get("_retrieval_score", 0.0), reverse=True
    )
    cau_hoi_thuong = cau_hoi.lower()
    cau_hoi_rong = any(cum in cau_hoi_thuong for cum in [
        "tóm tắt", "tổng hợp", "toàn bộ", "nội dung chính", "các quy định chính",
    ])
    gioi_han_moi_nguon = 4 if cau_hoi_rong else SO_CHUNK_TOI_DA_MOI_NGUON
    ket_qua = []
    dem_theo_nguon = {}
    noi_dung_da_lay = set()
    for doc in xep_hang:
        nguon = doc.metadata.get("source_file", "không rõ")
        if dem_theo_nguon.get(nguon, 0) >= gioi_han_moi_nguon:
            continue
        # Kho có hàng chục bộ slide dùng chung trang bìa/mục tiêu/củng cố. Nếu
        # không khử trùng, mấy suất EVIDENCE ít ỏi bị nội dung giống hệt nhau
        # chiếm mất, trong khi đoạn thực sự trả lời được câu hỏi bị đẩy ra.
        dau_van_ban = " ".join(doc.page_content.split())[:200].casefold()
        if dau_van_ban in noi_dung_da_lay:
            continue
        noi_dung_da_lay.add(dau_van_ban)
        ket_qua.append(doc)
        dem_theo_nguon[nguon] = dem_theo_nguon.get(nguon, 0) + 1
        if len(ket_qua) >= so_ket_qua:
            break
    return ket_qua


_DIEU_PATTERN = re.compile(r"Điều\s+\d+", re.IGNORECASE)


def tach_thuc_the_so_sanh(cau_hoi: str):
    """
    Nếu câu hỏi có dạng so sánh 2 thực thể (2 "Điều X", hoặc "...A và B"),
    trả về danh sách cụm từ cần truy hồi RIÊNG - để mỗi thực thể có "suất"
    chunk cân bằng thay vì 1 bên chiếm hết top-k toàn cục. Trả về None nếu
    không phải câu so sánh.
    """
    dieu = _DIEU_PATTERN.findall(cau_hoi)
    dieu_khac_nhau = list(dict.fromkeys(d.lower() for d in dieu))
    if len(dieu_khac_nhau) >= 2:
        # giữ nguyên chữ hoa/thường bản gốc, chỉ khử trùng theo lower
        da_thay = set()
        ket_qua = []
        for d in dieu:
            if d.lower() not in da_thay:
                da_thay.add(d.lower())
                ket_qua.append(d)
        return ket_qua

    co_tu_khoa_so_sanh = any(
        tu in cau_hoi.lower() for tu in ["so sánh", "khác nhau", "giống nhau"]
    )
    if co_tu_khoa_so_sanh and " và " in cau_hoi:
        truoc, sau = cau_hoi.split(" và ", 1)
        tu_truoc = truoc.strip().split()
        cum_a = " ".join(tu_truoc[-8:])  # vài từ cuối trước "và" - đủ ngữ cảnh cụm A
        cum_b = sau.strip().rstrip("?.")
        if len(cum_a) > 3 and len(cum_b) > 3:
            return [cum_a, cum_b]

    return None


def truy_hoi_hybrid(cau_hoi, vector_store, bm25_retriever, so_ket_qua=SO_KET_QUA_CUOI,
                    bo_loc=None):
    """Truy hồi 1 câu hỏi (không tách thực thể) bằng dense + BM25 + RRF."""
    so_ung_vien = SO_UNG_VIEN_MOI_RETRIEVER
    if bo_loc is not None:
        # FAISS không lọc theo metadata lúc tìm, chỉ lọc được SAU khi có kết
        # quả. Lấy đúng 15 ứng viên rồi mới lọc thì một phạm vi hẹp (một môn,
        # một lớp) thường còn lại 0-1 đoạn dù kho có sẵn hàng chục đoạn đúng,
        # nên phải nới rổ ứng viên ra trước khi lọc.
        so_ung_vien *= HE_SO_MO_RONG_KHI_LOC

    dense_co_diem = vector_store.similarity_search_with_score(cau_hoi, k=so_ung_vien)
    ket_qua_dense = []
    for doc, distance in dense_co_diem:
        if bo_loc is not None and not bo_loc(doc):
            continue
        doc.metadata["_dense_distance"] = float(distance)
        ket_qua_dense.append(doc)
        if len(ket_qua_dense) >= SO_UNG_VIEN_MOI_RETRIEVER:
            break
    ket_qua_bm25 = _ket_qua_bm25_co_diem(
        cau_hoi, bm25_retriever, SO_UNG_VIEN_MOI_RETRIEVER, bo_loc
    )
    hop_nhat = rrf_fusion(("dense", ket_qua_dense), ("bm25", ket_qua_bm25))
    return xep_hang_theo_lien_quan(cau_hoi, hop_nhat, so_ket_qua)


def truy_hoi(cau_hoi, vector_store, bm25_retriever, so_ket_qua=SO_KET_QUA_CUOI,
             bo_loc=None):
    """
    Điểm vào chính: tự phát hiện câu so sánh để làm balanced retrieval theo
    từng thực thể, nếu không thì truy hồi hybrid bình thường trên cả câu hỏi.

    `bo_loc` là hàm nhận Document trả về bool - dùng cho phạm vi truy xuất
    (môn/lớp/cấp học). Để None thì tìm trên cả kho như trước.
    """
    thuc_the = tach_thuc_the_so_sanh(cau_hoi)
    if not thuc_the:
        return truy_hoi_hybrid(cau_hoi, vector_store, bm25_retriever, so_ket_qua, bo_loc)

    so_moi_thuc_the = max(2, so_ket_qua // len(thuc_the))
    ket_qua_theo_thuc_the = []
    da_thay_noi_dung = set()
    for cum in thuc_the:
        for doc in truy_hoi_hybrid(
            cum, vector_store, bm25_retriever, so_moi_thuc_the, bo_loc
        ):
            if doc.page_content not in da_thay_noi_dung:
                da_thay_noi_dung.add(doc.page_content)
                doc.metadata["_cum_truy_van"] = cum
                ket_qua_theo_thuc_the.append(doc)

    return ket_qua_theo_thuc_the
