"""
Test cho bộ chỉ số IR/QA. Toàn bộ là số học trên thứ hạng nên không cần chỉ
mục, không cần Ollama - chạy trong vài mili giây.

Giá trị kỳ vọng đều tính tay trong comment: một công thức IR cài sai vẫn chạy
trơn tru và vẫn in ra số đẹp, chỉ có đối chiếu với giá trị tính tay mới bắt được.
"""

import math
import unittest

import chi_so_ir


class ThuHangTests(unittest.TestCase):
    def test_khu_trung_tai_lieu_giu_hang_dau_tien(self):
        # Hai chunk đầu cùng một file: file thứ hai vẫn phải là hạng 2, không
        # phải hạng 3.
        self.assertEqual(
            chi_so_ir.xep_hang_tai_lieu(["a.pdf", "a.pdf", "b.pdf", "a.pdf"]),
            ["a.pdf", "b.pdf"],
        )

    def test_khop_nhan_la_mot_phan_ten_file_khong_phan_biet_hoa_thuong(self):
        self.assertTrue(chi_so_ir.khop_nhan(
            "Thông tư quy định về DẠY THÊM học thêm.pdf", "dạy thêm"))
        self.assertFalse(chi_so_ir.khop_nhan("Luật Giáo Dục.pdf", "dạy thêm"))

    def test_moi_nhan_chi_duoc_tinh_mot_lan(self):
        # Ba tài liệu cùng khớp một nhãn vẫn chỉ là một yêu cầu được đáp ứng.
        thu_hang = chi_so_ir.thu_hang_lien_quan(
            ["a-dạy thêm.pdf", "b-dạy thêm.pdf", "c.pdf"], ["dạy thêm"])
        self.assertEqual(thu_hang, [1])

    def test_hai_nhan_cho_hai_thu_hang(self):
        thu_hang = chi_so_ir.thu_hang_lien_quan(
            ["x.pdf", "Luật Giáo Dục.pdf", "y.pdf", "Điều lệ trường.pdf"],
            ["Luật Giáo Dục", "Điều lệ"],
        )
        self.assertEqual(thu_hang, [2, 4])


class ChiSoTests(unittest.TestCase):
    def test_mrr_lay_hang_dau_tien(self):
        self.assertEqual(chi_so_ir.reciprocal_rank([3, 5]), 1 / 3)
        self.assertEqual(chi_so_ir.reciprocal_rank([1]), 1.0)
        self.assertEqual(chi_so_ir.reciprocal_rank([]), 0.0)

    def test_mrr_cat_o_k_thi_hang_sau_k_tinh_la_truot(self):
        self.assertEqual(chi_so_ir.reciprocal_rank([12], k=10), 0.0)
        self.assertEqual(chi_so_ir.reciprocal_rank([12], k=None), 1 / 12)

    def test_hit_at_k(self):
        self.assertEqual(chi_so_ir.hit_at_k([4], 3), 0.0)
        self.assertEqual(chi_so_ir.hit_at_k([4], 4), 1.0)

    def test_recall_va_precision(self):
        # 2 tài liệu đúng trong kho, top-5 tìm được 1 trong 2.
        self.assertEqual(chi_so_ir.recall_at_k([2, 9], 2, 5), 0.5)
        self.assertEqual(chi_so_ir.precision_at_k([2, 9], 5), 0.2)

    def test_average_precision_phat_tai_lieu_dung_thu_hai_ra_muon(self):
        # AP = (1/1 + 2/5) / 2 = 0.7 - tìm được cả hai nhưng cái sau ở hạng 5.
        self.assertAlmostEqual(
            chi_so_ir.average_precision([1, 5], so_lien_quan=2, k=10), 0.7)
        # Cả hai ở đầu danh sách thì AP = 1.
        self.assertAlmostEqual(
            chi_so_ir.average_precision([1, 2], so_lien_quan=2, k=10), 1.0)

    def test_ndcg_hang_1_la_tuyet_doi_va_giam_dan_theo_log(self):
        self.assertEqual(chi_so_ir.ndcg_at_k([1], 1, 10), 1.0)
        # DCG = 1/log2(4) = 0.5, IDCG = 1/log2(2) = 1 → nDCG = 0.5.
        self.assertAlmostEqual(chi_so_ir.ndcg_at_k([3], 1, 10), 0.5)
        self.assertEqual(chi_so_ir.ndcg_at_k([11], 1, 10), 0.0)

    def test_ndcg_phat_nhe_hon_mrr_o_hang_sau(self):
        # Ở hạng 4: MRR cho 0.25 còn nDCG cho 1/log2(5) ≈ 0.43. Đây chính là
        # lý do báo cáo cả hai - MRR khắt khe với vị trí đầu hơn hẳn.
        self.assertAlmostEqual(chi_so_ir.reciprocal_rank([4]), 0.25)
        self.assertAlmostEqual(chi_so_ir.ndcg_at_k([4], 1, 10), 1 / math.log2(5))


class TongHopTests(unittest.TestCase):
    def _luot(self, *thu_hang_moi_cau):
        return [
            chi_so_ir.LuotTruyHoi(cau_hoi=f"c{i}", nhom="nhom_a",
                                  thu_hang=list(t), so_lien_quan=1, so_ung_vien=10)
            for i, t in enumerate(thu_hang_moi_cau)
        ]

    def test_mrr_trung_binh_tren_ca_bo(self):
        # 1/1, 1/2, 0 → MRR = 0.5
        tt = chi_so_ir.tong_hop(self._luot([1], [2], []))
        self.assertAlmostEqual(tt["mrr"], 0.5)
        self.assertEqual(tt["so_cau"], 3)
        self.assertEqual(tt["so_cau_truot"], 1)
        self.assertAlmostEqual(tt["hit@1"], 1 / 3)
        self.assertAlmostEqual(tt["hit@3"], 2 / 3)
        self.assertAlmostEqual(tt["hang_trung_binh_khi_trung"], 1.5)

    def test_bo_rong_khong_no(self):
        self.assertEqual(chi_so_ir.tong_hop([]), {"so_cau": 0})

    def test_khoang_tin_cay_bao_quanh_trung_binh_va_lap_lai_duoc(self):
        gia_tri = [1.0, 0.5, 0.0, 1.0, 0.25, 0.0, 1.0, 0.33]
        thap, cao = chi_so_ir.khoang_tin_cay_bootstrap(gia_tri, so_lan=500)
        trung_binh = sum(gia_tri) / len(gia_tri)
        self.assertLessEqual(thap, trung_binh)
        self.assertGreaterEqual(cao, trung_binh)
        # Hạt giống cố định: hai lần chạy phải ra đúng một khoảng, nếu không
        # thì hai lần đo cùng một cấu hình lại báo hai kết luận khác nhau.
        self.assertEqual(
            (thap, cao), chi_so_ir.khoang_tin_cay_bootstrap(gia_tri, so_lan=500))

    def test_phan_bo_thu_hang_dem_du_moi_cau(self):
        luot = self._luot([1], [1], [3], [15], [])
        phan_bo = chi_so_ir.phan_bo_thu_hang(luot, k_toi_da=10)
        self.assertEqual(phan_bo["1"], 2)
        self.assertEqual(phan_bo["3"], 1)
        self.assertEqual(phan_bo[">10"], 1)
        self.assertEqual(phan_bo["truot"], 1)
        self.assertEqual(sum(phan_bo.values()), len(luot))

    def test_bang_markdown_co_dong_tong_va_dong_moi_nhom(self):
        luot = self._luot([1], [2])
        bang = chi_so_ir.bang_markdown(
            chi_so_ir.tong_hop(luot), chi_so_ir.tong_hop_theo_nhom(luot))
        self.assertIn("| nhom_a |", bang)
        self.assertIn("**Toàn bộ**", bang)
        self.assertIn("Hit@1", bang)


if __name__ == "__main__":
    unittest.main()
