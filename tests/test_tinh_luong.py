"""Công cụ tính lương: sai ở đây không hiện ra như một lỗi, nó hiện ra như một
con số trông rất hợp lý trong phiếu lương của giáo viên. Nên phần lớn test ở
đây đối chiếu ngược lại đúng con số in trong văn bản, chứ không chỉ kiểm tra
hàm chạy được.
"""

import unittest

import tinh_luong


class BangHeSoTests(unittest.TestCase):
    """Hai đầu mút phải khớp nguyên văn Thông tư - đó là phần duy nhất của bảng
    lương thực sự có căn cứ trong kho."""

    def test_a1_dung_dau_mut_thong_tu_04_va_31(self):
        a1 = tinh_luong.NGACH["A1"]
        self.assertEqual(a1.he_so(1), 2.34)
        self.assertEqual(a1.he_so(a1.so_bac), 4.98)

    def test_a2_2_dung_dau_mut(self):
        bang = tinh_luong.NGACH["A2.2"]
        self.assertEqual(bang.he_so(1), 4.00)
        self.assertEqual(bang.he_so(bang.so_bac), 6.38)

    def test_a2_1_dung_dau_mut(self):
        bang = tinh_luong.NGACH["A2.1"]
        self.assertEqual(bang.he_so(1), 4.40)
        self.assertEqual(bang.he_so(bang.so_bac), 6.78)

    def test_bac_ngoai_khung_thi_bao_loi(self):
        # Thà hỏng to còn hơn lặng lẽ trả về hệ số của một bậc không tồn tại.
        with self.assertRaises(ValueError):
            tinh_luong.NGACH["A1"].he_so(10)

    def test_moi_ngach_deu_buoc_deu(self):
        for ten, bang in tinh_luong.NGACH.items():
            buoc = {
                round(bang.he_so(b + 1) - bang.he_so(b), 2)
                for b in range(1, bang.so_bac)
            }
            self.assertEqual(len(buoc), 1, f"ngạch {ten} bước không đều")


class TinhTests(unittest.TestCase):
    def setUp(self):
        self.thpt3 = tinh_luong.tim_chuc_danh("thpt", "III")

    def test_gv_thpt_hang_iii_bac_1(self):
        kq = tinh_luong.tinh(tinh_luong.ThamSo(self.thpt3, bac=1))
        # 2,34 × 2.340.000 = 5.475.600; ưu đãi 40% = 2.190.240
        self.assertEqual(kq.dong[0].so_tien, 5_475_600)
        self.assertEqual(kq.dong[1].so_tien, 2_190_240)
        self.assertEqual(kq.tong_thu_nhap, 7_665_840)
        self.assertEqual(kq.khau_tru, 574_938)
        self.assertEqual(kq.thuc_linh, 7_090_902)

    def test_phu_cap_uu_dai_khong_nam_trong_nen_dong_bao_hiem(self):
        """Điều 7 khoản 1 Nghị định phụ cấp ưu đãi: khoản này "không dùng để
        tính đóng, hưởng chế độ bảo hiểm xã hội". Gộp nhầm vào nền đóng sẽ trừ
        thừa của giáo viên mỗi tháng."""
        kq = tinh_luong.tinh(tinh_luong.ThamSo(self.thpt3, bac=1))
        self.assertEqual(kq.nen_dong_bao_hiem, 5_475_600)
        self.assertLess(kq.nen_dong_bao_hiem, kq.tong_thu_nhap)

    def test_nen_uu_dai_gom_chuc_vu_va_vuot_khung(self):
        kq = tinh_luong.tinh(tinh_luong.ThamSo(
            self.thpt3, bac=9, he_so_chuc_vu=0.45, ty_le_vuot_khung=0.05,
        ))
        luong = round(4.98 * 2_340_000)
        chuc_vu = round(0.45 * 2_340_000)
        vuot_khung = round(luong * 0.05)
        uu_dai = round((luong + chuc_vu + vuot_khung) * 0.40)
        nhan = [d.so_tien for d in kq.dong]
        self.assertIn(uu_dai, nhan)

    def test_tham_nien_nha_giao_mac_dinh_khong_tinh(self):
        """Kho không có văn bản nào quy định khoản này, nên mặc định phải bỏ
        trống chứ không đoán."""
        kq = tinh_luong.tinh(tinh_luong.ThamSo(self.thpt3, bac=1))
        self.assertFalse(any("thâm niên nhà giáo" in d.nhan for d in kq.dong))

    def test_tham_nien_khai_ro_thi_tinh_kem_canh_bao(self):
        kq = tinh_luong.tinh(
            tinh_luong.ThamSo(self.thpt3, bac=1, ty_le_tham_nien=0.10)
        )
        self.assertTrue(any("thâm niên nhà giáo" in d.nhan for d in kq.dong))
        self.assertTrue(any("KHÔNG có văn bản" in c for c in kq.canh_bao))

    def test_bac_va_he_so_mau_thuan_thi_canh_bao(self):
        kq = tinh_luong.tinh(
            tinh_luong.ThamSo(self.thpt3, bac=1, he_so=3.00)
        )
        self.assertTrue(any("không phải" in c for c in kq.canh_bao))

    def test_dia_ban_dac_biet_kho_khan_nang_uu_dai_len_70(self):
        kq = tinh_luong.tinh(
            tinh_luong.ThamSo(self.thpt3, bac=1, dia_ban="dac_biet_kho_khan")
        )
        self.assertTrue(any("70%" in d.nhan for d in kq.dong))

    def test_dia_ban_khong_bao_gio_ha_muc_uu_dai(self):
        """Mầm non đã hưởng 45% ở địa bàn thường; khu vực I/II cũng 45% nên
        không được hạ xuống."""
        mn = tinh_luong.tim_chuc_danh("mam_non", "III")
        kq = tinh_luong.tinh(tinh_luong.ThamSo(mn, bac=1, dia_ban="kv1_kv2"))
        self.assertTrue(any("45%" in d.nhan for d in kq.dong))

    def test_can_cu_ngoai_kho_deu_co_canh_bao(self):
        kq = tinh_luong.tinh(tinh_luong.ThamSo(self.thpt3, bac=1))
        ngoai_kho = [c for c in kq.can_cu_da_dung if not c.trong_kho]
        self.assertTrue(ngoai_kho)
        for cc in ngoai_kho:
            self.assertTrue(
                any(cc.van_ban in c for c in kq.canh_bao),
                f"{cc.van_ban} nằm ngoài kho mà không có cảnh báo",
            )

    def test_nguon_trich_dan_chi_gom_van_ban_co_trong_kho(self):
        """Chip nguồn bấm vào phải mở được tài liệu; liệt kê văn bản không có
        trong kho sẽ tạo ra chip hỏng."""
        kq = tinh_luong.tinh(tinh_luong.ThamSo(self.thpt3, bac=1))
        for nguon in tinh_luong.nguon_trich_dan(kq):
            self.assertTrue(nguon["name"].endswith(".pdf"))
            self.assertTrue(nguon["excerpt"])

    def test_moi_chip_nguon_tro_toi_mot_tep_co_that(self):
        """Kho tự đặt lại tên tài liệu khi nạp, nên tên ghi trong hằng số có thể
        lệch với tên trên đĩa. Chip nào còn lại phải trỏ đúng tệp có thật."""
        import os

        from main import DATA_PATH

        co_tren_dia = set()
        for _, _, cac_tep in os.walk(DATA_PATH):
            co_tren_dia.update(cac_tep)

        kq = tinh_luong.tinh(tinh_luong.ThamSo(self.thpt3, bac=1))
        chip = tinh_luong.nguon_trich_dan(kq)
        self.assertTrue(chip, "không còn chip nguồn nào")
        for nguon in chip:
            self.assertIn(nguon["name"], co_tren_dia)


class NhanDienTests(unittest.TestCase):
    def test_cau_hoi_that_cua_nguoi_dung(self):
        ts = tinh_luong.nhan_dien(
            "GV THPT HẠNG 3 BẬC LƯƠNG 1 2.34 THÌ BẠN TÍNH RA TỔNG LƯƠNG "
            "CỦA TÔI LUÔN"
        )
        self.assertIsNotNone(ts)
        self.assertEqual(ts.chuc_danh.khoa, "thpt")
        self.assertEqual(ts.chuc_danh.hang, "III")
        self.assertEqual(ts.bac, 1)
        self.assertEqual(ts.he_so, 2.34)

    def test_hang_iii_khong_bi_doc_thanh_hang_i(self):
        """Lỗi kinh điển của regex chữ số La Mã: "hạng III" khớp trúng mẫu
        "hạng I" nếu thử sai thứ tự, và sai hạng là sai cả ngạch lương."""
        ts = tinh_luong.nhan_dien("tính lương giáo viên THPT hạng III bậc 2")
        self.assertEqual(ts.chuc_danh.hang, "III")
        ts = tinh_luong.nhan_dien("tính lương giáo viên THPT hạng II bậc 2")
        self.assertEqual(ts.chuc_danh.hang, "II")
        ts = tinh_luong.nhan_dien("tính lương giáo viên THPT hạng I bậc 2")
        self.assertEqual(ts.chuc_danh.hang, "I")

    def test_he_so_viet_bang_dau_phay(self):
        ts = tinh_luong.nhan_dien("lương giáo viên tiểu học hạng III hệ số 2,67")
        self.assertEqual(ts.he_so, 2.67)

    def test_he_so_cu_the_du_de_tinh_du_khong_co_chu_luong(self):
        """Người dùng hay gõ đúng phần khai chức danh rồi thôi. "hệ số 2,34"
        chỉ có một nghĩa trong kho này, nên không bắt họ phải viết thêm "tính
        lương giúp tôi" mới chịu tính."""
        ts = tinh_luong.nhan_dien("GV THPT hạng III bậc 1, hệ số 2,34")
        self.assertIsNotNone(ts)
        self.assertEqual(ts.chuc_danh.khoa, "thpt")
        self.assertEqual(ts.he_so, 2.34)

    def test_doc_duoc_dia_ban_va_cac_phu_cap(self):
        ts = tinh_luong.nhan_dien(
            "tính lương GV THPT hạng III bậc 5 ở vùng đặc biệt khó khăn, "
            "phụ cấp chức vụ 0,35, vượt khung 7%, thâm niên nhà giáo 12%"
        )
        self.assertEqual(ts.dia_ban, "dac_biet_kho_khan")
        self.assertEqual(ts.he_so_chuc_vu, 0.35)
        self.assertEqual(ts.ty_le_vuot_khung, 0.07)
        self.assertEqual(ts.ty_le_tham_nien, 0.12)

    def test_bo_qua_cau_tra_cuu_quy_dinh(self):
        """Câu hỏi về quy định phải đi đường RAG. Công cụ tính chen ngang một
        câu tra cứu còn tệ hơn là không chen."""
        for cau in [
            "Giáo viên THPT hạng III cần trình độ đào tạo như thế nào?",
            "Tiêu chuẩn thăng hạng giáo viên THPT hạng II là gì?",
            "Phụ cấp ưu đãi đối với giáo viên THPT được quy định ở đâu?",
        ]:
            self.assertIsNone(tinh_luong.nhan_dien(cau), cau)

    def test_bo_qua_cau_thieu_tham_so(self):
        # Có nói tính lương nhưng không có hạng/bậc thì không đoán bừa.
        self.assertIsNone(
            tinh_luong.nhan_dien("tính lương giáo viên THPT của tôi")
        )

    def test_bo_qua_cau_khong_lien_quan(self):
        self.assertIsNone(
            tinh_luong.nhan_dien(
                "tổng con heo và bò là 20, bò hơn heo 15, tính số con heo"
            )
        )

    def test_so_thap_phan_la_khong_bi_nuot_thanh_he_so(self):
        """Chỉ nhận số thập phân rơi đúng vào một bậc của ngạch."""
        ts = tinh_luong.nhan_dien("tính lương GV THPT hạng III bậc 1 tỉ lệ 9,99")
        self.assertIsNone(ts.he_so)
        self.assertEqual(ts.bac, 1)


class DinhDangTests(unittest.TestCase):
    def test_so_thap_phan_kieu_viet(self):
        self.assertEqual(tinh_luong.dinh_dang_so(2.34), "2,34")
        self.assertEqual(tinh_luong.dinh_dang_ty_le(0.105), "10,5%")

    def test_tien_co_dau_cham_ngan(self):
        self.assertEqual(tinh_luong.dinh_dang_tien(5_475_600), "5.475.600")

    def test_phieu_tinh_neu_ro_khong_phai_mo_hinh_sinh_ra(self):
        ket_qua = tinh_luong.tra_loi(
            "tính lương giáo viên THPT hạng III bậc 1"
        )
        self.assertIsNotNone(ket_qua)
        van_ban, nguon = ket_qua
        self.assertIn("5.475.600", van_ban)
        self.assertIn("không phải mô hình ngôn ngữ sinh ra", van_ban)
        self.assertTrue(nguon)


if __name__ == "__main__":
    unittest.main()
