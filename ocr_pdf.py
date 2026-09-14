"""
OCR CHO PDF BẢN SCAN (Tesseract, chạy offline)
===============================================
Gần 80% PDF trong kho là bản scan ảnh: mỗi trang chỉ có một tấm ảnh, không có
lớp văn bản nào để trích xuất. Trước đây chatbot không đọc được Luật Giáo dục,
các Nghị định, Thông tư - nay OCR chuyển chúng thành văn bản tra cứu được.

Kết quả OCR lưu cache theo hash nội dung file (giống bản phiên âm video), nên
chỉ chạy một lần cho mỗi tài liệu; build lại chỉ mục về sau không OCR lại.

Yêu cầu cài một lần:
    winget install --id UB-Mannheim.TesseractOCR -e
và gói ngôn ngữ tiếng Việt đặt tại thư mục `tessdata/` của dự án
(vie.traineddata, tải từ github.com/tesseract-ocr/tessdata_best).

    python ocr_pdf.py            # OCR mọi PDF scan chưa có bản OCR
    python ocr_pdf.py --thu      # chỉ liệt kê file sẽ phải OCR
"""

from __future__ import annotations

import argparse
import json
import re
import os
import shutil
import subprocess
import sys
import tempfile
import time

THU_MUC_DU_AN = os.path.dirname(os.path.abspath(__file__))
DATA_PATH = os.path.abspath(os.getenv(
    "RAG_DATA_PATH",
    os.path.join(THU_MUC_DU_AN, "ollama-rag-desktop", "data_giao_duc"),
))
THU_MUC_CACHE = os.path.abspath(os.getenv(
    "RAG_OCR_CACHE", os.path.join(THU_MUC_DU_AN, "ocr_cache")
))
THU_MUC_TESSDATA = os.path.abspath(os.getenv(
    "RAG_TESSDATA", os.path.join(THU_MUC_DU_AN, "tessdata")
))

NGON_NGU = os.getenv("RAG_OCR_NGON_NGU", "vie")
# 300 DPI là mức tiêu chuẩn cho OCR văn bản in; thấp hơn thì dấu tiếng Việt dễ sai.
DPI = int(os.getenv("RAG_OCR_DPI", "300"))
# Dưới ngưỡng này coi như trang không có lớp văn bản và cần OCR.
KY_TU_TOI_THIEU_MOI_TRANG = 80
# Mỗi trang là một tiến trình Tesseract riêng; chừa lại vài lõi cho máy dùng việc khác.
SO_LUONG_OCR = max(1, int(os.getenv("RAG_OCR_LUONG", "0")) or (os.cpu_count() or 4) - 2)


class ThieuTesseract(RuntimeError):
    """Chưa cài Tesseract - kèm hướng dẫn cài đặt."""


def tim_tesseract() -> str | None:
    duong_dan = os.getenv("RAG_TESSERACT_PATH")
    if duong_dan and os.path.exists(duong_dan):
        return duong_dan
    tim_thay = shutil.which("tesseract") or shutil.which("tesseract.exe")
    if tim_thay:
        return tim_thay
    for ung_vien in (
        r"C:\Program Files\Tesseract-OCR\tesseract.exe",
        r"C:\Program Files (x86)\Tesseract-OCR\tesseract.exe",
    ):
        if os.path.exists(ung_vien):
            return ung_vien
    return None


def san_sang() -> tuple[bool, str]:
    if tim_tesseract() is None:
        return False, (
            "Chưa cài Tesseract OCR. Chạy: "
            "winget install --id UB-Mannheim.TesseractOCR -e"
        )
    if not os.path.exists(os.path.join(THU_MUC_TESSDATA, f"{NGON_NGU}.traineddata")):
        return False, (
            f"Thiếu gói ngôn ngữ {NGON_NGU}.traineddata trong {THU_MUC_TESSDATA}. "
            "Tải từ github.com/tesseract-ocr/tessdata_best."
        )
    return True, "OCR sẵn sàng."


# Tesseract dựng đường kẻ bảng và ô công thức thành những ký tự vô nghĩa
# ("Mức tiền ‹ ‹", "|X|XIX|"). Chỉ ~1% số trang dính, nhưng chúng vẫn chiếm
# chỗ trong 900 ký tự mỗi khối EVIDENCE. CHỈ xóa ký tự, KHÔNG xóa dòng:
# thử xóa cả dòng thì mất luôn "Chương IV", "Mẫu số 3", "204/2004/NĐ-CP"
# nằm lẫn trong đó - tức là mất metadata chương dùng cho trích dẫn.
KY_TU_RAC = set('‹›«»|¦·•■●¨´`' + chr(92))


def lam_sach_ocr(van_ban: str) -> str:
    """Bỏ ký tự nhiễu do OCR dựng sai bảng/công thức. Giữ nguyên số dòng."""
    if not van_ban:
        return van_ban
    cac_dong = []
    for dong in van_ban.splitlines():
        d = ''.join(' ' if c in KY_TU_RAC else c for c in dong)
        cac_dong.append(re.sub(r'[ \t]{2,}', ' ', d).rstrip())
    return '\n'.join(cac_dong)


def _duong_dan_cache(duong_dan_pdf: str) -> str:
    from chunking_utils import tinh_hash_file

    os.makedirs(THU_MUC_CACHE, exist_ok=True)
    return os.path.join(
        THU_MUC_CACHE, f"{tinh_hash_file(duong_dan_pdf)[:16]}--{NGON_NGU}.json"
    )


def doc_cache(duong_dan_pdf: str) -> list[str] | None:
    """Trả về danh sách văn bản theo trang, hoặc None nếu chưa OCR lần nào."""
    duong_dan = _duong_dan_cache(duong_dan_pdf)
    if not os.path.exists(duong_dan):
        return None
    try:
        with open(duong_dan, encoding="utf-8") as f:
            return [lam_sach_ocr(t) for t in json.load(f).get("trang", [])]
    except (OSError, ValueError, TypeError):
        return None


def thieu_lop_van_ban(duong_dan_pdf: str) -> bool:
    """PDF scan: tổng văn bản trích được quá ít so với số trang."""
    try:
        import pypdf

        reader = pypdf.PdfReader(duong_dan_pdf)
        so_trang = len(reader.pages)
        if so_trang == 0:
            return False
        # Chỉ cần kiểm tra vài trang đầu là đủ kết luận, không phải mở cả file.
        mau = reader.pages[: min(3, so_trang)]
        tong = sum(len((trang.extract_text() or "").strip()) for trang in mau)
        return tong < KY_TU_TOI_THIEU_MOI_TRANG * len(mau)
    except Exception:
        return False


def _ocr_mot_anh(tesseract: str, duong_dan_anh: str) -> str:
    ket_qua = subprocess.run(
        [
            tesseract, duong_dan_anh, "stdout",
            "--tessdata-dir", THU_MUC_TESSDATA,
            "-l", NGON_NGU,
            "--psm", "3",       # tự phân tích bố cục trang, hợp với văn bản hành chính
            "--oem", "1",       # chỉ dùng LSTM: chính xác hơn hẳn với dấu tiếng Việt
        ],
        capture_output=True, timeout=300,
    )
    if ket_qua.returncode != 0:
        loi = ket_qua.stderr.decode("utf-8", errors="replace").strip().splitlines()
        raise RuntimeError(loi[-1] if loi else "Tesseract trả về lỗi không rõ")
    return lam_sach_ocr(
        ket_qua.stdout.decode("utf-8", errors="replace").strip()
    )


def ocr_file_pdf(duong_dan_pdf: str, bao_tien_do=None, bat_buoc_lam_lai=False) -> list[str]:
    """
    Render từng trang thành ảnh rồi đưa qua Tesseract. Dùng pypdfium2 để render
    (thư viện Python thuần, không cần cài poppler/ghostscript như pdf2image).
    Trả về danh sách văn bản theo trang.
    """
    if not bat_buoc_lam_lai:
        cache = doc_cache(duong_dan_pdf)
        if cache is not None:
            return cache

    tesseract = tim_tesseract()
    if tesseract is None:
        ok, thong_bao = san_sang()
        raise ThieuTesseract(thong_bao)

    from concurrent.futures import ThreadPoolExecutor

    import pypdfium2

    bat_dau = time.perf_counter()
    tai_lieu = pypdfium2.PdfDocument(duong_dan_pdf)
    thu_muc_tam = tempfile.mkdtemp(prefix="rag-ocr-")
    tong_trang = len(tai_lieu)
    cac_trang: list[str] = [""] * tong_trang
    da_xong = [0]

    def xu_ly_mot_trang(so_trang: int) -> None:
        # Render phải làm tuần tự (pypdfium2 không an toàn đa luồng trên cùng
        # một tài liệu), nhưng Tesseract là tiến trình riêng nên gọi song song
        # được - đó mới là phần chiếm gần hết thời gian.
        duong_dan_anh = os.path.join(thu_muc_tam, f"trang-{so_trang + 1}.png")
        try:
            cac_trang[so_trang] = _ocr_mot_anh(tesseract, duong_dan_anh)
        except Exception as exc:
            print(f"    ⚠️  Trang {so_trang + 1}: {exc}", flush=True)
        finally:
            if os.path.exists(duong_dan_anh):
                os.remove(duong_dan_anh)
            da_xong[0] += 1
            if bao_tien_do:
                bao_tien_do(da_xong[0], tong_trang)

    try:
        with ThreadPoolExecutor(max_workers=SO_LUONG_OCR) as pool:
            cho_xong = []
            for so_trang in range(tong_trang):
                anh = tai_lieu[so_trang].render(scale=DPI / 72).to_pil()
                anh.save(os.path.join(thu_muc_tam, f"trang-{so_trang + 1}.png"))
                cho_xong.append(pool.submit(xu_ly_mot_trang, so_trang))
                # Không render vượt quá xa hàng đợi OCR: file 100 trang ở 300 DPI
                # sẽ ngốn vài GB đĩa tạm nếu render hết một lượt.
                if len(cho_xong) >= SO_LUONG_OCR * 3:
                    cho_xong.pop(0).result()
            for tac_vu in cho_xong:
                tac_vu.result()
    finally:
        tai_lieu.close()
        shutil.rmtree(thu_muc_tam, ignore_errors=True)

    with open(_duong_dan_cache(duong_dan_pdf), "w", encoding="utf-8") as f:
        json.dump(
            {
                "nguon": os.path.basename(duong_dan_pdf),
                "ngon_ngu": NGON_NGU,
                "dpi": DPI,
                "giay_ocr": round(time.perf_counter() - bat_dau, 1),
                "so_trang": len(cac_trang),
                "trang": cac_trang,
            },
            f, ensure_ascii=False, indent=1,
        )
    return cac_trang


def ocr_file_anh(duong_dan_anh: str, bat_buoc_lam_lai: bool = False) -> str:
    """
    OCR một tấm ảnh rời (ảnh chụp bảng, đề thi photo, trang sách chụp bằng
    điện thoại). Khác PDF ở chỗ không có bước render: Tesseract đọc thẳng file
    ảnh. Vẫn dùng chung cache theo hash nội dung như PDF nên chụp lại cùng một
    tấm ảnh sẽ không phải OCR lần hai.
    """
    if not bat_buoc_lam_lai:
        cache = doc_cache(duong_dan_anh)
        if cache:
            return cache[0]

    tesseract = tim_tesseract()
    if tesseract is None:
        raise ThieuTesseract(san_sang()[1])

    bat_dau = time.perf_counter()
    van_ban = _ocr_mot_anh(tesseract, duong_dan_anh)

    with open(_duong_dan_cache(duong_dan_anh), "w", encoding="utf-8") as f:
        json.dump(
            {
                "nguon": os.path.basename(duong_dan_anh),
                "ngon_ngu": NGON_NGU,
                "giay_ocr": round(time.perf_counter() - bat_dau, 1),
                "so_trang": 1,
                "trang": [van_ban],
            },
            f, ensure_ascii=False, indent=1,
        )
    return van_ban


def quet_pdf_can_ocr() -> list[str]:
    can_ocr = []
    for thu_muc, _, ten_files in os.walk(DATA_PATH):
        for ten in ten_files:
            if not ten.lower().endswith(".pdf"):
                continue
            duong_dan = os.path.join(thu_muc, ten)
            if thieu_lop_van_ban(duong_dan):
                can_ocr.append(duong_dan)
    return sorted(can_ocr)


def main() -> int:
    for luong in (sys.stdout, sys.stderr):
        if hasattr(luong, "reconfigure"):
            luong.reconfigure(encoding="utf-8", errors="replace")

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--thu", action="store_true", help="chỉ liệt kê, không OCR")
    parser.add_argument("--lam-lai", action="store_true", help="bỏ qua cache đã có")
    parser.add_argument("duong_dan", nargs="*", help="chỉ OCR các file chỉ định")
    tham_so = parser.parse_args()

    ok, thong_bao = san_sang()
    if not ok and not tham_so.thu:
        print(f"LỖI: {thong_bao}")
        return 1

    danh_sach = tham_so.duong_dan or quet_pdf_can_ocr()
    if not danh_sach:
        print("Không có PDF nào thiếu lớp văn bản.")
        return 0

    print(f"{len(danh_sach)} PDF cần OCR (ngôn ngữ {NGON_NGU}, {DPI} DPI).\n")
    if tham_so.thu:
        for duong_dan in danh_sach:
            print("  " + os.path.basename(duong_dan))
        return 0

    tong_bat_dau = time.perf_counter()
    da_lam = bo_qua = loi = tong_trang = 0
    for thu_tu, duong_dan in enumerate(danh_sach, 1):
        ten = os.path.basename(duong_dan)
        if not tham_so.lam_lai and doc_cache(duong_dan) is not None:
            print(f"[{thu_tu}/{len(danh_sach)}] {ten[:60]} - đã có bản OCR")
            bo_qua += 1
            continue

        print(f"[{thu_tu}/{len(danh_sach)}] {ten[:60]}", flush=True)
        bat_dau = time.perf_counter()

        def tien_do(trang: int, tong: int) -> None:
            sys.stdout.write(f"\r    trang {trang}/{tong}   ")
            sys.stdout.flush()

        try:
            cac_trang = ocr_file_pdf(
                duong_dan, bao_tien_do=tien_do, bat_buoc_lam_lai=tham_so.lam_lai
            )
        except ThieuTesseract as exc:
            print(f"\n  {exc}")
            return 1
        except Exception as exc:
            print(f"\n    LỖI: {type(exc).__name__}: {exc}")
            loi += 1
            continue

        so_ky_tu = sum(len(t) for t in cac_trang)
        tong_trang += len(cac_trang)
        print(f"\r    {len(cac_trang)} trang, {so_ky_tu:,} ký tự, "
              f"{time.perf_counter() - bat_dau:.0f}s" + " " * 10, flush=True)
        da_lam += 1

    print(f"\nXong: {da_lam} file OCR mới ({tong_trang} trang), {bo_qua} đã có, "
          f"{loi} lỗi - {(time.perf_counter() - tong_bat_dau) / 60:.1f} phút.")
    if da_lam:
        print("Chạy `python capnhat_tailieu_moi.py` để nạp nội dung vừa OCR vào chỉ mục.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
