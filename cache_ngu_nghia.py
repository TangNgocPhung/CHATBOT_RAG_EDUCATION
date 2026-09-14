"""
CACHE NGỮ NGHĨA CHO CÂU TRẢ LỜI
================================
Trên máy chỉ có CPU, mỗi câu trả lời tốn khoảng 150 giây. Trong khi đó câu hỏi
tra cứu văn bản giáo dục lặp lại rất nhiều: cả một phòng giáo dục sẽ cùng hỏi
"quy định về dạy thêm", "đánh giá học sinh tiểu học" trong cùng một tuần. Trả
lại câu đã soạn cho câu hỏi tương đương là cách rút ngắn thời gian chờ lớn nhất
không cần đổi phần cứng.

VÌ SAO SO KHỚP THEO NGỮ NGHĨA CHỨ KHÔNG THEO CHUỖI: "Quy định về dạy thêm ra
sao?" và "Dạy thêm được quy định thế nào?" là cùng một câu hỏi nhưng khác từng
ký tự. Khóa cache theo chuỗi sẽ trượt gần hết. Kho đã có sẵn model nhúng bge-m3
đang chạy, nên nhúng câu hỏi rồi so cosine gần như không tốn thêm gì (~0,1 giây)
so với 150 giây phải tiết kiệm.

BỐN ĐIỀU KIỆN ĐỂ MỘT MỤC CACHE CÒN DÙNG ĐƯỢC - thiếu một là bỏ:
  1. Cùng model trả lời. Đổi từ qwen3.5:4b sang 9b mà trả lại câu của model cũ
     thì người dùng tưởng đã đổi nhưng thực chất chưa.
  2. Cùng vân tay chỉ mục. Kho vừa thêm/bớt tài liệu thì câu trả lời cũ có thể
     đã sai căn cứ - đây là rủi ro nghiêm trọng nhất với văn bản quy phạm.
  3. Đủ giống, VÀ nếu chỉ giống vừa phải thì phải cùng bộ bằng chứng - xem phần
     "HAI NGƯỠNG" bên dưới. Trả nhầm câu trả lời của một câu hỏi khác tệ hơn
     nhiều so với việc để người dùng chờ.
  4. Chưa quá hạn.

KHÔNG cache: câu có tệp đính kèm, câu hỏi nối tiếp phụ thuộc hội thoại trước,
và câu hỏi chứa URL. Cả ba đều phụ thuộc ngữ cảnh ngoài bản thân câu chữ nên
hai lần hỏi giống nhau vẫn có thể phải trả lời khác nhau.
"""

from __future__ import annotations

import json
import math
import os
import threading
import time

DUONG_DAN_CACHE = os.path.abspath(os.getenv(
    "RAG_CACHE_FILE",
    os.path.join(os.path.dirname(os.path.abspath(__file__)), "cache_cau_tra_loi.json"),
))


def bat_cache() -> bool:
    return os.getenv("RAG_BAT_CACHE", "1") == "1"


def _so_thuc(ten: str, mac_dinh: float) -> float:
    try:
        return float(os.getenv(ten, str(mac_dinh)))
    except ValueError:
        return mac_dinh


def _so_nguyen(ten: str, mac_dinh: int) -> int:
    try:
        return int(os.getenv(ten, str(mac_dinh)))
    except ValueError:
        return mac_dinh


# HAI NGƯỠNG, VÌ MỘT NGƯỠNG KHÔNG ĐỦ
# Đo trên chính kho này (hieu_chinh_cache.py): cặp câu diễn đạt khác nhau nhưng
# CÙNG một ý có cosine thấp nhất 0.896, còn cặp câu KHÁC ý nhau lại lên tới
# 0.902. Hai phân bố chồng lấn, nên không ngưỡng đơn lẻ nào vừa bắt được câu
# diễn đạt lại vừa tránh được nhầm lẫn. Cặp tệ nhất là "chuẩn nghề nghiệp giảng
# viên ĐẠI HỌC" và "... CAO ĐẲNG": khác đúng một từ, nhưng câu trả lời nằm ở hai
# thông tư khác nhau.
#
# Lối ra là dùng chính bước truy hồi làm chốt kiểm. Truy hồi chỉ tốn ~0,4 giây,
# bằng 1/400 thời gian sinh câu trả lời, nên "tra lại rồi mới quyết" gần như
# miễn phí:
#   - cosine >= NGUONG_TUONG_DONG : gần như chắc chắn cùng câu hỏi, trả ngay.
#   - cosine >= NGUONG_UNG_VIEN   : nghi là cùng câu hỏi, phải truy hồi rồi đối
#                                   chiếu; chỉ dùng lại khi bộ đoạn bằng chứng
#                                   TRÙNG KHỚP HOÀN TOÀN với lúc soạn câu cũ.
#                                   Cùng bằng chứng thì câu trả lời cũ vẫn đúng
#                                   căn cứ; khác một đoạn là soạn lại.
#   - thấp hơn                    : trượt.
# Nhờ chốt kiểm này, ngưỡng ứng viên hạ được xuống dưới mức chồng lấn mà vẫn an
# toàn hơn so với chỉ đặt một ngưỡng 0.96.
NGUONG_TUONG_DONG = _so_thuc("RAG_CACHE_NGUONG", 0.96)
NGUONG_UNG_VIEN = _so_thuc("RAG_CACHE_NGUONG_UNG_VIEN", 0.88)
SO_MUC_TOI_DA = _so_nguyen("RAG_CACHE_SO_MUC", 300)
SO_NGAY_HET_HAN = _so_nguyen("RAG_CACHE_NGAY", 30)


def _tich_vo_huong(a: list[float], b: list[float]) -> float:
    return sum(x * y for x, y in zip(a, b))


def _chuan_hoa(vector: list[float]) -> list[float]:
    """Chuẩn hóa sẵn khi ghi vào cache: lúc tra chỉ còn phép nhân, không phải
    tính lại độ dài của từng vector đã lưu."""
    do_dai = math.sqrt(_tich_vo_huong(vector, vector))
    if do_dai <= 0:
        return vector
    return [x / do_dai for x in vector]


class CacheNguNghia:
    def __init__(self, duong_dan: str = DUONG_DAN_CACHE):
        self.duong_dan = duong_dan
        self._khoa = threading.Lock()
        self._muc: list[dict] = []
        self._nap()

    # ---------- lưu trữ ----------

    def _nap(self) -> None:
        try:
            with open(self.duong_dan, encoding="utf-8") as f:
                du_lieu = json.load(f)
            muc = du_lieu.get("muc", []) if isinstance(du_lieu, dict) else []
            self._muc = [m for m in muc if isinstance(m, dict) and m.get("vector")]
        except (OSError, ValueError):
            # Không có cache hoặc cache hỏng đều không phải lỗi: chạy với cache rỗng.
            self._muc = []

    def _ghi(self) -> None:
        try:
            tam = self.duong_dan + ".tmp"
            with open(tam, "w", encoding="utf-8") as f:
                json.dump({"muc": self._muc}, f, ensure_ascii=False)
            os.replace(tam, self.duong_dan)
        except OSError as exc:
            print(f"⚠️  Không ghi được cache: {exc}")

    # ---------- tra và thêm ----------

    def tim(
        self,
        vector_cau_hoi: list[float],
        model: str,
        van_tay: str,
        nguong: float | None = None,
    ) -> tuple[dict | None, float]:
        """
        Trả về (mục giống nhất, độ tương đồng); mục là None nếu chưa đạt ngưỡng.

        `nguong` mặc định là NGUONG_UNG_VIEN - hàm này chỉ chọn ứng viên, còn
        quyết định dùng hay không thì để chỗ gọi, vì chỉ chỗ gọi mới biết bộ
        bằng chứng truy hồi được có trùng với lúc soạn câu cũ hay không.
        """
        if not bat_cache() or not vector_cau_hoi:
            return None, 0.0
        muc_nguong = NGUONG_UNG_VIEN if nguong is None else nguong
        chuan = _chuan_hoa(vector_cau_hoi)
        han = time.time() - SO_NGAY_HET_HAN * 86400
        tot_nhat, diem_tot_nhat = None, 0.0
        with self._khoa:
            for muc in self._muc:
                if muc.get("model") != model or muc.get("van_tay") != van_tay:
                    continue
                if muc.get("tao_luc", 0) < han:
                    continue
                diem = _tich_vo_huong(chuan, muc["vector"])
                if diem > diem_tot_nhat:
                    tot_nhat, diem_tot_nhat = muc, diem
            if tot_nhat is not None and diem_tot_nhat >= muc_nguong:
                return dict(tot_nhat), diem_tot_nhat
        return None, diem_tot_nhat

    def ghi_nhan_dung(self, cau_hoi_goc: str) -> None:
        """Đếm lượt dùng. Tách khỏi tim() vì tim() có thể trả về ứng viên rồi bị
        chốt kiểm bằng chứng loại - lúc đó không được tính là một lần dùng."""
        with self._khoa:
            for muc in self._muc:
                if muc.get("cau_hoi") == cau_hoi_goc:
                    muc["so_lan_dung"] = muc.get("so_lan_dung", 0) + 1
                    muc["dung_lan_cuoi"] = time.time()
                    return

    def them(
        self,
        cau_hoi: str,
        vector_cau_hoi: list[float],
        tra_loi: str,
        nguon: list,
        model: str,
        van_tay: str,
        canh_bao_hieu_luc: list | None = None,
        khoa_chunk: list[str] | None = None,
    ) -> None:
        if not bat_cache() or not vector_cau_hoi or not tra_loi.strip():
            return
        muc = {
            "cau_hoi": cau_hoi,
            "vector": _chuan_hoa(vector_cau_hoi),
            "tra_loi": tra_loi,
            "nguon": nguon,
            "canh_bao_hieu_luc": canh_bao_hieu_luc or [],
            # Dấu vân tay của bộ bằng chứng đã dùng để soạn câu này.
            "khoa_chunk": sorted(khoa_chunk or []),
            "model": model,
            "van_tay": van_tay,
            "tao_luc": time.time(),
            "dung_lan_cuoi": time.time(),
            "so_lan_dung": 0,
        }
        with self._khoa:
            self._muc.append(muc)
            self._don_dep()
            self._ghi()

    def _don_dep(self) -> None:
        """Bỏ mục hết hạn, mục thuộc chỉ mục cũ, rồi cắt bớt theo LRU."""
        han = time.time() - SO_NGAY_HET_HAN * 86400
        self._muc = [m for m in self._muc if m.get("tao_luc", 0) >= han]
        if len(self._muc) > SO_MUC_TOI_DA:
            self._muc.sort(key=lambda m: m.get("dung_lan_cuoi", 0), reverse=True)
            self._muc = self._muc[:SO_MUC_TOI_DA]

    def xoa_theo_van_tay_khac(self, van_tay: str) -> int:
        """
        Gọi sau khi cập nhật chỉ mục. Câu trả lời dựa trên kho cũ có thể đã sai
        căn cứ - với văn bản quy phạm thì đó không phải chuyện nhỏ, nên xóa hẳn
        chứ không để hết hạn tự nhiên.
        """
        with self._khoa:
            truoc = len(self._muc)
            self._muc = [m for m in self._muc if m.get("van_tay") == van_tay]
            da_xoa = truoc - len(self._muc)
            if da_xoa:
                self._ghi()
            return da_xoa

    def xoa_het(self) -> int:
        with self._khoa:
            da_xoa = len(self._muc)
            self._muc = []
            self._ghi()
            return da_xoa

    def thong_ke(self) -> dict:
        with self._khoa:
            return {
                "so_muc": len(self._muc),
                "so_lan_dung": sum(m.get("so_lan_dung", 0) for m in self._muc),
                "nguong": NGUONG_TUONG_DONG,
                "so_muc_toi_da": SO_MUC_TOI_DA,
                "bat": bat_cache(),
            }


def khoa_chunk_cua(tai_lieu) -> list[str]:
    """Khóa của các đoạn bằng chứng, đã sắp xếp - dùng để so hai lần truy hồi có
    ra đúng cùng một bộ bằng chứng hay không."""
    return sorted(
        doc.metadata.get("_chunk_key") or doc.metadata.get("source_file", "")
        for doc in tai_lieu
    )


def cung_bang_chung(muc: dict, tai_lieu) -> bool:
    """
    Cùng bằng chứng thì câu trả lời cũ vẫn đúng căn cứ.

    Đối chiếu theo khóa ĐOẠN chứ không theo tên file: hai câu hỏi về Điều 3 và
    Điều 5 của cùng một thông tư sẽ ra cùng tên file nhưng khác đoạn, mà câu trả
    lời thì hoàn toàn khác nhau.
    """
    da_luu = muc.get("khoa_chunk") or []
    return bool(da_luu) and da_luu == khoa_chunk_cua(tai_lieu)


def van_tay_chi_muc(so_vector: int, so_tai_lieu: int) -> str:
    """
    Vân tay để biết cache có thuộc về đúng phiên bản kho hay không. Số vector +
    số chunk là đủ: mọi thao tác thêm, bớt hay nạp lại tài liệu đều làm ít nhất
    một trong hai con số này đổi.
    """
    return f"{so_vector}-{so_tai_lieu}"


cache = CacheNguNghia()
