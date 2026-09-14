"""
HẬU KIỂM CÂU TRẢ LỜI (không cần gọi thêm mô hình)
==================================================
Hai rủi ro lớn nhất của RAG trên kho văn bản quy phạm là (1) trích dẫn sai số
EVIDENCE và (2) nêu một con số không hề có trong tài liệu được trích. Cả hai đều
kiểm tra được bằng đối chiếu chuỗi, rẻ và chắc chắn hơn là hỏi lại mô hình.

Kết quả dùng cho hai việc: hiện cảnh báo trên giao diện, và tính tỉ lệ
"trích dẫn hợp lệ / số liệu có căn cứ" trong bộ benchmark của đề án.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field

import tu_vung_kho

MAU_TRICH_DAN = re.compile(r"\[(\d{1,2})\]")
# Số có nghĩa trong văn bản quy phạm: 60 tín chỉ, 12,5%, 1.200.000 đồng, 30/6...
MAU_SO = re.compile(r"\d+(?:[.,]\d+)*")

# Số quá phổ biến/không mang thông tin thì không bắt lỗi (tránh cảnh báo nhiễu).
SO_BO_QUA = {"1", "2", "3", "4", "5", "6", "7", "8", "9", "10", "0"}


@dataclass
class KetQuaKiemTra:
    trich_dan_hop_le: bool = True
    so_lieu_co_can_cu: bool = True
    trich_dan_ngoai_pham_vi: list[int] = field(default_factory=list)
    so_khong_tim_thay: list[str] = field(default_factory=list)
    co_trich_dan: bool = False

    @property
    def dat(self) -> bool:
        return self.trich_dan_hop_le and self.so_lieu_co_can_cu

    def canh_bao(self) -> str:
        """Một câu ngắn cho giao diện; rỗng nếu không có gì đáng ngờ."""
        phan = []
        if self.trich_dan_ngoai_pham_vi:
            so = ", ".join(f"[{n}]" for n in self.trich_dan_ngoai_pham_vi)
            phan.append(f"trích dẫn {so} không ứng với nguồn nào")
        if self.so_khong_tim_thay:
            phan.append(
                "số liệu " + ", ".join(self.so_khong_tim_thay[:3])
                + " không thấy trong đoạn được trích"
            )
        if not phan:
            return ""
        return "Cần đối chiếu lại: " + "; ".join(phan) + "."


def _chuan_hoa_so(chuoi: str) -> str:
    """'1.200.000' và '1200000' là một; '12,5' giữ nguyên phần thập phân."""
    if chuoi.count(",") == 1 and len(chuoi.split(",")[1]) <= 2:
        nguyen, thap_phan = chuoi.split(",")
        return nguyen.replace(".", "").replace(",", "") + "." + thap_phan
    return chuoi.replace(".", "").replace(",", "")


def kiem_tra(cau_tra_loi: str, tai_lieu) -> KetQuaKiemTra:
    """
    tai_lieu: danh sách Document đã đưa vào prompt, theo đúng thứ tự EVIDENCE.
    """
    ket_qua = KetQuaKiemTra()
    if not cau_tra_loi or not cau_tra_loi.strip():
        return ket_qua

    so_trich_dan = [int(n) for n in MAU_TRICH_DAN.findall(cau_tra_loi)]
    ket_qua.co_trich_dan = bool(so_trich_dan)
    ngoai_pham_vi = sorted({n for n in so_trich_dan if not 1 <= n <= len(tai_lieu)})
    if ngoai_pham_vi:
        ket_qua.trich_dan_ngoai_pham_vi = ngoai_pham_vi
        ket_qua.trich_dan_hop_le = False

    # Đối chiếu số: chỉ xét phần nội dung thực sự được trích dẫn, và chấp nhận
    # số xuất hiện ở BẤT KỲ evidence nào - mô hình có thể đánh số lệch một bậc
    # nhưng thông tin vẫn nằm trong tài liệu, đó là mức sai nhẹ hơn nhiều.
    kho_so = set()
    for doc in tai_lieu:
        for so in MAU_SO.findall(doc.page_content):
            kho_so.add(_chuan_hoa_so(so))
        # Số hiệu văn bản thường CHỈ nằm ở tên file ("thong-tu-27-2020-...",
        # "cong-van-so-5512-..."), mà tên file cũng vào prompt qua dòng "Nguồn:".
        # Model nhắc lại số đó là có căn cứ, không phải bịa - trước đây bị gắn cờ oan.
        for so in MAU_SO.findall(str(doc.metadata.get("source_file", ""))):
            kho_so.add(_chuan_hoa_so(so))

    khong_thay = []
    for so in MAU_SO.findall(cau_tra_loi):
        if so in SO_BO_QUA or len(so) <= 1:
            continue
        if _chuan_hoa_so(so) not in kho_so and so not in khong_thay:
            khong_thay.append(so)
    if khong_thay:
        ket_qua.so_khong_tim_thay = khong_thay
        ket_qua.so_lieu_co_can_cu = False
    return ket_qua


# ============================================================
# NGƯỠNG TỪ CHỐI TRẢ LỜI
# ============================================================
# Chỉ chặn khi kết quả truy hồi gần như không dính gì tới câu hỏi. Ngưỡng đặt
# thấp có chủ đích: benchmark trước đây cho thấy threshold cứng chặn nhầm ~30%
# câu hỏi đúng, nên ở đây chỉ lọc trường hợp rõ ràng lạc đề.
DO_PHU_TOI_THIEU = 0.12


def ly_do_bo_qua(tai_lieu, cau_hoi: str = "", tu_vung=None) -> str:
    """
    Lý do nên bỏ qua bước sinh câu trả lời; chuỗi rỗng nghĩa là cứ trả lời.

    Ba lớp chặn, cố ý tách rời nhau:
      1. Không truy hồi được gì.
      2. Độ phủ từ vựng thô - lớp cũ, ngưỡng thấp, chỉ bắt trường hợp truy hồi
         về gần như rỗng nghĩa.
      3. Trọng số IDF + khoảng cách vector (tu_vung_kho) - bắt câu hỏi mà những
         từ MANG CHỦ ĐỀ không có trong kho, hoặc có đủ chữ nhưng lệch hẳn nghĩa.
         Đây là lớp bắt được "nấu phở bò", thứ mà lớp 2 bỏ lọt vì các từ chung
         chung như "hướng dẫn", "nguyên liệu" đã đẩy độ phủ lên.

    Trả về lý do chứ không phải bool để chỗ gọi ghi được vào log và benchmark:
    biết tín hiệu nào đã bắt thì mới chỉnh ngưỡng có căn cứ.
    """
    if not tai_lieu:
        return "khong_co_tai_lieu"
    do_phu = max(
        float(doc.metadata.get("_lexical_coverage", 0.0)) for doc in tai_lieu
    )
    if do_phu < DO_PHU_TOI_THIEU:
        return f"do_phu_tho={do_phu:.2f}"
    return tu_vung_kho.ly_do_ngoai_pham_vi(cau_hoi, tai_lieu, tu_vung)


def qua_it_lien_quan(tai_lieu, cau_hoi: str = "", tu_vung=None) -> bool:
    """Bản bool của ly_do_bo_qua. `cau_hoi` và `tu_vung` là tùy chọn để chỗ gọi
    cũ không phải sửa; thiếu chúng thì hàm chạy đúng như trước."""
    return bool(ly_do_bo_qua(tai_lieu, cau_hoi, tu_vung))
