"""
TỪ VỰNG KHO TÀI LIỆU - DÙNG ĐỂ NHẬN RA CÂU HỎI LẠC ĐỀ
======================================================
Vì sao cần module này: độ phủ từ vựng thô (`_lexical_coverage`) đếm mọi từ như
nhau, nên câu "Hướng dẫn nấu phở bò Hà Nội chuẩn vị cần những nguyên liệu gì?"
vẫn đạt độ phủ cao - "hướng", "dẫn", "chuẩn", "nội", "nguyên", "liệu" đều dày
đặc trong văn bản giáo dục. Benchmark đo được câu này chạy hết 189 giây chỉ để
nói "tôi không biết".

Tín hiệu đúng không phải BAO NHIÊU từ trùng, mà là những từ MANG CHỦ ĐỀ có
trùng không. "phở", "nấu" là từ hiếm - chúng quyết định câu hỏi nói về cái gì;
"hướng", "dẫn" thì không. Đó chính là IDF: từ càng hiếm trong kho, trọng số
càng cao. Kho chưa từng thấy từ nào thì từ đó nhận trọng số cao nhất.

Hai chỉ số được tính:
  - ty_le_tu_la:  bao nhiêu phần "sức nặng chủ đề" của câu hỏi nằm ở những từ
                  kho CHƯA TỪNG có. Cao = hỏi về thứ ngoài kho.
  - do_phu_idf:   bao nhiêu phần sức nặng đó thực sự xuất hiện trong các đoạn
                  vừa truy hồi. Thấp = truy hồi không chạm được vào chủ đề.

Cả hai đều chỉ đối chiếu chuỗi, không gọi thêm mô hình, chạy trong vài mili
giây - rẻ hơn rất nhiều so với 100-200 giây sinh văn bản trên CPU.
"""

from __future__ import annotations

import math
import os
from collections import Counter

from hybrid_retrieval import tach_tu_tieng_viet

# Chỉ dùng dạng CÓ DẤU để chấm, không dùng biến thể bỏ dấu như BM25. Lý do:
# "phở" bỏ dấu thành "pho", trùng luôn với "phổ" trong "phổ thông" - đúng cái
# từ đáng lẽ phải tố cáo câu hỏi lạc đề lại bị kho nhận là quen thuộc.
TACH_TU = tach_tu_tieng_viet

# Từ quá ngắn thường là hư từ còn sót; loại ra cho bớt nhiễu.
DO_DAI_TU_TOI_THIEU = 2


class TuVungKho:
    """Tần suất tài liệu (document frequency) của từng từ trong kho đã lập chỉ mục."""

    def __init__(self, tan_suat: dict[str, int], so_chunk: int):
        self.tan_suat = tan_suat
        self.so_chunk = max(1, so_chunk)
        # log(N+1) - trần IDF, tức trọng số của một từ kho chưa từng thấy.
        self.idf_toi_da = math.log((self.so_chunk + 1) / 1)

    def idf(self, tu: str) -> float:
        return math.log((self.so_chunk + 1) / (self.tan_suat.get(tu, 0) + 1))

    def tu_cau_hoi(self, cau_hoi: str) -> list[str]:
        return [t for t in TACH_TU(cau_hoi) if len(t) >= DO_DAI_TU_TOI_THIEU]

    def ty_le_tu_la(self, cau_hoi: str) -> float:
        """Phần sức nặng chủ đề nằm ở những từ kho chưa từng có (0..1)."""
        tokens = self.tu_cau_hoi(cau_hoi)
        if not tokens:
            return 0.0
        tong = sum(self.idf(t) for t in tokens)
        if tong <= 0:
            return 0.0
        la = sum(self.idf(t) for t in tokens if t not in self.tan_suat)
        return la / tong

    def do_phu_idf(self, cau_hoi: str, tai_lieu) -> float:
        """Phần sức nặng chủ đề thực sự có mặt trong các đoạn vừa truy hồi (0..1)."""
        tokens = self.tu_cau_hoi(cau_hoi)
        if not tokens:
            return 1.0
        tong = sum(self.idf(t) for t in tokens)
        if tong <= 0:
            return 1.0

        co_trong_doan = set()
        for doc in tai_lieu:
            tieu_de = " ".join(filter(None, [
                doc.metadata.get("source_file"),
                doc.metadata.get("chapter"),
                doc.metadata.get("article"),
                doc.metadata.get("context_label"),
            ]))
            co_trong_doan.update(TACH_TU(f"{tieu_de}\n{doc.page_content}"))

        phu = sum(self.idf(t) for t in tokens if t in co_trong_doan)
        return phu / tong


def xay_dung_tu_vung(documents) -> TuVungKho:
    """
    Đếm số chunk chứa mỗi từ. Nhận thẳng danh sách Document (thường là
    `bm25_retriever.docs`) để từ vựng khớp đúng với thứ đang tìm kiếm được.
    """
    tan_suat: Counter[str] = Counter()
    so_chunk = 0
    for doc in documents:
        so_chunk += 1
        tieu_de = " ".join(filter(None, [
            doc.metadata.get("source_file"),
            doc.metadata.get("chapter"),
            doc.metadata.get("article"),
            doc.metadata.get("context_label"),
        ]))
        noi_dung = doc.metadata.get("_noi_dung_goc") or doc.page_content
        tan_suat.update(set(TACH_TU(f"{tieu_de}\n{noi_dung}")))
    return TuVungKho(dict(tan_suat), so_chunk)


# ============================================================
# TÍN HIỆU NGỮ NGHĨA - bổ sung cho tín hiệu từ vựng ở trên
# ============================================================
# Từ vựng một mình không đủ. Benchmark cho thấy những câu như "Thủ tục đăng ký
# kết hôn với người nước ngoài cần giấy tờ gì?" đạt do_phu_idf tới 0.94: mọi từ
# của nó ("thủ tục", "đăng ký", "giấy tờ", "nước ngoài") đều có thật trong kho
# văn bản giáo dục. Không phép đếm từ nào tách được câu này khỏi câu đúng chủ đề.
#
# Khoảng cách vector thì tách được, vì nó đo NGHĨA chứ không đo chữ. Và có một
# tín hiệu còn mạnh hơn cả giá trị khoảng cách: 100% câu đúng chủ đề đều có ít
# nhất một đoạn lọt vào từ nhánh truy hồi ngữ nghĩa (khoảng cách nhỏ nhất đo
# được là 0.375), trong khi hơn một phần tư câu lạc đề KHÔNG có đoạn nào - toàn
# bộ kết quả của chúng đến từ trùng khớp từ khóa. Vì vậy "không có đoạn dense
# nào" phải quy về khoảng cách rất lớn, chứ không phải 0.
KHONG_CO_DOAN_DENSE = 9.99


def khoang_cach_dense_nho_nhat(tai_lieu) -> float:
    khoang_cach = [
        float(doc.metadata["_dense_distance"]) for doc in tai_lieu
        if "_dense_distance" in doc.metadata
    ]
    return min(khoang_cach) if khoang_cach else KHONG_CO_DOAN_DENSE


# ============================================================
# NGƯỠNG - hiệu chỉnh bằng benchmark, không đặt bằng cảm tính
# ============================================================
# Đặt qua biến môi trường để thử lại ngưỡng mà không phải sửa code:
#   RAG_TY_LE_TU_LA_TOI_DA, RAG_DO_PHU_IDF_TOI_THIEU, RAG_KHOANG_CACH_DENSE_TOI_DA
# Giá trị mặc định lấy từ `benchmark_chatbot.py --nhanh --do-nguong` trên bộ 127
# câu, chọn điểm còn CHỪA BIÊN chứ không phải điểm chặn được nhiều nhất: chặn
# tối đa luôn rơi đúng vào mép của câu đúng chủ đề khó nhất, tức là vừa khớp bộ
# đo này và sẽ chặn oan ngay câu thật đầu tiên lệch ra ngoài.
TY_LE_TU_LA_TOI_DA = float(os.getenv("RAG_TY_LE_TU_LA_TOI_DA", "0.30"))
DO_PHU_IDF_TOI_THIEU = float(os.getenv("RAG_DO_PHU_IDF_TOI_THIEU", "0.60"))
KHOANG_CACH_DENSE_TOI_DA = float(os.getenv("RAG_KHOANG_CACH_DENSE_TOI_DA", "1.00"))

# Câu quá ngắn thì thống kê không đáng tin - "Điều 5 quy định gì?" chỉ có vài từ,
# lệch một từ là tỉ lệ nhảy vọt. Dưới ngưỡng này thì không chặn.
SO_TU_TOI_THIEU_DE_CHAN = 4


def ly_do_ngoai_pham_vi(cau_hoi: str, tai_lieu, tu_vung: TuVungKho | None) -> str:
    """
    Trả về lý do ngắn nếu câu hỏi nằm ngoài phạm vi kho, chuỗi rỗng nếu không.
    Trả về lý do thay vì bool để benchmark và log biết được tín hiệu nào đã bắt.
    """
    if tu_vung is None:
        return ""
    tokens = tu_vung.tu_cau_hoi(cau_hoi)
    if len(tokens) < SO_TU_TOI_THIEU_DE_CHAN:
        return ""

    ty_le_la = tu_vung.ty_le_tu_la(cau_hoi)
    if ty_le_la >= TY_LE_TU_LA_TOI_DA:
        return f"tu_la={ty_le_la:.2f}"

    if tai_lieu:
        do_phu = tu_vung.do_phu_idf(cau_hoi, tai_lieu)
        if do_phu < DO_PHU_IDF_TOI_THIEU:
            return f"do_phu_idf={do_phu:.2f}"
        khoang_cach = khoang_cach_dense_nho_nhat(tai_lieu)
        if khoang_cach > KHOANG_CACH_DENSE_TOI_DA:
            return f"dense={khoang_cach:.2f}"
    return ""
