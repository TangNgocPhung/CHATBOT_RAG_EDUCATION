"""
ĐỒNG BỘ KHO TÀI LIỆU TỪ GOOGLE DRIVE
=====================================
Mục tiêu: người phụ trách chỉ cần upload tài liệu lên thư mục Drive dùng chung,
không phải tải file về, không phải chạy lại script nào. Máy chạy chatbot tự phát
hiện file mới, tự tải về kho cục bộ rồi tự cập nhật chỉ mục.

Vì sao vẫn phải tải file về máy: embedding và FAISS chạy hoàn toàn cục bộ (không
gửi dữ liệu ra ngoài), nên nội dung phải có mặt trên máy để đọc. Việc tải là do
máy tự làm nền, không ai phải thao tác.

Hai chế độ, tự chọn theo cấu hình sẵn có:

1. CÓ API KEY (khuyến nghị - tự phát hiện file mới mãi mãi)
   Đặt RAG_DRIVE_API_KEY. Script gọi Drive API để liệt kê đệ quy thư mục, so
   sánh md5Checksum, chỉ tải phần thay đổi. File Google Docs/Sheets/Slides được
   xuất sang .docx/.xlsx/.pptx tự động.

2. KHÔNG CÓ API KEY (chạy được ngay, danh sách cố định)
   Script đọc drive_manifest.json (danh sách file + ID đã xuất sẵn) và tải qua
   liên kết chia sẻ công khai. Thêm file mới trên Drive thì phải xuất lại
   manifest, nên chỉ dùng tạm.

Chạy tay:  python drive_sync.py
Xem trước: python drive_sync.py --thu
"""

from __future__ import annotations

import argparse
import json
import os
import re
import time
from dataclasses import dataclass, field

import requests

from document_loaders import DINH_DANG_HO_TRO

THU_MUC_DU_AN = os.path.dirname(os.path.abspath(__file__))

DATA_PATH = os.path.abspath(os.getenv(
    "RAG_DATA_PATH",
    os.path.join(THU_MUC_DU_AN, "ollama-rag-desktop", "data_giao_duc"),
))
DUONG_DAN_TRANG_THAI = os.path.abspath(os.getenv(
    "RAG_DRIVE_STATE", os.path.join(THU_MUC_DU_AN, "drive_state.json")
))
DUONG_DAN_MANIFEST = os.path.abspath(os.getenv(
    "RAG_DRIVE_MANIFEST", os.path.join(THU_MUC_DU_AN, "drive_manifest.json")
))

# Thư mục Drive dùng chung của đề án (có thể đổi bằng biến môi trường).
THU_MUC_DRIVE = os.getenv("RAG_DRIVE_FOLDER_ID", "1hDALiDKkmyOFhKw6gokMpIpwG5ZloCM-")
API_KEY = os.getenv("RAG_DRIVE_API_KEY", "").strip()

# Video lớn tải rất lâu; mặc định vẫn tải nhưng có ngưỡng chặn để không treo máy.
GIOI_HAN_MB = int(os.getenv("RAG_DRIVE_MAX_MB", "2048"))

# Tải liên tục hàng trăm file làm Google chặn tạm IP ("your computer or network
# may be sending automated queries", HTTP 403). Nghỉ giữa các lần tải và chờ dài
# rồi thử lại thì đi hết kho mà không bị chặn.
NGHI_GIAY = float(os.getenv("RAG_DRIVE_NGHI_GIAY", "2"))
CHO_THU_LAI = (30, 120, 300)
MA_LOI_TAM = {403, 408, 429, 500, 502, 503, 504}
# Khi Google chặn thì chặn cả IP: thử tiếp từng file chỉ tốn thời gian, nên bỏ
# cuộc sớm để lần hẹn giờ sau chạy lại từ đầu thay vì giữ khóa đồng bộ cả ngày.
NGUONG_CHAN_LIEN_TIEP = int(os.getenv("RAG_DRIVE_NGUONG_CHAN", "5"))

API_GOC = "https://www.googleapis.com/drive/v3/files"
MIME_THU_MUC = "application/vnd.google-apps.folder"

# Google Docs/Sheets/Slides không có nội dung nhị phân -> phải xuất sang Office.
XUAT_GOOGLE = {
    "application/vnd.google-apps.document": (
        "application/vnd.openxmlformats-officedocument.wordprocessingml.document", ".docx"),
    "application/vnd.google-apps.spreadsheet": (
        "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet", ".xlsx"),
    "application/vnd.google-apps.presentation": (
        "application/vnd.openxmlformats-officedocument.presentationml.presentation", ".pptx"),
}

# Người soạn hay đặt tên file trên Drive không kèm đuôi ("Luật Giáo Dục"), vì
# Drive hiển thị theo mimeType chứ không theo tên. Lọc định dạng chỉ xét đuôi
# tên nên những file này bị bỏ qua -> suy đuôi từ mimeType để không mất tài liệu.
DUOI_THEO_MIME = {
    "application/pdf": ".pdf",
    "application/msword": ".doc",
    "application/vnd.openxmlformats-officedocument.wordprocessingml.document": ".docx",
    "application/vnd.ms-excel": ".xls",
    "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet": ".xlsx",
    "application/vnd.openxmlformats-officedocument.presentationml.presentation": ".pptx",
    "text/plain": ".txt",
    "text/csv": ".csv",
    "text/html": ".html",
    "video/mp4": ".mp4",
    "audio/mpeg": ".mp3",
}

KY_TU_CAM = re.compile(r'[<>:"/\\|?*\x00-\x1f]')

# Thư mục trên Drive đặt tên tự do ("File doxc", "File excel - đuôi csv, xlxx");
# ánh xạ về đúng tên thư mục kho cục bộ đang dùng để không tạo bản sao song song.
BAN_DO_THU_MUC = {
    "file pdf": "pdf",
    "file doxc": "docx",
    "file docx": "docx",
    "file excel - đuôi csv, xlxx": "excel",
    "file pptx": "pptx",
    "video": "video",
    "html": "html",
}


class LoiDongBo(RuntimeError):
    """Không đồng bộ được - kèm hướng dẫn khắc phục cho người dùng cuối."""


@dataclass
class KetQuaDongBo:
    da_tai: list[str] = field(default_factory=list)
    da_xoa: list[str] = field(default_factory=list)
    da_co: list[str] = field(default_factory=list)
    bo_qua: list[str] = field(default_factory=list)
    loi: list[str] = field(default_factory=list)
    tong_file_drive: int = 0
    giay: float = 0.0

    @property
    def co_thay_doi(self) -> bool:
        return bool(self.da_tai or self.da_xoa)

    def tom_tat(self) -> str:
        if not self.co_thay_doi and not self.loi:
            return f"Drive không có thay đổi ({self.tong_file_drive} tài liệu)."
        phan = []
        if self.da_tai:
            phan.append(f"tải mới/cập nhật {len(self.da_tai)}")
        if self.da_xoa:
            phan.append(f"gỡ {len(self.da_xoa)}")
        if self.da_co:
            phan.append(f"đã có sẵn {len(self.da_co)}")
        if self.bo_qua:
            phan.append(f"bỏ qua {len(self.bo_qua)}")
        if self.loi:
            phan.append(f"lỗi {len(self.loi)}")
        return "Đồng bộ Drive: " + ", ".join(phan) + f" ({self.giay:.0f}s)."


def _ten_an_toan(ten: str) -> str:
    """Tên file/thư mục trên Drive có thể chứa ký tự Windows không nhận."""
    ten = KY_TU_CAM.sub("_", ten or "").strip().strip(".")
    return ten[:150] or "khong_ten"


def _ten_thu_muc_cuc_bo(ten_drive: str, la_cap_mot: bool) -> str:
    if la_cap_mot:
        return BAN_DO_THU_MUC.get(
            (ten_drive or "").strip().lower(), _ten_an_toan(ten_drive)
        )
    return _ten_an_toan(ten_drive)


def doc_trang_thai() -> dict:
    try:
        with open(DUONG_DAN_TRANG_THAI, encoding="utf-8") as f:
            du_lieu = json.load(f)
        return du_lieu if isinstance(du_lieu, dict) else {}
    except (OSError, ValueError):
        return {}


def luu_trang_thai(trang_thai: dict) -> None:
    with open(DUONG_DAN_TRANG_THAI, "w", encoding="utf-8") as f:
        json.dump(trang_thai, f, ensure_ascii=False, indent=1)


def da_cau_hinh() -> tuple[bool, str]:
    """Cho giao diện biết có bật được nút đồng bộ hay không."""
    if API_KEY:
        return True, "Đồng bộ trực tiếp qua Google Drive API."
    if os.path.exists(DUONG_DAN_MANIFEST):
        return True, "Đồng bộ theo danh sách drive_manifest.json (không có API key)."
    return False, (
        "Chưa cấu hình đồng bộ Drive: đặt RAG_DRIVE_API_KEY hoặc tạo drive_manifest.json."
    )


# ============================================================
# LIỆT KÊ FILE TRÊN DRIVE
# ============================================================
def _goi_api(tham_so: dict) -> dict:
    phan_hoi = requests.get(API_GOC, params={**tham_so, "key": API_KEY}, timeout=30)
    if phan_hoi.status_code == 403:
        raise LoiDongBo(
            "Google từ chối API key (403). Kiểm tra key đã bật Google Drive API "
            "và không giới hạn sai HTTP referrer."
        )
    if phan_hoi.status_code == 404:
        raise LoiDongBo("Không thấy thư mục Drive - kiểm tra RAG_DRIVE_FOLDER_ID.")
    phan_hoi.raise_for_status()
    return phan_hoi.json()


def liet_ke_qua_api(thu_muc_goc: str) -> list[dict]:
    """Duyệt đệ quy toàn bộ thư mục con, trả về danh sách file kèm đường dẫn tương đối."""
    ket_qua: list[dict] = []
    hang_doi = [(thu_muc_goc, "")]
    da_duyet = set()

    while hang_doi:
        thu_muc, duong_dan_tuong_doi = hang_doi.pop(0)
        if thu_muc in da_duyet:
            continue
        da_duyet.add(thu_muc)

        trang = None
        while True:
            tham_so = {
                "q": f"'{thu_muc}' in parents and trashed = false",
                "fields": "nextPageToken, files(id, name, mimeType, md5Checksum, size, modifiedTime)",
                "pageSize": 200,
                "supportsAllDrives": "true",
                "includeItemsFromAllDrives": "true",
            }
            if trang:
                tham_so["pageToken"] = trang
            du_lieu = _goi_api(tham_so)
            for muc in du_lieu.get("files", []):
                if muc.get("mimeType") == MIME_THU_MUC:
                    ten_cuc_bo = _ten_thu_muc_cuc_bo(
                        muc["name"], la_cap_mot=not duong_dan_tuong_doi
                    )
                    hang_doi.append((
                        muc["id"],
                        os.path.join(duong_dan_tuong_doi, ten_cuc_bo),
                    ))
                else:
                    ket_qua.append({**muc, "thu_muc": duong_dan_tuong_doi})
            trang = du_lieu.get("nextPageToken")
            if not trang:
                break
    return ket_qua


def liet_ke_qua_manifest() -> list[dict]:
    with open(DUONG_DAN_MANIFEST, encoding="utf-8") as f:
        du_lieu = json.load(f)
    return du_lieu.get("files", du_lieu if isinstance(du_lieu, list) else [])


# ============================================================
# TẢI FILE
# ============================================================
def _tai_qua_api(ma_file: str, dich: str, mime: str) -> None:
    if mime in XUAT_GOOGLE:
        url = f"{API_GOC}/{ma_file}/export"
        tham_so = {"mimeType": XUAT_GOOGLE[mime][0], "key": API_KEY}
    else:
        url = f"{API_GOC}/{ma_file}"
        tham_so = {"alt": "media", "key": API_KEY, "supportsAllDrives": "true"}
    with requests.get(url, params=tham_so, stream=True, timeout=(10, 120)) as phan_hoi:
        phan_hoi.raise_for_status()
        _ghi_ra_dia(phan_hoi, dich)


def _tai_qua_lien_ket_cong_khai(ma_file: str, dich: str) -> None:
    """
    Không có API key thì dùng liên kết chia sẻ. File lớn bị chèn trang xác nhận
    quét virus, phải gửi lại kèm token confirm thì mới ra nội dung thật.
    """
    phien = requests.Session()
    url = "https://drive.google.com/uc"
    tham_so = {"export": "download", "id": ma_file}
    phan_hoi = phien.get(url, params=tham_so, stream=True, timeout=(10, 120))
    loai = phan_hoi.headers.get("Content-Type", "")
    if "text/html" in loai:
        noi_dung = phan_hoi.text
        phan_hoi.close()
        token = None
        khop = re.search(r'name="confirm"\s+value="([^"]+)"', noi_dung) or \
            re.search(r"confirm=([0-9A-Za-z_-]+)", noi_dung)
        if khop:
            token = khop.group(1)
        if not token:
            raise LoiDongBo(
                "Google chặn tải trực tiếp file này. Hãy kiểm tra quyền chia sẻ "
                "là 'Bất kỳ ai có đường liên kết', hoặc cấu hình RAG_DRIVE_API_KEY."
            )
        phan_hoi = phien.get(
            "https://drive.usercontent.google.com/download",
            params={"id": ma_file, "export": "download", "confirm": token},
            stream=True, timeout=(10, 120),
        )
    phan_hoi.raise_for_status()
    _ghi_ra_dia(phan_hoi, dich)


def _tai_co_thu_lai(ma_file: str, dich: str, mime: str, bao_tien_do=None) -> int:
    """Tải một file, gặp chặn tạm thì chờ rồi thử lại. Trả về số lần phải chờ."""
    for lan in range(len(CHO_THU_LAI) + 1):
        try:
            if API_KEY:
                _tai_qua_api(ma_file, dich, mime)
            else:
                _tai_qua_lien_ket_cong_khai(ma_file, dich)
            return lan
        except requests.HTTPError as exc:
            ma = exc.response.status_code if exc.response is not None else 0
            if ma not in MA_LOI_TAM or lan == len(CHO_THU_LAI):
                raise
            cho = CHO_THU_LAI[lan]
            if bao_tien_do:
                bao_tien_do(
                    f"Google chặn tạm (HTTP {ma}), chờ {cho}s rồi thử lại "
                    f"({lan + 1}/{len(CHO_THU_LAI)})"
                )
            time.sleep(cho)
    raise LoiDongBo("Không tải được sau nhiều lần thử.")


def _ghi_ra_dia(phan_hoi, dich: str) -> None:
    """Ghi ra file tạm rồi mới đổi tên: tải dở dang không làm hỏng kho."""
    os.makedirs(os.path.dirname(dich), exist_ok=True)
    tam = dich + ".dangtai"
    with open(tam, "wb") as f:
        for khoi in phan_hoi.iter_content(1024 * 256):
            if khoi:
                f.write(khoi)
    os.replace(tam, dich)


def _md5_file(duong_dan: str) -> str:
    import hashlib

    h = hashlib.md5()
    with open(duong_dan, "rb") as f:
        for khoi in iter(lambda: f.read(65536), b""):
            h.update(khoi)
    return h.hexdigest()


# ============================================================
# ĐỒNG BỘ
# ============================================================
def dong_bo(
    xoa_file_thua: bool = True,
    bo_qua_video: bool = False,
    chay_thu: bool = False,
    bao_tien_do=None,
) -> KetQuaDongBo:
    bat_dau = time.perf_counter()
    ket_qua = KetQuaDongBo()
    san_sang, thong_bao = da_cau_hinh()
    if not san_sang:
        raise LoiDongBo(thong_bao)

    danh_sach = liet_ke_qua_api(THU_MUC_DRIVE) if API_KEY else liet_ke_qua_manifest()
    trang_thai = doc_trang_thai()
    con_tren_drive = set()
    chan_lien_tiep = 0

    for muc in danh_sach:
        mime = muc.get("mimeType", "")
        ten = _ten_an_toan(muc.get("name") or muc.get("title") or "")
        if mime in XUAT_GOOGLE and not ten.lower().endswith(XUAT_GOOGLE[mime][1]):
            ten += XUAT_GOOGLE[mime][1]
        duoi = os.path.splitext(ten)[1].lower()
        if duoi not in DINH_DANG_HO_TRO:
            duoi_suy_ra = DUOI_THEO_MIME.get(mime)
            if not duoi_suy_ra:
                continue
            ten += duoi_suy_ra
            duoi = duoi_suy_ra

        ket_qua.tong_file_drive += 1
        ma_file = muc["id"]
        con_tren_drive.add(ma_file)
        kich_thuoc = int(muc.get("size") or 0)
        la_video = duoi in {".mp4", ".mkv", ".mov", ".avi", ".webm", ".wmv", ".flv"}

        if bo_qua_video and la_video:
            ket_qua.bo_qua.append(ten)
            continue
        if kich_thuoc and kich_thuoc > GIOI_HAN_MB * 1024 * 1024:
            ket_qua.bo_qua.append(f"{ten} (>{GIOI_HAN_MB}MB)")
            continue

        dich = os.path.join(DATA_PATH, muc.get("thu_muc", ""), ten)
        ban_ghi = trang_thai.get(ma_file) or {}
        van_con = os.path.exists(dich)
        giong_nhau = (
            van_con
            and ban_ghi.get("duong_dan") == os.path.relpath(dich, DATA_PATH)
            and (
                (muc.get("md5Checksum") and ban_ghi.get("md5") == muc["md5Checksum"])
                or (not muc.get("md5Checksum")
                    and ban_ghi.get("modifiedTime") == muc.get("modifiedTime"))
            )
        )
        if giong_nhau:
            continue

        # Kho cục bộ có sẵn đúng file này (lần đầu chạy đồng bộ trên máy đã có
        # dữ liệu) -> chỉ ghi nhận, không tải lại hàng trăm MB.
        if van_con and kich_thuoc and os.path.getsize(dich) == kich_thuoc:
            trang_thai[ma_file] = {
                "duong_dan": os.path.relpath(dich, DATA_PATH),
                "md5": muc.get("md5Checksum") or _md5_file(dich),
                "modifiedTime": muc.get("modifiedTime"),
                "size": kich_thuoc,
            }
            ket_qua.da_co.append(ten)
            continue

        if chay_thu:
            ket_qua.da_tai.append(ten)
            continue

        try:
            if bao_tien_do:
                bao_tien_do(f"Đang tải {ten}")
            _tai_co_thu_lai(ma_file, dich, mime, bao_tien_do)
            if NGHI_GIAY:
                time.sleep(NGHI_GIAY)
            trang_thai[ma_file] = {
                "duong_dan": os.path.relpath(dich, DATA_PATH),
                "md5": muc.get("md5Checksum") or _md5_file(dich),
                "modifiedTime": muc.get("modifiedTime"),
                "size": os.path.getsize(dich),
            }
            ket_qua.da_tai.append(ten)
            chan_lien_tiep = 0
        except Exception as exc:
            ket_qua.loi.append(f"{ten}: {exc}")
            chan_lien_tiep += 1
            if chan_lien_tiep >= NGUONG_CHAN_LIEN_TIEP:
                ket_qua.loi.append(
                    f"Dừng sớm: Google chặn {chan_lien_tiep} file liên tiếp. "
                    "Chờ khoảng 1-2 giờ rồi đồng bộ lại, phần đã tải vẫn được giữ."
                )
                break

    # File bị xóa trên Drive -> gỡ khỏi kho cục bộ để chỉ mục không còn nội dung cũ.
    if xoa_file_thua and not chay_thu and chan_lien_tiep < NGUONG_CHAN_LIEN_TIEP:
        for ma_file, ban_ghi in list(trang_thai.items()):
            if ma_file in con_tren_drive:
                continue
            duong_dan = os.path.join(DATA_PATH, ban_ghi.get("duong_dan", ""))
            if os.path.isfile(duong_dan):
                try:
                    os.remove(duong_dan)
                    ket_qua.da_xoa.append(os.path.basename(duong_dan))
                except OSError as exc:
                    ket_qua.loi.append(f"{duong_dan}: {exc}")
            trang_thai.pop(ma_file, None)

    if not chay_thu:
        luu_trang_thai(trang_thai)
    ket_qua.giay = time.perf_counter() - bat_dau
    return ket_qua


def xuat_manifest(danh_sach: list[dict]) -> None:
    """Ghi danh sách file Drive ra manifest để máy không có API key vẫn tải được."""
    with open(DUONG_DAN_MANIFEST, "w", encoding="utf-8") as f:
        json.dump(
            {"thu_muc_goc": THU_MUC_DRIVE, "files": danh_sach},
            f, ensure_ascii=False, indent=1,
        )


def _bat_utf8_cho_console() -> None:
    """Console Windows mặc định là cp1252 nên in tiếng Việt sẽ ném UnicodeEncodeError."""
    import sys

    for luong in (sys.stdout, sys.stderr):
        if hasattr(luong, "reconfigure"):
            luong.reconfigure(encoding="utf-8", errors="replace")


def main() -> int:
    _bat_utf8_cho_console()
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--thu", action="store_true", help="chỉ xem sẽ tải gì, không tải")
    parser.add_argument("--giu-file-thua", action="store_true",
                        help="không xóa file cục bộ đã bị gỡ khỏi Drive")
    parser.add_argument("--bo-qua-video", action="store_true", help="không tải file video")
    parser.add_argument("--xuat-manifest", action="store_true",
                        help="ghi drive_manifest.json từ Drive API (cần API key)")
    tham_so = parser.parse_args()

    if tham_so.xuat_manifest:
        if not API_KEY:
            print("Cần RAG_DRIVE_API_KEY để xuất manifest.")
            return 1
        danh_sach = liet_ke_qua_api(THU_MUC_DRIVE)
        xuat_manifest(danh_sach)
        print(f"Đã ghi {len(danh_sach)} file vào {DUONG_DAN_MANIFEST}")
        return 0

    try:
        ket_qua = dong_bo(
            xoa_file_thua=not tham_so.giu_file_thua,
            bo_qua_video=tham_so.bo_qua_video,
            chay_thu=tham_so.thu,
            bao_tien_do=lambda dong: print("  " + dong, flush=True),
        )
    except LoiDongBo as exc:
        print(f"LỖI: {exc}")
        return 1

    print(ket_qua.tom_tat())
    for ten in ket_qua.da_tai:
        print(f"  + {ten}")
    for ten in ket_qua.da_xoa:
        print(f"  - {ten}")
    for ten in ket_qua.bo_qua:
        print(f"  ~ bỏ qua: {ten}")
    for loi in ket_qua.loi:
        print(f"  ! {loi}")
    if ket_qua.co_thay_doi:
        print("\nChạy tiếp `python capnhat_tailieu_moi.py` để nạp vào chỉ mục "
              "(giao diện web làm tự động sau mỗi lần đồng bộ).")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
