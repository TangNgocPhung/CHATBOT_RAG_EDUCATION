import os
import tempfile
import unittest
import unittest.mock

from langchain_core.documents import Document

import drive_sync
import kiem_tra_tra_loi
from chunking_utils import chunk_theo_cau_truc, suy_metadata
from document_loaders import BangDuLieuLoader, PdfLoader, suy_loai_tai_lieu
from hybrid_retrieval import mo_rong_truy_van, tach_tu_mo_rong, tach_tu_tieng_viet
from media_transcribe import dinh_dang_thoi_gian, doc_phu_de


class NhanDangDinhDangTests(unittest.TestCase):
    def test_phan_loai_theo_duoi_file(self):
        self.assertEqual(suy_loai_tai_lieu("bai-giang.mp4"), "video")
        self.assertEqual(suy_loai_tai_lieu("ghi-am.MP3"), "am_thanh")
        self.assertEqual(suy_loai_tai_lieu("tkb.xlsx"), "bang_du_lieu")
        self.assertEqual(suy_loai_tai_lieu("bai1.pptx"), "trinh_chieu")
        self.assertEqual(suy_loai_tai_lieu("thong-tu.pdf"), "van_ban")

    def test_metadata_mang_theo_loai_tai_lieu(self):
        goc = os.path.join("kho", "data")
        metadata = suy_metadata(os.path.join(goc, "video", "buoi1.mp4"), goc)
        self.assertEqual(metadata["loai_tai_lieu"], "video")
        self.assertEqual(metadata["loai_thu_muc"], "video")


class ChunkTheoPhanTuTests(unittest.TestCase):
    def test_moi_slide_la_mot_chunk_rieng(self):
        docs = [
            Document(page_content="Slide 1\nGiới thiệu bài học", metadata={
                "source": "bai.pptx", "context_label": "Slide 1",
                "slide": 1, "chunk_mode": "theo_phan_tu"}),
            Document(page_content="Slide 2\nLuyện tập gõ phím", metadata={
                "source": "bai.pptx", "context_label": "Slide 2",
                "slide": 2, "chunk_mode": "theo_phan_tu"}),
        ]
        chunks = chunk_theo_cau_truc(docs)
        self.assertEqual(len(chunks), 2)
        self.assertEqual(chunks[1].metadata["context_label"], "Slide 2")
        self.assertEqual(chunks[0].metadata["format_type"], "theo_phan_tu")
        self.assertNotIn("chunk_mode", chunks[0].metadata)

    def test_phan_tu_qua_dai_duoc_danh_so_phan(self):
        docs = [Document(page_content="câu dài. " * 400, metadata={
            "source": "tkb.xlsx", "context_label": "Sheet HK1",
            "chunk_mode": "theo_phan_tu"})]
        chunks = chunk_theo_cau_truc(docs)
        self.assertGreater(len(chunks), 1)
        self.assertIn("phần 1/", chunks[0].metadata["context_label"])

    def test_van_ban_thuong_van_chunk_theo_dieu(self):
        docs = [Document(
            page_content="Điều 1. Phạm vi\nNội dung một.\nĐiều 2. Đối tượng\nNội dung hai.",
            metadata={"source": "nghi-dinh.pdf"})]
        chunks = chunk_theo_cau_truc(docs)
        self.assertEqual(len(chunks), 2)
        self.assertEqual(chunks[0].metadata["format_type"], "structure_aware")
        self.assertTrue(chunks[1].metadata["article"].startswith("Điều 2"))


class PdfOcrTests(unittest.TestCase):
    """PdfLoader chỉ được dùng OCR khi PDF thật sự thiếu lớp văn bản."""

    def _gia_lap_pypdf(self, cac_trang):
        loader = unittest.mock.MagicMock()
        loader.return_value.load.return_value = [
            Document(page_content=noi_dung, metadata={"page": i})
            for i, noi_dung in enumerate(cac_trang)
        ]
        return loader

    def test_pdf_co_lop_van_ban_thi_khong_goi_ocr(self):
        day_du = ["Điều 1. Phạm vi điều chỉnh. " * 20] * 3
        with unittest.mock.patch(
            "langchain_community.document_loaders.PyPDFLoader",
            self._gia_lap_pypdf(day_du),
        ), unittest.mock.patch("ocr_pdf.doc_cache") as doc_cache:
            tai_lieu = PdfLoader("vanban.pdf").load()
        doc_cache.assert_not_called()
        self.assertEqual(len(tai_lieu), 3)

    def test_pdf_scan_dung_ban_ocr_da_cache(self):
        with unittest.mock.patch(
            "langchain_community.document_loaders.PyPDFLoader",
            self._gia_lap_pypdf(["", "", ""]),
        ), unittest.mock.patch(
            "ocr_pdf.doc_cache", return_value=["Điều 1. Nội dung trang một.", "", "Trang ba."]
        ):
            tai_lieu = PdfLoader("scan.pdf").load()
        # Trang rỗng bị bỏ, trang có chữ giữ đúng số trang gốc.
        self.assertEqual([d.metadata["page"] for d in tai_lieu], [1, 3])
        self.assertEqual(tai_lieu[0].metadata["nguon_van_ban"], "ocr")

    def test_khong_bat_ocr_thi_tra_ve_ket_qua_rong_thay_vi_loi(self):
        with unittest.mock.patch(
            "langchain_community.document_loaders.PyPDFLoader",
            self._gia_lap_pypdf(["", ""]),
        ), unittest.mock.patch("ocr_pdf.doc_cache", return_value=None):
            tai_lieu = PdfLoader("scan.pdf", cho_phep_ocr=False).load()
        self.assertEqual(len(tai_lieu), 2)


class BangDuLieuTests(unittest.TestCase):
    def test_moi_khoi_dong_deu_lap_lai_tieu_de_cot(self):
        with tempfile.TemporaryDirectory() as thu_muc:
            duong_dan = os.path.join(thu_muc, "tkb.csv")
            with open(duong_dan, "w", encoding="utf-8") as f:
                f.write("Thu,Tiet,Mon\n")
                for i in range(90):
                    f.write(f"Thu {i % 6 + 2},Tiet {i % 5 + 1},Mon {i}\n")
            docs = BangDuLieuLoader(duong_dan).load()
        self.assertGreater(len(docs), 1)
        for doc in docs:
            self.assertIn("Cột: Thu | Tiet | Mon", doc.page_content)
            self.assertEqual(doc.metadata["chunk_mode"], "theo_phan_tu")


class PhuDeTests(unittest.TestCase):
    def test_doc_srt_giu_moc_thoi_gian(self):
        with tempfile.TemporaryDirectory() as thu_muc:
            duong_dan = os.path.join(thu_muc, "bai.srt")
            with open(duong_dan, "w", encoding="utf-8") as f:
                f.write(
                    "1\n00:00:05,000 --> 00:00:08,500\nGiới thiệu bài học\n\n"
                    "2\n00:01:02,000 --> 00:01:04,000\nPhần luyện tập\n"
                )
            cac_doan = doc_phu_de(duong_dan)
        self.assertEqual(len(cac_doan), 2)
        self.assertEqual(cac_doan[0].bat_dau, 5.0)
        self.assertEqual(cac_doan[1].noi_dung, "Phần luyện tập")

    def test_nhan_thoi_gian_co_gio_khi_du_dai(self):
        self.assertEqual(dinh_dang_thoi_gian(72), "01:12")
        self.assertEqual(dinh_dang_thoi_gian(3725), "1:02:05")


class MoRongTruyVanTests(unittest.TestCase):
    def test_viet_tat_duoc_bung_thanh_cum_day_du(self):
        tokens = mo_rong_truy_van(tach_tu_tieng_viet("TKB lớp cao học"))
        self.assertIn("thời", tokens)
        self.assertIn("khóa", tokens)
        self.assertIn("biểu", tokens)

    def test_cum_day_du_duoc_them_dang_viet_tat(self):
        tokens = mo_rong_truy_van(tach_tu_tieng_viet("phân phối chương trình Tin học 5"))
        self.assertIn("ppct", tokens)

    def test_ai_viet_hoa_la_cong_nghe_con_ai_thuong_la_tu_de_hoi(self):
        cong_nghe = "Tích hợp AI vào môn Tin học lớp 5"
        self.assertIn("trí", mo_rong_truy_van(tach_tu_tieng_viet(cong_nghe), cong_nghe))
        tu_de_hoi = "Ai được miễn học phí?"
        self.assertNotIn("trí", mo_rong_truy_van(tach_tu_tieng_viet(tu_de_hoi), tu_de_hoi))

    def test_khong_lam_hong_cau_hoi_khong_co_viet_tat(self):
        goc = tach_tu_tieng_viet("điều kiện tốt nghiệp là gì")
        self.assertEqual(mo_rong_truy_van(goc)[: len(goc)], goc)


class TachTuMoRongTests(unittest.TestCase):
    """Nối cách người dùng gõ có dấu với cách đặt tên file không dấu trong kho."""

    def test_ten_file_camel_case_khop_voi_cau_hoi_co_dau(self):
        cau_hoi = set(tach_tu_mo_rong("Bài 1 môn Tin học lớp 5 gồm nội dung gì?"))
        ten_file = set(tach_tu_mo_rong("Bai1_TinHoc5.pptx"))
        self.assertTrue({"bai", "tin", "hoc"} <= cau_hoi & ten_file)

    def test_gach_duoi_la_dau_ngan_tu(self):
        self.assertIn("tim", tach_tu_mo_rong("b7_sap_xep_de_de_tim_c8.pptx"))

    def test_van_giu_dang_co_dau_de_khong_mat_thong_tin(self):
        tokens = tach_tu_mo_rong("Thời khóa biểu")
        self.assertIn("thời", tokens)
        self.assertIn("thoi", tokens)

    def test_khong_cat_giua_tu_tieng_viet(self):
        # Bẫy Unicode: dải "À-Ỹ" có xen chữ thường nên regex ngây thơ sẽ cắt
        # "học" thành "h" + "ọc".
        self.assertEqual(
            tach_tu_mo_rong("nội dung học tập"),
            ["nội", "dung", "học", "tập", "noi", "hoc", "tap"],
        )


class KiemTraTraLoiTests(unittest.TestCase):
    def tai_lieu(self):
        return [
            Document(page_content="Học viên phải hoàn thành 60 tín chỉ.", metadata={}),
            Document(page_content="Thời gian đào tạo là 24 tháng.", metadata={}),
        ]

    def test_trich_dan_vuot_so_evidence_bi_bat(self):
        ket_qua = kiem_tra_tra_loi.kiem_tra("Cần 60 tín chỉ [3].", self.tai_lieu())
        self.assertFalse(ket_qua.trich_dan_hop_le)
        self.assertEqual(ket_qua.trich_dan_ngoai_pham_vi, [3])
        self.assertIn("[3]", ket_qua.canh_bao())

    def test_so_lieu_khong_co_trong_tai_lieu_bi_bat(self):
        ket_qua = kiem_tra_tra_loi.kiem_tra("Cần 90 tín chỉ [1].", self.tai_lieu())
        self.assertFalse(ket_qua.so_lieu_co_can_cu)
        self.assertIn("90", ket_qua.so_khong_tim_thay)

    def test_cau_tra_loi_dung_thi_khong_canh_bao(self):
        ket_qua = kiem_tra_tra_loi.kiem_tra(
            "Chương trình yêu cầu 60 tín chỉ [1], đào tạo 24 tháng [2].", self.tai_lieu()
        )
        self.assertTrue(ket_qua.dat)
        self.assertEqual(ket_qua.canh_bao(), "")

    def test_dau_phan_cach_hang_nghin_khong_bi_coi_la_sai(self):
        tai_lieu = [Document(page_content="Mức thu 1200000 đồng mỗi tháng.", metadata={})]
        ket_qua = kiem_tra_tra_loi.kiem_tra("Mức thu là 1.200.000 đồng [1].", tai_lieu)
        self.assertTrue(ket_qua.so_lieu_co_can_cu)

    def test_tu_choi_khi_khong_co_chunk_nao_lien_quan(self):
        self.assertTrue(kiem_tra_tra_loi.qua_it_lien_quan([]))
        lac_de = [Document(page_content="x", metadata={"_lexical_coverage": 0.02})]
        self.assertTrue(kiem_tra_tra_loi.qua_it_lien_quan(lac_de))
        dung_chu_de = [Document(page_content="x", metadata={"_lexical_coverage": 0.4})]
        self.assertFalse(kiem_tra_tra_loi.qua_it_lien_quan(dung_chu_de))


class DriveSyncTests(unittest.TestCase):
    def test_thu_muc_drive_anh_xa_ve_kho_cuc_bo(self):
        self.assertEqual(drive_sync._ten_thu_muc_cuc_bo("File doxc", True), "docx")
        self.assertEqual(drive_sync._ten_thu_muc_cuc_bo("File pdf ", True), "pdf")
        self.assertEqual(
            drive_sync._ten_thu_muc_cuc_bo("File excel - đuôi csv, xlxx", True), "excel"
        )

    def test_thu_muc_con_giu_nguyen_ten(self):
        self.assertEqual(
            drive_sync._ten_thu_muc_cuc_bo("PPT Tin học 5 KNTT", False),
            "PPT Tin học 5 KNTT",
        )

    def test_ky_tu_cam_cua_windows_bi_thay_the(self):
        self.assertEqual(drive_sync._ten_an_toan('bao:cao/quy*1?.docx'), "bao_cao_quy_1_.docx")


if __name__ == "__main__":
    unittest.main()
