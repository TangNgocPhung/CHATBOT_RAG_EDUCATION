import unittest

import van_ban_meta as vm


class TrichSoHieuTests(unittest.TestCase):
    def test_so_hieu_co_nam(self):
        self.assertEqual(
            vm.trich_so_hieu("Thông tư số 27/2020/TT-BGDĐT ngày 04 tháng 9"),
            ["27/2020/TT-BGDĐT"],
        )

    def test_so_hieu_khong_co_nam(self):
        self.assertEqual(vm.trich_so_hieu("Số:527/QĐ-TTg Hà Nội"), ["527/QĐ-TTg"])
        self.assertEqual(vm.trich_so_hieu("Chỉ thị 20/CT-TTg"), ["20/CT-TTg"])

    def test_khong_tach_nham_duoi_cua_so_hieu_day_du(self):
        # "2020/TT-BGDĐT" nằm trong "27/2020/TT-BGDĐT" không được tính thành
        # một số hiệu riêng mang số 2020.
        self.assertEqual(vm.trich_so_hieu("27/2020/TT-BGDĐT"), ["27/2020/TT-BGDĐT"])

    def test_chiu_duoc_nhieu_OCR(self):
        self.assertEqual(vm.trich_so_hieu("02/2022/TT-\nBGDĐT"), ["2/2022/TT-BGDĐT"])
        self.assertEqual(vm.trich_so_hieu("28/2023/NĐ- CP"), ["28/2023/NĐ-CP"])

    def test_suy_loai_van_ban(self):
        self.assertEqual(vm.suy_loai_van_ban("27/2020/TT-BGDĐT"), "Thông tư")
        self.assertEqual(vm.suy_loai_van_ban("527/QĐ-TTg"), "Quyết định")
        self.assertIsNone(vm.suy_loai_van_ban(None))


class SoHieuChinhTests(unittest.TestCase):
    TIEU_DE = (
        "CHÍNH PHỦ CỘNG HÒA XÃ HỘI CHỦ NGHĨA VIỆT NAM\n"
        "Số:311/2025/NĐ-CP Hà Nội, ngày 05 tháng 12 năm 2025\n"
        "NGHỊ ĐỊNH\n"
        "Căn cứ Luật Tổ chức Chính phủ số 63/2025/QH15;\n"
        "Căn cứ Nghị định số 37/2025/NĐ-CP ngày 26 tháng 02 năm 2025;\n"
    )

    def test_lay_dung_so_hieu_cua_chinh_van_ban(self):
        so_hieu, uoc_doan = vm.suy_so_hieu_chinh("311-cp.signed.pdf", self.TIEU_DE)
        self.assertEqual(so_hieu, "311/2025/NĐ-CP")
        self.assertFalse(uoc_doan)

    def test_khong_lay_so_hieu_tu_phan_can_cu(self):
        # Thông tư nào của Bộ GDĐT cũng "Căn cứ Nghị định 37/2025/NĐ-CP", nếu
        # quét cả phần Căn cứ thì hàng loạt văn bản bị gán chung một số hiệu.
        tieu_de = "BỘ GIÁO DỤC VÀ ĐÀO TẠO\nTHÔNG TƯ\n" + self.TIEU_DE.split("NGHỊ ĐỊNH")[1]
        so_hieu, _ = vm.suy_so_hieu_chinh("thong-tu-abc.pdf", tieu_de)
        self.assertIsNone(so_hieu)

    def test_ngay_ban_hanh_khong_lay_tu_phan_can_cu(self):
        tieu_de = vm.cat_khoi_tieu_de(self.TIEU_DE)
        self.assertEqual(vm.trich_ngay_ban_hanh(tieu_de), "2025-12-05")

    def test_ban_du_thao_chua_dien_so_thi_KHONG_doan_tu_ten_file(self):
        # Đổi ý so với bản đầu: trước đây ghép số đầu tên file vào ô trống thành
        # "39/2026/TT-BGDĐT". Bỏ hẳn, vì hai lý do đo được trên chính kho này:
        #   - Ô số bỏ trống = bản dự thảo chưa được cấp số. Điền vào là dựng lên
        #     một văn bản không tồn tại, rồi quan hệ hiệu lực bám theo nó.
        #   - Số đầu tên file không phải số hiệu mà là ID tải về của cổng thông
        #     tin: "1483-ttg.signed.pdf" là Quyết định 92/QĐ-TTg, còn
        #     "281-cp.signed.pdf" là Nghị quyết 29/NQ-CP.
        tieu_de = "BỘ GIÁO DỤC VÀ ĐÀO TẠO\nSố: /2026/TT-BGDĐT Hà Nội\nTHÔNG TƯ\n"
        so_hieu, _ = vm.suy_so_hieu_chinh("39-bgddt.pdf", tieu_de)
        self.assertIsNone(so_hieu)

    def test_khong_doan_bua_khi_khong_co_dau_hieu_nao(self):
        so_hieu, _ = vm.suy_so_hieu_chinh("tai-lieu.pdf", "Một tài liệu bất kỳ")
        self.assertIsNone(so_hieu)


class QuanHeVanBanTests(unittest.TestCase):
    def test_cau_chu_dong_tao_quan_he(self):
        thay_the, sua_doi = vm.trich_quan_he(
            "Thông tư này thay thế Thông tư số 17/2012/TT-BGDĐT ngày 16 tháng 5 năm 2012."
        )
        self.assertEqual(thay_the, ["17/2012/TT-BGDĐT"])
        self.assertEqual(sua_doi, [])

    def test_sua_doi_bo_sung_duoc_tach_rieng(self):
        thay_the, sua_doi = vm.trich_quan_he(
            "Sửa đổi, bổ sung một số điều của Nghị định số 71/2020/NĐ-CP ngày 30 tháng 6"
        )
        self.assertEqual(sua_doi, ["71/2020/NĐ-CP"])
        self.assertEqual(thay_the, [])

    def test_bo_qua_cau_bi_dong_trong_van_ban_hop_nhat(self):
        # Bản hợp nhất chú thích: "Điều này ĐƯỢC sửa đổi THEO QUY ĐỊNH TẠI ...
        # Nghị định số 311/2025/NĐ-CP". Hiểu sai chiều sẽ kết luận ngược rằng
        # Nghị định 71 sửa đổi Nghị định 311.
        thay_the, sua_doi = vm.trich_quan_he(
            "Điều này được sửa đổi theo quy định tại khoản 1 Điều 1 "
            "của Nghị định số 311/2025/NĐ-CP"
        )
        self.assertEqual((thay_the, sua_doi), ([], []))

    def test_bo_qua_khi_chu_ngu_la_van_ban_khac(self):
        thay_the, _ = vm.trich_quan_he(
            "Nghị định số 311/2025/NĐ-CP thay thế Nghị định số 71/2020/NĐ-CP"
        )
        self.assertEqual(thay_the, [])

    def test_bo_qua_dong_tu_khong_kem_so_hieu(self):
        thay_the, sua_doi = vm.trich_quan_he(
            "Việc thay thế thành viên Hội đồng trường được thực hiện theo quy định."
        )
        self.assertEqual((thay_the, sua_doi), ([], []))


class DoiChieuToanKhoTests(unittest.TestCase):
    def kho_mau(self):
        return vm.xay_dung_ho_so({
            "moi.pdf": (
                "BỘ GIÁO DỤC VÀ ĐÀO TẠO\nSố: 29/2024/TT-BGDĐT Hà Nội, "
                "ngày 30 tháng 12 năm 2024\nTHÔNG TƯ\n"
                "Căn cứ ...\nThông tư này thay thế Thông tư số 17/2012/TT-BGDĐT."
            ),
            "cu.pdf": (
                "BỘ GIÁO DỤC VÀ ĐÀO TẠO\nSố: 17/2012/TT-BGDĐT Hà Nội, "
                "ngày 16 tháng 5 năm 2012\nTHÔNG TƯ\nCăn cứ ...\nQuy định về dạy thêm."
            ),
        })

    def test_quan_he_duoc_noi_hai_chieu(self):
        ho_so = self.kho_mau()
        self.assertEqual(ho_so["cu.pdf"].bi_thay_the_boi, ["moi.pdf"])
        self.assertFalse(ho_so["cu.pdf"].con_hieu_luc)
        self.assertTrue(ho_so["moi.pdf"].con_hieu_luc)

    def test_nhan_hien_thi_gon(self):
        ho_so = self.kho_mau()
        self.assertEqual(ho_so["moi.pdf"].nhan(), "Thông tư 29/2024/TT-BGDĐT · 30/12/2024")

    def test_canh_bao_gan_dung_so_evidence(self):
        ho_so = self.kho_mau()
        canh_bao = vm.canh_bao_hieu_luc(ho_so, [
            {"evidence": 1, "name": "moi.pdf"},
            {"evidence": 2, "name": "cu.pdf"},
        ])
        self.assertEqual(len(canh_bao), 1)
        self.assertEqual(canh_bao[0]["evidence"], 2)
        self.assertEqual(canh_bao[0]["loai"], "thay_the")
        self.assertIn("29/2024/TT-BGDĐT", canh_bao[0]["thong_bao"])

    def test_khong_canh_bao_khi_moi_nguon_deu_con_hieu_luc(self):
        ho_so = self.kho_mau()
        self.assertEqual(
            vm.canh_bao_hieu_luc(ho_so, [{"evidence": 1, "name": "moi.pdf"}]), []
        )


if __name__ == "__main__":
    unittest.main()


class ChuanHoaMaTests(unittest.TestCase):
    """OCR làm mất dấu trong mã văn bản. Không khôi phục thì cùng một Nghị định
    thành hai node khác nhau trong đồ thị."""

    def test_khoi_phuc_dau_da_mat(self):
        self.assertEqual(vm.trich_so_hieu("86/2022/ND-CP"), ["86/2022/NĐ-CP"])
        self.assertEqual(vm.trich_so_hieu("32/2018/TT-BGDDT"), ["32/2018/TT-BGDĐT"])
        self.assertEqual(vm.trich_so_hieu("527/QD-TTg"), ["527/QĐ-TTg"])

    def test_hai_bien_the_ve_cung_mot_chuoi(self):
        self.assertEqual(
            vm.trich_so_hieu("37/2025/ND-CP"), vm.trich_so_hieu("37/2025/NĐ-CP")
        )

    def test_khong_dung_vao_ma_von_khong_co_dau(self):
        self.assertEqual(vm.chuan_hoa_ma("CP"), "CP")
        self.assertEqual(vm.chuan_hoa_ma("TTg"), "TTg")
        self.assertEqual(vm.chuan_hoa_ma("BTC"), "BTC")


class SoHieuLuatTests(unittest.TestCase):
    """Luật đánh số không có gạch nối nên hai mẫu kia bỏ sót hết - mà Luật lại
    là thứ được viện dẫn nhiều nhất ở phần Căn cứ."""

    def test_bat_duoc_so_hieu_luat(self):
        self.assertEqual(vm.trich_so_hieu("Luật Giáo dục số 43/2019/QH14"), ["43/2019/QH14"])
        self.assertEqual(vm.suy_loai_van_ban("43/2019/QH14"), "Luật")


class TrichCanCuTests(unittest.TestCase):
    NOI_DUNG = """BỘ GIÁO DỤC VÀ ĐÀO TẠO
Số: 27/2020/TT-BGDĐT
Căn cứ Luật Giáo dục số 43/2019/QH14;
Căn cứ Nghị định số 37/2025/NĐ-CP ngày 26 tháng 02 năm 2025;
Can cir Nghi dinh so 86/2022/ND-CP ngay 24 thang 10 nam 2022;
Điều 1. Phạm vi
Căn cứ vào kết quả đánh giá theo Thông tư 99/9999/TT-XX thì học sinh lên lớp.
"""

    def test_lay_du_cac_can_cu(self):
        self.assertEqual(
            vm.trich_can_cu(self.NOI_DUNG),
            ["43/2019/QH14", "37/2025/NĐ-CP", "86/2022/NĐ-CP"],
        )

    def test_chiu_duoc_ban_OCR_hong(self):
        # "Can cir" (mất dấu) vẫn phải nhận ra là một mệnh đề căn cứ.
        self.assertIn("86/2022/NĐ-CP", vm.trich_can_cu(self.NOI_DUNG))

    def test_dung_lai_truoc_than_bai(self):
        # "Căn cứ vào kết quả đánh giá" sau Điều 1 không phải căn cứ pháp lý.
        self.assertNotIn("99/9999/TT-XX", vm.trich_can_cu(self.NOI_DUNG))


class KhoiTieuDeTests(unittest.TestCase):
    DU_THAO = """BỘ GIÁO DỤC VÀ ĐÀO TẠO
Số:    /2025/TT-BGDĐT
Can cir Luat Giao duc so 43/2019/QH14;
"""

    def test_cat_duoc_ca_khi_OCR_hong(self):
        # Không cắt được ở "Can cir" thì số hiệu của văn bản được viện dẫn sẽ bị
        # nhận nhầm thành số hiệu của chính văn bản này.
        self.assertEqual(
            vm.cat_khoi_tieu_de("Số: 1/2025/TT-X Can cir Luat"), "Số: 1/2025/TT-X "
        )

    def test_dong_so_khong_bat_chu_so_giua_cau(self):
        # "Luật Giáo dục SỐ 43/2019/QH14" - chữ "số" ở đây không phải ô số hiệu.
        self.assertIsNone(vm.MAU_DONG_SO.search("Căn cứ Luật Giáo dục số 43/2019/QH14"))
        self.assertIsNotNone(vm.MAU_DONG_SO.search("Số: 27/2020/TT-BGDĐT"))

    def test_khong_gan_so_hieu_cua_van_ban_duoc_vien_dan(self):
        so_hieu, _ = vm.suy_so_hieu_chinh("18-bgddt.pdf", self.DU_THAO)
        self.assertIsNone(so_hieu)
