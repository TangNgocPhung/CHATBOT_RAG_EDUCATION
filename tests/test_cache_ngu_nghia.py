"""Cache ngữ nghĩa. Rủi ro lớn nhất không phải là trượt cache mà là TRÚNG NHẦM:
trả câu trả lời của câu hỏi khác, hoặc trả câu dựa trên kho tài liệu đã cũ. Với
văn bản quy phạm thì cả hai đều là sai căn cứ, nên phần lớn test ở đây kiểm tra
các trường hợp BẮT BUỘC phải trượt."""

import math
import os
import time
import tempfile
import unittest
from unittest.mock import patch

import cache_ngu_nghia
from cache_ngu_nghia import CacheNguNghia, van_tay_chi_muc


def vector(*gia_tri) -> list[float]:
    return list(gia_tri)


# Hai vector gần như trùng hướng (cosine ~0.999) và một vector vuông góc.
GIONG_A = vector(1.0, 0.0, 0.0)
GIONG_B = vector(0.999, 0.045, 0.0)
KHAC_HAN = vector(0.0, 1.0, 0.0)

VAN_TAY = "8827-8827"
MODEL = "qwen3.5:4b"


class CacheTests(unittest.TestCase):
    def setUp(self):
        self.thu_muc = tempfile.TemporaryDirectory()
        self.duong_dan = os.path.join(self.thu_muc.name, "cache.json")
        self.cache = CacheNguNghia(self.duong_dan)

    def tearDown(self):
        self.thu_muc.cleanup()

    def _them_mau(self, cau_hoi="Quy định về dạy thêm?", vec=None, **kwargs):
        self.cache.them(
            cau_hoi=cau_hoi,
            vector_cau_hoi=vec or GIONG_A,
            tra_loi="Theo Thông tư [1], ...",
            nguon=[{"name": "day-them.pdf"}],
            model=kwargs.get("model", MODEL),
            van_tay=kwargs.get("van_tay", VAN_TAY),
            canh_bao_hieu_luc=kwargs.get("canh_bao_hieu_luc"),
        )

    # ---------- trúng ----------

    def test_trung_khi_cau_hoi_tuong_duong(self):
        self._them_mau()
        muc, diem = self.cache.tim(GIONG_B, MODEL, VAN_TAY)
        self.assertIsNotNone(muc)
        self.assertGreater(diem, cache_ngu_nghia.NGUONG_TUONG_DONG)
        self.assertEqual(muc["tra_loi"], "Theo Thông tư [1], ...")

    def test_tra_ve_ca_nguon_va_canh_bao_hieu_luc(self):
        """Câu lấy từ cache mà mất cảnh báo 'văn bản đã bị thay thế' thì nguy
        hiểm hơn hẳn việc bắt người dùng chờ."""
        canh_bao = [{"type": "hieu_luc", "message": "Đã bị thay thế", "evidence": 1,
                     "kind": "thay_the"}]
        self._them_mau(canh_bao_hieu_luc=canh_bao)
        muc, _ = self.cache.tim(GIONG_A, MODEL, VAN_TAY)
        self.assertEqual(muc["canh_bao_hieu_luc"], canh_bao)
        self.assertEqual(muc["nguon"], [{"name": "day-them.pdf"}])

    def test_dem_so_lan_dung(self):
        # tim() chỉ chọn ứng viên nên không đếm; chỗ gọi đếm sau khi đã quyết
        # dùng thật (xem ChotKiemBangChungTests.test_ghi_nhan_dung_tach_khoi_tim).
        self._them_mau()
        self.cache.tim(GIONG_A, MODEL, VAN_TAY)
        self.cache.ghi_nhan_dung("Quy định về dạy thêm?")
        self.cache.ghi_nhan_dung("Quy định về dạy thêm?")
        self.assertEqual(self.cache.thong_ke()["so_lan_dung"], 2)

    # ---------- bắt buộc phải trượt ----------

    def test_truot_khi_cau_hoi_khac_han(self):
        self._them_mau()
        muc, _ = self.cache.tim(KHAC_HAN, MODEL, VAN_TAY)
        self.assertIsNone(muc)

    def test_truot_khi_doi_model(self):
        """Đổi sang model khác mà vẫn trả câu của model cũ thì người dùng tưởng
        đã đổi nhưng thực chất chưa."""
        self._them_mau()
        muc, _ = self.cache.tim(GIONG_A, "qwen3.5:9b", VAN_TAY)
        self.assertIsNone(muc)

    def test_truot_khi_chi_muc_da_doi(self):
        self._them_mau()
        muc, _ = self.cache.tim(GIONG_A, MODEL, "9000-9000")
        self.assertIsNone(muc)

    def test_truot_khi_muc_qua_han(self):
        """Đẩy thẳng tao_luc về quá khứ thay vì đặt hạn bằng 0: đồng hồ Windows
        có độ phân giải ~15ms nên tao_luc và mốc hết hạn có thể rơi cùng một
        tick, làm test đỗ hay trượt tùy lúc chạy."""
        self._them_mau()
        qua_han = time.time() - (cache_ngu_nghia.SO_NGAY_HET_HAN + 1) * 86400
        self.cache._muc[0]["tao_luc"] = qua_han
        muc, _ = self.cache.tim(GIONG_A, MODEL, VAN_TAY)
        self.assertIsNone(muc)

    def test_truot_khi_vector_rong(self):
        self._them_mau()
        muc, _ = self.cache.tim([], MODEL, VAN_TAY)
        self.assertIsNone(muc)

    def test_khong_them_cau_tra_loi_rong(self):
        self.cache.them("Câu?", GIONG_A, "   ", [], MODEL, VAN_TAY)
        self.assertEqual(self.cache.thong_ke()["so_muc"], 0)

    def test_tat_bang_bien_moi_truong(self):
        with patch.dict(os.environ, {"RAG_BAT_CACHE": "0"}):
            self.cache.them("Câu?", GIONG_A, "Đáp.", [], MODEL, VAN_TAY)
            self.assertEqual(self.cache.thong_ke()["so_muc"], 0)
            muc, _ = self.cache.tim(GIONG_A, MODEL, VAN_TAY)
        self.assertIsNone(muc)

    # ---------- dọn dẹp và lưu trữ ----------

    def test_xoa_muc_thuoc_chi_muc_cu(self):
        self._them_mau(cau_hoi="Câu kho cũ?", van_tay="cu-cu")
        self._them_mau(cau_hoi="Câu kho mới?", van_tay=VAN_TAY)
        self.assertEqual(self.cache.xoa_theo_van_tay_khac(VAN_TAY), 1)
        self.assertEqual(self.cache.thong_ke()["so_muc"], 1)

    def test_cat_bot_theo_so_muc_toi_da(self):
        with patch.object(cache_ngu_nghia, "SO_MUC_TOI_DA", 3):
            for i in range(6):
                self._them_mau(cau_hoi=f"Câu {i}?")
        self.assertEqual(self.cache.thong_ke()["so_muc"], 3)

    def test_ghi_va_nap_lai_tu_dia(self):
        self._them_mau()
        cache_moi = CacheNguNghia(self.duong_dan)
        muc, _ = cache_moi.tim(GIONG_A, MODEL, VAN_TAY)
        self.assertIsNotNone(muc)

    def test_cache_hong_tren_dia_khong_lam_vo_ung_dung(self):
        with open(self.duong_dan, "w", encoding="utf-8") as f:
            f.write("{ day khong phai json hop le")
        cache_moi = CacheNguNghia(self.duong_dan)
        self.assertEqual(cache_moi.thong_ke()["so_muc"], 0)

    def test_vector_duoc_chuan_hoa_khi_luu(self):
        self.cache.them("Câu?", vector(3.0, 4.0, 0.0), "Đáp.", [], MODEL, VAN_TAY)
        luu = self.cache._muc[0]["vector"]
        self.assertAlmostEqual(math.sqrt(sum(x * x for x in luu)), 1.0, places=6)

    def test_vector_khong_lam_vo_khi_do_dai_bang_khong(self):
        self.cache.them("Câu?", vector(0.0, 0.0, 0.0), "Đáp.", [], MODEL, VAN_TAY)
        self.assertEqual(self.cache.thong_ke()["so_muc"], 1)


class ChotKiemBangChungTests(unittest.TestCase):
    """Ngưỡng cosine đơn lẻ không tách được 'giảng viên đại học' khỏi 'giảng viên
    cao đẳng' (đo được 0.902, cao hơn cả cặp diễn đạt lại thấp nhất 0.896). Chốt
    kiểm là bộ đoạn bằng chứng: cùng bằng chứng thì câu cũ vẫn đúng căn cứ."""

    def setUp(self):
        self.thu_muc = tempfile.TemporaryDirectory()
        self.cache = CacheNguNghia(os.path.join(self.thu_muc.name, "c.json"))

    def tearDown(self):
        self.thu_muc.cleanup()

    @staticmethod
    def _doan(khoa, nguon="a.pdf"):
        from langchain_core.documents import Document
        return Document(page_content="x",
                        metadata={"_chunk_key": khoa, "source_file": nguon})

    def test_khoa_chunk_duoc_sap_xep(self):
        khoa = cache_ngu_nghia.khoa_chunk_cua(
            [self._doan("zzz"), self._doan("aaa"), self._doan("mmm")]
        )
        self.assertEqual(khoa, ["aaa", "mmm", "zzz"])

    def test_dung_lai_khi_bang_chung_trung_khop(self):
        self.cache.them("Câu cũ?", GIONG_A, "Đáp.", [], MODEL, VAN_TAY,
                        khoa_chunk=["c1", "c2"])
        muc, _ = self.cache.tim(GIONG_A, MODEL, VAN_TAY)
        self.assertTrue(cache_ngu_nghia.cung_bang_chung(
            muc, [self._doan("c2"), self._doan("c1")]
        ))

    def test_khong_dung_lai_khi_lech_mot_doan(self):
        self.cache.them("Câu cũ?", GIONG_A, "Đáp.", [], MODEL, VAN_TAY,
                        khoa_chunk=["c1", "c2"])
        muc, _ = self.cache.tim(GIONG_A, MODEL, VAN_TAY)
        self.assertFalse(cache_ngu_nghia.cung_bang_chung(
            muc, [self._doan("c1"), self._doan("c3")]
        ))

    def test_cung_ten_file_nhung_khac_doan_thi_khong_dung_lai(self):
        """Điều 3 và Điều 5 của cùng một thông tư ra cùng tên file nhưng câu trả
        lời khác hẳn - nên phải đối chiếu theo đoạn, không theo tên file."""
        self.cache.them("Điều 3 quy định gì?", GIONG_A, "Đáp.", [], MODEL, VAN_TAY,
                        khoa_chunk=["tt-dieu3"])
        muc, _ = self.cache.tim(GIONG_A, MODEL, VAN_TAY)
        self.assertFalse(cache_ngu_nghia.cung_bang_chung(
            muc, [self._doan("tt-dieu5", nguon="thong-tu.pdf")]
        ))

    def test_muc_cu_khong_co_khoa_chunk_thi_khong_dung_lai(self):
        """Mục lưu từ phiên bản trước chưa có khóa đoạn: thà soạn lại còn hơn
        dùng một câu không kiểm chứng được căn cứ."""
        self.assertFalse(cache_ngu_nghia.cung_bang_chung({}, [self._doan("c1")]))

    def test_ung_vien_duoi_nguong_chac_chan_van_duoc_tra_ve(self):
        """tim() trả ứng viên từ NGUONG_UNG_VIEN để chỗ gọi còn cơ hội đối chiếu
        bằng chứng; nếu chặn ngay ở NGUONG_TUONG_DONG thì chốt kiểm vô dụng."""
        self.cache.them("Câu?", GIONG_A, "Đáp.", [], MODEL, VAN_TAY,
                        khoa_chunk=["c1"])
        # cosine ~0.94: dưới ngưỡng chắc chắn 0.96, trên ngưỡng ứng viên 0.88.
        hoi_giong = vector(0.94, 0.341, 0.0)
        muc, diem = self.cache.tim(hoi_giong, MODEL, VAN_TAY)
        self.assertIsNotNone(muc)
        self.assertLess(diem, cache_ngu_nghia.NGUONG_TUONG_DONG)
        self.assertGreaterEqual(diem, cache_ngu_nghia.NGUONG_UNG_VIEN)

    def test_ghi_nhan_dung_tach_khoi_tim(self):
        """tim() không được tự đếm: ứng viên có thể bị chốt kiểm loại, lúc đó
        không phải là một lần dùng cache."""
        self.cache.them("Câu?", GIONG_A, "Đáp.", [], MODEL, VAN_TAY,
                        khoa_chunk=["c1"])
        self.cache.tim(GIONG_A, MODEL, VAN_TAY)
        self.assertEqual(self.cache.thong_ke()["so_lan_dung"], 0)
        self.cache.ghi_nhan_dung("Câu?")
        self.assertEqual(self.cache.thong_ke()["so_lan_dung"], 1)


class VanTayTests(unittest.TestCase):
    def test_van_tay_doi_khi_so_vector_doi(self):
        self.assertNotEqual(van_tay_chi_muc(8827, 8827), van_tay_chi_muc(8900, 8827))

    def test_van_tay_doi_khi_so_chunk_doi(self):
        self.assertNotEqual(van_tay_chi_muc(8827, 8827), van_tay_chi_muc(8827, 8900))


if __name__ == "__main__":
    unittest.main()
