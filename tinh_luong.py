"""
CÔNG CỤ TÍNH LƯƠNG NHÀ GIÁO - TÍNH BẰNG PYTHON, KHÔNG ĐỂ MÔ HÌNH LÀM TOÁN
==========================================================================
Vì sao tách hẳn khỏi RAG thay vì dạy prompt cách tính: ba lớp bảo vệ của dự án
đều chống lại việc mô hình tự sinh ra con số.

  - Prompt (main.py) cấm "ghép số liệu của hai EVIDENCE khác nhau thành thông
    tin mới" - mà tính lương CHÍNH LÀ lấy hệ số ở Thông tư nhân lương cơ sở ở
    Nghị định.
  - Hậu kiểm (kiem_tra_tra_loi.py) gắn cờ mọi con số không có nguyên văn trong
    đoạn trích - kết quả tính ra thì không văn bản nào chứa sẵn.
  - Model đang chạy là loại 3B trên CPU; số học nhiều bước không đáng tin.

Nới ba lớp đó ra để mô hình được làm toán là đánh đổi sai: mất cả cơ chế chống
bịa, đổi lấy một phép nhân. Ở đây đi hướng ngược lại - phép tính do Python làm,
deterministic, chạy trong micro giây thay vì 150 giây, và mỗi hằng số đi kèm
đúng điều khoản quy định nó.

NGUYÊN TẮC: hằng số nào chưa có văn bản trong kho chứng minh thì đánh dấu
`trong_kho=False` và kết quả phải nói rõ. Thà hiện "chưa có căn cứ trong kho"
còn hơn im lặng đưa ra một con số trông như đã được kiểm chứng.

    python tinh_luong.py "tính lương giáo viên THPT hạng III bậc 1"
"""

from __future__ import annotations

import re
import sys
from dataclasses import dataclass, field


# ============================================================
# HẰNG SỐ KÈM CĂN CỨ
# ============================================================
@dataclass(frozen=True)
class CanCu:
    """Một con số kèm nơi nó được quy định.

    `trong_kho=False` nghĩa là kho tài liệu của chatbot CHƯA có văn bản này -
    con số vẫn dùng được nhưng kết quả phải cảnh báo, không được trình bày như
    thể đã tra được nguồn.
    """

    van_ban: str
    dieu_khoan: str
    trong_kho: bool = True
    ten_tep: str | None = None
    trich: str = ""

    def mo_ta(self) -> str:
        return f"{self.van_ban}, {self.dieu_khoan}"


NGHI_DINH_73 = CanCu(
    van_ban="Nghị định 73/2024/NĐ-CP",
    dieu_khoan="Điều 3 khoản 2",
    ten_tep="Nghị định quy định mức lương cơ sở và chế độ tiền thưởng đối với "
            "cán bộ, công chức, viên chức và lực lượng vũ trang.pdf",
    trich="Từ ngày 01 tháng 7 năm 2024, mức lương cơ sở là 2.340.000 đồng/tháng.",
)

THONG_TU_31 = CanCu(
    van_ban="Thông tư 31/2026/TT-BGDĐT",
    dieu_khoan="Điều 6 đến Điều 14",
    ten_tep="Thông tư quy định mã số, bổ nhiệm chức danh và xếp lương đối với "
            "nhà giáo trong cơ sở giáo dục công lập.pdf",
    trich="Được áp dụng bảng lương tương ứng ban hành kèm theo Nghị định "
          "số 204/2004/NĐ-CP.",
)

THONG_TU_04 = CanCu(
    van_ban="Thông tư 04/2021/TT-BGDĐT",
    dieu_khoan="Điều 8",
    ten_tep="Thông tư quy định mã số, tiêu chuẩn chức danh nghề nghiệp và bổ "
            "nhiệm, xếp lương viên chức giảng dạy trong các trường trung học "
            "phổ thông công lập.pdf",
    trich="Giáo viên trung học phổ thông hạng III, mã số V.07.05.15, được áp "
          "dụng hệ số lương của viên chức loại A1, từ hệ số lương 2,34 đến hệ "
          "số lương 4,98.",
)

ND_UU_DAI = CanCu(
    van_ban="Nghị định về phụ cấp ưu đãi theo nghề đối với nhà giáo",
    dieu_khoan="Điều 3 và Điều 5",
    ten_tep="Nghị định quy định chế độ phụ cấp ưu đãi theo nghề đối với nhà "
            "giáo, cán bộ quản lý cơ sở giáo dục và nhân sự hỗ trợ giáo dục "
            "công tác trong các cơ sở giáo dục công lập.pdf",
    trich="Mức phụ cấp ưu đãi 40% được áp dụng đối với nhà giáo giảng dạy "
          "trong trường trung học cơ sở, trường trung học phổ thông, trường "
          "trung học nghề.",
)

# Bảng lương chuyên môn nghiệp vụ là phụ lục của Nghị định 204/2004 - văn bản
# này KHÔNG nằm trong kho, chỉ được các Thông tư dẫn chiếu tới. Hai đầu mút của
# mỗi ngạch thì có trong kho (Thông tư ghi rõ "từ ... đến ..."), phần bậc ở giữa
# là nội suy đều theo đúng cấu trúc bảng lương. `_kiem_tra_bang()` bên dưới đối
# chiếu lại hai đầu mút với con số đọc được từ Thông tư.
ND_204 = CanCu(
    van_ban="Nghị định 204/2004/NĐ-CP",
    dieu_khoan="Bảng 3 - bảng lương chuyên môn nghiệp vụ",
    trong_kho=False,
    trich="Hai đầu mút của mỗi ngạch lấy từ Thông tư có trong kho; các bậc ở "
          "giữa nội suy đều theo cấu trúc bảng lương.",
)

# Tỉ lệ trích đóng của NGƯỜI LAO ĐỘNG: BHXH 8% + BHYT 1,5% + BHTN 1%.
# Do pháp luật bảo hiểm quy định, không phải văn bản giáo dục - kho chưa có.
BAO_HIEM = CanCu(
    van_ban="Luật Bảo hiểm xã hội và Luật Bảo hiểm y tế",
    dieu_khoan="mức đóng của người lao động: BHXH 8% + BHYT 1,5% + BHTN 1%",
    trong_kho=False,
)

LUONG_CO_SO = 2_340_000
TY_LE_BHXH = 0.08
TY_LE_BHYT = 0.015
TY_LE_BHTN = 0.01
TY_LE_TRICH_DONG = TY_LE_BHXH + TY_LE_BHYT + TY_LE_BHTN  # 10,5%


# ============================================================
# BẢNG HỆ SỐ LƯƠNG THEO NGẠCH
# ============================================================
@dataclass(frozen=True)
class BangHeSo:
    """Một ngạch viên chức: hệ số bậc 1, hệ số bậc cuối, số bậc.

    Sinh ra cả bảng thay vì chép tay 60 con số: chép tay thì sai một chữ số là
    sai lương cả đời một người, mà không ai rà lại được. Sinh ra thì chỉ cần
    đúng ba tham số, và hai trong ba tham số đối chiếu thẳng được với câu
    "từ hệ số lương X đến hệ số lương Y" in trong Thông tư.
    """

    dau: float
    cuoi: float
    so_bac: int

    @property
    def buoc(self) -> float:
        return round((self.cuoi - self.dau) / (self.so_bac - 1), 2)

    def he_so(self, bac: int) -> float:
        if not 1 <= bac <= self.so_bac:
            raise ValueError(
                f"Ngạch này chỉ có {self.so_bac} bậc, không có bậc {bac}."
            )
        return round(self.dau + self.buoc * (bac - 1), 2)

    def cac_bac(self) -> list[float]:
        return [self.he_so(b) for b in range(1, self.so_bac + 1)]


NGACH: dict[str, BangHeSo] = {
    "A0": BangHeSo(2.10, 4.89, 10),
    "A1": BangHeSo(2.34, 4.98, 9),
    "A2.1": BangHeSo(4.40, 6.78, 8),
    "A2.2": BangHeSo(4.00, 6.38, 8),
    "A3.1": BangHeSo(6.20, 8.00, 6),
    "A3.2": BangHeSo(5.75, 7.55, 6),
    "B": BangHeSo(1.86, 4.06, 12),
}


def _kiem_tra_bang() -> None:
    """Bậc cuối sinh ra phải đúng bằng đầu mút ghi trong Thông tư, và bước phải
    đều. Chạy ngay lúc import: bảng sai thì phải hỏng ở đây, chứ không phải
    hỏng lặng lẽ trong phiếu lương của ai đó."""
    for ten, bang in NGACH.items():
        cuoi = bang.he_so(bang.so_bac)
        if abs(cuoi - bang.cuoi) > 0.005:
            raise AssertionError(
                f"Ngạch {ten}: bậc cuối sinh ra {cuoi} khác đầu mút {bang.cuoi}"
            )
        buoc = {
            round(bang.he_so(b + 1) - bang.he_so(b), 2)
            for b in range(1, bang.so_bac)
        }
        if len(buoc) != 1:
            raise AssertionError(f"Ngạch {ten}: bước không đều - {sorted(buoc)}")


_kiem_tra_bang()


# ============================================================
# CHỨC DANH NHÀ GIÁO -> NGẠCH
# ============================================================
@dataclass(frozen=True)
class ChucDanh:
    khoa: str
    ten: str
    hang: str
    ma_so: str
    ngach: str
    pc_uu_dai: float  # tỉ lệ mặc định ở địa bàn thường
    can_cu: CanCu
    # Văn bản từng là căn cứ xếp lương cho chức danh này, nay đã hết hiệu lực.
    # Giáo viên hay cầm bản Thông tư cũ đi đối chiếu, nên nói thẳng ra là nó đã
    # bị thay thế MÀ hệ số không đổi, thay vì im lặng để họ tự nghi ngờ.
    can_cu_cu: CanCu | None = None

    @property
    def bang(self) -> BangHeSo:
        return NGACH[self.ngach]

    def mo_ta(self) -> str:
        return f"{self.ten} hạng {self.hang} (mã số {self.ma_so})"


# Thông tư 31/2026 Điều 17 làm hết hiệu lực Điều 8 của Thông tư 04/2021 (và các
# Điều tương ứng của 01, 02, 03/2021). Hệ số thì GIỮ NGUYÊN - đối chiếu hai văn
# bản cho kết quả trùng khít với giáo viên phổ thông, chỉ khác căn cứ pháp lý.
CHUC_DANH: list[ChucDanh] = [
    ChucDanh("mam_non", "Giáo viên mầm non", "III", "V.07.02.26", "A0", 0.45, THONG_TU_31),
    ChucDanh("mam_non", "Giáo viên mầm non", "II", "V.07.02.25", "A1", 0.45, THONG_TU_31),
    ChucDanh("mam_non", "Giáo viên mầm non", "I", "V.07.02.24", "A2.2", 0.45, THONG_TU_31),

    ChucDanh("tieu_hoc", "Giáo viên tiểu học", "III", "V.07.03.29", "A1", 0.45, THONG_TU_31),
    ChucDanh("tieu_hoc", "Giáo viên tiểu học", "II", "V.07.03.28", "A2.2", 0.45, THONG_TU_31),
    ChucDanh("tieu_hoc", "Giáo viên tiểu học", "I", "V.07.03.27", "A2.1", 0.45, THONG_TU_31),

    ChucDanh("thcs", "Giáo viên trung học cơ sở", "III", "V.07.04.32", "A1", 0.40, THONG_TU_31),
    ChucDanh("thcs", "Giáo viên trung học cơ sở", "II", "V.07.04.31", "A2.2", 0.40, THONG_TU_31),
    ChucDanh("thcs", "Giáo viên trung học cơ sở", "I", "V.07.04.30", "A2.1", 0.40, THONG_TU_31),

    ChucDanh("thpt", "Giáo viên trung học phổ thông", "III", "V.07.05.15", "A1", 0.40, THONG_TU_31, THONG_TU_04),
    ChucDanh("thpt", "Giáo viên trung học phổ thông", "II", "V.07.05.14", "A2.2", 0.40, THONG_TU_31, THONG_TU_04),
    ChucDanh("thpt", "Giáo viên trung học phổ thông", "I", "V.07.05.13", "A2.1", 0.40, THONG_TU_31, THONG_TU_04),

    ChucDanh("du_bi_dh", "Giáo viên dự bị đại học", "III", "V.07.07.19", "A1", 0.80, THONG_TU_31),
    ChucDanh("du_bi_dh", "Giáo viên dự bị đại học", "II", "V.07.07.18", "A2.2", 0.80, THONG_TU_31),
    ChucDanh("du_bi_dh", "Giáo viên dự bị đại học", "I", "V.07.07.17", "A2.1", 0.80, THONG_TU_31),

    ChucDanh("giang_vien", "Giảng viên đại học", "III", "V.07.01.03", "A1", 0.25, THONG_TU_31),
    ChucDanh("giang_vien", "Giảng viên chính", "II", "V.07.01.02", "A2.1", 0.25, THONG_TU_31),
    ChucDanh("giang_vien", "Giảng viên cao cấp", "I", "V.07.01.01", "A3.1", 0.25, THONG_TU_31),
]

# Địa bàn nâng mức phụ cấp ưu đãi (Nghị định phụ cấp ưu đãi, Điều 3).
DIA_BAN = {
    "thuong": (None, "địa bàn thường"),
    "kv1_kv2": (0.45, "xã khu vực I, khu vực II vùng đồng bào dân tộc thiểu số "
                      "và miền núi; xã đảo, hải đảo, xã biên giới"),
    "dac_biet_kho_khan": (0.70, "vùng có điều kiện kinh tế - xã hội đặc biệt "
                                "khó khăn"),
    "chuyen_noi_tru": (0.80, "trường chuyên, phổ thông dân tộc nội trú, trường "
                             "dự bị đại học"),
}


def tim_chuc_danh(cap_hoc: str, hang: str) -> ChucDanh | None:
    for cd in CHUC_DANH:
        if cd.khoa == cap_hoc and cd.hang == hang:
            return cd
    return None


# ============================================================
# THAM SỐ VÀ KẾT QUẢ
# ============================================================
@dataclass
class ThamSo:
    chuc_danh: ChucDanh
    bac: int | None = None
    he_so: float | None = None
    dia_ban: str = "thuong"
    pc_uu_dai: float | None = None        # ghi đè tỉ lệ suy ra từ chức danh
    he_so_chuc_vu: float = 0.0            # phụ cấp chức vụ lãnh đạo
    ty_le_vuot_khung: float = 0.0         # phụ cấp thâm niên vượt khung
    he_so_bao_luu: float = 0.0
    ty_le_tham_nien: float | None = None   # phụ cấp thâm niên nhà giáo, nếu có

    def he_so_hien_huong(self) -> float:
        if self.he_so is not None:
            return self.he_so
        return self.chuc_danh.bang.he_so(self.bac or 1)


@dataclass
class Dong:
    """Một dòng trong phiếu tính: nhãn, cách ra con số, và số tiền."""

    nhan: str
    cong_thuc: str
    so_tien: int
    can_cu: CanCu | None = None


@dataclass
class KetQua:
    tham_so: ThamSo
    dong: list[Dong] = field(default_factory=list)
    tong_thu_nhap: int = 0
    nen_dong_bao_hiem: int = 0
    khau_tru: int = 0
    thuc_linh: int = 0
    canh_bao: list[str] = field(default_factory=list)
    can_cu_da_dung: list[CanCu] = field(default_factory=list)


def _tien(x: float) -> int:
    """Làm tròn tới đồng. Không giữ phần lẻ: phiếu lương trả bằng đồng."""
    return int(round(x))


def dinh_dang_tien(x: int) -> str:
    return f"{x:,}".replace(",", ".")


def dinh_dang_so(x: float, chu_so: int = 2) -> str:
    """Số thập phân kiểu Việt: 2,34 chứ không phải 2.34. Quan trọng hơn thẩm mỹ -
    văn bản quy phạm viết "hệ số lương 2,34", người đọc phải đối chiếu được
    nguyên dạng con số in trong Thông tư."""
    return f"{x:.{chu_so}f}".replace(".", ",")


def dinh_dang_ty_le(x: float) -> str:
    return f"{x * 100:g}%".replace(".", ",")


# ============================================================
# PHÉP TÍNH
# ============================================================
def tinh(ts: ThamSo) -> KetQua:
    """Tính lương hằng tháng. Mỗi bước là một dòng kèm công thức đã thay số -
    người dùng phải kiểm lại được bằng máy tính bỏ túi, không phải tin suông."""
    kq = KetQua(tham_so=ts)
    cd = ts.chuc_danh
    lcs = LUONG_CO_SO

    he_so = ts.he_so_hien_huong()
    if ts.bac is not None and ts.he_so is not None:
        he_so_theo_bac = cd.bang.he_so(ts.bac)
        if abs(he_so_theo_bac - ts.he_so) > 0.005:
            kq.canh_bao.append(
                f"Bậc {ts.bac} của {cd.mo_ta()} có hệ số "
                f"{dinh_dang_so(he_so_theo_bac)}, không phải "
                f"{dinh_dang_so(ts.he_so)} như câu hỏi nêu. Kết quả dưới đây "
                f"tính theo hệ số {dinh_dang_so(he_so)}."
            )

    # 1. Lương theo hệ số
    luong_he_so = _tien(he_so * lcs)
    kq.dong.append(Dong(
        "Lương theo hệ số",
        f"{dinh_dang_so(he_so)} × {dinh_dang_tien(lcs)}",
        luong_he_so,
        NGHI_DINH_73,
    ))

    # 2. Phụ cấp chức vụ lãnh đạo
    pc_chuc_vu = _tien(ts.he_so_chuc_vu * lcs) if ts.he_so_chuc_vu else 0
    if pc_chuc_vu:
        kq.dong.append(Dong(
            "Phụ cấp chức vụ lãnh đạo",
            f"{dinh_dang_so(ts.he_so_chuc_vu)} × {dinh_dang_tien(lcs)}",
            pc_chuc_vu,
            ND_204,
        ))

    # 3. Phụ cấp thâm niên vượt khung
    pc_vuot_khung = (
        _tien(luong_he_so * ts.ty_le_vuot_khung) if ts.ty_le_vuot_khung else 0
    )
    if pc_vuot_khung:
        kq.dong.append(Dong(
            "Phụ cấp thâm niên vượt khung",
            f"{dinh_dang_tien(luong_he_so)} × "
            f"{dinh_dang_ty_le(ts.ty_le_vuot_khung)}",
            pc_vuot_khung,
            ND_204,
        ))

    # 4. Chênh lệch bảo lưu
    pc_bao_luu = _tien(ts.he_so_bao_luu * lcs) if ts.he_so_bao_luu else 0
    if pc_bao_luu:
        kq.dong.append(Dong(
            "Hệ số chênh lệch bảo lưu",
            f"{dinh_dang_so(ts.he_so_bao_luu)} × {dinh_dang_tien(lcs)}",
            pc_bao_luu,
            ND_204,
        ))

    # 5. Phụ cấp ưu đãi theo nghề.
    #    Nền tính KHÔNG gồm phụ cấp thâm niên nhà giáo - Điều 5 Nghị định phụ
    #    cấp ưu đãi liệt kê đúng bốn thành phần: hệ số lương hiện hưởng, phụ cấp
    #    chức vụ lãnh đạo, phụ cấp thâm niên vượt khung, hệ số chênh lệch bảo lưu.
    ty_le_ud = ts.pc_uu_dai if ts.pc_uu_dai is not None else _uu_dai_theo_dia_ban(ts)
    nen_uu_dai = luong_he_so + pc_chuc_vu + pc_vuot_khung + pc_bao_luu
    pc_uu_dai = _tien(nen_uu_dai * ty_le_ud)
    kq.dong.append(Dong(
        f"Phụ cấp ưu đãi theo nghề ({dinh_dang_ty_le(ty_le_ud)})",
        f"{dinh_dang_tien(nen_uu_dai)} × {dinh_dang_ty_le(ty_le_ud)}",
        pc_uu_dai,
        ND_UU_DAI,
    ))

    # 6. Phụ cấp thâm niên nhà giáo - chỉ tính khi người dùng khai rõ tỉ lệ.
    #    Mặc định KHÔNG tính: kho tài liệu không có văn bản nào quy định khoản
    #    này, nên tự ý cộng vào là đưa ra một con số không có căn cứ.
    pc_tham_nien = 0
    if ts.ty_le_tham_nien:
        nen_tn = luong_he_so + pc_chuc_vu + pc_vuot_khung
        pc_tham_nien = _tien(nen_tn * ts.ty_le_tham_nien)
        kq.dong.append(Dong(
            f"Phụ cấp thâm niên nhà giáo ({dinh_dang_ty_le(ts.ty_le_tham_nien)})",
            f"{dinh_dang_tien(nen_tn)} × {dinh_dang_ty_le(ts.ty_le_tham_nien)}",
            pc_tham_nien,
            None,
        ))
        kq.canh_bao.append(
            "Phụ cấp thâm niên nhà giáo tính theo tỉ lệ bạn cung cấp. Kho tài "
            "liệu hiện KHÔNG có văn bản nào quy định khoản phụ cấp này, nên "
            "con số đó chưa được đối chiếu với nguồn nào."
        )

    kq.tong_thu_nhap = (
        luong_he_so + pc_chuc_vu + pc_vuot_khung + pc_bao_luu
        + pc_uu_dai + pc_tham_nien
    )

    # 7. Trích đóng bảo hiểm. Phụ cấp ưu đãi KHÔNG nằm trong nền đóng -
    #    Điều 7 khoản 1: "không dùng để tính đóng, hưởng chế độ bảo hiểm xã hội".
    kq.nen_dong_bao_hiem = (
        luong_he_so + pc_chuc_vu + pc_vuot_khung + pc_bao_luu + pc_tham_nien
    )
    kq.khau_tru = _tien(kq.nen_dong_bao_hiem * TY_LE_TRICH_DONG)
    kq.thuc_linh = kq.tong_thu_nhap - kq.khau_tru

    kq.can_cu_da_dung = _gom_can_cu(kq)
    for cc in kq.can_cu_da_dung:
        if not cc.trong_kho:
            kq.canh_bao.append(
                f"{cc.van_ban} chưa có trong kho tài liệu: con số lấy theo quy "
                f"định hiện hành nhưng chatbot không trích dẫn được nguồn."
            )
    return kq


def _uu_dai_theo_dia_ban(ts: ThamSo) -> float:
    muc, _ = DIA_BAN.get(ts.dia_ban, (None, ""))
    if muc is None:
        return ts.chuc_danh.pc_uu_dai
    # Địa bàn chỉ nâng lên, không hạ xuống: Điều 8 cho hưởng mức cao nhất trong
    # các mức mà một người cùng lúc thuộc diện được hưởng.
    return max(muc, ts.chuc_danh.pc_uu_dai)


def _gom_can_cu(kq: KetQua) -> list[CanCu]:
    ra: list[CanCu] = []
    for d in kq.dong:
        if d.can_cu is not None and d.can_cu not in ra:
            ra.append(d.can_cu)
    cd_can_cu = kq.tham_so.chuc_danh.can_cu
    if cd_can_cu not in ra:
        ra.insert(min(1, len(ra)), cd_can_cu)
    if BAO_HIEM not in ra:
        ra.append(BAO_HIEM)
    return ra


# ============================================================
# NHẬN DIỆN CÂU HỎI
# ============================================================
# Chỉ nhận khi câu hỏi vừa NÓI VỀ LƯƠNG vừa đủ tham số để tính. Thiếu một trong
# hai thì trả None để câu hỏi đi tiếp đường RAG bình thường - công cụ này chen
# ngang một câu tra cứu quy định thì tệ hơn hẳn việc không chen.
TU_KHOA_TINH = re.compile(
    r"tính|bao nhiêu|thực lĩnh|thực nhận|lĩnh bao nhiêu|tổng lương|"
    r"tổng thu nhập|lương của tôi|nhận được|ra lương",
    re.IGNORECASE,
)
TU_KHOA_LUONG = re.compile(r"lương|thu nhập|phụ cấp|thực lĩnh", re.IGNORECASE)

# Câu hỏi về QUY ĐỊNH, không phải về số tiền. Có mấy chữ này thì nhường đường
# cho RAG kể cả khi câu có đủ hạng và bậc: "điều kiện thăng hạng giáo viên THPT
# hạng II là gì" cần trích văn bản, không cần một phiếu lương.
TU_KHOA_TRA_CUU = re.compile(
    r"tiêu chuẩn|trình độ|điều kiện|thăng hạng|bổ nhiệm|nhiệm vụ|chứng chỉ|"
    r"quy định (?:ở đâu|tại đâu|thế nào|như thế nào)|căn cứ nào|văn bản nào",
    re.IGNORECASE,
)

CAP_HOC_MAU = [
    ("thpt", r"thpt|trung học phổ thông|trung hoc pho thong|cấp 3|cấp ba"),
    ("thcs", r"thcs|trung học cơ sở|trung hoc co so|cấp 2|cấp hai"),
    ("tieu_hoc", r"tiểu học|tieu hoc|cấp 1|cấp một"),
    ("mam_non", r"mầm non|mam non|mẫu giáo"),
    ("du_bi_dh", r"dự bị đại học|du bi dai hoc"),
    ("giang_vien", r"giảng viên|giang vien"),
]

# "hạng I" phải khớp SAU "hạng II" và "hạng III", nếu không "hạng III" bị đọc
# nhầm thành hạng I. Thứ tự danh sách này chính là thứ tự thử.
HANG_MAU = [
    ("III", r"hạng\s*(?:iii|3|ba)\b"),
    ("II", r"hạng\s*(?:ii|2|hai)\b"),
    ("I", r"hạng\s*(?:i|1|một|nhất)\b"),
]


def _so_thap_phan(chuoi: str) -> float:
    return float(chuoi.replace(",", "."))


def nhan_dien(cau_hoi: str) -> ThamSo | None:
    """Đọc câu hỏi thành tham số tính lương; None nghĩa là không phải câu tính
    lương, hoặc thiếu tham số nên không tính nổi."""
    if not cau_hoi or TU_KHOA_TRA_CUU.search(cau_hoi):
        return None

    thap = cau_hoi.lower()

    # Một HỆ SỐ CỤ THỂ tự nó đã đủ cả hai điều kiện dưới đây. Trong kho văn bản
    # giáo dục, "hệ số" viết kèm hai chữ số thập phân chỉ có một nghĩa là hệ số
    # lương, và không ai đưa con số đó vào câu hỏi tra cứu quy định - nó là tham
    # số của phép tính. Nhờ vậy "GV THPT hạng III bậc 1, hệ số 2,34" vẫn tính
    # được dù trong câu không có chữ "lương" nào.
    co_he_so_ro = bool(re.search(r"hệ\s*số\s*(?:lương\s*)?\d[.,]\d{1,2}", thap))

    # Cổng 1 - câu này có thuộc chuyện tiền lương không.
    if not co_he_so_ro and not TU_KHOA_LUONG.search(cau_hoi):
        return None
    # Cổng 2 - người dùng có muốn một CON SỐ không, hay chỉ hỏi quy định.
    if not co_he_so_ro and not TU_KHOA_TINH.search(cau_hoi):
        return None

    cap_hoc = next((k for k, mau in CAP_HOC_MAU if re.search(mau, thap)), None)
    if cap_hoc is None:
        return None

    hang = next((h for h, mau in HANG_MAU if re.search(mau, thap)), None)
    if hang is None:
        return None

    cd = tim_chuc_danh(cap_hoc, hang)
    if cd is None:
        return None

    bac = None
    m = re.search(r"bậc\s*(?:lương\s*)?(\d{1,2})", thap)
    if m:
        so = int(m.group(1))
        if 1 <= so <= cd.bang.so_bac:
            bac = so

    he_so = None
    m = re.search(r"hệ\s*số\s*(?:lương\s*)?(\d[.,]\d{1,2})", thap)
    if m:
        he_so = _so_thap_phan(m.group(1))
    else:
        # "bậc 1 2.34" - con số thập phân đứng riêng mà rơi đúng vào một bậc của
        # ngạch thì hiểu là hệ số. Chỉ nhận khi khớp đúng bảng, để không nuốt
        # nhầm một con số bất kỳ trong câu.
        for ung_vien in re.findall(r"\d[.,]\d{1,2}", thap):
            gia_tri = _so_thap_phan(ung_vien)
            if gia_tri in cd.bang.cac_bac():
                he_so = gia_tri
                break

    if bac is None and he_so is None:
        return None

    ts = ThamSo(chuc_danh=cd, bac=bac, he_so=he_so)

    if re.search(r"đặc biệt khó khăn|dac biet kho khan", thap):
        ts.dia_ban = "dac_biet_kho_khan"
    elif re.search(r"trường chuyên|nội trú|noi tru", thap):
        ts.dia_ban = "chuyen_noi_tru"
    elif re.search(r"khu vực i{1,2}\b|vùng dân tộc|miền núi|biên giới|hải đảo", thap):
        ts.dia_ban = "kv1_kv2"

    m = re.search(r"ưu đãi\s*(\d{1,2})\s*%", thap)
    if m:
        ts.pc_uu_dai = int(m.group(1)) / 100

    m = re.search(r"chức vụ\s*(?:lãnh đạo\s*)?(\d[.,]\d{1,2})", thap)
    if m:
        ts.he_so_chuc_vu = _so_thap_phan(m.group(1))

    m = re.search(r"vượt khung\s*(\d{1,2})\s*%", thap)
    if m:
        ts.ty_le_vuot_khung = int(m.group(1)) / 100

    m = re.search(r"thâm niên\s*(?:nhà giáo\s*)?(\d{1,2})\s*%", thap)
    if m:
        ts.ty_le_tham_nien = int(m.group(1)) / 100

    return ts


# ============================================================
# TRÌNH BÀY
# ============================================================
def dinh_dang(kq: KetQua) -> str:
    """Phiếu tính dạng Markdown: kết luận trước, rồi từng dòng kèm công thức."""
    ts = kq.tham_so
    cd = ts.chuc_danh
    he_so = ts.he_so_hien_huong()

    dau_de = f"**{cd.mo_ta()}**"
    if ts.bac:
        dau_de += f", bậc {ts.bac}"
    dau_de += f", hệ số {dinh_dang_so(he_so)}"

    dong = [
        f"Tổng thu nhập **{dinh_dang_tien(kq.tong_thu_nhap)} đồng/tháng**, "
        f"thực lĩnh sau trích đóng bảo hiểm "
        f"**{dinh_dang_tien(kq.thuc_linh)} đồng/tháng**.",
        "",
        f"{dau_de} · ngạch {cd.ngach} · lương cơ sở "
        f"{dinh_dang_tien(LUONG_CO_SO)} đồng/tháng.",
        "",
        "| Khoản | Cách tính | Số tiền |",
        "|---|---|---:|",
    ]
    for d in kq.dong:
        dong.append(f"| {d.nhan} | {d.cong_thuc} | {dinh_dang_tien(d.so_tien)} |")
    dong.append(
        f"| **Tổng thu nhập** | cộng các khoản trên | "
        f"**{dinh_dang_tien(kq.tong_thu_nhap)}** |"
    )
    dong.append(
        f"| Trích đóng BHXH, BHYT, BHTN | "
        f"{dinh_dang_tien(kq.nen_dong_bao_hiem)} × "
        f"{dinh_dang_ty_le(TY_LE_TRICH_DONG)} | "
        f"−{dinh_dang_tien(kq.khau_tru)} |"
    )
    dong.append(
        f"| **Thực lĩnh** | tổng thu nhập − trích đóng | "
        f"**{dinh_dang_tien(kq.thuc_linh)}** |"
    )

    dong.append("")
    dong.append("**Căn cứ:**")
    for cc in kq.can_cu_da_dung:
        nhan = "" if cc.trong_kho else " *(chưa có trong kho tài liệu)*"
        dong.append(f"- {cc.mo_ta()}{nhan}")
    if cd.can_cu_cu is not None:
        dong.append(
            f"- {cd.can_cu_cu.mo_ta()} — căn cứ trước đây, đã hết hiệu lực theo "
            f"Điều 17 {cd.can_cu.van_ban}. Hệ số lương của chức danh này "
            f"KHÔNG đổi giữa hai văn bản, nên kết quả tính ra là như nhau."
        )

    if kq.canh_bao:
        dong.append("")
        dong.append("**Lưu ý:**")
        for c in kq.canh_bao:
            dong.append(f"- {c}")

    dong.append("")
    dong.append(
        "*Phép tính do công cụ tính lương thực hiện, không phải mô hình ngôn "
        "ngữ sinh ra. Kết quả chưa gồm các khoản riêng của đơn vị (kiêm nhiệm, "
        "thừa giờ, thi đua) và chưa trừ thuế thu nhập cá nhân.*"
    )
    return "\n".join(dong)


def _thu_muc_kho() -> str:
    import os

    return os.path.abspath(os.getenv(
        "RAG_DATA_PATH",
        os.path.join(
            os.path.dirname(os.path.abspath(__file__)),
            "ollama-rag-desktop", "data_giao_duc",
        ),
    ))


_ten_tep_trong_kho: list[str] | None = None


def ten_tep_that(ten: str) -> str | None:
    """Tên tệp thật trong kho ứng với `ten`, hoặc None nếu kho không có.

    Không so khớp nguyên văn vì kho tự đặt lại tên tài liệu khi nạp - một bản
    trong kho đang mang tên bị cắt ngắn so với tiêu đề đầy đủ của Nghị định.
    Ghim cứng tên tệp vào hằng số thì chip nguồn sẽ hỏng lặng lẽ ở lần đổi tên
    tiếp theo, nên ở đây đối chiếu theo tiền tố dài nhất còn trùng.
    """
    import os
    import unicodedata

    global _ten_tep_trong_kho
    if _ten_tep_trong_kho is None:
        _ten_tep_trong_kho = []
        for thu_muc, _, cac_tep in os.walk(_thu_muc_kho()):
            del thu_muc
            _ten_tep_trong_kho.extend(cac_tep)

    chuan = lambda s: unicodedata.normalize("NFC", s).lower()
    muc = chuan(ten)
    if any(chuan(t) == muc for t in _ten_tep_trong_kho):
        return ten

    goc = muc.removesuffix(".pdf")
    ung_vien = [
        t for t in _ten_tep_trong_kho
        if goc.startswith(chuan(t).removesuffix(".pdf"))
        or chuan(t).removesuffix(".pdf").startswith(goc)
    ]
    # Tiền tố trùng càng dài thì càng chắc là cùng một văn bản.
    return max(ung_vien, key=len) if ung_vien else None


def nguon_trich_dan(kq: KetQua) -> list[dict]:
    """Chip nguồn cho giao diện, đúng hình dạng mà RAGService._sources trả ra.

    Chỉ liệt kê văn bản CÓ trong kho: chip nguồn bấm vào phải mở được tài liệu,
    còn văn bản ngoài kho đã được nêu ở phần "Căn cứ" kèm nhãn cảnh báo.
    """
    from urllib.parse import quote

    nguon = []
    so = 0
    for cc in kq.can_cu_da_dung:
        if not cc.trong_kho or not cc.ten_tep:
            continue
        ten = ten_tep_that(cc.ten_tep)
        if ten is None:
            # Kho không có tệp thì thà bỏ chip còn hơn để người dùng bấm vào
            # một liên kết 404; phần "Căn cứ" vẫn nêu đủ số hiệu và điều khoản.
            continue
        so += 1
        nguon.append({
            "evidence": so,
            "name": ten,
            "van_ban": None,
            "validity": None,
            "page": None,
            "chapter": None,
            "article": cc.dieu_khoan,
            "context": cc.van_ban,
            "excerpt": cc.trich,
            "url": f"/api/source?name={quote(cc.ten_tep)}",
            "external": False,
            "kind": "van_ban",
            "time_start": None,
        })
    return nguon


def tra_loi(cau_hoi: str) -> tuple[str, list[dict]] | None:
    """Đường tắt cho chỗ gọi: câu hỏi vào, (phiếu tính, nguồn) ra, None nếu
    không phải câu tính lương."""
    ts = nhan_dien(cau_hoi)
    if ts is None:
        return None
    kq = tinh(ts)
    return dinh_dang(kq), nguon_trich_dan(kq)


def main(argv: list[str]) -> int:
    if len(argv) < 2:
        print(__doc__)
        return 1
    ket_qua = tra_loi(" ".join(argv[1:]))
    if ket_qua is None:
        print("Không nhận ra đây là câu hỏi tính lương, hoặc thiếu tham số "
              "(cần cấp học, hạng, và bậc hoặc hệ số).")
        return 1
    print(ket_qua[0])
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
