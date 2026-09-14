"""Sinh câu hỏi gợi ý cho giao diện: gợi ý mở đầu và gợi ý hỏi tiếp.

Hai chỗ cần gợi ý: màn hình chào (ngoài bốn thẻ chủ đề cố định) và cuối mỗi câu
trả lời. Cả hai đều dựng từ dữ liệu có sẵn - tên tài liệu trong kho, số hiệu và
nhãn hiệu lực của nguồn vừa trích - chứ không gọi thêm mô hình: một lượt sinh
nữa trên CPU là thêm hàng chục giây chỉ để có một hàng nút bấm, mà câu do mô
hình tự nghĩ lại hay hỏi sang thứ kho không có tài liệu để trả lời.
"""

from __future__ import annotations

import os
import random
import re


SO_GOI_Y_MO_DAU = 6
SO_GOI_Y_TIEP = 3
SO_GOI_Y_TOI_DA = 12

# Câu hỏi mở đầu viết tay theo bốn nhóm chủ đề trên màn hình chào. Mỗi câu đều
# có văn bản tương ứng trong kho để bấm vào là ra được câu trả lời có nguồn.
GOI_Y_CHU_DE = (
    # Mầm non & phổ thông
    "Chương trình giáo dục phổ thông 2018 đặt ra những yêu cầu nào về phẩm chất và năng lực?",
    "Việc đánh giá học sinh tiểu học được thực hiện theo những hình thức nào?",
    "Kế hoạch bài dạy theo Công văn 5512 gồm những phần nào?",
    "Ma trận và bản đặc tả đề kiểm tra được xây dựng theo các bước nào?",
    "Quy định về dạy thêm, học thêm hiện nay như thế nào?",
    "Học sinh phổ thông được miễn học phí và sách giáo khoa trong những trường hợp nào?",
    # Giáo dục nghề nghiệp
    "Khung trình độ quốc gia Việt Nam gồm những bậc trình độ nào?",
    "Khung cơ cấu hệ thống giáo dục quốc dân gồm những cấp học và trình độ nào?",
    "Cơ sở giáo dục nghề nghiệp được tự chủ những nội dung gì?",
    # Giáo dục đại học
    "Quy định về tự chủ của cơ sở giáo dục đại học gồm những nội dung nào?",
    "Việc ứng dụng công nghệ trong giáo dục đại học và giáo dục nghề nghiệp được quy định thế nào?",
    "Quỹ Học bổng Quốc gia được tổ chức, quản lý và sử dụng ra sao?",
    "Chương trình xây dựng nguồn tài nguyên giáo dục mở có những mục tiêu nào?",
    # Chính sách và đội ngũ nhà giáo
    "Luật Nhà giáo được hướng dẫn thi hành với những nội dung chính nào?",
    "Nhà giáo và cán bộ quản lý giáo dục được hưởng phụ cấp ưu đãi theo nghề thế nào?",
    "Lộ trình nâng trình độ chuẩn được đào tạo của giáo viên mầm non, tiểu học, trung học cơ sở ra sao?",
    "Sở Giáo dục và Đào tạo có những chức năng, nhiệm vụ và quyền hạn nào?",
)

# Tên tệp bắt đầu bằng một trong các từ này thì đọc lên đã thành tên văn bản,
# chỉ cần ghép thêm phần hỏi.
_LOAI_VAN_BAN_MO_DAU = (
    "thông tư", "nghị định", "nghị quyết", "quyết định", "công văn", "công điện",
    "chỉ thị", "thông báo", "luật", "kế hoạch", "đề án", "hướng dẫn", "quy định",
    "quy chế", "phê duyệt", "sửa đổi",
)

# "...về các công nghệ ch--caa14599": cổng văn bản cắt tên dài rồi dán mã băm.
_MA_BAM_CUOI = re.compile(r"-{2}[0-9a-f]{6,}$")
# Số hiệu trong tên tệp tải về bị đổi dấu "/" thành "_": "86_2021_NĐ-CP".
_SO_HIEU_GACH_DUOI = re.compile(r"(\d)_(\d{4})_([A-Za-zĐđ])")
_KY_TU_CO_DAU = re.compile(
    "[ăâđêôơưàáảãạằắẳẵặầấẩẫậèéẻẽẹềếểễệìíỉĩịòóỏõọồốổỗộờớởỡợùúủũụừứửữựỳýỷỹỵ]"
)
_DIEU_DAU = re.compile(r"^\s*(Điều\s+\d+)", re.IGNORECASE)
_KHONG_PHAI_CHU = re.compile(r"\W+", re.UNICODE)

_DO_DAI_TIEU_DE_TOI_THIEU = 30
_SO_TU_TIEU_DE_TOI_THIEU = 5
_SO_DAU_TOI_THIEU = 3
# Tên văn bản dài 150 ký tự vẫn là tên hợp lệ, nhưng nhồi cả vào một nút gợi ý
# thì không ai đọc; kho còn thừa tên ngắn để chọn nên bỏ qua là rẻ nhất.
_DO_DAI_CAU_HOI_TOI_DA = 120


def _chuan_hoa(cau: str) -> str:
    """Dạng rút gọn chỉ để so trùng, không dùng để hiển thị."""
    return _KHONG_PHAI_CHU.sub(" ", str(cau or "").casefold()).strip()


def _loc_trung(cac_cau, da_co=()) -> list[str]:
    """Bỏ câu trùng nhau và câu trùng với những gì đã hỏi/đã có."""
    da_thay = [_chuan_hoa(cau) for cau in da_co if cau]
    ket_qua = []
    for cau in cac_cau:
        khoa = _chuan_hoa(cau)
        if not khoa:
            continue
        # Bao nhau cũng coi là trùng: "Tóm tắt tệp A" và "Tóm tắt tệp A gồm gì"
        # đặt cạnh nhau chỉ làm loãng ba chỗ gợi ý ít ỏi.
        if any(khoa == cu or khoa in cu or cu in khoa for cu in da_thay):
            continue
        da_thay.append(khoa)
        ket_qua.append(str(cau).strip())
    return ket_qua


def _lam_sach_tieu_de(ten_file: str) -> str | None:
    """Đổi tên tệp thành cụm từ đọc được, trả None nếu tên chỉ là mã số.

    Kho có hai kiểu tên lẫn nhau: tên tải từ cổng văn bản ("Thông tư quy định về
    dạy thêm, học thêm.pdf") dùng làm gợi ý rất tốt, còn tên mã hóa
    ("5512_BGDDT-GDTrH_462988.doc", "PPCT-5.docx", "20-bgddt.pdf") thì không đọc
    lên thành câu hỏi được nên phải loại.
    """
    ten = os.path.splitext(str(ten_file or ""))[0].strip()
    ten = _SO_HIEU_GACH_DUOI.sub(r"\1/\2/\3", ten).replace("_", " ")
    khop_ma = _MA_BAM_CUOI.search(ten)
    if khop_ma:
        # Chữ cuối thường bị cắt dở ("...về các công nghệ ch") nên bỏ luôn.
        ten = ten[: khop_ma.start()].rstrip(" -")
        ten = ten.rsplit(" ", 1)[0]
    ten = re.sub(r"\s+", " ", ten).strip(" -.,;")
    if len(ten) < _DO_DAI_TIEU_DE_TOI_THIEU or len(ten.split()) < _SO_TU_TIEU_DE_TOI_THIEU:
        return None
    # Không có dấu tiếng Việt thì gần như chắc chắn là tên viết tắt, viết liền
    # ("PhanPhoi-ChuongTrinh-Tin4", "QUAN 10 - NOI DUNG GDKNCDS KHOI LOP 3-4-5").
    if len(_KY_TU_CO_DAU.findall(ten.casefold())) < _SO_DAU_TOI_THIEU:
        return None
    return ten


def _cau_hoi_tu_tieu_de(tieu_de: str) -> str:
    if tieu_de.casefold().startswith(_LOAI_VAN_BAN_MO_DAU):
        return f"{tieu_de} có những nội dung chính nào?"
    return f"Nội dung chính của tài liệu \"{tieu_de}\" là gì?"


def goi_y_tu_kho(ho_so=None) -> list[str]:
    """Câu hỏi dựng từ tên tài liệu thật trong kho - gợi ý nào cũng có nguồn."""
    cau_hoi = []
    for ten_file in (ho_so or {}):
        tieu_de = _lam_sach_tieu_de(ten_file)
        if not tieu_de:
            continue
        cau = _cau_hoi_tu_tieu_de(tieu_de)
        if len(cau) <= _DO_DAI_CAU_HOI_TOI_DA:
            cau_hoi.append(cau)
    return _loc_trung(cau_hoi)


def goi_y_mo_dau(ho_so=None, so_luong: int = SO_GOI_Y_MO_DAU, bo_ngau_nhien=None) -> list[str]:
    """Gợi ý cho màn hình chào, đổi mẻ mỗi lần gọi."""
    bo = bo_ngau_nhien or random
    try:
        so_luong = int(so_luong)
    except (TypeError, ValueError):
        so_luong = SO_GOI_Y_MO_DAU
    so_luong = max(1, min(so_luong, SO_GOI_Y_TOI_DA))

    tu_kho = goi_y_tu_kho(ho_so)
    chu_de = list(GOI_Y_CHU_DE)
    bo.shuffle(tu_kho)
    bo.shuffle(chu_de)
    # Trộn một nửa từ tên tài liệu trong kho, một nửa là câu hỏi chủ đề: chỉ lấy
    # từ kho thì gợi ý nào cũng dài dòng như tên văn bản, chỉ lấy chủ đề thì kho
    # thêm tài liệu mới mà gợi ý vẫn y nguyên mấy câu cũ.
    phan_kho = tu_kho[: so_luong // 2]
    ket_qua = _loc_trung(phan_kho + chu_de[: so_luong - len(phan_kho)])
    if len(ket_qua) < so_luong:
        ket_qua = _loc_trung(ket_qua + tu_kho + chu_de)[:so_luong]
    bo.shuffle(ket_qua)
    return ket_qua[:so_luong]


def _ten_goi(nguon: dict) -> str:
    """Cách gọi nguồn trong câu gợi ý: ưu tiên số hiệu, sau đó tới tên tài liệu."""
    van_ban = nguon.get("van_ban") or {}
    if van_ban.get("so_hieu"):
        return f"{van_ban.get('loai') or 'Văn bản'} {van_ban['so_hieu']}"
    ten_file = nguon.get("name") or ""
    return _lam_sach_tieu_de(ten_file) or str(ten_file) or "tài liệu này"


def _cau_hoi_theo_nguon(nguon: dict, ten: str) -> str | None:
    """Một câu hỏi tiếp cho đúng nguồn này, theo thứ tự cần biết trước.

    Vướng hiệu lực là thứ phải hỏi trước tiên - đọc tiếp một văn bản đã bị thay
    thế thì càng đọc càng sai. Hết chuyện hiệu lực mới tới đọc sâu vào Điều đang
    được trích, rồi mới tới quan hệ với các văn bản cũ.
    """
    ma_hieu_luc = (nguon.get("validity") or {}).get("code")
    if ma_hieu_luc == "bi_thay_the":
        return f"Văn bản nào đã thay thế {ten}?"
    if ma_hieu_luc in {"bi_sua_doi", "doan_sua_doi"}:
        return f"{ten} đã được sửa đổi, bổ sung những nội dung nào?"
    if ma_hieu_luc == "chua_hieu_luc":
        return f"{ten} có hiệu lực từ ngày nào và áp dụng ra sao?"
    if ma_hieu_luc == "du_thao":
        return f"Đã có văn bản chính thức nào ban hành thay cho bản dự thảo {ten} chưa?"
    khop_dieu = _DIEU_DAU.match(str(nguon.get("article") or ""))
    if khop_dieu:
        return f"{khop_dieu.group(1)} của {ten} quy định chi tiết những gì?"
    if (nguon.get("van_ban") or {}).get("thay_the"):
        return f"{ten} thay thế những văn bản nào?"
    return None


def goi_y_tiep_theo(cau_hoi: str, cac_nguon=None, so_luong: int = SO_GOI_Y_TIEP) -> list[str]:
    """Gợi ý hỏi tiếp sau một câu trả lời có trích nguồn."""
    cac_nguon = [nguon for nguon in (cac_nguon or []) if isinstance(nguon, dict)]
    # Mỗi văn bản chỉ góp một câu: một câu trả lời thường trích hai ba đoạn của
    # cùng một thông tư, để nguyên thì cả ba chỗ gợi ý đều hỏi về đúng văn bản
    # đó và người đọc mất hẳn hướng nhìn sang những nguồn còn lại.
    ung_vien = []
    da_co = set()
    for nguon in cac_nguon[:4]:
        ten = _ten_goi(nguon)
        if ten in da_co:
            continue
        cau = _cau_hoi_theo_nguon(nguon, ten)
        if cau:
            da_co.add(ten)
            ung_vien.append(cau)
    if cac_nguon:
        ung_vien.append(f"Tóm tắt những nội dung chính của {_ten_goi(cac_nguon[0])}")
    ung_vien += [
        "Nội dung này áp dụng cho những đối tượng nào?",
        "Có mốc thời gian hoặc lộ trình thực hiện nào không?",
        "Còn văn bản nào khác trong kho quy định về nội dung này?",
    ]
    return _loc_trung(ung_vien, da_co=[cau_hoi])[:max(0, so_luong)]


def goi_y_theo_tep(cau_hoi: str, ten_tep=None, so_luong: int = SO_GOI_Y_TIEP) -> list[str]:
    """Gợi ý hỏi tiếp khi câu trả lời chỉ dựa trên tệp người dùng đính kèm."""
    ten_tep = [str(ten) for ten in (ten_tep or []) if ten]
    ung_vien = [f"Tóm tắt tệp {ten}" for ten in ten_tep[:2]]
    if len(ten_tep) > 1:
        ung_vien.append("So sánh nội dung giữa các tệp đã đính kèm")
    ung_vien += [f"Tệp {ten} gồm những phần nào?" for ten in ten_tep[:2]]
    ung_vien.append("Trong tệp có nêu mốc thời gian hoặc số liệu nào không?")
    return _loc_trung(ung_vien, da_co=[cau_hoi])[:max(0, so_luong)]
