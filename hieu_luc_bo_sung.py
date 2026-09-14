"""
HIỆU LỰC THEO THỜI GIAN - PHẦN BỔ SUNG CHO van_ban_meta
=========================================================================
van_ban_meta trả lời câu hỏi "văn bản này có bị văn bản KHÁC thay thế không".
Còn hai câu hỏi nữa cũng quyết định một đoạn trích có dùng được hay không, mà
quan hệ giữa các văn bản không trả lời được:

  1. Tài liệu này ĐÃ ĐƯỢC BAN HÀNH chưa, hay mới chỉ là bản dự thảo đăng lấy ý
     kiến? Bản dự thảo có đầy đủ cấu trúc Điều - Khoản y hệt văn bản thật, chỉ
     khác đúng hai chỗ trống: ô số hiệu ("Số: /2026/TT-BGDĐT") và ngày ban hành
     ("Hà Nội, ngày tháng năm 2026"). Trong kho hiện tại, hơn một phần ba số
     đoạn đã lập chỉ mục đến từ các bản dự thảo như vậy.
  2. Văn bản đã ban hành nhưng ĐÃ TỚI NGÀY ÁP DỤNG chưa? Nghị định ký tháng 6
     mà "có hiệu lực thi hành từ ngày 01 tháng 10" thì trong suốt mấy tháng đó,
     trả lời theo nó là sai thời điểm.

Thêm một mức cảnh báo thứ ba, chi tiết hơn mức tài liệu: bản hợp nhất chú thích
ngay tại chỗ phần đã bị sửa ("Cụm từ ... được thay thế ... theo quy định tại
điểm b khoản 2 Điều 10 của Thông tư số 51/2026/TT-BGDĐT"). Khi đúng ĐOẠN được
trích có chú thích này thì cảnh báo đích danh đoạn đó, thay vì gắn cờ cả tài liệu.

Cách so khớp: bỏ dấu, hạ chữ thường rồi XÓA HẾT khoảng trắng trước khi dò mẫu.
Kho là PDF quét nên OCR chèn khoảng trắng vào giữa từ rất tùy tiện ("có hi ệu
l ực", "s ố 51/2026"); nén như vậy thì hai cách viết thành một chuỗi, đổi lại
mẫu regex không được chứa dấu cách.

Chạy trực tiếp để xem báo cáo toàn kho:  python hieu_luc_bo_sung.py
"""

from __future__ import annotations

import json
import os
import re
import unicodedata
from dataclasses import asdict, dataclass
from datetime import date

import van_ban_meta

THU_MUC_DU_AN = os.path.dirname(os.path.abspath(__file__))
DUONG_DAN_TINH_TRANG = os.path.abspath(os.getenv(
    "RAG_TINH_TRANG_HIEU_LUC",
    os.path.join(THU_MUC_DU_AN, "tinh_trang_hieu_luc.json"),
))


def nen(van_ban: str) -> str:
    """'có hi ệu l ực' -> 'cohieuluc'. Xem ghi chú về OCR ở đầu file."""
    tach_roi = unicodedata.normalize("NFD", van_ban or "")
    khong_dau = "".join(c for c in tach_roi if not unicodedata.combining(c))
    return re.sub(r"\s+", "", khong_dau.replace("đ", "d").replace("Đ", "D").lower())


def nen_co_ban_do(van_ban: str) -> tuple[str, list[int]]:
    """Như nen() nhưng trả thêm vị trí gốc của từng ký tự, để sau khi dò mẫu
    trên bản nén vẫn cắt được đúng khúc tương ứng trong văn bản gốc."""
    chuoi = []
    vi_tri = []
    for i, ky_tu in enumerate(unicodedata.normalize("NFD", van_ban or "")):
        if unicodedata.combining(ky_tu) or ky_tu.isspace():
            continue
        chuoi.append(ky_tu.replace("đ", "d").replace("Đ", "D").lower())
        vi_tri.append(i)
    return "".join(chuoi), vi_tri


_LOAI = r"ttlt|tt|nd|qd|ct|nq"
# Ô số hiệu bỏ trống: "Số: /2026/TT-BGDĐT", có bản mất cả năm "Số: /QĐ-BGDĐT".
# (?<![\d/]) là điều kiện sống còn: thiếu nó thì phần đuôi "/2020/TT-BGDĐT" của
# một số hiệu ĐẦY ĐỦ cũng khớp, và mọi văn bản đều bị coi là dự thảo.
MAU_O_SO_HIEU_TRONG = re.compile(rf"(?<![\d/])/(?:\d{{4}}/)?(?:{_LOAI})-[a-z]")
MAU_O_NGAY_TRONG = re.compile(r"ngaythangnam")
MAU_DU_THAO = re.compile(r"duthao")
# Chỉ xét dự thảo trong các tệp THỰC SỰ là văn bản quy phạm: bài giảng hay bảng
# tính cũng có thể chứa chữ "ngày tháng năm" ở một biểu mẫu nào đó.
MAU_DANG_VAN_BAN = re.compile(rf"(?:{_LOAI})-[a-z]{{2,}}|thongtu|nghidinh|quyetdinh")

MAU_NGAY_HIEU_LUC = re.compile(
    r"cohieuluc(?:thihanh)?(?:ke)?tungay(\d{1,2})thang(\d{1,2})nam(\d{4})"
)
MAU_HIEU_LUC_NGAY_KY = re.compile(r"cohieuluc(?:thihanh)?(?:ke)?tungayky")
# Chú thích của bản hợp nhất: "... được thay thế bởi ... theo quy định tại ...".
MAU_DAU_SUA_TAI_CHO = re.compile(r"duoc(?:baibo|thaythe|suadoi,?bosung)")
MAU_VIEN_DAN = re.compile(r"theoquydinhtai")

DO_DAI_PHAN_DAU = van_ban_meta.DO_DAI_PHAN_DAU


@dataclass
class TinhTrangThoiGian:
    """Phần hồ sơ mà van_ban_meta.HoSoVanBan chưa có."""

    ten_file: str
    la_du_thao: bool = False
    ngay_hieu_luc: str | None = None  # ISO "2026-10-01", cùng dạng ngay_ban_hanh

    def chua_toi_ngay_hieu_luc(self, hom_nay: date | None = None) -> bool:
        if not self.ngay_hieu_luc:
            return False
        return self.ngay_hieu_luc > (hom_nay or date.today()).isoformat()

    def ngay_hieu_luc_viet(self) -> str:
        nam, thang, ngay = self.ngay_hieu_luc.split("-")
        return f"{int(ngay)}/{int(thang)}/{nam}"


def phat_hien_du_thao(phan_dau: str) -> bool:
    """Nhận diện bản dự thảo qua hai ô còn bỏ trống ở khối tiêu đề."""
    tieu_de = nen(van_ban_meta.cat_khoi_tieu_de(phan_dau))
    if not MAU_DANG_VAN_BAN.search(tieu_de):
        return False
    return bool(
        MAU_O_SO_HIEU_TRONG.search(tieu_de)
        or MAU_O_NGAY_TRONG.search(tieu_de)
        or MAU_DU_THAO.search(tieu_de)
    )


def trich_ngay_hieu_luc(van_ban: str, ngay_ban_hanh: str | None = None) -> str | None:
    """
    "có hiệu lực thi hành từ ngày 01 tháng 10 năm 2026" -> "2026-10-01".

    "Có hiệu lực kể từ ngày ký" thì lấy luôn ngày ban hành đọc được ở tiêu đề -
    dạng này chiếm phần lớn các Quyết định trong kho.
    """
    van_ban_nen = nen(van_ban)
    for khop in MAU_NGAY_HIEU_LUC.finditer(van_ban_nen):
        ngay, thang, nam = (int(phan) for phan in khop.groups())
        if 1 <= ngay <= 31 and 1 <= thang <= 12 and 1990 <= nam <= 2100:
            return f"{nam:04d}-{thang:02d}-{ngay:02d}"
    if ngay_ban_hanh and MAU_HIEU_LUC_NGAY_KY.search(van_ban_nen):
        return ngay_ban_hanh
    return None


def van_ban_sua_doan(noi_dung: str) -> list[str]:
    """
    Số hiệu các văn bản đã sửa đổi/bãi bỏ CHÍNH đoạn văn bản này.

    Bắt buộc đúng thứ tự "được sửa đổi/bãi bỏ ... theo quy định tại ... <số
    hiệu>", và chỉ nhận số hiệu nằm SAU cụm viện dẫn. Thiếu ràng buộc thứ tự
    này thì câu ngược chiều - "khoản 1 Điều 9 Nghị định số 71/2020/NĐ-CP đã
    được sửa đổi tại Nghị định này" - sẽ bị đọc thành "đoạn này bị chính
    71/2020/NĐ-CP sửa", tức là ngược hẳn quan hệ thật.
    """
    ket_qua: list[str] = []
    # Chỉ cắt câu ở dấu chấm/chấm phẩy, KHÔNG cắt ở xuống dòng: OCR ngắt dòng
    # giữa câu liên tục, cắt thêm theo xuống dòng sẽ tách vế "được thay thế..."
    # khỏi vế "...theo quy định tại ... Thông tư số 45/2026/TT-BGDĐT".
    for cau in re.split(r"[.;]", noi_dung or ""):
        cau_nen, ban_do = nen_co_ban_do(cau)
        dau_sua = MAU_DAU_SUA_TAI_CHO.search(cau_nen)
        if not dau_sua:
            continue
        vien_dan = MAU_VIEN_DAN.search(cau_nen, dau_sua.end())
        if not vien_dan:
            continue
        phan_sau = cau[ban_do[vien_dan.end() - 1] :]
        for so_hieu in van_ban_meta.trich_so_hieu(phan_sau):
            if so_hieu not in ket_qua:
                ket_qua.append(so_hieu)
    return ket_qua


# ============================================================
# DỰNG VÀ LƯU TRỮ
# ============================================================

def xay_dung(
    van_ban_theo_file: dict[str, str],
    ho_so: dict[str, van_ban_meta.HoSoVanBan] | None = None,
) -> dict[str, TinhTrangThoiGian]:
    """van_ban_theo_file: {tên file: toàn bộ text đã lập chỉ mục} - giống
    van_ban_meta.xay_dung_ho_so để hai bên dùng chung một nguồn dữ liệu."""
    ho_so = ho_so or {}
    tinh_trang: dict[str, TinhTrangThoiGian] = {}
    for ten_file, van_ban in van_ban_theo_file.items():
        phan_dau = van_ban[:DO_DAI_PHAN_DAU]
        muc = ho_so.get(ten_file)
        tinh_trang[ten_file] = TinhTrangThoiGian(
            ten_file=ten_file,
            la_du_thao=phat_hien_du_thao(phan_dau),
            ngay_hieu_luc=trich_ngay_hieu_luc(
                van_ban, muc.ngay_ban_hanh if muc else None
            ),
        )
    return tinh_trang


def xay_dung_tu_vector_store(
    vector_store, ho_so: dict[str, van_ban_meta.HoSoVanBan] | None = None
) -> dict[str, TinhTrangThoiGian]:
    van_ban_theo_file: dict[str, list[str]] = {}
    for doc in vector_store.docstore._dict.values():
        ten_file = doc.metadata.get("source_file")
        if ten_file:
            van_ban_theo_file.setdefault(ten_file, []).append(doc.page_content)
    return xay_dung(
        {ten: "\n".join(phan) for ten, phan in van_ban_theo_file.items()}, ho_so
    )


def luu(tinh_trang: dict[str, TinhTrangThoiGian]) -> None:
    with open(DUONG_DAN_TINH_TRANG, "w", encoding="utf-8") as tep:
        json.dump(
            {ten: asdict(muc) for ten, muc in tinh_trang.items()},
            tep, ensure_ascii=False, indent=1,
        )


def tai() -> dict[str, TinhTrangThoiGian]:
    try:
        with open(DUONG_DAN_TINH_TRANG, encoding="utf-8") as tep:
            du_lieu = json.load(tep)
        return {ten: TinhTrangThoiGian(**muc) for ten, muc in du_lieu.items()}
    except (OSError, ValueError, TypeError):
        return {}


# ============================================================
# CẢNH BÁO KÈM THEO CÂU TRẢ LỜI
# ============================================================
# Trả về đúng dạng dict mà van_ban_meta.canh_bao_hieu_luc dùng, để tầng dịch vụ
# chỉ việc nối hai danh sách rồi phát ra cùng một loại sự kiện.

def canh_bao(
    tinh_trang: dict[str, TinhTrangThoiGian],
    cac_nguon: list[dict],
    hom_nay: date | None = None,
) -> list[dict]:
    ket_qua = []
    da_bao = set()
    for nguon in cac_nguon:
        ten_file = nguon.get("name")
        muc = tinh_trang.get(ten_file)
        if not muc or ten_file in da_bao:
            continue
        so = nguon.get("evidence")
        if muc.la_du_thao:
            da_bao.add(ten_file)
            ket_qua.append({
                "evidence": so,
                "nguon": ten_file,
                "loai": "du_thao",
                "thong_bao": (
                    f"Nguồn [{so}] là BẢN DỰ THẢO - ô số hiệu và ngày ban hành còn "
                    "bỏ trống, chưa phải văn bản đã ban hành nên không dùng làm căn cứ."
                ),
            })
        elif muc.chua_toi_ngay_hieu_luc(hom_nay):
            da_bao.add(ten_file)
            ket_qua.append({
                "evidence": so,
                "nguon": ten_file,
                "loai": "chua_hieu_luc",
                "thong_bao": (
                    f"Nguồn [{so}] đã ban hành nhưng phải tới "
                    f"{muc.ngay_hieu_luc_viet()} mới có hiệu lực thi hành."
                ),
            })
    return ket_qua


def canh_bao_doan(cac_nguon: list[dict], documents) -> list[dict]:
    """Cảnh báo ở mức ĐOẠN: chú thích sửa đổi nằm ngay trong chunk được trích."""
    ket_qua = []
    for nguon, doc in zip(cac_nguon, documents):
        cac_van_ban = van_ban_sua_doan(doc.page_content)
        if not cac_van_ban:
            continue
        ket_qua.append({
            "evidence": nguon.get("evidence"),
            "nguon": nguon.get("name"),
            "loai": "doan_sua_doi",
            "thong_bao": (
                f"Nguồn [{nguon.get('evidence')}]: chính đoạn được trích đã bị "
                f"{', '.join(cac_van_ban)} sửa đổi hoặc bãi bỏ - phần chữ trong đoạn "
                "là bản trước khi sửa."
            ),
        })
    return ket_qua


def nhan_hieu_luc(muc_ho_so, muc_thoi_gian, noi_dung: str = "", hom_nay: date | None = None):
    """
    Gộp hiểu biết của cả hai module thành MỘT nhãn ngắn để hiện cạnh nguồn trích.

    Trả về dict {code, label, note, level} hoặc None khi không có gì để nói -
    tài liệu không phải văn bản quy phạm (bài giảng, bảng tính, video) thì gắn
    nhãn gì cũng chỉ làm nhiễu.

    level quyết định màu: "cao" đỏ (không được dùng làm căn cứ), "vua" vàng
    (dùng được nhưng phải lưu ý), "thap" xanh (đang có hiệu lực).
    """
    if muc_ho_so is not None and getattr(muc_ho_so, "bi_thay_the_boi", None):
        return {
            "code": "bi_thay_the",
            "label": "Đã bị thay thế",
            "note": "Văn bản này đã bị một văn bản khác trong kho thay thế.",
            "level": "cao",
        }
    if muc_thoi_gian is not None and muc_thoi_gian.la_du_thao:
        return {
            "code": "du_thao",
            "label": "Dự thảo",
            "note": "Ô số hiệu và ngày ban hành còn bỏ trống - chưa phải văn bản đã ban hành.",
            "level": "cao",
        }
    if muc_thoi_gian is not None and muc_thoi_gian.chua_toi_ngay_hieu_luc(hom_nay):
        return {
            "code": "chua_hieu_luc",
            "label": f"Hiệu lực {muc_thoi_gian.ngay_hieu_luc_viet()}",
            "note": "Đã ban hành nhưng chưa tới ngày thi hành.",
            "level": "vua",
        }
    if van_ban_sua_doan(noi_dung):
        return {
            "code": "doan_sua_doi",
            "label": "Đoạn đã sửa",
            "note": "Chính đoạn được trích đã bị một văn bản khác sửa đổi hoặc bãi bỏ.",
            "level": "vua",
        }
    if muc_ho_so is not None and getattr(muc_ho_so, "bi_sua_doi_boi", None):
        return {
            "code": "bi_sua_doi",
            "label": "Đã được sửa đổi",
            "note": "Văn bản còn hiệu lực nhưng đã được văn bản khác sửa đổi, bổ sung.",
            "level": "vua",
        }
    if muc_ho_so is not None and getattr(muc_ho_so, "so_hieu", None):
        ghi_chu = "Văn bản đã ban hành và đang có hiệu lực."
        if muc_thoi_gian is not None and muc_thoi_gian.ngay_hieu_luc:
            ghi_chu = f"Có hiệu lực từ {muc_thoi_gian.ngay_hieu_luc_viet()}."
        return {
            "code": "con_hieu_luc",
            "label": "Đang hiệu lực",
            "note": ghi_chu,
            "level": "thap",
        }
    return None


def main() -> int:
    """Báo cáo nhanh trên kho đang lập chỉ mục (không cần chạy máy chủ web)."""
    from main import build_hoac_load_vector_store, tao_embeddings_va_llm

    embeddings, _ = tao_embeddings_va_llm()
    vector_store, _ = build_hoac_load_vector_store(embeddings)
    ho_so = van_ban_meta.tai_ho_so() or van_ban_meta.xay_dung_tu_vector_store(vector_store)
    tinh_trang = xay_dung_tu_vector_store(vector_store, ho_so)
    luu(tinh_trang)

    du_thao = [m for m in tinh_trang.values() if m.la_du_thao]
    chua_hieu_luc = [m for m in tinh_trang.values() if m.chua_toi_ngay_hieu_luc()]
    co_ngay = [m for m in tinh_trang.values() if m.ngay_hieu_luc]
    print(f"Tổng số nguồn:            {len(tinh_trang)}")
    print(f"Bản dự thảo:              {len(du_thao)}")
    print(f"Đọc được ngày hiệu lực:   {len(co_ngay)}")
    print(f"Chưa tới ngày hiệu lực:   {len(chua_hieu_luc)}")
    if du_thao:
        print("\nDự thảo:")
        for muc in du_thao[:20]:
            print(f"  - {muc.ten_file}")
    if chua_hieu_luc:
        print("\nChưa tới ngày áp dụng:")
        for muc in chua_hieu_luc[:20]:
            print(f"  - {muc.ten_file} (từ {muc.ngay_hieu_luc_viet()})")
    print(f"\nĐã lưu: {DUONG_DAN_TINH_TRANG}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
