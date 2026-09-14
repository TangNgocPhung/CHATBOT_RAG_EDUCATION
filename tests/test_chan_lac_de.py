"""Cổng chặn câu hỏi lạc đề: phải bắt được câu ngoài kho mà KHÔNG chặn oan
câu đúng chủ đề. Từ chối oan nguy hiểm hơn nhiều so với trả lời chậm, nên phần
lớn test ở đây là test không-được-chặn."""

import unittest
from unittest.mock import patch

from langchain_core.documents import Document

import kiem_tra_tra_loi
import tu_vung_kho


def doan(noi_dung, nguon="a.pdf", do_phu=0.9, khoang_cach=None):
    metadata = {"source_file": nguon, "_lexical_coverage": do_phu}
    if khoang_cach is not None:
        metadata["_dense_distance"] = khoang_cach
    return Document(page_content=noi_dung, metadata=metadata)


KHO_MAU = [
    doan("Quy định về dạy thêm học thêm trong nhà trường phổ thông."),
    doan("Đánh giá học sinh tiểu học bằng nhận xét và điểm số."),
    doan("Chuẩn nghề nghiệp giảng viên đại học gồm các tiêu chuẩn về đạo đức."),
    doan("Phân phối chương trình môn Tin học lớp 5 theo từng tuần."),
    doan("Chế độ phụ cấp ưu đãi theo nghề đối với nhà giáo công lập."),
]


class TuVungKhoTests(unittest.TestCase):
    def setUp(self):
        self.tu_vung = tu_vung_kho.xay_dung_tu_vung(KHO_MAU)

    def test_dem_dung_so_chunk(self):
        self.assertEqual(self.tu_vung.so_chunk, len(KHO_MAU))

    def test_tu_pho_bien_co_idf_thap_hon_tu_hiem(self):
        # "học" có mặt ở nhiều đoạn, "phụ cấp" chỉ một đoạn.
        self.assertLess(self.tu_vung.idf("học"), self.tu_vung.idf("cấp"))

    def test_tu_kho_chua_tung_thay_co_idf_cao_nhat(self):
        self.assertEqual(self.tu_vung.idf("phở"), self.tu_vung.idf_toi_da)

    def test_bo_dau_khong_lam_tu_la_thanh_quen(self):
        """'phở' bỏ dấu thành 'pho', trùng 'phổ' trong 'phổ thông'. Nếu chấm
        trên dạng bỏ dấu thì đúng cái từ tố cáo câu lạc đề lại bị coi là quen."""
        tu_vung = tu_vung_kho.xay_dung_tu_vung([doan("giáo dục phổ thông")])
        self.assertNotIn("phở", tu_vung.tan_suat)

    def test_ty_le_tu_la_cao_khi_cau_hoi_toan_tu_ngoai_kho(self):
        cao = self.tu_vung.ty_le_tu_la("Cách nấu phở bò gia truyền ngon")
        thap = self.tu_vung.ty_le_tu_la("Quy định về dạy thêm học thêm thế nào")
        self.assertGreater(cao, thap)
        self.assertEqual(thap, 0.0)

    def test_do_phu_idf_thap_khi_doan_khong_cham_chu_de(self):
        do_phu = self.tu_vung.do_phu_idf("Cách nấu phở bò gia truyền", KHO_MAU)
        self.assertLess(do_phu, 0.5)

    def test_do_phu_idf_cao_khi_doan_dung_chu_de(self):
        do_phu = self.tu_vung.do_phu_idf(
            "Quy định về dạy thêm học thêm", KHO_MAU
        )
        self.assertGreater(do_phu, 0.9)


class KhoangCachDenseTests(unittest.TestCase):
    def test_khong_co_doan_dense_thi_coi_nhu_rat_xa(self):
        """Mọi câu đúng chủ đề trong benchmark đều có ít nhất một đoạn đến từ
        nhánh truy hồi ngữ nghĩa. Không có đoạn nào là dấu hiệu lạc đề, nên phải
        quy về khoảng cách lớn - trả 0.0 sẽ bị đọc ngược thành khớp hoàn hảo."""
        chi_co_bm25 = [doan("nội dung", khoang_cach=None)]
        self.assertEqual(
            tu_vung_kho.khoang_cach_dense_nho_nhat(chi_co_bm25),
            tu_vung_kho.KHONG_CO_DOAN_DENSE,
        )

    def test_lay_khoang_cach_nho_nhat(self):
        tai_lieu = [
            doan("a", khoang_cach=0.8),
            doan("b", khoang_cach=0.4),
            doan("c"),
        ]
        self.assertAlmostEqual(tu_vung_kho.khoang_cach_dense_nho_nhat(tai_lieu), 0.4)


class LyDoNgoaiPhamViTests(unittest.TestCase):
    def setUp(self):
        self.tu_vung = tu_vung_kho.xay_dung_tu_vung(KHO_MAU)

    def test_khong_chan_cau_dung_chu_de(self):
        ly_do = tu_vung_kho.ly_do_ngoai_pham_vi(
            "Quy định về dạy thêm học thêm trong nhà trường",
            [doan("Quy định về dạy thêm học thêm trong nhà trường phổ thông.",
                  khoang_cach=0.5)],
            self.tu_vung,
        )
        self.assertEqual(ly_do, "")

    def test_chan_cau_toan_tu_la(self):
        ly_do = tu_vung_kho.ly_do_ngoai_pham_vi(
            "Cách nấu phở bò gia truyền ngon nhất",
            [doan("Quy định về dạy thêm.", khoang_cach=0.5)],
            self.tu_vung,
        )
        self.assertTrue(ly_do.startswith("tu_la="), ly_do)

    def test_chan_khi_khoang_cach_dense_qua_lon(self):
        """Câu mà mọi từ đều có thật trong kho nhưng nghĩa thì không - đây là
        loại mà phép đếm từ không tách được, chỉ vector mới tách được."""
        ly_do = tu_vung_kho.ly_do_ngoai_pham_vi(
            "Đánh giá học sinh tiểu học theo quy định",
            [doan("Đánh giá học sinh tiểu học bằng nhận xét và điểm số.",
                  khoang_cach=5.0)],
            self.tu_vung,
        )
        self.assertTrue(ly_do.startswith("dense="), ly_do)

    def test_khong_chan_cau_qua_ngan(self):
        """'Điều 5 quy định gì?' chỉ vài từ, lệch một từ là tỉ lệ nhảy vọt."""
        ly_do = tu_vung_kho.ly_do_ngoai_pham_vi(
            "Phở bò", [doan("Quy định.", khoang_cach=0.5)], self.tu_vung
        )
        self.assertEqual(ly_do, "")

    def test_khong_co_tu_vung_thi_khong_chan(self):
        self.assertEqual(
            tu_vung_kho.ly_do_ngoai_pham_vi("bất kỳ câu hỏi nào ở đây", KHO_MAU, None),
            "",
        )


class QuaItLienQuanTests(unittest.TestCase):
    """qua_it_lien_quan giữ nguyên chữ ký cũ - chỗ gọi cũ không được vỡ."""

    def test_khong_co_tai_lieu_thi_chan(self):
        self.assertTrue(kiem_tra_tra_loi.qua_it_lien_quan([]))

    def test_goi_kieu_cu_van_chay_theo_do_phu_tho(self):
        lac_de = [doan("nội dung", do_phu=0.01)]
        dung_chu_de = [doan("nội dung", do_phu=0.8)]
        self.assertTrue(kiem_tra_tra_loi.qua_it_lien_quan(lac_de))
        self.assertFalse(kiem_tra_tra_loi.qua_it_lien_quan(dung_chu_de))

    def test_lop_tu_vung_bat_duoc_cai_lop_do_phu_tho_bo_lot(self):
        """Chính là ca đo được trên benchmark: độ phủ thô 0.58 nên lọt lớp cũ,
        nhưng chủ đề thì hoàn toàn ngoài kho."""
        tu_vung = tu_vung_kho.xay_dung_tu_vung(KHO_MAU)
        tai_lieu = [doan("Quy định về dạy thêm học thêm.", do_phu=0.58,
                         khoang_cach=0.5)]
        self.assertFalse(kiem_tra_tra_loi.qua_it_lien_quan(tai_lieu))
        self.assertTrue(
            kiem_tra_tra_loi.qua_it_lien_quan(
                tai_lieu, "Cách nấu phở bò gia truyền ngon nhất", tu_vung
            )
        )

    def test_nguong_doc_duoc_tu_bien_moi_truong(self):
        with patch.object(tu_vung_kho, "KHOANG_CACH_DENSE_TOI_DA", 0.1):
            ly_do = tu_vung_kho.ly_do_ngoai_pham_vi(
                "Quy định về dạy thêm học thêm trong nhà trường",
                [doan("Quy định về dạy thêm học thêm.", khoang_cach=0.5)],
                tu_vung_kho.xay_dung_tu_vung(KHO_MAU),
            )
        self.assertTrue(ly_do.startswith("dense="), ly_do)


if __name__ == "__main__":
    unittest.main()
