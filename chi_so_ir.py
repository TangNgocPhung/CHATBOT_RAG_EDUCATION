"""
CHỈ SỐ IR/QA KINH ĐIỂN: MRR, Hit@K, Recall@K, nDCG@K, MAP
=========================================================
Bộ benchmark cũ chỉ trả lời được câu "nguồn đúng CÓ nằm trong danh sách truy
hồi không". Đó là Hit@K với đúng một K, và nó không phân biệt được hệ thống đặt
tài liệu đúng ở vị trí 1 với hệ thống đặt nó ở vị trí 4 - trong khi với RAG,
khác biệt đó là thật: prompt chỉ nhận vài đoạn, đoạn đúng nằm càng sâu càng dễ
bị đoạn nhiễu lấn át, và khi siết SO_KET_QUA_CUOI để tiết kiệm token thì đoạn
đúng nằm sâu là thứ rơi ra ngoài trước tiên.

Module này chỉ làm số học trên THỨ HẠNG, không biết gì về FAISS/BM25/LLM, nên
test được mà không cần dựng chỉ mục.

QUY ƯỚC
  thu_hang    : vị trí 1-based của các kết quả ĐÚNG trong danh sách trả về, sắp
                tăng dần. [] nghĩa là truy hồi trượt hoàn toàn.
  so_lien_quan: tổng số tài liệu đúng câu hỏi này có trong kho (dùng cho
                Recall/MAP/nDCG; bộ câu hỏi hiện tại hầu hết là 1).
  k           : cắt ở top-k. Đo ở nhiều k để thấy hệ thống hỏng chỗ nào: Hit@1
                thấp mà Hit@10 cao nghĩa là truy hồi TÌM ĐƯỢC tài liệu nhưng
                xếp hạng kém - lỗi của reranker, không phải của embedding.

ĐƠN VỊ ĐO LÀ TÀI LIỆU, KHÔNG PHẢI CHUNK
  Nhãn trong bo_cau_hoi_benchmark.json là một phần TÊN FILE, nên thứ hạng phải
  tính trên danh sách tài liệu đã khử trùng lặp (xem xep_hang_tai_lieu). Tính
  thẳng trên chunk thì một tài liệu chiếm 2 chunk liền sẽ tự đẩy mọi tài liệu
  sau nó xuống 2 bậc, làm MRR trông tệ hơn thực tế.
"""

from __future__ import annotations

import math
import random
from dataclasses import dataclass, field

# Bốn mốc quen thuộc trong báo cáo IR. @1 là "trúng ngay phát đầu", @10 là "còn
# cứu được bằng rerank". Chỉ số nào cũng phải kèm k mới có nghĩa.
CAC_K_MAC_DINH = (1, 3, 5, 10)


@dataclass
class LuotTruyHoi:
    """Một câu hỏi đã chấm xong, đủ dữ liệu để tính mọi chỉ số ở trên."""

    cau_hoi: str = ""
    nhom: str = ""
    thu_hang: list[int] = field(default_factory=list)
    so_lien_quan: int = 1
    so_ung_vien: int = 0  # độ dài danh sách trả về, để biết k nào còn nghĩa
    nguon_xep_hang: list[str] = field(default_factory=list)

    @property
    def thu_hang_dau(self) -> int | None:
        return min(self.thu_hang) if self.thu_hang else None


def xep_hang_tai_lieu(ten_nguon_theo_thu_tu) -> list[str]:
    """
    Gộp danh sách chunk thành danh sách TÀI LIỆU, giữ thứ hạng lần xuất hiện
    đầu tiên. Một tài liệu ra ở chunk 1 và chunk 2 thì vẫn chỉ là hạng 1.
    """
    da_thay: set[str] = set()
    ket_qua: list[str] = []
    for ten in ten_nguon_theo_thu_tu:
        ten = (ten or "").strip()
        if not ten or ten in da_thay:
            continue
        da_thay.add(ten)
        ket_qua.append(ten)
    return ket_qua


def khop_nhan(ten_nguon: str, khoa: str) -> bool:
    """
    Đúng luật khớp mà benchmark vẫn dùng: nhãn là một phần tên file, so không
    phân biệt hoa thường. Tách riêng để mọi chỗ khớp giống nhau - hai luật khớp
    lệch nhau là cách êm ái nhất để có hai con số không so được với nhau.
    """
    return khoa.casefold().strip() in ten_nguon.casefold()


def thu_hang_lien_quan(danh_sach_nguon, nguon_mong_doi) -> list[int]:
    """
    Vị trí 1-based của những nguồn khớp nhãn, trong danh sách ĐÃ xếp hạng.

    Mỗi nhãn chỉ tính một lần, kể cả khi hai tài liệu khác nhau cùng khớp: nhãn
    "dạy thêm" trúng cả thông tư lẫn công văn hướng dẫn thì đó vẫn là một yêu
    cầu thông tin được đáp ứng, không phải hai.
    """
    thu_hang: list[int] = []
    khoa_da_dung: set[str] = set()
    for vi_tri, ten in enumerate(danh_sach_nguon, 1):
        for khoa in nguon_mong_doi:
            if khoa in khoa_da_dung:
                continue
            if khop_nhan(ten, khoa):
                khoa_da_dung.add(khoa)
                thu_hang.append(vi_tri)
                break
    return sorted(thu_hang)


def _cat(thu_hang, k: int | None) -> list[int]:
    return [r for r in thu_hang if k is None or r <= k]


def reciprocal_rank(thu_hang, k: int | None = None) -> float:
    """RR = 1/hạng của kết quả đúng ĐẦU TIÊN, 0 nếu không có trong top-k."""
    trong_k = _cat(thu_hang, k)
    return 1.0 / min(trong_k) if trong_k else 0.0


def hit_at_k(thu_hang, k: int) -> float:
    """Hit@K (còn gọi Success@K): 1 nếu top-k có ít nhất một kết quả đúng."""
    return 1.0 if _cat(thu_hang, k) else 0.0


def recall_at_k(thu_hang, so_lien_quan: int, k: int) -> float:
    if so_lien_quan <= 0:
        return 0.0
    return len(_cat(thu_hang, k)) / so_lien_quan


def precision_at_k(thu_hang, k: int) -> float:
    if k <= 0:
        return 0.0
    return len(_cat(thu_hang, k)) / k


def average_precision(thu_hang, so_lien_quan: int, k: int | None = None) -> float:
    """
    AP: trung bình precision đo tại mỗi vị trí có kết quả đúng. Chỉ khác MRR khi
    câu hỏi có nhiều hơn một tài liệu đúng - lúc đó AP phạt việc tìm được tài
    liệu đúng thứ hai quá muộn, còn MRR thì không nhìn thấy.
    """
    trong_k = _cat(thu_hang, k)
    if not trong_k or so_lien_quan <= 0:
        return 0.0
    tong = sum((thu_tu + 1) / hang for thu_tu, hang in enumerate(trong_k))
    mau = min(so_lien_quan, k) if k else so_lien_quan
    return tong / max(1, mau)


def ndcg_at_k(thu_hang, so_lien_quan: int, k: int) -> float:
    """
    nDCG với gain nhị phân (đúng/sai - kho này không có nhãn mức độ liên quan).
    Chiết khấu 1/log2(hạng+1) nên khoảng cách hạng 1→2 nặng hơn hạng 9→10, đúng
    với cách một prompt RAG thực sự tiêu thụ danh sách.
    """
    trong_k = _cat(thu_hang, k)
    if not trong_k or so_lien_quan <= 0:
        return 0.0
    dcg = sum(1.0 / math.log2(hang + 1) for hang in trong_k)
    idcg = sum(1.0 / math.log2(i + 1) for i in range(1, min(so_lien_quan, k) + 1))
    return dcg / idcg if idcg else 0.0


def khoang_tin_cay_bootstrap(
    gia_tri: list[float],
    so_lan: int = 2000,
    do_tin_cay: float = 0.95,
    hat_giong: int = 20260915,
) -> tuple[float, float]:
    """
    Khoảng tin cậy percentile bootstrap cho giá trị trung bình.

    Bộ câu hỏi chỉ có ~100 câu nên chênh lệch 2-3 điểm phần trăm giữa hai cấu
    hình thường nằm gọn trong nhiễu. Báo cáo MRR kèm khoảng tin cậy để không
    tuyên bố một thay đổi là cải thiện trong khi nó chỉ là may rủi lấy mẫu.
    """
    if not gia_tri:
        return (0.0, 0.0)
    if len(gia_tri) == 1:
        return (gia_tri[0], gia_tri[0])
    rng = random.Random(hat_giong)
    n = len(gia_tri)
    trung_binh = sorted(sum(rng.choices(gia_tri, k=n)) / n for _ in range(so_lan))
    le = (1.0 - do_tin_cay) / 2.0
    thap = trung_binh[int(le * so_lan)]
    cao = trung_binh[min(so_lan - 1, int((1.0 - le) * so_lan))]
    return (thap, cao)


def tong_hop(cac_luot: list[LuotTruyHoi], cac_k=CAC_K_MAC_DINH,
             k_mrr: int | None = 10) -> dict:
    """
    Chỉ số trung bình trên một tập câu hỏi.

    k_mrr: cắt MRR ở top-k (MRR@10 là quy ước phổ biến, ví dụ MS MARCO). Để
    None nếu muốn MRR trên toàn bộ danh sách trả về.
    """
    if not cac_luot:
        return {"so_cau": 0}

    n = len(cac_luot)
    rr = [reciprocal_rank(l.thu_hang, k_mrr) for l in cac_luot]
    thap, cao = khoang_tin_cay_bootstrap(rr)
    ket_qua = {
        "so_cau": n,
        "k_mrr": k_mrr,
        "mrr": sum(rr) / n,
        "mrr_ktc95": [thap, cao],
        "so_ung_vien_tb": sum(l.so_ung_vien for l in cac_luot) / n,
        # Hạng trung bình CHỈ trên các câu tìm được - trộn câu trượt vào thì
        # phải gán cho nó một hạng vô cực tuỳ tiện.
        "hang_trung_binh_khi_trung": None,
        "so_cau_truot": sum(1 for l in cac_luot if not l.thu_hang),
    }
    hang_trung = [l.thu_hang_dau for l in cac_luot if l.thu_hang_dau]
    if hang_trung:
        ket_qua["hang_trung_binh_khi_trung"] = sum(hang_trung) / len(hang_trung)

    for k in cac_k:
        ket_qua[f"hit@{k}"] = sum(hit_at_k(l.thu_hang, k) for l in cac_luot) / n
        ket_qua[f"recall@{k}"] = sum(
            recall_at_k(l.thu_hang, l.so_lien_quan, k) for l in cac_luot
        ) / n
        ket_qua[f"precision@{k}"] = sum(
            precision_at_k(l.thu_hang, k) for l in cac_luot
        ) / n
        ket_qua[f"ndcg@{k}"] = sum(
            ndcg_at_k(l.thu_hang, l.so_lien_quan, k) for l in cac_luot
        ) / n
    k_map = max(cac_k)
    ket_qua[f"map@{k_map}"] = sum(
        average_precision(l.thu_hang, l.so_lien_quan, k_map) for l in cac_luot
    ) / n
    return ket_qua


def tong_hop_theo_nhom(cac_luot: list[LuotTruyHoi], cac_k=CAC_K_MAC_DINH,
                       k_mrr: int | None = 10) -> dict[str, dict]:
    theo_nhom: dict[str, list[LuotTruyHoi]] = {}
    for luot in cac_luot:
        theo_nhom.setdefault(luot.nhom or "khac", []).append(luot)
    return {
        nhom: tong_hop(nhom_luot, cac_k, k_mrr)
        for nhom, nhom_luot in sorted(theo_nhom.items())
    }


def phan_bo_thu_hang(cac_luot: list[LuotTruyHoi], k_toi_da: int = 10) -> dict[str, int]:
    """
    Đếm số câu theo hạng của kết quả đúng đầu tiên. Đây là bảng phải đọc khi MRR
    tụt: tụt vì nhiều câu trượt hẳn, hay vì cả loạt câu bị đẩy từ hạng 1 xuống
    hạng 2, là hai hướng sửa hoàn toàn khác nhau.
    """
    phan_bo = {str(i): 0 for i in range(1, k_toi_da + 1)}
    phan_bo[f">{k_toi_da}"] = 0
    phan_bo["truot"] = 0
    for luot in cac_luot:
        hang = luot.thu_hang_dau
        if hang is None:
            phan_bo["truot"] += 1
        elif hang <= k_toi_da:
            phan_bo[str(hang)] += 1
        else:
            phan_bo[f">{k_toi_da}"] += 1
    return phan_bo


def bang_markdown(tom_tat_chung: dict, tom_tat_nhom: dict[str, dict],
                  cac_k=CAC_K_MAC_DINH) -> str:
    """Bảng dán thẳng vào báo cáo đề án, khỏi phải gõ lại số từ màn hình."""
    k_lon_nhat = max(cac_k)
    cot = (["Nhóm câu hỏi", "Số câu", "MRR"]
           + [f"Hit@{k}" for k in cac_k]
           + [f"nDCG@{k_lon_nhat}"])
    dong = ["| " + " | ".join(cot) + " |",
            "|" + "|".join(["---"] * len(cot)) + "|"]

    def mot_dong(ten: str, tt: dict) -> str:
        o = [ten, str(tt["so_cau"]), f"{tt['mrr']:.3f}"]
        o += [f"{tt['hit@' + str(k)] * 100:.1f}%" for k in cac_k]
        o += [f"{tt['ndcg@' + str(k_lon_nhat)]:.3f}"]
        return "| " + " | ".join(o) + " |"

    for ten, tt in tom_tat_nhom.items():
        dong.append(mot_dong(ten, tt))
    dong.append(mot_dong("**Toàn bộ**", tom_tat_chung))
    return "\n".join(dong)
