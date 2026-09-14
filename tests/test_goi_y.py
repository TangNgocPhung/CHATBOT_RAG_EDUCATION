import random
import unittest

from fastapi.testclient import TestClient

import goi_y_cau_hoi
from api import app
from rag_service import service
from van_ban_meta import HoSoVanBan


class TieuDeTuTenTepTests(unittest.TestCase):
    def test_ten_tai_tu_cong_van_ban_thanh_cau_hoi(self):
        cau_hoi = goi_y_cau_hoi.goi_y_tu_kho(
            {"Thông tư quy định về dạy thêm, học thêm.pdf": None}
        )
        self.assertEqual(
            cau_hoi,
            ["Thông tư quy định về dạy thêm, học thêm có những nội dung chính nào?"],
        )

    def test_ten_ma_hoa_bi_loai(self):
        self.assertEqual(
            goi_y_cau_hoi.goi_y_tu_kho({
                "20-bgddt.pdf": None,
                "PPCT-5.docx": None,
                "5512_BGDDT-GDTrH_462988 (1).doc": None,
                "PhanPhoi-ChuongTrinh-Tin4.docx": None,
                "QUAN 10 - NOI DUNG GDKNCDS KHOI LOP 3-4-5-2.docx": None,
            }),
            [],
        )

    def test_ten_bi_cat_ngan_thi_bo_chu_cat_do_va_ma_bam(self):
        tieu_de = goi_y_cau_hoi._lam_sach_tieu_de(
            "Phê duyệt đề án Chương trình học bổng toàn phần dành cho sinh viên "
            "xuất sắc đi đào tạo về các công nghệ ch--caa14599.pdf"
        )
        self.assertTrue(tieu_de.endswith("về các công nghệ"), tieu_de)

    def test_so_hieu_trong_ten_tep_duoc_tra_lai_dau_gach_cheo(self):
        tieu_de = goi_y_cau_hoi._lam_sach_tieu_de(
            "Sửa đổi, bổ sung một số điều của Nghị định số 86_2021_NĐ-CP.pdf"
        )
        self.assertIn("86/2021/NĐ-CP", tieu_de)

    def test_ten_qua_dai_khong_dung_lam_goi_y(self):
        dai = "Thông tư quy định " + "tiêu chuẩn và quy trình biên soạn tài liệu " * 4
        self.assertEqual(goi_y_cau_hoi.goi_y_tu_kho({f"{dai}.pdf": None}), [])


class GoiYMoDauTests(unittest.TestCase):
    def test_khong_co_kho_van_ban_van_co_goi_y_chu_de(self):
        goi_y = goi_y_cau_hoi.goi_y_mo_dau({}, 6, random.Random(1))
        self.assertEqual(len(goi_y), 6)
        self.assertEqual(len(set(goi_y)), 6)

    def test_tron_ca_goi_y_tu_kho_va_goi_y_chu_de(self):
        ho_so = {
            f"Thông tư quy định nội dung {chu} trong trường phổ thông.pdf": None
            for chu in "ABCDEFGHIJ"
        }
        goi_y = goi_y_cau_hoi.goi_y_mo_dau(ho_so, 6, random.Random(3))
        tu_kho = [cau for cau in goi_y if "trong trường phổ thông" in cau]
        self.assertEqual(len(tu_kho), 3)
        self.assertEqual(len(goi_y), 6)

    def test_so_luong_bi_chan_tren_va_chan_duoi(self):
        self.assertEqual(len(goi_y_cau_hoi.goi_y_mo_dau({}, 0)), 1)
        self.assertEqual(
            len(goi_y_cau_hoi.goi_y_mo_dau({}, 999)), goi_y_cau_hoi.SO_GOI_Y_TOI_DA
        )


class GoiYTiepTheoTests(unittest.TestCase):
    def nguon(self, **ghi_de):
        nguon = {
            "name": "Thông tư quy định về dạy thêm, học thêm.pdf",
            "van_ban": {"so_hieu": "29/2024/TT-BGDĐT", "loai": "Thông tư", "thay_the": []},
            "validity": {"code": "con_hieu_luc"},
        }
        nguon.update(ghi_de)
        return nguon

    def test_van_ban_bi_thay_the_thi_goi_y_tim_van_ban_thay_the(self):
        goi_y = goi_y_cau_hoi.goi_y_tiep_theo(
            "Dạy thêm được quy định thế nào?",
            [self.nguon(validity={"code": "bi_thay_the"})],
        )
        self.assertEqual(
            goi_y[0], "Văn bản nào đã thay thế Thông tư 29/2024/TT-BGDĐT?"
        )

    def test_dieu_duoc_trich_thanh_goi_y_hoi_sau(self):
        goi_y = goi_y_cau_hoi.goi_y_tiep_theo(
            "Dạy thêm được quy định thế nào?",
            [self.nguon(article="Điều 4. Các trường hợp không được dạy thêm")],
        )
        self.assertIn(
            "Điều 4 của Thông tư 29/2024/TT-BGDĐT quy định chi tiết những gì?", goi_y
        )

    def test_ban_du_thao_thi_goi_y_tim_ban_chinh_thuc(self):
        goi_y = goi_y_cau_hoi.goi_y_tiep_theo(
            "Chế độ dạy thêm giờ thế nào?",
            [self.nguon(validity={"code": "du_thao"})],
        )
        self.assertEqual(
            goi_y[0],
            "Đã có văn bản chính thức nào ban hành thay cho bản dự thảo "
            "Thông tư 29/2024/TT-BGDĐT chưa?",
        )

    def test_moi_van_ban_chi_gop_mot_cau_goi_y(self):
        # Một câu trả lời hay trích hai ba Điều của cùng một thông tư; cả ba chỗ
        # gợi ý đều hỏi về văn bản đó thì mất hướng nhìn sang nguồn khác.
        goi_y = goi_y_cau_hoi.goi_y_tiep_theo(
            "Dạy thêm được quy định thế nào?",
            [
                self.nguon(article="Điều 2. Giải thích từ ngữ"),
                self.nguon(article="Điều 5. Dạy thêm trong nhà trường"),
                self.nguon(
                    name="Thông tư quy định chế độ làm việc của giáo viên.pdf",
                    van_ban={"so_hieu": "5/2025/TT-BGDĐT", "loai": "Thông tư", "thay_the": []},
                    validity={"code": "du_thao"},
                ),
            ],
        )
        self.assertEqual(
            goi_y[:2],
            [
                "Điều 2 của Thông tư 29/2024/TT-BGDĐT quy định chi tiết những gì?",
                "Đã có văn bản chính thức nào ban hành thay cho bản dự thảo "
                "Thông tư 5/2025/TT-BGDĐT chưa?",
            ],
        )

    def test_khong_goi_y_lai_dung_cau_vua_hoi(self):
        cau_hoi = "Tóm tắt những nội dung chính của Thông tư 29/2024/TT-BGDĐT"
        goi_y = goi_y_cau_hoi.goi_y_tiep_theo(cau_hoi, [self.nguon()])
        self.assertNotIn(cau_hoi, goi_y)
        self.assertEqual(len(goi_y), goi_y_cau_hoi.SO_GOI_Y_TIEP)

    def test_khong_co_nguon_van_tra_goi_y_chung(self):
        goi_y = goi_y_cau_hoi.goi_y_tiep_theo("Câu hỏi gì đó", [])
        self.assertEqual(len(goi_y), goi_y_cau_hoi.SO_GOI_Y_TIEP)
        self.assertNotIn("", goi_y)

    def test_goi_y_theo_tep_dinh_kem_uu_tien_tom_tat(self):
        goi_y = goi_y_cau_hoi.goi_y_theo_tep("Tệp này nói gì?", ["bao-cao.pdf"])
        self.assertEqual(goi_y[0], "Tóm tắt tệp bao-cao.pdf")

    def test_nhieu_tep_thi_goi_y_so_sanh(self):
        goi_y = goi_y_cau_hoi.goi_y_theo_tep(
            "Hai tệp này nói gì?", ["bao-cao.pdf", "ke-hoach.docx"]
        )
        self.assertIn("So sánh nội dung giữa các tệp đã đính kèm", goi_y)


class GoiYApiTests(unittest.TestCase):
    def setUp(self):
        self.client = TestClient(app)
        self.ho_so_goc = service.ho_so_van_ban
        service.ho_so_van_ban = {
            "Thông tư quy định về dạy thêm, học thêm.pdf": HoSoVanBan(
                ten_file="Thông tư quy định về dạy thêm, học thêm.pdf",
                so_hieu="29/2024/TT-BGDĐT",
            )
        }

    def tearDown(self):
        service.ho_so_van_ban = self.ho_so_goc

    def test_tra_ve_dung_so_luong_goi_y(self):
        response = self.client.get("/api/goi-y?so_luong=4")
        self.assertEqual(response.status_code, 200)
        goi_y = response.json()["goi_y"]
        self.assertEqual(len(goi_y), 4)
        self.assertEqual(len(set(goi_y)), 4)

    def test_goi_y_co_san_khi_kho_tri_thuc_chua_nap(self):
        # Giao diện lấy gợi ý ngay lúc mở trang, trước cả khi Ollama trả lời
        # được, nên endpoint không được phụ thuộc vào trạng thái "ready".
        trang_thai_goc = service.status.state
        service.status.state = "loading"
        try:
            response = self.client.get("/api/goi-y")
        finally:
            service.status.state = trang_thai_goc
        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.json()["goi_y"])


if __name__ == "__main__":
    unittest.main()
