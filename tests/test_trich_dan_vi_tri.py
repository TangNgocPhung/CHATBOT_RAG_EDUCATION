"""Trích dẫn phải chỉ đúng chỗ trong tài liệu gốc: trang PDF, phần EPUB, ảnh OCR."""

import os
import tempfile
import unittest
import unittest.mock
import zipfile

from langchain_core.documents import Document

from chunking_utils import CHUNK_SIZE, chunk_theo_cau_truc
from document_loaders import (
    AnhLoader,
    EpubLoader,
    PdfLoader,
    suy_loai_tai_lieu,
    tao_loader_cho_file,
)
from rag_service import RAGService


def _trang(so_trang: int, noi_dung: str) -> Document:
    return Document(
        page_content=noi_dung,
        metadata={"source": "vb.pdf", "source_file": "vb.pdf", "so_trang": so_trang},
    )


class SoTrangQuaChunkTests(unittest.TestCase):
    def test_chunk_mang_theo_trang_no_bat_dau(self):
        docs = [
            _trang(1, "Chương I\nQUY ĐỊNH CHUNG\nĐiều 1. Phạm vi điều chỉnh\n" + "a" * 300),
            _trang(2, "Điều 2. Đối tượng áp dụng\n" + "b" * 300),
            _trang(3, "Điều 3. Giải thích từ ngữ\n" + "c" * 300),
        ]
        chunks = chunk_theo_cau_truc(docs)
        theo_dieu = {
            c.metadata["article"].split(".")[0]: c.metadata["so_trang"]
            for c in chunks if c.metadata.get("article")
        }
        self.assertEqual(theo_dieu["Điều 1"], 1)
        self.assertEqual(theo_dieu["Điều 2"], 2)
        self.assertEqual(theo_dieu["Điều 3"], 3)

    def test_khong_gan_trang_cua_trang_dau_cho_moi_chunk(self):
        """Lỗi cũ: metadata lấy từ trang đầu nên chunk nào cũng báo 'Trang 1'."""
        docs = [_trang(i, f"Điều {i}. Nội dung điều {i}\n" + "x" * 400) for i in range(1, 6)]
        chunks = chunk_theo_cau_truc(docs)
        cac_trang = {c.metadata.get("so_trang") for c in chunks}
        self.assertEqual(cac_trang, {1, 2, 3, 4, 5})

    def test_van_ban_khong_co_dieu_van_lan_theo_trang(self):
        docs = [_trang(i, f"Đoạn tự do số {i}. " + "y" * CHUNK_SIZE) for i in range(1, 4)]
        chunks = chunk_theo_cau_truc(docs)
        self.assertTrue(all(c.metadata.get("so_trang") for c in chunks))
        # Trang chỉ được tăng dần theo thứ tự đọc, không nhảy lung tung.
        cac_trang = [c.metadata["so_trang"] for c in chunks]
        self.assertEqual(cac_trang, sorted(cac_trang))

    def test_slide_khong_bi_gan_so_trang(self):
        docs = [Document(page_content="Nội dung slide", metadata={
            "source": "bai.pptx", "context_label": "Slide 3", "chunk_mode": "theo_phan_tu"})]
        self.assertIsNone(chunk_theo_cau_truc(docs)[0].metadata.get("so_trang"))


class DanhSoTrangPdfTests(unittest.TestCase):
    def test_quy_ve_dem_tu_1(self):
        """PyPDFLoader đếm trang từ 0, còn neo #page= của trình duyệt đếm từ 1."""
        tai_lieu = [
            Document(page_content="trang dau", metadata={"page": 0}),
            Document(page_content="trang hai", metadata={"page": 1}),
        ]
        ket_qua = PdfLoader._danh_so_trang(tai_lieu)
        self.assertEqual([d.metadata["so_trang"] for d in ket_qua], [1, 2])

    def test_thieu_metadata_page_thi_dem_theo_thu_tu(self):
        tai_lieu = [Document(page_content="a", metadata={}) for _ in range(3)]
        ket_qua = PdfLoader._danh_so_trang(tai_lieu)
        self.assertEqual([d.metadata["so_trang"] for d in ket_qua], [1, 2, 3])


class NeoNguonTests(unittest.TestCase):
    def test_pdf_co_neo_page(self):
        nguon = RAGService._sources([Document(page_content="x", metadata={
            "source_file": "thong-tu.pdf", "so_trang": 7})])[0]
        self.assertEqual(nguon["page"], 7)
        self.assertTrue(nguon["url"].endswith("#page=7"))

    def test_tep_dinh_kem_cung_nhay_dung_trang(self):
        nguon = RAGService._sources([Document(page_content="x", metadata={
            "source_file": "de-thi.pdf", "so_trang": 3, "tep_dinh_kem": "ma123",
            "source_url": "/api/tep/ma123/noi-dung"})])[0]
        self.assertEqual(nguon["url"], "/api/tep/ma123/noi-dung#page=3")

    def test_khong_gan_neo_cho_trang_web_ngoai(self):
        nguon = RAGService._sources([Document(page_content="x", metadata={
            "source_file": "bao-cao.pdf", "so_trang": 2,
            "source_url": "https://moet.gov.vn/bao-cao.pdf"})])[0]
        self.assertNotIn("#page=", nguon["url"])

    def test_video_van_giu_neo_thoi_gian(self):
        nguon = RAGService._sources([Document(page_content="x", metadata={
            "source_file": "bai-giang.mp4", "time_start": 95.4})])[0]
        self.assertTrue(nguon["url"].endswith("#t=95"))
        self.assertIsNone(nguon["page"])


def _tao_epub(duong_dan: str, co_container: bool = True) -> str:
    container = (
        '<?xml version="1.0"?><container version="1.0" '
        'xmlns="urn:oasis:names:tc:opendocument:xmlns:container"><rootfiles>'
        '<rootfile full-path="OEBPS/sach.opf"/></rootfiles></container>'
    )
    opf = (
        '<?xml version="1.0"?><package xmlns="http://www.idpf.org/2007/opf"><manifest>'
        '<item id="bia" href="bia.xhtml"/>'
        '<item id="c1" href="text/chuong1.xhtml"/>'
        '<item id="c2" href="text/chuong%202.xhtml"/>'
        "</manifest><spine>"
        '<itemref idref="bia"/><itemref idref="c1"/><itemref idref="c2"/>'
        "</spine></package>"
    )
    with zipfile.ZipFile(duong_dan, "w") as goi:
        if co_container:
            goi.writestr("META-INF/container.xml", container)
        goi.writestr("OEBPS/sach.opf", opf)
        goi.writestr("OEBPS/bia.xhtml", "<html><body><h1>Bìa</h1></body></html>")
        goi.writestr("OEBPS/text/chuong1.xhtml", (
            "<html><head><title>tiêu đề tab</title></head><body>"
            "<h1>Chương 1: Nguyên lý dạy học</h1><p>" + "Nội dung chương một. " * 20
            + "</p></body></html>"
        ))
        goi.writestr("OEBPS/text/chuong 2.xhtml", (
            "<html><body><h2>Chương 2: Đánh giá</h2><p>"
            + "Nội dung chương hai. " * 20 + "</p></body></html>"
        ))
    return duong_dan


class EpubTests(unittest.TestCase):
    def setUp(self):
        self.thu_muc = tempfile.TemporaryDirectory()
        self.addCleanup(self.thu_muc.cleanup)
        self.duong_dan = _tao_epub(os.path.join(self.thu_muc.name, "sach.epub"))

    def test_moi_chuong_la_mot_document_theo_thu_tu_spine(self):
        docs = EpubLoader(self.duong_dan).load()
        self.assertEqual(
            [d.metadata["context_label"] for d in docs],
            ["Chương 1: Nguyên lý dạy học", "Chương 2: Đánh giá"],
        )
        self.assertEqual(docs[0].metadata["chunk_mode"], "theo_phan_tu")

    def test_bo_qua_bia_va_khong_lan_tieu_de_tab(self):
        docs = EpubLoader(self.duong_dan).load()
        self.assertEqual(len(docs), 2)  # bìa quá ngắn nên bị loại
        self.assertNotIn("tiêu đề tab", docs[0].page_content)

    def test_giai_ma_duoc_ten_tep_co_khoang_trang(self):
        docs = EpubLoader(self.duong_dan).load()
        self.assertIn("Nội dung chương hai", docs[1].page_content)

    def test_thieu_container_van_tim_duoc_opf(self):
        duong_dan = _tao_epub(
            os.path.join(self.thu_muc.name, "khong-container.epub"), co_container=False
        )
        self.assertEqual(len(EpubLoader(duong_dan).load()), 2)

    def test_epub_rong_bao_loi_ro_rang(self):
        duong_dan = os.path.join(self.thu_muc.name, "rong.epub")
        with zipfile.ZipFile(duong_dan, "w") as goi:
            goi.writestr("mimetype", "application/epub+zip")
        with self.assertRaises(ValueError):
            EpubLoader(duong_dan).load()


class AnhTests(unittest.TestCase):
    def test_nhan_dang_nhom_anh(self):
        self.assertEqual(suy_loai_tai_lieu("bang-diem.JPG"), "anh")
        self.assertEqual(suy_loai_tai_lieu("de-thi.png"), "anh")
        self.assertIsInstance(tao_loader_cho_file("anh.jpeg"), AnhLoader)
        self.assertIsInstance(tao_loader_cho_file("sach.epub"), EpubLoader)

    def test_ocr_thanh_document_kem_nhan_vi_tri(self):
        with unittest.mock.patch("ocr_pdf.ocr_file_anh", return_value="Điều 5. Học phí"):
            docs = AnhLoader("bang.png").load()
        self.assertEqual(docs[0].page_content, "Điều 5. Học phí")
        self.assertEqual(docs[0].metadata["context_label"], "Ảnh chụp")
        self.assertEqual(docs[0].metadata["nguon_van_ban"], "ocr")

    def test_anh_khong_doc_duoc_chu_thi_khong_tao_chunk_rong(self):
        with unittest.mock.patch("ocr_pdf.ocr_file_anh", return_value="   "):
            self.assertEqual(AnhLoader("trang.png").load(), [])

    def test_tat_ocr_thi_bo_qua(self):
        self.assertEqual(AnhLoader("anh.png", cho_phep_ocr=False).load(), [])


if __name__ == "__main__":
    unittest.main()
