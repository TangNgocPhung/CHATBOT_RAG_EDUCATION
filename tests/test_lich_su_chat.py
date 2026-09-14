"""Lưu hội thoại phía máy chủ. Ràng buộc quan trọng nhất: hỏng phần ghi lịch sử
KHÔNG được làm hỏng câu trả lời - người dùng vẫn phải nhận được nội dung."""

import os
import sqlite3
import tempfile
import unittest
from unittest.mock import patch

import lich_su_chat


class LichSuChatTests(unittest.TestCase):
    def setUp(self):
        self.thu_muc = tempfile.TemporaryDirectory()
        duong_dan = os.path.join(self.thu_muc.name, "test_lich_su.db")
        self.patcher = patch.object(lich_su_chat, "DUONG_DAN_DB", duong_dan)
        self.patcher.start()
        lich_su_chat.dong_ket_noi()

    def tearDown(self):
        lich_su_chat.dong_ket_noi()
        self.patcher.stop()
        self.thu_muc.cleanup()

    def test_ghi_luot_dau_tien_tao_hoi_thoai_moi(self):
        ma = lich_su_chat.ghi_luot("client-1", "Dạy thêm quy định thế nào?", "Trả lời.")
        self.assertIsNotNone(ma)
        chi_tiet = lich_su_chat.chi_tiet_hoi_thoai(ma)
        self.assertEqual(len(chi_tiet["luot"]), 1)
        self.assertEqual(chi_tiet["client_id"], "client-1")

    def test_tieu_de_lay_tu_cau_hoi_dau(self):
        ma = lich_su_chat.ghi_luot("c", "Quy định về dạy thêm học thêm?", "x")
        self.assertEqual(
            lich_su_chat.chi_tiet_hoi_thoai(ma)["tieu_de"],
            "Quy định về dạy thêm học thêm?",
        )

    def test_tieu_de_dai_bi_cat_ngan(self):
        cau_dai = "Quy định " * 40
        ma = lich_su_chat.ghi_luot("c", cau_dai, "x")
        tieu_de = lich_su_chat.chi_tiet_hoi_thoai(ma)["tieu_de"]
        self.assertLessEqual(len(tieu_de), lich_su_chat.DO_DAI_TIEU_DE)
        self.assertTrue(tieu_de.endswith("…"))

    def test_luot_sau_noi_vao_dung_hoi_thoai(self):
        ma = lich_su_chat.ghi_luot("c", "Câu một?", "Đáp một.")
        lich_su_chat.ghi_luot("c", "Câu hai?", "Đáp hai.", hoi_thoai_id=ma)
        chi_tiet = lich_su_chat.chi_tiet_hoi_thoai(ma)
        self.assertEqual([l["cau_hoi"] for l in chi_tiet["luot"]], ["Câu một?", "Câu hai?"])

    def test_dung_lai_ma_do_trinh_duyet_cap(self):
        """Giao diện tự sinh mã cuộc trò chuyện trước khi gửi; máy chủ dùng lại
        chính mã đó nên hai bên khớp nhau mà không cần thêm vòng gọi."""
        ma = lich_su_chat.ghi_luot("c", "Câu?", "Đáp.", hoi_thoai_id="1757000000-a1b2")
        self.assertEqual(ma, "1757000000-a1b2")

    def test_ma_sai_dinh_dang_thi_may_chu_tu_sinh_ma_khac(self):
        for xau in ("ngắn", "có dấu cách", "ký;tự*lạ", "x" * 100, ""):
            ma = lich_su_chat.ghi_luot("c", "Câu?", "Đáp.", hoi_thoai_id=xau)
            self.assertIsNotNone(ma)
            self.assertNotEqual(ma, xau)

    def test_ma_trung_cua_nguoi_khac_thi_tach_hoi_thoai_moi(self):
        """Mã do trình duyệt cấp nên hai máy có thể trùng nhau. Khi đó không
        được ghi đè lên hội thoại của người kia."""
        ma_a = lich_su_chat.ghi_luot("client-A", "Câu của A?", "x",
                                     hoi_thoai_id="trung-ma-12345")
        ma_b = lich_su_chat.ghi_luot("client-B", "Câu của B?", "y",
                                     hoi_thoai_id="trung-ma-12345")
        self.assertEqual(ma_a, "trung-ma-12345")
        self.assertNotEqual(ma_b, ma_a)
        self.assertEqual(len(lich_su_chat.chi_tiet_hoi_thoai(ma_a)["luot"]), 1)

    def test_danh_sach_chi_tra_ve_hoi_thoai_cua_dung_client(self):
        lich_su_chat.ghi_luot("client-A", "Câu của A?", "x")
        lich_su_chat.ghi_luot("client-B", "Câu của B?", "y")
        cua_a = lich_su_chat.danh_sach_hoi_thoai("client-A")
        self.assertEqual(len(cua_a), 1)
        self.assertEqual(cua_a[0]["tieu_de"], "Câu của A?")
        self.assertEqual(cua_a[0]["so_luot"], 1)

    def test_danh_sach_xep_moi_nhat_len_dau(self):
        cu = lich_su_chat.ghi_luot("c", "Câu cũ?", "x")
        moi = lich_su_chat.ghi_luot("c", "Câu mới?", "y")
        ds = lich_su_chat.danh_sach_hoi_thoai("c")
        self.assertEqual([d["id"] for d in ds], [moi, cu])

    def test_luu_kem_nguon_va_chi_so_chat_luong(self):
        ma = lich_su_chat.ghi_luot(
            "c", "Câu?", "Đáp.",
            nguon=["a.pdf", "b.pdf"], model="qwen3.5:4b", giay=12.5,
            trich_dan_ok=False, so_lieu_ok=False, tu_choi=True, tu_cache=True,
        )
        luot = lich_su_chat.chi_tiet_hoi_thoai(ma)["luot"][0]
        self.assertEqual(luot["nguon"], ["a.pdf", "b.pdf"])
        self.assertEqual(luot["model"], "qwen3.5:4b")
        self.assertEqual(luot["giay"], 12.5)
        self.assertEqual(luot["trich_dan_ok"], 0)
        self.assertEqual(luot["tu_cache"], 1)

    def test_xoa_hoi_thoai_xoa_ca_cac_luot(self):
        ma = lich_su_chat.ghi_luot("c", "Câu?", "Đáp.")
        self.assertTrue(lich_su_chat.xoa_hoi_thoai(ma))
        self.assertIsNone(lich_su_chat.chi_tiet_hoi_thoai(ma))
        conn = lich_su_chat._connect()
        con_lai = conn.execute(
            "SELECT COUNT(*) FROM luot WHERE hoi_thoai_id = ?", (ma,)
        ).fetchone()[0]
        self.assertEqual(con_lai, 0)

    def test_xoa_hoi_thoai_khong_co_that_tra_ve_false(self):
        self.assertFalse(lich_su_chat.xoa_hoi_thoai("khong-co"))

    def test_xoa_theo_client_khong_dung_toi_client_khac(self):
        lich_su_chat.ghi_luot("client-A", "Câu A?", "x")
        lich_su_chat.ghi_luot("client-B", "Câu B?", "y")
        self.assertEqual(lich_su_chat.xoa_theo_client("client-A"), 1)
        self.assertEqual(len(lich_su_chat.danh_sach_hoi_thoai("client-B")), 1)

    def test_tat_bang_bien_moi_truong_thi_khong_ghi(self):
        with patch.dict(os.environ, {"RAG_LUU_LICH_SU": "0"}):
            self.assertIsNone(lich_su_chat.ghi_luot("c", "Câu?", "Đáp."))

    def test_loi_ghi_khong_nem_ra_ngoai(self):
        """Câu trả lời quan trọng hơn dòng log. Lỗi DB chỉ được in ra, không
        được nổi lên tới người dùng."""
        with patch.object(lich_su_chat, "_connect", side_effect=sqlite3.Error("hỏng")):
            self.assertIsNone(lich_su_chat.ghi_luot("c", "Câu?", "Đáp."))
            self.assertEqual(lich_su_chat.danh_sach_hoi_thoai("c"), [])
            self.assertIsNone(lich_su_chat.chi_tiet_hoi_thoai("bat-ky"))


class ThongKeTests(unittest.TestCase):
    def setUp(self):
        self.thu_muc = tempfile.TemporaryDirectory()
        self.patcher = patch.object(
            lich_su_chat, "DUONG_DAN_DB",
            os.path.join(self.thu_muc.name, "tk.db"),
        )
        self.patcher.start()
        lich_su_chat.dong_ket_noi()

    def tearDown(self):
        lich_su_chat.dong_ket_noi()
        self.patcher.stop()
        self.thu_muc.cleanup()

    def test_thong_ke_tinh_dung_cac_ty_le(self):
        lich_su_chat.ghi_luot("c", "Câu chậm?", "x", giay=200.0)
        lich_su_chat.ghi_luot("c", "Câu nhanh?", "y", giay=0.0, tu_cache=True)
        lich_su_chat.ghi_luot("c", "Câu lạc đề?", "z", giay=1.0, tu_choi=True)
        tk = lich_su_chat.thong_ke()
        self.assertEqual(tk["so_luot"], 3)
        self.assertEqual(tk["so_tu_choi"], 1)
        self.assertEqual(tk["so_tra_tu_cache"], 1)
        self.assertAlmostEqual(tk["ty_le_tu_choi"], 0.333, places=2)
        self.assertEqual(tk["cham_nhat"][0]["cau_hoi"], "Câu chậm?")

    def test_cau_hay_hoi_lai_chi_liet_ke_cau_lap_lai(self):
        for _ in range(3):
            lich_su_chat.ghi_luot("c", "Dạy thêm quy định thế nào?", "x")
        lich_su_chat.ghi_luot("c", "Câu hỏi chỉ một lần?", "y")
        hay_hoi = lich_su_chat.thong_ke()["cau_hay_hoi_lai"]
        self.assertEqual(len(hay_hoi), 1)
        self.assertEqual(hay_hoi[0]["so_lan"], 3)

    def test_thong_ke_kho_rong_khong_chia_cho_khong(self):
        tk = lich_su_chat.thong_ke()
        self.assertEqual(tk["so_luot"], 0)
        self.assertEqual(tk["ty_le_tu_choi"], 0.0)


if __name__ == "__main__":
    unittest.main()
