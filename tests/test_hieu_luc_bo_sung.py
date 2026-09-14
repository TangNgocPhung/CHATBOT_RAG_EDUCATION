import unittest
from datetime import date

from langchain_core.documents import Document

import hieu_luc_bo_sung as hieu_luc
import van_ban_meta


TIEU_DE_DU_THAO = (
    "BỘ GIÁO DỤC VÀ ĐÀO TẠO CỘNG HÒA XÃ HỘI CHỦ NGHĨA VIỆT NAM\n"
    "Số:        /2026/TT-BGDĐT     Hà Nội, ngày      tháng      năm 2026\n"
    "THÔNG TƯ Quy định về công tác sinh viên\n"
    "Căn cứ Luật Giáo dục số 43/2019/QH14;"
)
TIEU_DE_DA_BAN_HANH = (
    "BỘ GIÁO DỤC VÀ ĐÀO TẠO CỘNG HÒA XÃ HỘI CHỦ NGHĨA VIỆT NAM\n"
    "Số: 29/2023/TT-BGDĐT     Hà Nội, ngày 31 tháng 12 năm 2023\n"
    "THÔNG TƯ Hướng dẫn công tác thi đua, khen thưởng ngành Giáo dục\n"
    "Căn cứ Luật Giáo dục số 43/2019/QH14;"
)


class PhatHienDuThaoTests(unittest.TestCase):
    def test_o_so_hieu_va_ngay_bo_trong_la_du_thao(self):
        self.assertTrue(hieu_luc.phat_hien_du_thao(TIEU_DE_DU_THAO))

    def test_van_ban_da_ban_hanh_khong_bi_gan_co_du_thao(self):
        self.assertFalse(hieu_luc.phat_hien_du_thao(TIEU_DE_DA_BAN_HANH))

    def test_ocr_mat_chu_so_van_nhan_ra_du_thao(self):
        # PDF quét thường mất hẳn chữ "Số:" lẫn dấu tiếng Việt.
        ocr = (
            "BO GIAO DUC VA DAO TAO CONG HOA XA HOI CHU NGHIA VIET NAM\n"
            "Doc lap - Tu do - Hanh phuc   /2025/TT-BGDDT  Ha Noi, ngay thang nam 2025\n"
            "THONG TU Quy dinh ve khen thuong va ky luat hoc sinh"
        )
        self.assertTrue(hieu_luc.phat_hien_du_thao(ocr))

    def test_bieu_mau_trong_bai_giang_khong_bi_coi_la_du_thao(self):
        # "ngày tháng năm" ở ô điền của một biểu mẫu, không phải văn bản quy phạm.
        self.assertFalse(
            hieu_luc.phat_hien_du_thao(
                "PHIẾU ĐĂNG KÝ\nHọ và tên: ...\nNgày tháng năm sinh: ...\nLớp: ..."
            )
        )

    def test_khong_nham_duoi_so_hieu_day_du_thanh_o_trong(self):
        # "/2020/TT-BGDĐT" là phần đuôi của một số hiệu ĐẦY ĐỦ đứng ngay trước.
        self.assertFalse(
            hieu_luc.phat_hien_du_thao(
                "Số: 27/2020/TT-BGDĐT Hà Nội, ngày 4 tháng 9 năm 2020"
            )
        )


class NgayHieuLucTests(unittest.TestCase):
    def test_doc_duoc_ngay_hieu_luc(self):
        self.assertEqual(
            hieu_luc.trich_ngay_hieu_luc(
                "Thông tư này có hiệu lực thi hành kể từ ngày 15 tháng 02 năm 2024."
            ),
            "2024-02-15",
        )

    def test_chiu_duoc_khoang_trang_do_ocr_chen_giua_tu(self):
        self.assertEqual(
            hieu_luc.trich_ngay_hieu_luc(
                "Nghị định này có hi ệu l ực thi hành t ừ ngày 01 tháng 10 n ăm 2026."
            ),
            "2026-10-01",
        )

    def test_hieu_luc_ke_tu_ngay_ky_lay_theo_ngay_ban_hanh(self):
        self.assertEqual(
            hieu_luc.trich_ngay_hieu_luc(
                "Quyết định này có hiệu lực kể từ ngày ký.", "2025-09-25"
            ),
            "2025-09-25",
        )

    def test_khong_co_ngay_ban_hanh_thi_khong_doan_bua(self):
        self.assertIsNone(
            hieu_luc.trich_ngay_hieu_luc("Quyết định này có hiệu lực kể từ ngày ký.")
        )

    def test_moc_so_sanh_ngay_hieu_luc(self):
        muc = hieu_luc.TinhTrangThoiGian("tt.pdf", ngay_hieu_luc="2026-10-01")
        self.assertTrue(muc.chua_toi_ngay_hieu_luc(date(2026, 9, 12)))
        self.assertFalse(muc.chua_toi_ngay_hieu_luc(date(2026, 10, 1)))
        self.assertEqual(muc.ngay_hieu_luc_viet(), "1/10/2026")


class ChuThichHopNhatTests(unittest.TestCase):
    def test_nhan_ra_doan_bi_sua_doi_tai_cho(self):
        doan = (
            "Điểm này được bãi bỏ theo quy định tại khoản 9 Điều 1 của "
            "Thông tư số 45/2026/TT-BGDĐT, có hiệu lực kể từ ngày 10 tháng 6 năm 2026."
        )
        self.assertEqual(hieu_luc.van_ban_sua_doan(doan), ["45/2026/TT-BGDĐT"])

    def test_xuong_dong_giua_cau_khong_lam_mat_dau(self):
        doan = (
            "Cụm từ Phòng Giáo dục và Đào tạo được thay thế\n"
            "theo quy định tại điểm b khoản 2 Điều 10 của\n"
            "Thông tư số 51/2026/TT-BGDĐT"
        )
        self.assertEqual(hieu_luc.van_ban_sua_doan(doan), ["51/2026/TT-BGDĐT"])

    def test_cau_nguoc_chieu_khong_bi_doc_nguoc_quan_he(self):
        # Ở đây 71/2020/NĐ-CP là văn bản BỊ sửa, còn "Nghị định này" mới là văn
        # bản đi sửa - không được báo thành "đoạn này bị 71/2020/NĐ-CP sửa".
        self.assertEqual(
            hieu_luc.van_ban_sua_doan(
                "Nguồn kinh phí thực hiện theo quy định tại khoản 1 Điều 9 "
                "Nghị định số 71/2020/NĐ-CP đã được sửa đổi, bổ sung tại Nghị định này"
            ),
            [],
        )

    def test_cau_thuong_nhac_toi_sua_doi_khong_bi_bat_nham(self):
        self.assertEqual(
            hieu_luc.van_ban_sua_doan(
                "Trường hợp các văn bản được dẫn chiếu tại Thông tư này được sửa đổi, "
                "bổ sung thì áp dụng theo văn bản mới."
            ),
            [],
        )


class CanhBaoTests(unittest.TestCase):
    def setUp(self):
        self.tinh_trang = {
            "du-thao.pdf": hieu_luc.TinhTrangThoiGian("du-thao.pdf", la_du_thao=True),
            "sap-ap-dung.pdf": hieu_luc.TinhTrangThoiGian(
                "sap-ap-dung.pdf", ngay_hieu_luc="2026-10-01"
            ),
            "dang-dung.pdf": hieu_luc.TinhTrangThoiGian(
                "dang-dung.pdf", ngay_hieu_luc="2024-01-01"
            ),
        }

    def _nguon(self, *ten):
        return [{"evidence": i, "name": t} for i, t in enumerate(ten, 1)]

    def test_canh_bao_du_thao_va_chua_hieu_luc(self):
        canh_bao = hieu_luc.canh_bao(
            self.tinh_trang,
            self._nguon("du-thao.pdf", "sap-ap-dung.pdf", "dang-dung.pdf"),
            hom_nay=date(2026, 9, 12),
        )
        self.assertEqual([c["loai"] for c in canh_bao], ["du_thao", "chua_hieu_luc"])
        self.assertEqual([c["evidence"] for c in canh_bao], [1, 2])
        self.assertIn("DỰ THẢO", canh_bao[0]["thong_bao"])
        self.assertIn("1/10/2026", canh_bao[1]["thong_bao"])

    def test_mot_nguon_chi_canh_bao_mot_lan(self):
        canh_bao = hieu_luc.canh_bao(
            self.tinh_trang,
            self._nguon("du-thao.pdf", "du-thao.pdf"),
            hom_nay=date(2026, 9, 12),
        )
        self.assertEqual(len(canh_bao), 1)

    def test_dinh_dang_giong_canh_bao_cua_van_ban_meta(self):
        """Hai nguồn cảnh báo phải cùng khuôn thì tầng dịch vụ mới nối được."""
        ho_so = {
            "cu.pdf": van_ban_meta.HoSoVanBan(
                ten_file="cu.pdf",
                so_hieu="21/2020/TT-BGDĐT",
                loai="Thông tư",
                bi_thay_the_boi=["moi.pdf"],
            ),
            "moi.pdf": van_ban_meta.HoSoVanBan(
                ten_file="moi.pdf", so_hieu="29/2023/TT-BGDĐT", loai="Thông tư"
            ),
        }
        cua_ho = van_ban_meta.canh_bao_hieu_luc(ho_so, self._nguon("cu.pdf"))
        cua_toi = hieu_luc.canh_bao(
            self.tinh_trang, self._nguon("du-thao.pdf"), hom_nay=date(2026, 9, 12)
        )
        khoa_chung = {"evidence", "nguon", "loai", "thong_bao"}
        self.assertTrue(khoa_chung.issubset(cua_ho[0]))
        self.assertTrue(khoa_chung.issubset(cua_toi[0]))

    def test_canh_bao_doan_gan_dung_so_evidence(self):
        tai_lieu = [
            Document(page_content="Nội dung bình thường.", metadata={}),
            Document(
                page_content=(
                    "Khoản này được bãi bỏ theo quy định tại khoản 9 Điều 1 của "
                    "Thông tư số 45/2026/TT-BGDĐT."
                ),
                metadata={},
            ),
        ]
        canh_bao = hieu_luc.canh_bao_doan(self._nguon("a.pdf", "b.pdf"), tai_lieu)
        self.assertEqual(len(canh_bao), 1)
        self.assertEqual(canh_bao[0]["evidence"], 2)
        self.assertEqual(canh_bao[0]["loai"], "doan_sua_doi")
        self.assertIn("45/2026/TT-BGDĐT", canh_bao[0]["thong_bao"])


class XayDungTests(unittest.TestCase):
    def test_xay_dung_ho_so_thoi_gian_cho_ca_kho(self):
        ho_so = {
            "qd.pdf": van_ban_meta.HoSoVanBan(
                ten_file="qd.pdf", ngay_ban_hanh="2025-09-25"
            )
        }
        tinh_trang = hieu_luc.xay_dung(
            {
                "du-thao.pdf": TIEU_DE_DU_THAO,
                "qd.pdf": (
                    "QUYẾT ĐỊNH Số: 2121/QĐ-TTg\n"
                    "Quyết định này có hiệu lực kể từ ngày ký."
                ),
            },
            ho_so,
        )
        self.assertTrue(tinh_trang["du-thao.pdf"].la_du_thao)
        self.assertFalse(tinh_trang["qd.pdf"].la_du_thao)
        self.assertEqual(tinh_trang["qd.pdf"].ngay_hieu_luc, "2025-09-25")


if __name__ == "__main__":
    unittest.main()
