"""
HỒ SƠ VĂN BẢN VÀ QUAN HỆ HIỆU LỰC
==================================
Kho tài liệu chứa cả văn bản cũ lẫn văn bản mới thay thế nó nằm cạnh nhau.
Một chatbot chỉ tìm theo độ tương đồng sẽ vô tư trích dẫn Thông tư đã hết hiệu
lực mà không hề biết, vì về mặt ngữ nghĩa thì hai văn bản gần như giống hệt nhau.

Module này đọc chính nội dung đã lập chỉ mục để rút ra:
  - Hồ sơ từng văn bản: số hiệu, loại, cơ quan ban hành, ngày ban hành.
  - Quan hệ giữa các văn bản: A thay thế / bãi bỏ / sửa đổi B.

Nhờ đó hệ thống cảnh báo được "nguồn [2] đã bị thay thế bởi văn bản X cũng có
trong kho" và hạ bậc văn bản hết hiệu lực khi xếp hạng truy hồi.

Toàn bộ dựa trên đối chiếu chuỗi, không gọi thêm mô hình nào.
"""

from __future__ import annotations

import json
import os
import re
from dataclasses import asdict, dataclass, field

THU_MUC_DU_AN = os.path.dirname(os.path.abspath(__file__))
DUONG_DAN_HO_SO = os.path.abspath(os.getenv(
    "RAG_HO_SO_VAN_BAN", os.path.join(THU_MUC_DU_AN, "ho_so_van_ban.json")
))
DUONG_DAN_META_LLM = os.path.abspath(os.getenv(
    "RAG_META_LLM", os.path.join(THU_MUC_DU_AN, "meta_llm.json")
))

# "27/2020/TT-BGDĐT", "81/2021/NĐ-CP", "123/2025/QH15".
# \s* ở mọi mối nối vì OCR hay chèn xuống dòng hoặc khoảng trắng thừa
# ("02/2022/TT-\nBGDĐT", "28/2023/NĐ- CP").
MAU_SO_HIEU = re.compile(
    r"(\d{1,4})\s*/\s*(\d{4})\s*/\s*([A-ZĐ]{2,7})\s*[-–]\s*([A-ZĐ][A-ZĐ0-9]{1,14})"
)
# Quyết định/Chỉ thị của Thủ tướng và công văn không có năm trong số hiệu:
# "527/QĐ-TTg", "20/CT-TTg", "5512/BGDĐT-GDTrH".
# (?<![\d/]) chặn trường hợp con số thật ra là phần năm của một số hiệu khác:
# bản dự thảo "Số: /2026/TT-BGDĐT" (chưa điền số) sẽ bị đọc thành "văn bản số
# 2026" nếu thiếu điều kiện này.
MAU_SO_KHONG_NAM = re.compile(
    r"(?<![\d/])(\d{1,5})\s*/\s*([A-ZĐ]{2,10})\s*[-–]\s*([A-ZĐ][A-ZĐa-z0-9]{1,12})"
)
# Luật và Nghị quyết Quốc hội đánh số KHÔNG có gạch nối: "43/2019/QH14",
# "124/2025/QH15". Hai mẫu trên đều đòi dấu gạch nên bỏ sót toàn bộ các Luật -
# mà Luật lại là thứ được viện dẫn nhiều nhất ở phần "Căn cứ".
MAU_SO_HIEU_LUAT = re.compile(r"(?<![\d/])(\d{1,4})\s*/\s*(\d{4})\s*/\s*(QH\d{2})\b")

# OCR đọc chữ "Số" ra đủ kiểu: "Sô", "sé", "SỐ", "S0". Vẫn an toàn vì ngay
# sau đó bắt buộc phải khớp một số hiệu đầy đủ.
#
# Nhưng "số" còn là một từ thường gặp giữa câu: "Căn cứ Luật Giáo dục SỐ
# 43/2019/QH14". Bắt cả những chỗ đó thì văn bản bị gán luôn số hiệu của cái
# Luật mà nó viện dẫn - ba Thông tư dự thảo đã dính đúng lỗi này. Ô số hiệu thật
# ở khối tiêu đề luôn nhận ra được bằng một trong hai dấu hiệu: đứng đầu dòng,
# hoặc có dấu hai chấm ngay sau. Chữ "số" giữa câu không có cả hai.
MAU_DONG_SO = re.compile(
    r"(?:^|\n)[^\S\n]*S[ốôồổỗọóoáàảã0-9é]{0,2}[^\S\n]*[:.]?[^\S\n]*"
    r"|S[ốôồổỗọóoáàảã0-9é]{0,2}[^\S\n]*:[^\S\n]*",
    re.IGNORECASE,
)
MAU_NGAY = re.compile(r"ngày\s+(\d{1,2})\s+tháng\s+(\d{1,2})\s+năm\s+(\d{4})", re.IGNORECASE)

# Chỉ nhận là quan hệ văn bản khi ngay sau động từ có một số hiệu thật. Nếu bắt
# theo động từ trần thì dính hàng loạt câu vô can: "thay thế thành viên Hội
# đồng trường", "thay thế việc nộp bản sao", "hết hiệu lực sau khi thanh lý".
MAU_QUAN_HE = re.compile(
    r"(bãi bỏ|thay thế|sửa đổi,?\s*(?:bổ sung)?|hết hiệu lực)"
    r"(\s+(?:bởi|tại))?"
    r"([^.;\n]{0,140})",
    re.IGNORECASE,
)
# Bản hợp nhất chú thích ngược chiều mà không dùng chữ "bởi": "Điều này ĐƯỢC
# sửa đổi THEO QUY ĐỊNH TẠI khoản 1 Điều 1 của Nghị định số 311/2025/NĐ-CP".
# Nhận ra cặp dấu hiệu này mới tránh được kết luận ngược "71 sửa đổi 311".
MAU_BI_DONG_TRUOC = re.compile(r"\b(được|bị)\s*$", re.IGNORECASE)
MAU_BI_DONG_SAU = re.compile(r"^\s*(theo|tại|bởi)\b", re.IGNORECASE)

# "Căn cứ Nghị định số 37/2025/NĐ-CP ngày 26 tháng 02 năm 2025 của Chính phủ;"
# Đây là loại quan hệ nhiều nhất trong văn bản quy phạm - mỗi Thông tư viện dẫn
# 3-6 văn bản - nhưng trước giờ bị bỏ qua hoàn toàn, nên đồ thị gần như không có
# cạnh nào. Phần đuôi [^;\n] dừng ở dấu chấm phẩy vì mỗi căn cứ là một mệnh đề
# riêng; lấy quá dấu này sẽ gộp nhầm số hiệu của căn cứ kế tiếp.
# c[^\s]{0,3} thay vì "cứ" vì OCR đọc ra đủ kiểu: "Can cir", "Can cie", "Can ct'r".
# Nhận rộng không sao: mệnh đề nào không chứa số hiệu hợp lệ thì tự bị loại.
MAU_CAN_CU_QUAN_HE = re.compile(r"C[ăâa]n\s*c[^\s]{0,3}\s+([^;\n]{0,220})", re.IGNORECASE)
# Khối "Căn cứ" nằm giữa tiêu đề và phần nội dung. Quét quá chỗ này sẽ nhặt
# phải "căn cứ vào kết quả đánh giá" trong thân bài.
MAU_HET_KHOI_CAN_CU = re.compile(
    r"(Đi[eề]u\s*1\b|QUY[ỂẾE]T\s*Đ[ỊI]NH\s*:|Ch[uư][oơ]ng\s*I\b)", re.IGNORECASE
)

LOAI_VAN_BAN = {
    "TT": "Thông tư", "TTLT": "Thông tư liên tịch", "NĐ": "Nghị định",
    "QĐ": "Quyết định", "NQ": "Nghị quyết", "CT": "Chỉ thị", "QH": "Luật",
}

CO_QUAN_THUONG_GAP = [
    "BỘ GIÁO DỤC VÀ ĐÀO TẠO", "THỦ TƯỚNG CHÍNH PHỦ", "CHÍNH PHỦ", "QUỐC HỘI",
    "BỘ LAO ĐỘNG - THƯƠNG BINH VÀ XÃ HỘI", "BỘ TÀI CHÍNH", "BỘ NỘI VỤ",
    "BỘ KHOA HỌC VÀ CÔNG NGHỆ", "BỘ Y TẾ", "VĂN PHÒNG CHÍNH PHỦ",
]


@dataclass
class HoSoVanBan:
    ten_file: str
    so_hieu: str | None = None
    so_hieu_uoc_doan: bool = False
    loai: str | None = None
    co_quan: str | None = None
    ngay_ban_hanh: str | None = None
    # Số hiệu các văn bản mà văn bản này thay thế / bãi bỏ / sửa đổi.
    thay_the: list[str] = field(default_factory=list)
    sua_doi: list[str] = field(default_factory=list)
    # Số hiệu các văn bản được viện dẫn ở phần "Căn cứ ...".
    can_cu: list[str] = field(default_factory=list)
    # Được điền ở bước đối chiếu toàn kho (tên file, không phải số hiệu).
    bi_thay_the_boi: list[str] = field(default_factory=list)
    bi_sua_doi_boi: list[str] = field(default_factory=list)
    # False với giáo án .pptx, ma trận đề .docx, thời khoá biểu .xlsx... Những
    # file này không có số hiệu là ĐÚNG, không phải trích trượt; tách ra để
    # không làm hỏng thống kê độ phủ và không đổ vào đồ thị như văn bản.
    la_qppl: bool = True
    # Bản chưa ký, ô số hiệu còn bỏ trống. Vẫn tra cứu được nhưng phải gắn nhãn.
    la_du_thao: bool = False
    # "regex" | "llm" - biết số hiệu này từ đâu ra để còn lần ngược khi sai.
    nguon_meta: str = "regex"

    @property
    def con_hieu_luc(self) -> bool:
        return not self.bi_thay_the_boi

    def nhan(self) -> str:
        """Chuỗi ngắn để hiển thị: 'Thông tư 27/2020/TT-BGDĐT · 04/9/2020'."""
        phan = []
        if self.so_hieu:
            phan.append(f"{self.loai or 'Văn bản'} {self.so_hieu}")
        if self.ngay_ban_hanh:
            nam, thang, ngay = self.ngay_ban_hanh.split("-")
            phan.append(f"{int(ngay)}/{int(thang)}/{nam}")
        return " · ".join(phan)


# OCR làm mất dấu trong chính mã văn bản: "NĐ-CP" đọc ra "ND-CP", "TT-BGDĐT"
# đọc ra "TT-BGDDT". Hai chuỗi khác nhau nhưng là một văn bản. Với FAISS thì
# chỉ lỡ một cảnh báo hiệu lực; với Neo4j thì MERGE đẻ ra hai node cho cùng một
# Nghị định - và 37/2025/NĐ-CP, văn bản được viện dẫn nhiều nhất trong kho
# (29 lần), bị tách làm đôi thành 29 + 7.
#
# Quy tắc khôi phục dựa trên một điều luôn đúng: OCR chỉ LÀM MẤT dấu chứ không
# tự thêm dấu vào. Nên mã nào bỏ dấu đi thì trùng với đúng một mã chuẩn, mã
# chuẩn đó là bản gốc. Dùng danh sách trắng thay vì thay D->Đ vô điều kiện để
# không đụng vào những mã vốn không có dấu (CP, TTg, QH15, BTC...).
MA_CHUAN = {
    "TT", "TTLT", "NĐ", "QĐ", "NQ", "CT", "QH", "CĐ", "TB", "CV", "HD", "KH", "PL",
    "BGDĐT", "CP", "TTg", "BLĐTBXH", "BTC", "BNV", "BKHCN", "BYT", "VPCP", "BTP",
    "BQP", "BCA", "BXD", "BNG", "BTNMT", "BTTTT", "TW", "GDTrH", "GDĐH", "GDTX",
}
_MA_THEO_KHOA = {}
for _ma in MA_CHUAN:
    _khoa = _ma.upper().replace("Đ", "D")
    # Khoá đụng nhau thì không suy ra được bản gốc, bỏ cả hai cho an toàn.
    _MA_THEO_KHOA[_khoa] = None if _khoa in _MA_THEO_KHOA else _ma


def chuan_hoa_ma(ma: str) -> str:
    """'ND' -> 'NĐ', 'BGDDT' -> 'BGDĐT'; giữ nguyên 'CP', 'TTg', 'QH15'."""
    if ma in MA_CHUAN:
        return ma
    return _MA_THEO_KHOA.get(ma.upper().replace("Đ", "D")) or ma


def chuan_hoa_so_hieu(khop) -> str:
    so, nam, loai, co_quan = (phan.strip() for phan in khop.groups()[:4])
    return f"{int(so)}/{nam}/{chuan_hoa_ma(loai.upper())}-{chuan_hoa_ma(co_quan.upper())}"


def trich_so_hieu(van_ban: str) -> list[str]:
    """
    Mọi số hiệu văn bản xuất hiện trong đoạn text, cả hai kiểu đánh số:
      - Có năm:    27/2020/TT-BGDĐT  (thông tư, nghị định, luật)
      - Không năm: 527/QĐ-TTg, 20/CT-TTg, 5512/BGDĐT-GDTrH
                   (quyết định, chỉ thị của Thủ tướng và công văn)

    Kiểu có năm phải quét trước rồi che vùng đã khớp lại, nếu không thì phần
    đuôi "2020/TT-BGDĐT" của số hiệu đầy đủ sẽ bị đọc nhầm thành một số hiệu
    riêng mang số 2020.
    """
    van_ban = van_ban or ""
    ket_qua: list[str] = []
    cac_vung: list[tuple[int, int]] = []
    for khop in MAU_SO_HIEU.finditer(van_ban):
        cac_vung.append((khop.start(), khop.end()))
        so_hieu = chuan_hoa_so_hieu(khop)
        if so_hieu not in ket_qua:
            ket_qua.append(so_hieu)

    for khop in MAU_SO_KHONG_NAM.finditer(van_ban):
        if any(bat_dau <= khop.start() < ket_thuc for bat_dau, ket_thuc in cac_vung):
            continue
        so, loai, co_quan = (phan.strip() for phan in khop.groups())
        so_hieu = f"{int(so)}/{chuan_hoa_ma(loai.upper())}-{chuan_hoa_ma(co_quan)}"
        if so_hieu not in ket_qua:
            ket_qua.append(so_hieu)

    for khop in MAU_SO_HIEU_LUAT.finditer(van_ban):
        if any(bat_dau <= khop.start() < ket_thuc for bat_dau, ket_thuc in cac_vung):
            continue
        so, nam, khoa = (phan.strip() for phan in khop.groups())
        so_hieu = f"{int(so)}/{nam}/{khoa.upper()}"
        if so_hieu not in ket_qua:
            ket_qua.append(so_hieu)
    return ket_qua


def _so_dau_ten_file(ten_file: str) -> str | None:
    """'311-cp.signed.pdf' -> '311'; 'thong-tu-27-2020-tt-bgddt.doc' -> '27'."""
    khop = re.match(r"[^\d]*?(\d{1,4})\b", ten_file or "")
    return khop.group(1) if khop else None


# Văn bản quy phạm Việt Nam luôn có cấu trúc: khối tiêu đề (cơ quan, số hiệu,
# ngày) rồi mới tới phần "Căn cứ ..." liệt kê hàng loạt văn bản KHÁC. Cắt đúng
# ranh giới này là cách rẻ nhất để không nhầm số hiệu của mình với số hiệu được
# viện dẫn - trước khi cắt, sáu Thông tư khác nhau đều bị gán chung số hiệu của
# Nghị định 37/2025/NĐ-CP chỉ vì thông tư nào cũng căn cứ vào nó.
# Phải chịu được cả bản OCR hỏng ("Can cir", "Can cie", "Can ct'r"): không cắt
# được ở đây thì cả khối "Căn cứ" bị tính là tiêu đề, và số hiệu của những văn
# bản được viện dẫn sẽ bị nhận nhầm thành số hiệu của chính văn bản này.
# Nhận rộng là hướng an toàn - cắt sớm thì cùng lắm mất vài dòng tiêu đề, còn
# cắt hụt thì gán sai số hiệu.
MAU_CAN_CU = re.compile(r"\bC[ăâa]n\s*c[^\s]{0,3}\s+(?=\S)", re.IGNORECASE)
# Bản dự thảo chưa có số: "Số: /2026/TT-BGDĐT".
MAU_SO_HIEU_THIEU_SO = re.compile(r"/\s*(\d{4})\s*/\s*([A-ZĐ]{2,7})\s*[-–]\s*([A-ZĐ][A-ZĐ0-9]{1,14})")


def cat_khoi_tieu_de(van_ban: str) -> str:
    khop = MAU_CAN_CU.search(van_ban or "")
    return (van_ban or "")[: khop.start()] if khop else (van_ban or "")


def suy_so_hieu_chinh(ten_file: str, phan_dau: str) -> tuple[str | None, bool]:
    """
    Xác định số hiệu CỦA CHÍNH văn bản. Trả về (số hiệu, có phải suy đoán không).

      1. Số hiệu trong khối tiêu đề trùng số đứng đầu tên file -> chắc chắn nhất:
         kho đặt tên theo số hiệu (311-cp.pdf, thong-tu-27-2020-...), và tên file
         là chữ gõ máy nên đáng tin hơn con số vừa OCR từ ảnh scan.
      2. Đứng ngay sau chữ "Số:" trong khối tiêu đề.

    Cố tình KHÔNG lấy "số hiệu đầu tiên gặp được" làm phương án cuối: thà không
    biết còn hơn gán nhầm, vì số hiệu sai sẽ đẻ ra cảnh báo hiệu lực sai.

    Vì lý do đó đã BỎ phương án "ô số bỏ trống thì lấy số đầu tên file điền vào"
    ("Số: /2026/TT-BGDĐT" + "18-bgddt.pdf" -> "18/2026/TT-BGDĐT"). Ô số bỏ trống
    nghĩa là bản dự thảo chưa được cấp số, điền vào là bịa ra một văn bản không
    tồn tại. Mà số đầu tên file cũng không đáng tin: với các file tải từ cổng
    thông tin nó là ID tải về chứ không phải số hiệu - "1483-ttg.signed.pdf"
    thật ra là Quyết định 92/QĐ-TTg, "281-cp.signed.pdf" là Nghị quyết 29/NQ-CP.
    """
    tieu_de = cat_khoi_tieu_de(phan_dau)
    so_ten_file = _so_dau_ten_file(ten_file)
    cac_so_hieu = trich_so_hieu(tieu_de)

    if so_ten_file:
        for so_hieu in cac_so_hieu:
            if so_hieu.split("/")[0] == so_ten_file:
                return so_hieu, False

    khop_dong_so = MAU_DONG_SO.search(tieu_de)
    if khop_dong_so:
        ngay_sau = tieu_de[khop_dong_so.end(): khop_dong_so.end() + 40].lstrip()
        cac_ung_vien = trich_so_hieu(ngay_sau[:30])
        if cac_ung_vien:
            # Số OCR được ở đây khác số trong tên file thì không chắc bên nào
            # đúng (ảnh scan mờ hay đọc nhầm 1531 thành 527) - vẫn nhận nhưng
            # đánh dấu là suy đoán để không dùng nó khẳng định hiệu lực.
            khong_khop_ten_file = bool(
                so_ten_file and cac_ung_vien[0].split("/")[0] != so_ten_file
            )
            return cac_ung_vien[0], khong_khop_ten_file

    return None, False


def suy_loai_van_ban(so_hieu: str | None) -> str | None:
    """'27/2020/TT-BGDĐT' -> Thông tư; '527/QĐ-TTg' -> Quyết định."""
    if not so_hieu:
        return None
    ma = so_hieu.split("/")[-1].split("-")[0].upper()
    # "43/2019/QH14" -> mã là "QH14", phải bỏ số khoá Quốc hội mới tra được.
    return LOAI_VAN_BAN.get(ma) or LOAI_VAN_BAN.get(re.sub(r"\d+$", "", ma))


def trich_ngay_ban_hanh(phan_dau: str) -> str | None:
    khop = MAU_NGAY.search(phan_dau or "")
    if not khop:
        return None
    ngay, thang, nam = (int(phan) for phan in khop.groups())
    if not (1 <= ngay <= 31 and 1 <= thang <= 12 and 1990 <= nam <= 2100):
        return None
    return f"{nam:04d}-{thang:02d}-{ngay:02d}"


def trich_co_quan(phan_dau: str) -> str | None:
    dau_van_ban = (phan_dau or "")[:400].upper()
    for co_quan in CO_QUAN_THUONG_GAP:
        if co_quan in dau_van_ban:
            return co_quan.title()
    return None


def trich_quan_he(van_ban: str) -> tuple[list[str], list[str]]:
    """
    Trả về (danh sách số hiệu bị văn bản này thay thế/bãi bỏ,
            danh sách số hiệu bị văn bản này sửa đổi, bổ sung).
    Bỏ qua câu ở thể bị động ("được sửa đổi, bổ sung bởi Luật số ...") vì khi đó
    chiều quan hệ ngược lại, và chiều đó sẽ được ghi nhận từ phía văn bản kia.
    """
    thay_the: list[str] = []
    sua_doi: list[str] = []
    van_ban = van_ban or ""
    for khop in MAU_QUAN_HE.finditer(van_ban):
        dong_tu = khop.group(1).lower()
        bi_dong = bool(khop.group(2))
        cac_so_hieu = trich_so_hieu(khop.group(3))
        if not cac_so_hieu or bi_dong:
            continue
        # Chủ ngữ phải là chính văn bản này ("Thông tư này thay thế..."). Nếu
        # ngay trước động từ đã có một số hiệu khác thì câu đang nói về văn bản
        # đó, không phải văn bản đang đọc - ví dụ dòng chú thích "Nghị định số
        # 311/2025/NĐ-CP sửa đổi, bổ sung một số điều của Nghị định này".
        truoc_do = van_ban[max(0, khop.start() - 70): khop.start()]
        if trich_so_hieu(truoc_do):
            continue
        if MAU_BI_DONG_TRUOC.search(truoc_do) and MAU_BI_DONG_SAU.match(khop.group(3)):
            continue
        dich = thay_the if dong_tu.startswith(("bãi bỏ", "thay thế", "hết hiệu lực")) else sua_doi
        for so_hieu in cac_so_hieu:
            if so_hieu not in dich:
                dich.append(so_hieu)
    return thay_the, sua_doi


def trich_can_cu(van_ban: str) -> list[str]:
    """
    Số hiệu các văn bản mà văn bản này viện dẫn ở phần "Căn cứ ...".

    Khác với thay_the/sua_doi, quan hệ này KHÔNG nói gì về hiệu lực - nó chỉ nói
    "văn bản A được ban hành dựa trên cơ sở pháp lý B". Giá trị của nó là cho
    phép đi ngược: khi B bị thay thế, mọi A từng căn cứ vào B đều đáng rà lại.

    Chỉ lấy số hiệu ĐẦU TIÊN của mỗi mệnh đề. Một mệnh đề căn cứ hay kèm theo
    văn bản sửa đổi của chính nó ("Căn cứ Luật X; Luật sửa đổi một số điều của
    Luật X số 34/2018/QH14") - số sau là văn bản khác, không phải cái được căn cứ.
    """
    van_ban = van_ban or ""
    khop_het = MAU_HET_KHOI_CAN_CU.search(van_ban)
    khoi = van_ban[: khop_het.start()] if khop_het else van_ban[:4000]
    ket_qua: list[str] = []
    for khop in MAU_CAN_CU_QUAN_HE.finditer(khoi):
        cac_so_hieu = trich_so_hieu(khop.group(1))
        if cac_so_hieu and cac_so_hieu[0] not in ket_qua:
            ket_qua.append(cac_so_hieu[0])
    return ket_qua


# ============================================================
# DỰNG HỒ SƠ CHO CẢ KHO
# ============================================================
# Chỉ phần đầu văn bản mới chứa quốc hiệu, số hiệu và ngày ban hành.
DO_DAI_PHAN_DAU = 1200


# Văn bản quy phạm luôn mở đầu bằng quốc hiệu, và luôn có khối "Căn cứ".
# Thiếu cả hai thì đây là giáo án, đề kiểm tra, thời khoá biểu - không phải
# văn bản, và không có số hiệu để mà trích.
MAU_DAU_HIEU_QPPL = re.compile(
    r"C[ỘÔOQ][NC]G\s*H[OÒÓ]A\s*X[AÃ]\s*H[ỘÔO]I|C[ăâa]n\s*c[ứưu]\b", re.IGNORECASE
)


def tai_meta_llm() -> dict[str, dict]:
    """
    Kết quả của trich_meta_llm.py, nếu đã chạy. Không có file thì chạy như cũ -
    module này vẫn phải dùng được khi chưa ai chạy bước trích bằng LLM.
    """
    if not os.path.exists(DUONG_DAN_META_LLM):
        return {}
    try:
        with open(DUONG_DAN_META_LLM, encoding="utf-8") as f:
            return json.load(f)
    except (OSError, json.JSONDecodeError):
        return {}


def xay_dung_ho_so(van_ban_theo_file: dict[str, str]) -> dict[str, HoSoVanBan]:
    """van_ban_theo_file: {ten_file: toàn bộ text đã lập chỉ mục của file đó}."""
    meta_llm = tai_meta_llm()
    ho_so: dict[str, HoSoVanBan] = {}
    for ten_file, van_ban in van_ban_theo_file.items():
        phan_dau = van_ban[:DO_DAI_PHAN_DAU]
        so_hieu, uoc_doan = suy_so_hieu_chinh(ten_file, phan_dau)
        # Ngày ban hành cũng phải lấy trong khối tiêu đề, nếu không sẽ nhặt
        # nhầm ngày của văn bản được viện dẫn ở phần "Căn cứ".
        tieu_de = cat_khoi_tieu_de(phan_dau)
        co_quan = trich_co_quan(tieu_de)
        ngay_ban_hanh = trich_ngay_ban_hanh(tieu_de)
        nguon_meta = "regex"
        la_du_thao = False

        # LLM chỉ được quyền lấn chỗ khi regex không biết gì, hoặc khi regex chỉ
        # đang đoán (uoc_doan). Số hiệu regex đã chắc thì giữ: nó đối chiếu được
        # với tên file nên đáng tin hơn, và giữ nguyên thì kết quả không đổi
        # giữa các lần chạy. Số hiệu từ LLM đã qua kiểm chứng trong
        # trich_meta_llm._hop_le() nên không còn là suy đoán nữa.
        muc_llm = meta_llm.get(ten_file)
        if muc_llm and (not so_hieu or uoc_doan):
            if muc_llm.get("so_hieu"):
                so_hieu, uoc_doan, nguon_meta = muc_llm["so_hieu"], False, "llm"
            la_du_thao = bool(muc_llm.get("la_du_thao"))
            co_quan = co_quan or muc_llm.get("co_quan")
            ngay_ban_hanh = ngay_ban_hanh or muc_llm.get("ngay_ban_hanh")

        thay_the, sua_doi = trich_quan_he(van_ban)
        can_cu = trich_can_cu(van_ban)
        # Văn bản không tự thay thế chính nó (câu "Thông tư này thay thế Thông
        # tư số <chính nó>" không tồn tại, nhưng OCR lỗi có thể tạo ra).
        thay_the = [s for s in thay_the if s != so_hieu]
        sua_doi = [s for s in sua_doi if s != so_hieu]
        can_cu = [s for s in can_cu if s != so_hieu]
        ho_so[ten_file] = HoSoVanBan(
            ten_file=ten_file,
            so_hieu=so_hieu,
            so_hieu_uoc_doan=uoc_doan,
            loai=suy_loai_van_ban(so_hieu) or (muc_llm or {}).get("loai"),
            co_quan=co_quan,
            ngay_ban_hanh=ngay_ban_hanh,
            thay_the=thay_the,
            sua_doi=sua_doi,
            can_cu=can_cu,
            la_qppl=bool(MAU_DAU_HIEU_QPPL.search(phan_dau)),
            la_du_thao=la_du_thao,
            nguon_meta=nguon_meta,
        )

    # Đối chiếu hai chiều: văn bản nào trong kho là mục tiêu của quan hệ đó.
    theo_so_hieu: dict[str, list[str]] = {}
    for ten_file, muc in ho_so.items():
        if muc.so_hieu:
            theo_so_hieu.setdefault(muc.so_hieu, []).append(ten_file)

    for ten_file, muc in ho_so.items():
        for so_hieu in muc.thay_the:
            for file_dich in theo_so_hieu.get(so_hieu, []):
                if file_dich != ten_file:
                    ho_so[file_dich].bi_thay_the_boi.append(ten_file)
        for so_hieu in muc.sua_doi:
            for file_dich in theo_so_hieu.get(so_hieu, []):
                if file_dich != ten_file:
                    ho_so[file_dich].bi_sua_doi_boi.append(ten_file)
    return ho_so


def xay_dung_tu_vector_store(vector_store) -> dict[str, HoSoVanBan]:
    """Gom lại text theo từng file nguồn từ chính các chunk đã lập chỉ mục."""
    van_ban_theo_file: dict[str, list[str]] = {}
    for doc in vector_store.docstore._dict.values():
        ten_file = doc.metadata.get("source_file")
        if ten_file:
            van_ban_theo_file.setdefault(ten_file, []).append(doc.page_content)
    return xay_dung_ho_so({
        ten: "\n".join(cac_phan) for ten, cac_phan in van_ban_theo_file.items()
    })


def luu_ho_so(ho_so: dict[str, HoSoVanBan]) -> None:
    with open(DUONG_DAN_HO_SO, "w", encoding="utf-8") as f:
        json.dump(
            {ten: asdict(muc) for ten, muc in ho_so.items()},
            f, ensure_ascii=False, indent=1,
        )


def tai_ho_so() -> dict[str, HoSoVanBan]:
    try:
        with open(DUONG_DAN_HO_SO, encoding="utf-8") as f:
            du_lieu = json.load(f)
        return {ten: HoSoVanBan(**muc) for ten, muc in du_lieu.items()}
    except (OSError, ValueError, TypeError):
        return {}


# ============================================================
# CẢNH BÁO HIỆU LỰC CHO CÂU TRẢ LỜI
# ============================================================
def canh_bao_hieu_luc(ho_so: dict[str, HoSoVanBan], cac_nguon: list[dict]) -> list[dict]:
    """
    cac_nguon: danh sách nguồn đã đưa vào prompt (có "evidence" và "name").
    Trả về danh sách cảnh báo, mỗi cảnh báo gắn với đúng số EVIDENCE để người
    đọc biết chính xác câu nào đang dựa trên văn bản đã hết hiệu lực.
    """
    canh_bao = []
    da_bao = set()
    for nguon in cac_nguon:
        ten_file = nguon.get("name")
        muc = ho_so.get(ten_file)
        if not muc or ten_file in da_bao:
            continue
        if muc.bi_thay_the_boi:
            da_bao.add(ten_file)
            canh_bao.append({
                "evidence": nguon.get("evidence"),
                "nguon": ten_file,
                "loai": "thay_the",
                "thay_the_boi": muc.bi_thay_the_boi,
                "thong_bao": (
                    f"Nguồn [{nguon.get('evidence')}] {_ten_ngan(muc)} đã bị thay thế bởi "
                    f"{_danh_sach_ten(ho_so, muc.bi_thay_the_boi)} — văn bản này cũng có trong kho."
                ),
            })
        elif muc.bi_sua_doi_boi:
            da_bao.add(ten_file)
            canh_bao.append({
                "evidence": nguon.get("evidence"),
                "nguon": ten_file,
                "loai": "sua_doi",
                "sua_doi_boi": muc.bi_sua_doi_boi,
                "thong_bao": (
                    f"Nguồn [{nguon.get('evidence')}] {_ten_ngan(muc)} đã được sửa đổi, bổ sung bởi "
                    f"{_danh_sach_ten(ho_so, muc.bi_sua_doi_boi)} — nên đối chiếu thêm."
                ),
            })
    return canh_bao


def _ten_ngan(muc: HoSoVanBan) -> str:
    return muc.nhan() or muc.ten_file


def _danh_sach_ten(ho_so: dict[str, HoSoVanBan], cac_file: list[str]) -> str:
    ten = []
    for ten_file in cac_file[:2]:
        muc = ho_so.get(ten_file)
        ten.append(_ten_ngan(muc) if muc else ten_file)
    con_lai = len(cac_file) - len(ten)
    chuoi = ", ".join(ten)
    return f"{chuoi} và {con_lai} văn bản khác" if con_lai > 0 else chuoi


def main() -> int:
    """CLI: dựng lại hồ sơ từ chỉ mục hiện có và in thống kê."""
    import sys

    for luong in (sys.stdout, sys.stderr):
        if hasattr(luong, "reconfigure"):
            luong.reconfigure(encoding="utf-8", errors="replace")

    from langchain_community.vectorstores import FAISS

    from main import DUONG_DAN_LUU_INDEX, tao_embeddings_va_llm

    embeddings, _ = tao_embeddings_va_llm()
    vector_store = FAISS.load_local(
        DUONG_DAN_LUU_INDEX, embeddings, allow_dangerous_deserialization=True
    )
    ho_so = xay_dung_tu_vector_store(vector_store)
    luu_ho_so(ho_so)

    co_so_hieu = sum(1 for m in ho_so.values() if m.so_hieu)
    co_ngay = sum(1 for m in ho_so.values() if m.ngay_ban_hanh)
    bi_thay_the = [m for m in ho_so.values() if m.bi_thay_the_boi]
    bi_sua_doi = [m for m in ho_so.values() if m.bi_sua_doi_boi]
    tong_quan_he = sum(len(m.thay_the) + len(m.sua_doi) for m in ho_so.values())

    print(f"Đã lập hồ sơ {len(ho_so)} tài liệu:")
    print(f"  - Nhận ra số hiệu:      {co_so_hieu}")
    print(f"  - Nhận ra ngày ban hành:{co_ngay}")
    print(f"  - Quan hệ trích được:   {tong_quan_he}")
    print(f"  - Bị thay thế bởi văn bản khác TRONG KHO: {len(bi_thay_the)}")
    for muc in bi_thay_the:
        print(f"      {muc.ten_file[:55]} <- {', '.join(muc.bi_thay_the_boi)[:60]}")
    print(f"  - Bị sửa đổi bởi văn bản khác TRONG KHO:  {len(bi_sua_doi)}")
    for muc in bi_sua_doi:
        print(f"      {muc.ten_file[:55]} <- {', '.join(muc.bi_sua_doi_boi)[:60]}")
    print(f"\nĐã ghi {DUONG_DAN_HO_SO}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
