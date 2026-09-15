"""
GỘP KHO TÀI LIỆU VỀ MỘT THƯ MỤC DUY NHẤT
========================================

Dồn hết tài liệu từ các thư mục con (docx, excel, pdf, pptx, sgk, video,
tai_lieu_dinh_kem) lên thẳng gốc kho, để người dùng chỉ phải nhìn một chỗ.

Việc khó không nằm ở chỗ chuyển tệp mà ở chỗ ba nơi khác đang ghi nhớ đường
dẫn cũ. Không sửa kèm thì:

  * sổ ghi chép (data_giao_duc_da_xu_ly.json) coi 543 tệp là mới -> lập chỉ
    mục lại từ đầu, mất nhiều giờ;
  * chỉ mục FAISS vẫn trỏ vào đường dẫn cũ -> trích dẫn mở không ra tệp;
  * drive_state.json không thấy tệp ở chỗ cũ -> lượt đồng bộ kế tiếp tải lại
    409 tài liệu, rồi xóa nhầm.

Nên script này chuyển tệp VÀ viết lại cả ba. Chạy khi ứng dụng đã tắt hẳn và
không có lượt lập chỉ mục nào đang chạy.

    .venv\\Scripts\\python.exe gop_kho_mot_thu_muc.py --thu-xem      # xem trước
    .venv\\Scripts\\python.exe gop_kho_mot_thu_muc.py                # làm thật
"""

from __future__ import annotations

import argparse
import json
import os
import pickle
import shutil
import sys
import time

THU_MUC_DU_AN = os.path.dirname(os.path.abspath(__file__))
DATA_PATH = os.path.abspath(os.getenv(
    "RAG_DATA_PATH",
    os.path.join(THU_MUC_DU_AN, "ollama-rag-desktop", "data_giao_duc"),
))
DUONG_DAN_SO_GHI_CHEP = os.getenv(
    "RAG_LEDGER_PATH", os.path.join(THU_MUC_DU_AN, "data_giao_duc_da_xu_ly.json")
)
DUONG_DAN_INDEX = os.getenv(
    "RAG_INDEX_PATH", os.path.join(THU_MUC_DU_AN, "faiss_index_data_giao_duc")
)
DUONG_DAN_DRIVE_STATE = os.getenv(
    "RAG_DRIVE_STATE", os.path.join(THU_MUC_DU_AN, "drive_state.json")
)


def _chuan(duong_dan: str) -> str:
    return os.path.normcase(os.path.abspath(duong_dan))


def lap_ke_hoach() -> tuple[dict[str, str], list[str]]:
    """Trả về {đường dẫn cũ: đường dẫn mới} và danh sách tên bị trùng.

    Trùng tên là lý do duy nhất khiến gộp phẳng không an toàn: hai tệp khác
    nhau ở hai thư mục con sẽ đè lên nhau khi về chung một chỗ.
    """
    ke_hoach: dict[str, str] = {}
    theo_ten: dict[str, list[str]] = {}
    for thu_muc, _, ten_files in os.walk(DATA_PATH):
        for ten_file in ten_files:
            cu = os.path.join(thu_muc, ten_file)
            theo_ten.setdefault(ten_file.casefold(), []).append(cu)
            if _chuan(thu_muc) == _chuan(DATA_PATH):
                continue  # đã nằm sẵn ở gốc
            ke_hoach[cu] = os.path.join(DATA_PATH, ten_file)
    trung = [ten for ten, ds in theo_ten.items() if len(ds) > 1]
    return ke_hoach, trung


def chuyen_tep(ke_hoach: dict[str, str]) -> None:
    for cu, moi in ke_hoach.items():
        shutil.move(cu, moi)


def don_thu_muc_rong() -> list[str]:
    """Xóa các thư mục con đã rỗng sau khi chuyển; giữ lại thư mục còn tệp."""
    da_xoa = []
    # Xóa từ thư mục sâu nhất trở ra: thư mục cha chỉ rỗng sau khi con đã đi.
    thu_muc_con = [
        thu_muc for thu_muc, _, _ in os.walk(DATA_PATH)
        if _chuan(thu_muc) != _chuan(DATA_PATH)
    ]
    for thu_muc in sorted(thu_muc_con, key=lambda d: d.count(os.sep), reverse=True):
        if os.path.isdir(thu_muc) and not os.listdir(thu_muc):
            os.rmdir(thu_muc)
            da_xoa.append(os.path.relpath(thu_muc, DATA_PATH))
    return da_xoa


def _sao_luu(duong_dan: str) -> str | None:
    """Giữ một bản trước khi ghi đè: sai sót ở bước này rất khó dựng lại."""
    if not os.path.exists(duong_dan):
        return None
    ban_sao = f"{duong_dan}.truoc-khi-gop-{time.strftime('%Y%m%d-%H%M%S')}"
    shutil.copy2(duong_dan, ban_sao)
    return ban_sao


def sua_so_ghi_chep(doi_chieu: dict[str, str]) -> int:
    try:
        with open(DUONG_DAN_SO_GHI_CHEP, encoding="utf-8") as f:
            so = json.load(f)
    except (OSError, ValueError):
        return 0
    if not isinstance(so, dict):
        return 0

    _sao_luu(DUONG_DAN_SO_GHI_CHEP)
    moi, dem = {}, 0
    for duong_dan, ban_ghi in so.items():
        dich = doi_chieu.get(_chuan(duong_dan))
        if dich:
            dem += 1
        moi[dich or duong_dan] = ban_ghi
    with open(DUONG_DAN_SO_GHI_CHEP, "w", encoding="utf-8") as f:
        json.dump(moi, f, ensure_ascii=False, indent=1)
    return dem


def sua_chi_muc_faiss(doi_chieu: dict[str, str]) -> int:
    """Viết lại metadata 'source' trong docstore để trích dẫn vẫn mở được tệp."""
    duong_dan_pkl = os.path.join(DUONG_DAN_INDEX, "index.pkl")
    if not os.path.isfile(duong_dan_pkl):
        return 0
    with open(duong_dan_pkl, "rb") as f:
        goi = pickle.load(f)

    docstore = goi[0]
    kho = getattr(docstore, "_dict", None)
    if not isinstance(kho, dict):
        print("  ! Không đọc được docstore, bỏ qua bước sửa chỉ mục.")
        return 0

    dem = 0
    for tai_lieu in kho.values():
        meta = getattr(tai_lieu, "metadata", None)
        if not isinstance(meta, dict):
            continue
        dich = doi_chieu.get(_chuan(meta.get("source", "")))
        if not dich:
            continue
        meta["source"] = dich
        # Kho phẳng thì không còn thư mục con để suy loại nữa.
        meta["loai_thu_muc"] = "goc"
        dem += 1

    if dem:
        _sao_luu(duong_dan_pkl)
        with open(duong_dan_pkl, "wb") as f:
            pickle.dump(goi, f)
    return dem


def sua_drive_state(doi_chieu_tuong_doi: dict[str, str]) -> int:
    """Đổi đường dẫn tương đối để lượt đồng bộ kế tiếp không tải lại cả kho."""
    try:
        with open(DUONG_DAN_DRIVE_STATE, encoding="utf-8") as f:
            trang_thai = json.load(f)
    except (OSError, ValueError):
        return 0
    if not isinstance(trang_thai, dict):
        return 0

    _sao_luu(DUONG_DAN_DRIVE_STATE)
    dem = 0
    for ban_ghi in trang_thai.values():
        if not isinstance(ban_ghi, dict):
            continue
        cu = ban_ghi.get("duong_dan")
        moi = doi_chieu_tuong_doi.get(os.path.normcase(cu or ""))
        if moi and moi != cu:
            ban_ghi["duong_dan"] = moi
            dem += 1
    with open(DUONG_DAN_DRIVE_STATE, "w", encoding="utf-8") as f:
        json.dump(trang_thai, f, ensure_ascii=False, indent=1)
    return dem


def main() -> int:
    bo_phan_tich = argparse.ArgumentParser(description=__doc__)
    bo_phan_tich.add_argument(
        "--thu-xem", action="store_true",
        help="Chỉ in ra sẽ làm gì, không đụng vào tệp nào.",
    )
    tham_so = bo_phan_tich.parse_args()

    if not os.path.isdir(DATA_PATH):
        print(f"Không thấy kho tài liệu: {DATA_PATH}")
        return 1

    ke_hoach, trung = lap_ke_hoach()
    print(f"Kho: {DATA_PATH}")
    print(f"Số tệp cần chuyển lên gốc: {len(ke_hoach)}")

    if trung:
        print("\nDỪNG: có tên tệp trùng nhau giữa các thư mục con, gộp lại sẽ")
        print("đè mất dữ liệu. Hãy đổi tên rồi chạy lại:")
        for ten in trung[:20]:
            print(f"  - {ten}")
        return 1

    if not ke_hoach:
        print("Kho đã phẳng sẵn, không có gì để làm.")
        return 0

    if tham_so.thu_xem:
        for cu, moi in list(ke_hoach.items())[:10]:
            print(f"  {os.path.relpath(cu, DATA_PATH)}  ->  {os.path.basename(moi)}")
        if len(ke_hoach) > 10:
            print(f"  ... và {len(ke_hoach) - 10} tệp nữa")
        print("\n(Chạy lại không kèm --thu-xem để làm thật.)")
        return 0

    doi_chieu = {_chuan(cu): moi for cu, moi in ke_hoach.items()}
    doi_chieu_tuong_doi = {
        os.path.normcase(os.path.relpath(cu, DATA_PATH)):
            os.path.relpath(moi, DATA_PATH)
        for cu, moi in ke_hoach.items()
    }

    print("\nĐang chuyển tệp...")
    chuyen_tep(ke_hoach)
    da_xoa = don_thu_muc_rong()
    print(f"  Đã chuyển {len(ke_hoach)} tệp, dọn {len(da_xoa)} thư mục rỗng.")

    print("Đang sửa sổ ghi chép...")
    print(f"  Đã đổi {sua_so_ghi_chep(doi_chieu)} đường dẫn.")

    print("Đang sửa chỉ mục FAISS...")
    print(f"  Đã đổi {sua_chi_muc_faiss(doi_chieu)} đoạn văn bản.")

    print("Đang sửa trạng thái đồng bộ Drive...")
    print(f"  Đã đổi {sua_drive_state(doi_chieu_tuong_doi)} bản ghi.")

    print("\nXong. Mở lại start_ui.bat; kho sẽ hiện tất cả trong một thư mục")
    print("và KHÔNG phải lập chỉ mục lại. Bản sao lưu nằm cạnh tệp gốc, đuôi")
    print("'.truoc-khi-gop-...' - xóa được sau khi bạn kiểm tra thấy ổn.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
