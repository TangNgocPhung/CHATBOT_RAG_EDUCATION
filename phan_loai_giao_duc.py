"""
PHÂN LOẠI GIÁO DỤC CHO TỪNG TÀI LIỆU (môn học / cấp học / lớp / loại nội dung)
==============================================================================
Vì sao cần: kho trộn lẫn văn bản quy phạm, bài giảng nhiều môn và đề kiểm tra
nhiều khối. Người đang học Tin học lớp 4 hỏi "bài 2 nói về gì" vẫn nhận về
chunk "Bài 2 Động năng Thế năng" của Vật lí, vì xét theo từ khóa thì hai đoạn
giống nhau thật. Lỗi này không sửa được bằng xếp hạng - chỉ sửa được bằng cách
thu hẹp phạm vi TRƯỚC khi tìm.

Ba nguyên tắc:

1. Suy từ TÊN FILE trước, nội dung sau. Tên file trong kho đặt khá kỷ luật
   ("KNTT Bai 1 Khai quat ve nha o.pptx", "0.MaTran-DacTa-Lop4-TheoChuDe.docx")
   trong khi nội dung PDF bản scan đi qua OCR luôn có nhiễu.

2. Mỗi trường là DANH SÁCH chứ không phải một giá trị. Một thông tư áp cho cả
   tiểu học lẫn THCS; ép nó về một cấp học là bịa ra thông tin văn bản không nói.

3. Không đoán bừa. Không thấy dấu hiệu thì để rỗng và giao diện nói rõ tài liệu
   "chưa phân loại" - cùng tinh thần với chỗ khác trong dự án: thà nhận không
   biết còn hơn trả lời sai.

Chạy bằng quy tắc chứ không gọi LLM: 233 tài liệu nhân một lượt LLM là vài
tiếng trên CPU máy này, trong khi dấu hiệu cần tìm chỉ là mấy chục từ khóa cố
định. Cùng lý do với tinh_luong.py - việc nào tính được thì đừng bắt mô hình đoán.
"""

from __future__ import annotations

import json
import os
import re
from dataclasses import asdict, dataclass, field

from hybrid_retrieval import bo_dau, tach_camel_va_so

THU_MUC_DU_AN = os.path.dirname(os.path.abspath(__file__))
DUONG_DAN_PHAN_LOAI = os.path.abspath(os.getenv(
    "RAG_PHAN_LOAI_PATH", os.path.join(THU_MUC_DU_AN, "phan_loai_tai_lieu.json")
))

# Chỉ quét phần đầu tài liệu: phạm vi áp dụng của một văn bản nằm ở tiêu đề và
# Điều 1, còn quét cả file thì mọi môn được nhắc thoáng qua một lần đều bị gắn.
DO_DAI_QUET_NOI_DUNG = 3000


# ============================================================
# TỪ ĐIỂN DẤU HIỆU
# ============================================================
# Viết bằng regex trên chuỗi ĐÃ bỏ dấu và tách camel (xem _chuan_hoa), vì tên
# file trong kho viết cả ba kiểu: "Tin học 5", "TinHoc5", "tin-hoc-5".
MON_HOC: dict[str, str] = {
    "Toán": r"(?<!an )toan hoc|mon toan|toan lop|(?<!an )toan(?= \d)",
    "Khoa học": r"(?<!nha )khoa hoc(?! tu nhien| xa hoi| giao duc| may tinh| cong nghe| ki thuat| ky thuat)",
    "Khoa học tự nhiên": r"khoa hoc tu nhien|khtn",
    "Lịch sử và Địa lí": r"lich su va dia li|lsdl",
    "Tự nhiên và Xã hội": r"tu nhien va xa hoi",
    "Ngữ văn": r"ngu van|tieng viet|tap lam van|doan bai van|mon van|van(?= \d)",
    "Tiếng Anh": r"tieng anh|mon anh|english|anh van",
    "Vật lí": r"vat li|vat ly|mon li",
    "Hoá học": r"hoa hoc|hoa ly|mon hoa|hoa(?= \d)",
    "Sinh học": r"sinh hoc|mon sinh|sinh(?= \d)",
    "Lịch sử": r"lich su|mon su|su(?= \d)",
    "Địa lí": r"dia li|dia ly|mon dia|dia(?= \d)",
    "Tin học": r"tin hoc|mon tin|tin(?= \d)",
    "Công nghệ": r"(?<!ung dung )cong nghe(?! so| thong tin| cao| moi)|mon cong nghe",
    "Giáo dục công dân": r"giao duc cong dan|gdcd",
    "Giáo dục kinh tế và pháp luật": r"giao duc kinh te va phap luat|ktpl",
    "Đạo đức": r"mon dao duc|dao duc lop",
    "Âm nhạc": r"am nhac",
    "Mĩ thuật": r"mi thuat|my thuat",
    "Giáo dục thể chất": r"giao duc the chat|the duc",
    "Hoạt động trải nghiệm": r"hoat dong trai nghiem|trai nghiem huong nghiep|hdtn",
    "Giáo dục hướng nghiệp": r"giao duc huong nghiep|huong nghiep",
    "Giáo dục quốc phòng và an ninh": r"quoc phong va an ninh|gdqp",
    "Giáo dục kĩ năng sống": r"giao duc ki nang|giao duc ky nang|ki nang song|ky nang song",
    "Kinh tế học": r"kinh te vi mo|kinh te vĩ mo|kinh te hoc",
    "Giáo dục học": r"giao duc hoc",
    "Lí luận chính trị": r"chu nghia xa hoi|chu nghia bao thu|tu tuong ho chi minh|triet hoc",
}
def _them_dang_viet_lien(mau: str) -> str:
    """
    Thêm biến thể viết liền cho các nhánh chữ thường thuần: "tin hoc" -> "tinhoc".

    "Tinhoc5_Bai15.pptx" không có ranh giới hoa/thường nào để tách nên sau
    chuẩn hóa vẫn là một token "tinhoc"; thiếu biến thể này thì tên file đã nói
    rõ môn mà vẫn phải đi đoán theo nội dung - và nội dung bài Tin học thì đầy
    tên môn khác được lấy làm ví dụ.
    """
    them = [
        nhanh.replace(" ", "")
        for nhanh in mau.split("|")
        if " " in nhanh and re.fullmatch(r"[a-z ]+", nhanh)
    ]
    return "|".join([mau] + [t for t in them if t not in mau]) if them else mau


# Bọc \b hai đầu cho MỌI mẫu: không có ranh giới từ thì "khoa hoc" chứa
# "hoa hoc" và mọi bài Khoa học lớp 5 đều bị gắn nhầm sang môn Hoá học.
_MON_DA_BIEN_DICH = {
    ten: re.compile(rf"\b(?:{_them_dang_viet_lien(mau)})\b")
    for ten, mau in MON_HOC.items()
}

# Môn tích hợp nuốt luôn tên môn thành phần: "Lịch sử và Địa lí 4" khớp cả
# "lich su" lẫn "dia li", gắn đủ ba môn thì bộ lọc "Địa lí" kéo về cả sách tích
# hợp tiểu học lẫn sách Địa lí THPT - hai thứ khác hẳn nhau.
MON_BAO_TRUM: dict[str, tuple[str, ...]] = {
    "Lịch sử và Địa lí": ("Lịch sử", "Địa lí"),
    "Khoa học tự nhiên": ("Khoa học", "Vật lí", "Hoá học", "Sinh học"),
    "Tự nhiên và Xã hội": ("Khoa học",),
    "Giáo dục kinh tế và pháp luật": ("Kinh tế học",),
}

CAP_HOC: dict[str, str] = {
    "Mầm non": r"mam non|mau giao|nha tre",
    "Tiểu học": r"tieu hoc",
    "THCS": r"trung hoc co so|thcs",
    "THPT": r"trung hoc pho thong|thpt",
    "Giáo dục thường xuyên": r"giao duc thuong xuyen|gdtx|xoa mu chu|bo tuc van hoa",
    "Giáo dục nghề nghiệp": r"giao duc nghe nghiep|cao dang|trung cap|day nghe|hoc nghe",
    "Đại học": r"dai hoc|sinh vien|hoc phan|tin chi|sau dai hoc|thac si|tien si",
}
_CAP_DA_BIEN_DICH = {
    ten: re.compile(rf"\b(?:{_them_dang_viet_lien(mau)})\b")
    for ten, mau in CAP_HOC.items()
}

# "lop 4", "khoi 4", "lop4" (đã tách thành "lop 4" ở bước chuẩn hóa)
MAU_LOP = re.compile(r"\b(?:lop|khoi)\s+(\d{1,2})\b")
# "Tin4", "GDCD 12" - tên môn dính ngay số lớp. Cố ý KHÔNG bắt "bai 2" hay
# "chuong 3": số đứng sau "bai"/"chuong" là thứ tự bài, không phải lớp.
_TEN_MON_TRUOC_SO = (
    r"toan|van|tin|tin hoc|li|ly|vat li|hoa|sinh|su|lich su|dia|gdcd|ktpl"
    r"|anh|tieng anh|ngu van|cong nghe|am nhac|mi thuat|dao duc|khoa hoc"
    r"|giao duc cong dan|cong dan|the duc|tu nhien va xa hoi|khtn|lsdl"
)
MAU_MON_KEM_LOP = re.compile(
    rf"\b(?:{_them_dang_viet_lien(_TEN_MON_TRUOC_SO)})\s+(\d{{1,2}})\b"
)

LOAI_NOI_DUNG_MAC_DINH = "hoc_lieu_khac"
NHAN_LOAI_NOI_DUNG = {
    "van_ban_quy_pham": "Văn bản quy phạm",
    "bai_giang": "Bài giảng",
    "de_kiem_tra": "Đề và câu hỏi kiểm tra",
    "hoc_lieu_khac": "Học liệu khác",
}

MAU_DE_KIEM_TRA = re.compile(
    r"ma tran|dac ta|de thi|de kiem tra|de minh hoa|cau hoi minh hoa|bo cau hoi"
    r"|ngan hang cau hoi|dap an|de on tap|de cuong on tap|phieu bai tap"
)
MAU_BAI_GIANG = re.compile(
    r"bai giang|giao an|ke hoach bai day|slide|bai day|ppt|powerpoint"
    r"|kntt|ctst|canh dieu"
)
# Số hiệu văn bản nằm ngay trong tên file: "02_2026_TT-BGDDT", "159-ndcp.signed",
# "2732qdttg" - dấu hiệu chắc chắn hơn mọi từ khóa nội dung.
MAU_SO_HIEU_TEN_FILE = re.compile(
    r"\b(?:tt|nd|qd|ct|nq|tb|cd|kh)\s*(?:bgddt|bgd|bnv|btc|bkhcn|ttg|cp|ndcp)\b"
    r"|\bbgddt\b|\bbgd\b|\bttg\b|\bndcp\b|\bqdttg\b|\bbnv\b|\bbkhcn\b"
    r"|\bqh\d{2}\b|\b\d{1,4} (?:cp|nq|ct|tb|cd)\b"
)


@dataclass
class PhanLoai:
    """Nhãn phân loại của MỘT file nguồn. Danh sách rỗng = chưa phân loại được."""

    ten_file: str
    mon_hoc: list[str] = field(default_factory=list)
    cap_hoc: list[str] = field(default_factory=list)
    lop: list[int] = field(default_factory=list)
    loai_noi_dung: str = LOAI_NOI_DUNG_MAC_DINH
    # Dấu hiệu lấy được từ đâu - để người quản trị soát lại chỗ máy đoán sai.
    nguon: list[str] = field(default_factory=list)

    @property
    def da_phan_loai(self) -> bool:
        return bool(self.mon_hoc or self.cap_hoc or self.lop)


def _chuan_hoa(van_ban: str) -> str:
    """
    "Bai1_TinHoc5.pptx" -> " bai 1 tin hoc 5 pptx ".

    Bọc hai đầu bằng khoảng trắng để \\b trong regex khớp được cả từ đứng đầu và
    đứng cuối chuỗi mà không phải viết thêm nhánh đặc biệt.
    """
    khong_dau = bo_dau(tach_camel_va_so(van_ban or "")).lower()
    return " " + re.sub(r"[^a-z0-9]+", " ", khong_dau).strip() + " "


def _tim_nhan(chuoi: str, bang: dict[str, re.Pattern]) -> list[str]:
    return [ten for ten, mau in bang.items() if mau.search(chuoi)]


def _bo_mon_bi_bao_trum(cac_mon: list[str]) -> list[str]:
    bi_nuot = {
        thanh_phan
        for tich_hop, thanh_phans in MON_BAO_TRUM.items() if tich_hop in cac_mon
        for thanh_phan in thanh_phans
    }
    return [mon for mon in cac_mon if mon not in bi_nuot]


def _tim_lop(chuoi: str) -> list[int]:
    so = {int(s) for s in MAU_LOP.findall(chuoi)}
    so |= {int(s) for s in MAU_MON_KEM_LOP.findall(chuoi)}
    return sorted(s for s in so if 1 <= s <= 12)


def _cap_tu_lop(cac_lop: list[int]) -> list[str]:
    cap = set()
    for lop in cac_lop:
        if 1 <= lop <= 5:
            cap.add("Tiểu học")
        elif 6 <= lop <= 9:
            cap.add("THCS")
        elif 10 <= lop <= 12:
            cap.add("THPT")
    return sorted(cap)


def _suy_loai_noi_dung(ten_chuan: str, noi_dung_chuan: str, la_qppl: bool,
                       loai_tai_lieu: str | None) -> str:
    """
    Thứ tự xét có chủ đích: hồ sơ văn bản (đã đối chiếu số hiệu thật) đáng tin
    hơn từ khóa tên file, và "ma trận đề" đáng tin hơn "là file pptx".
    """
    if la_qppl or MAU_SO_HIEU_TEN_FILE.search(ten_chuan):
        return "van_ban_quy_pham"
    if MAU_DE_KIEM_TRA.search(ten_chuan) or MAU_DE_KIEM_TRA.search(noi_dung_chuan):
        return "de_kiem_tra"
    if MAU_BAI_GIANG.search(ten_chuan) or loai_tai_lieu == "trinh_chieu":
        return "bai_giang"
    return LOAI_NOI_DUNG_MAC_DINH


MAU_NHAC_TOI_MON = re.compile(r"\bmon\b|\bmon hoc\b")


def _duoc_gan_mon(loai_noi_dung: str, chuoi: str) -> bool:
    """
    Văn bản quy phạm chỉ được gắn môn khi có hẳn chữ "môn" đi kèm.

    Đo trên kho thật: không có chắn này thì "Thông tư quy định ứng dụng công
    nghệ trong giáo dục đại học" bị xếp vào môn Công nghệ và "học bổng cho nhà
    khoa học" vào môn Khoa học - lọc theo môn Công nghệ sẽ trả về thông tư hành
    chính, đúng kiểu sai mà người dùng không nhận ra vì họ tin là đã lọc rồi.

    Đã thử nới cho cả "chương trình" nhưng phải bỏ: gần như nghị định nào cũng
    có "chương trình đào tạo"/"chương trình mục tiêu", nên cổng coi như không có.
    Bài giảng thì ngược lại: tên nó vốn chỉ có mỗi tên môn, không ai viết "môn".
    """
    if loai_noi_dung != "van_ban_quy_pham":
        return True
    return bool(MAU_NHAC_TOI_MON.search(chuoi))


def suy_phan_loai(ten_file: str, noi_dung: str = "", la_qppl: bool = False,
                  loai_tai_lieu: str | None = None) -> PhanLoai:
    """Gắn nhãn cho một file. `noi_dung` chỉ cần phần đầu tài liệu."""
    ten_chuan = _chuan_hoa(ten_file)
    noi_dung_chuan = _chuan_hoa(noi_dung[:DO_DAI_QUET_NOI_DUNG]) if noi_dung else ""
    loai = _suy_loai_noi_dung(ten_chuan, noi_dung_chuan, la_qppl, loai_tai_lieu)

    cap = _tim_nhan(ten_chuan, _CAP_DA_BIEN_DICH)
    lop = _tim_lop(ten_chuan)
    mon = _tim_nhan(ten_chuan, _MON_DA_BIEN_DICH) if _duoc_gan_mon(loai, ten_chuan) else []
    nguon = ["ten_file"] if (mon or cap or lop) else []

    # Nội dung chỉ được dùng để BỔ SUNG trường còn trống, không ghi đè tên file:
    # một thông tư về tiểu học vẫn nhắc "trung học cơ sở" ở phần căn cứ.
    if noi_dung_chuan.strip():
        if not mon and _duoc_gan_mon(loai, noi_dung_chuan):
            them = _bo_mon_bi_bao_trum(_tim_nhan(noi_dung_chuan, _MON_DA_BIEN_DICH))
            # Chỉ nhận khi nội dung nói tới ĐÚNG MỘT môn. Nhiều môn cùng lúc là
            # đang liệt kê chứ không phải đang khai báo: bài Tin học lớp 3 lấy
            # ví dụ "thư mục Tiếng Việt 3, Tin học 3, Toán 3", gắn cả ba thì lọc
            # môn Toán lại ra bài Tin học.
            if len(them) == 1:
                mon, nguon = them, nguon + ["noi_dung"]
        if not cap:
            them = _tim_nhan(noi_dung_chuan, _CAP_DA_BIEN_DICH)
            if them:
                cap, nguon = them, nguon + ["noi_dung"]

    for cap_suy_ra in _cap_tu_lop(lop):
        if cap_suy_ra not in cap:
            cap.append(cap_suy_ra)

    return PhanLoai(
        ten_file=ten_file,
        mon_hoc=sorted(_bo_mon_bi_bao_trum(mon)),
        cap_hoc=sorted(cap),
        lop=lop,
        loai_noi_dung=loai,
        nguon=sorted(set(nguon)),
    )


# ============================================================
# DỰNG BẢNG PHÂN LOẠI CHO CẢ KHO
# ============================================================
def xay_dung_tu_vector_store(vector_store, ho_so: dict | None = None) -> dict[str, PhanLoai]:
    """
    Gom chunk theo file nguồn rồi gắn nhãn cho từng file.

    Chỉ ghép các chunk ĐẦU của mỗi file cho đủ DO_DAI_QUET_NOI_DUNG: chunk nằm
    sẵn trong chỉ mục nên không phải đọc lại file gốc, và cả bảng 211 tài liệu
    dựng xong trong chưa tới một giây - rẻ hơn nhiều so với embed lại.
    """
    dau_file: dict[str, list[str]] = {}
    loai_tai_lieu: dict[str, str] = {}
    for doc in vector_store.docstore._dict.values():
        ten_file = doc.metadata.get("source_file")
        if not ten_file:
            continue
        phan = dau_file.setdefault(ten_file, [])
        if sum(len(p) for p in phan) < DO_DAI_QUET_NOI_DUNG:
            phan.append(doc.page_content)
        loai_tai_lieu.setdefault(ten_file, doc.metadata.get("loai_tai_lieu"))

    ho_so = ho_so or {}
    bang = {}
    for ten_file, cac_phan in dau_file.items():
        muc = ho_so.get(ten_file)
        bang[ten_file] = suy_phan_loai(
            ten_file,
            noi_dung="\n".join(cac_phan),
            la_qppl=bool(getattr(muc, "la_qppl", False)),
            loai_tai_lieu=loai_tai_lieu.get(ten_file),
        )
    return bang


def gan_vao_chunk(vector_store, bang: dict[str, PhanLoai]) -> int:
    """
    Chép nhãn của file xuống từng chunk của nó.

    Phải chạy TRƯỚC khi dựng BM25 vì BM25 sao chép metadata sang tài liệu riêng
    của nó - gắn sau thì nhánh BM25 lọc hụt, đúng cái bẫy mà _lap_ho_so_van_ban
    đã gặp với nhãn hết hiệu lực.
    """
    da_gan = 0
    for doc in vector_store.docstore._dict.values():
        muc = bang.get(doc.metadata.get("source_file"))
        if not muc:
            continue
        doc.metadata["mon_hoc"] = muc.mon_hoc
        doc.metadata["cap_hoc"] = muc.cap_hoc
        doc.metadata["lop"] = muc.lop
        doc.metadata["loai_noi_dung"] = muc.loai_noi_dung
        da_gan += 1
    return da_gan


def luu(bang: dict[str, PhanLoai]) -> None:
    with open(DUONG_DAN_PHAN_LOAI, "w", encoding="utf-8") as f:
        json.dump(
            {ten: asdict(muc) for ten, muc in bang.items()},
            f, ensure_ascii=False, indent=1,
        )


def tai() -> dict[str, PhanLoai]:
    try:
        with open(DUONG_DAN_PHAN_LOAI, encoding="utf-8") as f:
            du_lieu = json.load(f)
        return {ten: PhanLoai(**muc) for ten, muc in du_lieu.items()}
    except (OSError, ValueError, TypeError):
        return {}


# ============================================================
# PHẠM VI TRUY XUẤT
# ============================================================
KHOA_PHAM_VI = ("mon_hoc", "cap_hoc", "lop", "loai_noi_dung")


def chuan_hoa_pham_vi(pham_vi: dict | None) -> dict:
    """
    Bỏ khóa lạ, bỏ giá trị rỗng, ép "lop" về số. Trả về {} nghĩa là hỏi cả kho.

    Chỉ giữ giá trị CÓ THẬT trong từ điển: người dùng gửi môn "Bùa chú" thì
    phải rơi vào nhánh "phạm vi rỗng, hỏi cả kho" chứ không phải nhánh "không
    tài liệu nào khớp, từ chối trả lời" - hai thứ này gây hiểu lầm khác nhau.
    """
    if not isinstance(pham_vi, dict):
        return {}
    hop_le = {
        "mon_hoc": set(MON_HOC),
        "cap_hoc": set(CAP_HOC),
        "lop": set(range(1, 13)),
        "loai_noi_dung": set(NHAN_LOAI_NOI_DUNG),
    }
    ket_qua = {}
    for khoa in KHOA_PHAM_VI:
        gia_tri = pham_vi.get(khoa)
        if gia_tri in (None, "", [], ()):
            continue
        danh_sach = gia_tri if isinstance(gia_tri, (list, tuple, set)) else [gia_tri]
        sach = []
        for v in danh_sach:
            if khoa == "lop":
                try:
                    v = int(v)
                except (TypeError, ValueError):
                    continue
            if v in hop_le[khoa] and v not in sach:
                sach.append(v)
        if sach:
            ket_qua[khoa] = sach
    return ket_qua


def khop(metadata: dict, pham_vi: dict) -> bool:
    """Chunk lọt qua phạm vi khi MỌI tiêu chí đều có ít nhất một giá trị trùng."""
    for khoa, mong_muon in pham_vi.items():
        cua_chunk = metadata.get(khoa)
        if cua_chunk is None:
            return False
        if not isinstance(cua_chunk, (list, tuple, set)):
            cua_chunk = [cua_chunk]
        if not set(cua_chunk) & set(mong_muon):
            return False
    return True


def bo_loc_tu_pham_vi(pham_vi: dict | None):
    """Trả về hàm lọc dùng cho truy_hoi, hoặc None nếu không giới hạn gì."""
    pham_vi = chuan_hoa_pham_vi(pham_vi)
    if not pham_vi:
        return None
    return lambda doc: khop(doc.metadata, pham_vi)


def cac_file_trong_pham_vi(bang: dict[str, PhanLoai], pham_vi: dict | None) -> list[str]:
    pham_vi = chuan_hoa_pham_vi(pham_vi)
    if not pham_vi:
        return sorted(bang)
    return sorted(ten for ten, muc in bang.items() if khop(asdict(muc), pham_vi))


def mo_ta_pham_vi(pham_vi: dict | None) -> str:
    """Câu mô tả ngắn để ghép vào lời từ chối: người dùng cần biết mình đang
    tự bó hẹp phạm vi, nếu không sẽ tưởng kho thiếu tài liệu."""
    pham_vi = chuan_hoa_pham_vi(pham_vi)
    if not pham_vi:
        return ""
    phan = []
    if pham_vi.get("mon_hoc"):
        phan.append("môn " + ", ".join(pham_vi["mon_hoc"]))
    if pham_vi.get("lop"):
        phan.append("lớp " + ", ".join(str(l) for l in pham_vi["lop"]))
    if pham_vi.get("cap_hoc"):
        phan.append(", ".join(pham_vi["cap_hoc"]))
    if pham_vi.get("loai_noi_dung"):
        phan.append(", ".join(
            NHAN_LOAI_NOI_DUNG[l].lower() for l in pham_vi["loai_noi_dung"]
        ))
    return " · ".join(phan)


def tom_tat(bang: dict[str, PhanLoai]) -> dict:
    """Danh sách lựa chọn cho giao diện, kèm số tài liệu từng nhãn.

    Chỉ liệt kê nhãn CÓ tài liệu: một hộp chọn 27 môn mà 20 môn bấm vào không
    ra gì thì tệ hơn là không có hộp chọn.
    """
    dem_mon: dict[str, int] = {}
    dem_cap: dict[str, int] = {}
    dem_lop: dict[int, int] = {}
    dem_loai: dict[str, int] = {}
    chua_phan_loai = 0
    for muc in bang.values():
        for mon in muc.mon_hoc:
            dem_mon[mon] = dem_mon.get(mon, 0) + 1
        for cap in muc.cap_hoc:
            dem_cap[cap] = dem_cap.get(cap, 0) + 1
        for lop in muc.lop:
            dem_lop[lop] = dem_lop.get(lop, 0) + 1
        dem_loai[muc.loai_noi_dung] = dem_loai.get(muc.loai_noi_dung, 0) + 1
        if not muc.da_phan_loai:
            chua_phan_loai += 1

    def _sap(dem: dict, nhan=None):
        return [
            {"gia_tri": k, "nhan": (nhan or {}).get(k, str(k)), "so_tai_lieu": v}
            for k, v in sorted(dem.items(), key=lambda x: (-x[1], str(x[0])))
        ]

    return {
        "tong_tai_lieu": len(bang),
        "chua_phan_loai": chua_phan_loai,
        "mon_hoc": _sap(dem_mon),
        "cap_hoc": _sap(dem_cap),
        "lop": [
            {"gia_tri": k, "nhan": f"Lớp {k}", "so_tai_lieu": v}
            for k, v in sorted(dem_lop.items())
        ],
        "loai_noi_dung": _sap(dem_loai, NHAN_LOAI_NOI_DUNG),
    }
