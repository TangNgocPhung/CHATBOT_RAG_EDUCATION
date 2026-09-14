"""
PHIÊN ÂM TRƯỚC TOÀN BỘ VIDEO TRONG KHO
=======================================
Nên chạy riêng bước này thay vì để lúc build chỉ mục: phiên âm trên CPU mất
hàng chục phút mỗi video, chạy tách ra thì có thể làm qua đêm và xem được tiến
độ từng file. Kết quả lưu cache theo hash nội dung nên build chỉ mục sau đó chỉ
mất vài giây cho phần video.

    python phien_am_video.py                # phiên âm mọi video chưa có bản ghi
    python phien_am_video.py --model medium # chính xác hơn, chậm hơn
    python phien_am_video.py --lam-lai      # bỏ cache, phiên âm lại từ đầu
"""

from __future__ import annotations

import argparse
import os
import sys
import time

from media_transcribe import (
    MODEL_MAC_DINH,
    ThieuFasterWhisper,
    dinh_dang_thoi_gian,
    doc_cache,
    la_file_media,
    phien_am,
)

THU_MUC_DU_AN = os.path.dirname(os.path.abspath(__file__))
DATA_PATH = os.path.abspath(os.getenv(
    "RAG_DATA_PATH",
    os.path.join(THU_MUC_DU_AN, "ollama-rag-desktop", "data_giao_duc"),
))


def quet_media() -> list[str]:
    ket_qua = []
    for thu_muc, _, ten_files in os.walk(DATA_PATH):
        for ten in ten_files:
            duong_dan = os.path.join(thu_muc, ten)
            if la_file_media(duong_dan):
                ket_qua.append(duong_dan)
    return sorted(ket_qua)


def main() -> int:
    for luong in (sys.stdout, sys.stderr):
        if hasattr(luong, "reconfigure"):
            luong.reconfigure(encoding="utf-8", errors="replace")

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--model", default=MODEL_MAC_DINH,
                        help="tiny/base/small/medium/large-v3 (mặc định: %(default)s)")
    parser.add_argument("--lam-lai", action="store_true", help="bỏ qua cache đã có")
    parser.add_argument("duong_dan", nargs="*", help="chỉ phiên âm các file chỉ định")
    tham_so = parser.parse_args()

    danh_sach = tham_so.duong_dan or quet_media()
    if not danh_sach:
        print(f"Không tìm thấy video/âm thanh nào trong {DATA_PATH}")
        return 0

    print(f"Tìm thấy {len(danh_sach)} file media. Model: {tham_so.model}\n")
    tong_bat_dau = time.perf_counter()
    da_lam = bo_qua = loi = 0

    for thu_tu, duong_dan in enumerate(danh_sach, 1):
        ten = os.path.basename(duong_dan)
        if not tham_so.lam_lai and doc_cache(duong_dan, tham_so.model) is not None:
            print(f"[{thu_tu}/{len(danh_sach)}] {ten} - đã có bản phiên âm, bỏ qua")
            bo_qua += 1
            continue

        print(f"[{thu_tu}/{len(danh_sach)}] {ten}", flush=True)
        bat_dau = time.perf_counter()
        lan_in_cuoi = [0.0]

        def tien_do(giay_da_xu_ly: float, tong_giay: float) -> None:
            # In tối đa 1 lần/2 giây để không làm rác console.
            if time.perf_counter() - lan_in_cuoi[0] < 2:
                return
            lan_in_cuoi[0] = time.perf_counter()
            phan_tram = f" ({giay_da_xu_ly / tong_giay * 100:.0f}%)" if tong_giay else ""
            sys.stdout.write(
                f"\r    đã xử lý {dinh_dang_thoi_gian(giay_da_xu_ly)}{phan_tram}   "
            )
            sys.stdout.flush()

        try:
            cac_doan = phien_am(
                duong_dan, ten_model=tham_so.model,
                bat_buoc_lam_lai=tham_so.lam_lai, bao_tien_do=tien_do,
            )
        except ThieuFasterWhisper as exc:
            print(f"\n  {exc}")
            return 1
        except Exception as exc:
            print(f"\n    LỖI: {type(exc).__name__}: {exc}")
            loi += 1
            continue

        giay = time.perf_counter() - bat_dau
        do_dai = cac_doan[-1].ket_thuc if cac_doan else 0
        print(f"\r    {len(cac_doan)} đoạn, dài {dinh_dang_thoi_gian(do_dai)}, "
              f"phiên âm mất {giay / 60:.1f} phút" + " " * 10, flush=True)
        da_lam += 1

    print(f"\nXong: {da_lam} phiên âm mới, {bo_qua} đã có sẵn, {loi} lỗi "
          f"({(time.perf_counter() - tong_bat_dau) / 60:.1f} phút).")
    if da_lam:
        print("Chạy `python capnhat_tailieu_moi.py` (hoặc bấm Cập nhật kho tri "
              "thức trên giao diện) để nạp nội dung video vào chỉ mục.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
