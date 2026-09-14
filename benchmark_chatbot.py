"""
ĐO CHẤT LƯỢNG PIPELINE RAG TRÊN BỘ CÂU HỎI THẬT
================================================
Chạy một câu hỏi:      python benchmark_chatbot.py "câu hỏi của bạn"
Chạy cả bộ (đầy đủ):   python benchmark_chatbot.py --bo
Chạy nhanh, chỉ truy hồi: python benchmark_chatbot.py --nhanh
Quét ngưỡng chặn:      python benchmark_chatbot.py --nhanh --do-nguong
Chỉ một nhóm:          python benchmark_chatbot.py --nhanh --nhom video
Lấy mẫu N câu:         python benchmark_chatbot.py --bo --so 20

HAI CHẾ ĐỘ, HAI MỤC ĐÍCH KHÁC NHAU
  --bo    gọi đủ cả LLM. Đo được chất lượng câu chữ (trích dẫn, số liệu) nhưng
          tốn ~150 giây/câu trên CPU, tức hơn 5 tiếng cho cả bộ 127 câu.
  --nhanh chỉ chạy truy hồi + cổng chặn lạc đề, KHÔNG gọi LLM. Vài phút cho cả
          bộ. Đây là chế độ dùng khi tinh chỉnh tham số truy hồi hoặc ngưỡng
          chặn, vì hai thứ đó không phụ thuộc vào model sinh câu trả lời.

Các chỉ số được đo (đều tính tự động, không chấm tay):
  - Truy hồi đúng nguồn: nguồn mong đợi có nằm trong danh sách được truy hồi không.
  - Chặn đúng:           câu ngoài phạm vi kho có bị cổng chặn bắt không.
  - Từ chối oan:         câu ĐÚNG chủ đề có bị cổng chặn bắt nhầm không (chỉ số
                         quan trọng nhất khi siết ngưỡng - siết quá tay là hỏng).
  - Trích dẫn hợp lệ:    mọi [n] trong câu trả lời đều ứng với một EVIDENCE có thật.
  - Số liệu có căn cứ:   mọi con số trong câu trả lời đều xuất hiện trong đoạn được trích.
  - Thời gian trả lời.

Kết quả ghi ra ket_qua_benchmark.json để đưa số liệu vào báo cáo đề án.
"""

from __future__ import annotations

import argparse
import json
import os
import random
import re
import sys
import time
from dataclasses import asdict, dataclass, field

import kiem_tra_tra_loi
import tu_vung_kho
from rag_service import RAGService

THU_MUC_DU_AN = os.path.dirname(os.path.abspath(__file__))
DUONG_DAN_BO_CAU_HOI = os.path.join(THU_MUC_DU_AN, "bo_cau_hoi_benchmark.json")
DUONG_DAN_KET_QUA = os.path.join(THU_MUC_DU_AN, "ket_qua_benchmark.json")

CAU_HOI_MAC_DINH = (
    "Theo quy định về dạy thêm, học thêm, những trường hợp nào "
    "không được tổ chức dạy thêm?"
)
CUM_TU_CHOI = "không tìm thấy thông tin"


@dataclass
class KetQuaMotCau:
    cau_hoi: str
    nhom: str = ""
    tra_loi: str = ""
    nguon: list[str] = field(default_factory=list)
    truy_hoi_dung_nguon: bool | None = None
    trich_dan_hop_le: bool = True
    so_lieu_co_can_cu: bool = True
    da_tu_choi: bool = False
    tu_choi_dung: bool | None = None
    giay: float = 0.0
    so_dang_ngo: list[str] = field(default_factory=list)
    loi: str = ""
    # Cổng chặn lạc đề: có bắn không và tín hiệu nào đã bắt.
    bi_chan_som: bool = False
    ly_do_chan: str = ""
    # Giá trị thô của hai tín hiệu, giữ lại để quét ngưỡng mà không phải chạy lại.
    ty_le_tu_la: float = 0.0
    do_phu_idf: float = 1.0
    do_phu_tho: float = 0.0
    # Khoảng cách vector nhỏ nhất trong nhóm truy hồi - tín hiệu NGỮ NGHĨA, độc
    # lập với từ vựng, nên bắt được câu lạc đề mà mọi từ đều có thật trong kho.
    khoang_cach_dense: float = 0.0


def _bat_utf8_cho_console() -> None:
    for luong in (sys.stdout, sys.stderr):
        if hasattr(luong, "reconfigure"):
            luong.reconfigure(encoding="utf-8", errors="replace")


def _cham_diem(kq: KetQuaMotCau, muc: dict) -> None:
    """Đối chiếu kết quả với nhãn trong bộ câu hỏi. Dùng chung cho cả hai chế độ."""
    if muc.get("mong_doi_tu_choi"):
        kq.tu_choi_dung = kq.da_tu_choi
    mong_doi = muc.get("nguon_mong_doi")
    if mong_doi:
        kq.truy_hoi_dung_nguon = any(
            any(khoa.casefold() in ten.casefold() for ten in kq.nguon)
            for khoa in mong_doi
        )


def _ghi_tin_hieu(kq: KetQuaMotCau, cau_hoi: str, tai_lieu, tu_vung) -> None:
    """Lưu giá trị thô của các tín hiệu chặn để quét ngưỡng về sau."""
    if tai_lieu:
        kq.do_phu_tho = max(
            float(d.metadata.get("_lexical_coverage", 0.0)) for d in tai_lieu
        )
    if tu_vung is not None:
        kq.ty_le_tu_la = tu_vung.ty_le_tu_la(cau_hoi)
        kq.do_phu_idf = tu_vung.do_phu_idf(cau_hoi, tai_lieu) if tai_lieu else 0.0
    kq.khoang_cach_dense = (
        tu_vung_kho.khoang_cach_dense_nho_nhat(tai_lieu) if tai_lieu
        else tu_vung_kho.KHONG_CO_DOAN_DENSE
    )


def chay_mot_cau(service: RAGService, muc: dict) -> KetQuaMotCau:
    """Chế độ đầy đủ: gọi cả LLM, đo luôn chất lượng câu chữ."""
    ket_qua = KetQuaMotCau(cau_hoi=muc["cau_hoi"], nhom=muc.get("nhom", ""))
    bat_dau = time.perf_counter()
    try:
        for su_kien in service.stream_answer(muc["cau_hoi"]):
            loai = su_kien["type"]
            if loai == "token":
                ket_qua.tra_loi += su_kien.get("content", "")
            elif loai == "sources":
                ket_qua.nguon = [n["name"] for n in su_kien.get("sources", [])]
            elif loai == "done":
                ket_qua.giay = su_kien.get("elapsed_seconds") or 0.0
                ket_qua.trich_dan_hop_le = su_kien.get("citations_ok", True)
                ket_qua.so_lieu_co_can_cu = su_kien.get("figures_ok", True)
                ket_qua.da_tu_choi = bool(su_kien.get("abstained"))
                ket_qua.bi_chan_som = bool(su_kien.get("abstained"))
                ket_qua.ly_do_chan = su_kien.get("ly_do_chan", "")
                ket_qua.so_dang_ngo = su_kien.get("unverified_figures", [])
    except Exception as exc:
        # Một câu hỏi lỗi (ví dụ trúng PDF chưa OCR) không được làm hỏng cả lượt
        # đo - ghi lại thành một lượt "từ chối có lý do" rồi chạy tiếp.
        ket_qua.loi = f"{type(exc).__name__}: {exc}"
        ket_qua.tra_loi = str(exc)
        ket_qua.da_tu_choi = True
    if not ket_qua.giay:
        ket_qua.giay = round(time.perf_counter() - bat_dau, 1)

    ket_qua.da_tu_choi = ket_qua.da_tu_choi or (
        CUM_TU_CHOI in ket_qua.tra_loi.lower()
    )
    _cham_diem(ket_qua, muc)
    return ket_qua


def chay_mot_cau_nhanh(service: RAGService, muc: dict) -> KetQuaMotCau:
    """
    Chế độ nhanh: chỉ truy hồi và chấm cổng chặn, KHÔNG gọi LLM.

    Đủ để đo hai thứ quan trọng nhất khi chỉnh tham số - truy hồi có ra đúng
    tài liệu không, và cổng chặn có bắt đúng câu lạc đề mà không chặn oan câu
    đúng chủ đề không. Chất lượng câu chữ thì phải chạy --bo mới đo được.
    """
    cau_hoi = muc["cau_hoi"]
    ket_qua = KetQuaMotCau(cau_hoi=cau_hoi, nhom=muc.get("nhom", ""))
    bat_dau = time.perf_counter()
    cau_truy_hoi, _ = RAGService._conversation_inputs(cau_hoi, None)
    tai_lieu = []
    try:
        tai_lieu = service._retrieve(cau_truy_hoi)
    except ValueError as exc:
        # PDF chưa OCR hoặc URL hỏng: hệ thống vẫn từ chối có lý do, tính là chặn.
        ket_qua.loi = f"{type(exc).__name__}: {exc}"
        ket_qua.ly_do_chan = "khong_truy_hoi_duoc"
    except Exception as exc:
        ket_qua.loi = f"{type(exc).__name__}: {exc}"

    ket_qua.nguon = [d.metadata.get("source_file", "") for d in tai_lieu]
    _ghi_tin_hieu(ket_qua, cau_truy_hoi, tai_lieu, service.tu_vung)
    if not ket_qua.ly_do_chan:
        ket_qua.ly_do_chan = tu_vung_kho.ly_do_ngoai_pham_vi(
            cau_truy_hoi, tai_lieu, service.tu_vung
        )
        if not tai_lieu:
            ket_qua.ly_do_chan = ket_qua.ly_do_chan or "khong_co_tai_lieu"
        elif ket_qua.do_phu_tho < kiem_tra_tra_loi.DO_PHU_TOI_THIEU:
            ket_qua.ly_do_chan = f"do_phu_tho={ket_qua.do_phu_tho:.2f}"

    ket_qua.bi_chan_som = bool(ket_qua.ly_do_chan)
    ket_qua.da_tu_choi = ket_qua.bi_chan_som
    ket_qua.giay = round(time.perf_counter() - bat_dau, 2)
    _cham_diem(ket_qua, muc)
    return ket_qua


def _ty_le(cac_gia_tri: list[bool]) -> str:
    if not cac_gia_tri:
        return "—"
    dung = sum(1 for g in cac_gia_tri if g)
    return f"{dung}/{len(cac_gia_tri)} ({dung / len(cac_gia_tri) * 100:.0f}%)"


def _la_cau_trong_pham_vi(kq: KetQuaMotCau) -> bool:
    return kq.nhom != "ngoai_pham_vi"


def in_bang_tong_ket(cac_ket_qua: list[KetQuaMotCau], nhanh: bool) -> None:
    print("\n" + "=" * 78)
    print("TỔNG KẾT BENCHMARK" + (" (chế độ nhanh - chỉ truy hồi)" if nhanh else ""))
    print("=" * 78)
    cot_cuoi = "Giây/câu"
    print(f"{'Nhóm':<18}{'Câu':>5}{'Đúng nguồn':>15}{'Chặn':>9}"
          f"{'Trích dẫn':>15}{'Số liệu':>15}{cot_cuoi:>11}")
    theo_nhom: dict[str, list[KetQuaMotCau]] = {}
    for kq in cac_ket_qua:
        theo_nhom.setdefault(kq.nhom or "khac", []).append(kq)

    for nhom, nhom_kq in theo_nhom.items():
        dung_nguon = [k.truy_hoi_dung_nguon for k in nhom_kq
                      if k.truy_hoi_dung_nguon is not None]
        cot_nguon = _ty_le(dung_nguon) if dung_nguon else "—"
        so_chan = sum(1 for k in nhom_kq if k.bi_chan_som)
        cot_chan = f"{so_chan}/{len(nhom_kq)}"
        cot_trich = "—" if nhanh else _ty_le([k.trich_dan_hop_le for k in nhom_kq])
        cot_so = "—" if nhanh else _ty_le([k.so_lieu_co_can_cu for k in nhom_kq])
        print(f"{nhom:<18}{len(nhom_kq):>5}{cot_nguon:>15}{cot_chan:>9}"
              f"{cot_trich:>15}{cot_so:>15}"
              f"{sum(k.giay for k in nhom_kq) / len(nhom_kq):>11.1f}")

    print("-" * 78)
    tat_ca_nguon = [k.truy_hoi_dung_nguon for k in cac_ket_qua
                    if k.truy_hoi_dung_nguon is not None]
    print(f"Truy hồi đúng nguồn : {_ty_le(tat_ca_nguon)}")

    # Hai con số quyết định việc siết ngưỡng chặn có lành mạnh hay không.
    ngoai = [k for k in cac_ket_qua if not _la_cau_trong_pham_vi(k)]
    trong = [k for k in cac_ket_qua if _la_cau_trong_pham_vi(k)]
    if ngoai:
        print(f"Chặn đúng câu lạc đề: {_ty_le([k.bi_chan_som for k in ngoai])}")
    if trong:
        oan = [k for k in trong if k.bi_chan_som]
        print(f"Từ chối OAN câu đúng: {len(oan)}/{len(trong)} "
              f"({len(oan) / len(trong) * 100:.0f}%)")
        for k in oan[:5]:
            print(f"    · [{k.ly_do_chan}] {k.cau_hoi[:60]}")

    if not nhanh:
        print(f"Trích dẫn hợp lệ    : {_ty_le([k.trich_dan_hop_le for k in cac_ket_qua])}")
        print(f"Số liệu có căn cứ   : {_ty_le([k.so_lieu_co_can_cu for k in cac_ket_qua])}")
    print(f"Thời gian trung bình: "
          f"{sum(k.giay for k in cac_ket_qua) / max(1, len(cac_ket_qua)):.1f}s/câu")


def in_bang_quet_nguong(cac_ket_qua: list[KetQuaMotCau]) -> None:
    """
    Quét thử nhiều cặp ngưỡng trên kết quả ĐÃ truy hồi - chỉ là số học nên
    tức thì, không phải chạy lại truy hồi cho từng ngưỡng.

    Đọc bảng: chọn hàng chặn được nhiều câu lạc đề nhất mà cột "oan" vẫn bằng 0.
    Ngưỡng nào bắt đầu làm cột "oan" khác 0 là ngưỡng đã siết quá tay.
    """
    ngoai = [k for k in cac_ket_qua if not _la_cau_trong_pham_vi(k)]
    trong = [k for k in cac_ket_qua if _la_cau_trong_pham_vi(k)]
    if not ngoai or not trong:
        print("\nKhông đủ cả câu trong phạm vi lẫn ngoài phạm vi để quét ngưỡng.")
        return

    print("\n" + "=" * 78)
    print(f"QUÉT NGƯỠNG CHẶN  ({len(trong)} câu đúng chủ đề, {len(ngoai)} câu lạc đề)")
    print("=" * 78)
    print(f"{'do_phu_idf <':>14}{'dense >':>10}{'chặn đúng':>13}"
          f"{'từ chối oan':>14}{'biên':>16}")

    def chan(kq: KetQuaMotCau, nguong_phu: float, nguong_dense: float) -> bool:
        if kq.ly_do_chan in {"khong_co_tai_lieu", "khong_truy_hoi_duoc"}:
            return True
        if kq.do_phu_tho < kiem_tra_tra_loi.DO_PHU_TOI_THIEU:
            return True
        if kq.ty_le_tu_la >= tu_vung_kho.TY_LE_TU_LA_TOI_DA:
            return True
        return kq.do_phu_idf < nguong_phu or kq.khoang_cach_dense > nguong_dense

    # Biên an toàn: khoảng cách từ ngưỡng tới câu đúng chủ đề SÁT ngưỡng nhất.
    # Biên mỏng nghĩa là ngưỡng đang vừa khít bộ đo này, nên câu thật đầu tiên
    # lệch ra ngoài sẽ bị chặn oan - đọc cột này trước khi chọn hàng.
    idf_thap_nhat = min(k.do_phu_idf for k in trong)
    dense_cao_nhat = max(k.khoang_cach_dense for k in trong)

    tot_nhat = None
    for nguong_phu in (0.50, 0.55, 0.60, 0.62, 0.65):
        for nguong_dense in (0.90, 0.95, 1.00, 1.05, 1.10, 1.20):
            bat = sum(1 for k in ngoai if chan(k, nguong_phu, nguong_dense))
            oan = sum(1 for k in trong if chan(k, nguong_phu, nguong_dense))
            bien = min(idf_thap_nhat - nguong_phu, nguong_dense - dense_cao_nhat)
            print(f"{nguong_phu:>14.2f}{nguong_dense:>10.2f}"
                  f"{bat:>8}/{len(ngoai):<5}{oan:>8}/{len(trong):<6}{bien:>+15.3f}")
            # Đòi hỏi biên tối thiểu 0.05 chứ không chỉ "oan == 0": điểm chặn
            # được nhiều nhất luôn nằm sát mép và sẽ hỏng ngay khi gặp câu mới.
            if oan == 0 and bien >= 0.05 and (tot_nhat is None or bat > tot_nhat[0]):
                tot_nhat = (bat, nguong_phu, nguong_dense, bien)

    print("-" * 78)
    print(f"Câu đúng chủ đề khó nhất: do_phu_idf thấp nhất {idf_thap_nhat:.3f}, "
          f"dense cao nhất {dense_cao_nhat:.3f}")
    if tot_nhat:
        bat, nguong_phu, nguong_dense, bien = tot_nhat
        print(f"Chọn: do_phu_idf < {nguong_phu:.2f}, dense > {nguong_dense:.2f} "
              f"→ chặn {bat}/{len(ngoai)} câu lạc đề, biên {bien:+.3f}")
        print(f"Đặt bằng biến môi trường:\n"
              f"    RAG_DO_PHU_IDF_TOI_THIEU={nguong_phu}\n"
              f"    RAG_KHOANG_CACH_DENSE_TOI_DA={nguong_dense}")
    else:
        print("Không cặp ngưỡng nào vừa không chặn oan vừa còn biên ≥ 0.05.")


def _nap_danh_sach(nhom_loc: str | None, so_luong: int | None) -> list[dict]:
    with open(DUONG_DAN_BO_CAU_HOI, encoding="utf-8") as f:
        bo = json.load(f)
    danh_sach = [
        muc for muc in bo["cau_hoi"]
        if not nhom_loc or muc.get("nhom") == nhom_loc
    ]
    if so_luong and so_luong < len(danh_sach):
        # Lấy mẫu cố định hạt giống: hai lần chạy khác nhau vẫn so sánh được.
        danh_sach = random.Random(20260912).sample(danh_sach, so_luong)
    return danh_sach


def _duong_dan_ket_qua(nhanh: bool) -> str:
    """Tách tệp theo chế độ: bản --nhanh đo truy hồi, bản đầy đủ đo cả trích dẫn
    và số liệu. Ghi chung một tệp thì lần chạy sau xóa mất số liệu lần trước."""
    goc, duoi = os.path.splitext(DUONG_DAN_KET_QUA)
    return f"{goc}_{'nhanh' if nhanh else 'day_du'}{duoi}"


def _ghi_ket_qua(service: RAGService, cac_ket_qua: list, nhanh: bool,
                 xong: bool = False) -> str:
    """Ghi nguyên trạng kết quả hiện có. Ghi ra tệp tạm rồi đổi tên để crash
    giữa chừng không để lại JSON cụt đầu."""
    duong_dan = _duong_dan_ket_qua(nhanh)
    trang_thai = service.status_dict()
    tam = duong_dan + ".tmp"
    with open(tam, "w", encoding="utf-8") as f:
        json.dump(
            {
                "chay_luc": time.strftime("%Y-%m-%d %H:%M:%S"),
                "che_do": "nhanh" if nhanh else "day_du",
                "hoan_tat": xong,
                "model": trang_thai["model"],
                "so_vector": trang_thai["vector_count"],
                "nguong": {
                    "ty_le_tu_la_toi_da": tu_vung_kho.TY_LE_TU_LA_TOI_DA,
                    "do_phu_idf_toi_thieu": tu_vung_kho.DO_PHU_IDF_TOI_THIEU,
                    "do_phu_tho_toi_thieu": kiem_tra_tra_loi.DO_PHU_TOI_THIEU,
                },
                "ket_qua": [asdict(k) for k in cac_ket_qua],
            },
            f, ensure_ascii=False, indent=1,
        )
    os.replace(tam, duong_dan)
    return duong_dan


def chay_bo_cau_hoi(
    service: RAGService,
    nhom_loc: str | None,
    nhanh: bool,
    so_luong: int | None,
    do_nguong: bool,
) -> int:
    danh_sach = _nap_danh_sach(nhom_loc, so_luong)
    if not danh_sach:
        print(f"Không có câu hỏi nào thuộc nhóm '{nhom_loc}'.")
        return 1

    cac_ket_qua = []
    for thu_tu, muc in enumerate(danh_sach, 1):
        chay = chay_mot_cau_nhanh if nhanh else chay_mot_cau
        kq = chay(service, muc)
        cac_ket_qua.append(kq)
        # Ghi sau MỖI câu: bộ đầy đủ chạy ~3 tiếng, chỉ lưu ở cuối thì một lần
        # Ollama chết là mất trắng. Ghi nguyên tệp ~120KB, không đáng so với 100s/câu.
        _ghi_ket_qua(service, cac_ket_qua, nhanh)

        dau_hieu = []
        if kq.truy_hoi_dung_nguon is not None:
            dau_hieu.append("nguồn ĐÚNG" if kq.truy_hoi_dung_nguon else "nguồn SAI")
        if kq.bi_chan_som:
            dau_hieu.append(f"CHẶN ({kq.ly_do_chan})")
        if kq.tu_choi_dung is False:
            dau_hieu.append("KHÔNG chặn được")
        if not nhanh and not kq.trich_dan_hop_le:
            dau_hieu.append("trích dẫn lỗi")
        if not nhanh and not kq.so_lieu_co_can_cu:
            chi_tiet = ", ".join(kq.so_dang_ngo[:3])
            dau_hieu.append(
                f"số liệu đáng ngờ ({chi_tiet})" if chi_tiet else "số liệu đáng ngờ"
            )
        if kq.loi:
            dau_hieu.append("LỖI")

        if nhanh:
            # Một dòng mỗi câu: cả bộ 127 câu vẫn đọc hết được trong một màn hình.
            print(f"[{thu_tu:>3}/{len(danh_sach)}] {kq.giay:>5.2f}s "
                  f"{' · '.join(dau_hieu) or 'ổn':<40} {kq.cau_hoi[:52]}", flush=True)
        else:
            print(f"\n[{thu_tu}/{len(danh_sach)}] {muc['cau_hoi']}", flush=True)
            print(f"    {kq.giay:.1f}s · {' · '.join(dau_hieu) or 'ổn'}")
            print(f"    nguồn: {', '.join(kq.nguon[:3]) or '(không có)'}")
            print(f"    {' '.join(kq.tra_loi.split())[:220]}")

    in_bang_tong_ket(cac_ket_qua, nhanh)
    if do_nguong:
        in_bang_quet_nguong(cac_ket_qua)

    print(f"\nĐã ghi chi tiết vào "
          f"{_ghi_ket_qua(service, cac_ket_qua, nhanh, xong=True)}")
    return 0


def chay_mot_cau_hoi_le(service: RAGService, cau_hoi: str) -> int:
    kq = chay_mot_cau(service, {"cau_hoi": cau_hoi})
    print(f"\nCÂU HỎI: {cau_hoi}\n")
    print(kq.tra_loi.strip())
    print("\nNGUỒN ĐƯỢC TRUY HỒI:")
    for thu_tu, ten in enumerate(kq.nguon, 1):
        print(f"[{thu_tu}] {ten}")
    print(f"\nModel: {service.status_dict()['model']}")
    print(f"Trích dẫn hợp lệ: {'có' if kq.trich_dan_hop_le else 'KHÔNG'}")
    print(f"Số liệu có căn cứ: {'có' if kq.so_lieu_co_can_cu else 'KHÔNG'}")
    print(f"Thời gian: {kq.giay}s")
    co_trich_dan = bool(re.search(r"\[\d+\]", kq.tra_loi))
    return 0 if kq.tra_loi.strip() and (co_trich_dan or kq.da_tu_choi) else 2


def main() -> int:
    _bat_utf8_cho_console()
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("question", nargs="?", default=CAU_HOI_MAC_DINH)
    parser.add_argument("--bo", action="store_true",
                        help="chạy cả bộ câu hỏi, gọi đủ LLM (chậm)")
    parser.add_argument("--nhanh", action="store_true",
                        help="chạy cả bộ nhưng chỉ đo truy hồi và cổng chặn")
    parser.add_argument("--nhom", default=None, help="chỉ chạy một nhóm câu hỏi")
    parser.add_argument("--so", type=int, default=None,
                        help="chỉ lấy mẫu N câu (hạt giống cố định)")
    parser.add_argument("--do-nguong", action="store_true",
                        help="in bảng quét ngưỡng chặn sau khi chạy")
    tham_so = parser.parse_args()

    service = RAGService()
    service.initialize()
    if service.status.state != "ready":
        print(f"LỖI KHỞI TẠO: {service.status.message}")
        return 1

    if tham_so.bo or tham_so.nhanh or tham_so.nhom:
        return chay_bo_cau_hoi(
            service, tham_so.nhom, tham_so.nhanh, tham_so.so, tham_so.do_nguong
        )
    return chay_mot_cau_hoi_le(service, tham_so.question)


if __name__ == "__main__":
    raise SystemExit(main())
