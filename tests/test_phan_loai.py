"""
Test cho tầng phân loại giáo dục và bộ lọc phạm vi truy xuất.

Phần lớn test ở đây là "không được gắn nhầm": gắn thiếu nhãn chỉ làm tài liệu
không lọc được, còn gắn nhầm nhãn thì bộ lọc trả về tài liệu sai môn mà người
dùng lại tin là đã lọc đúng - hỏng nặng hơn nhiều.
"""

import unittest

from langchain_core.documents import Document

import phan_loai_giao_duc as pl
from hybrid_retrieval import truy_hoi_hybrid


class GanNhanTests(unittest.TestCase):
    def test_ten_file_co_mon_va_lop(self):
        muc = pl.suy_phan_loai("1.CauHoiMinhHoa-Tin4.docx")
        self.assertEqual(muc.mon_hoc, ["Tin học"])
        self.assertEqual(muc.lop, [4])
        self.assertEqual(muc.cap_hoc, ["Tiểu học"])
        self.assertEqual(muc.loai_noi_dung, "de_kiem_tra")

    def test_viet_lien_va_camel_van_tach_duoc(self):
        muc = pl.suy_phan_loai("Bai1_TinHoc5.pptx")
        self.assertEqual(muc.mon_hoc, ["Tin học"])
        self.assertEqual(muc.lop, [5])

    def test_khoa_hoc_khong_bi_nham_thanh_hoa_hoc(self):
        """'khoa hoc' chứa nguyên chuỗi 'hoa hoc'; thiếu ranh giới từ là mọi bài
        Khoa học tiểu học đều chạy sang môn Hoá."""
        muc = pl.suy_phan_loai("Khoa hoc 5 bai 3.pptx")
        self.assertEqual(muc.mon_hoc, ["Khoa học"])

    def test_an_toan_giao_thong_khong_thanh_mon_toan(self):
        muc = pl.suy_phan_loai("An toan giao thong.pptx")
        self.assertEqual(muc.mon_hoc, [])

    def test_so_bai_khong_bi_hieu_thanh_so_lop(self):
        muc = pl.suy_phan_loai("KNTT Bai 2 Dong nang The nang.pptx")
        self.assertEqual(muc.lop, [])

    def test_mon_tich_hop_nuot_mon_thanh_phan(self):
        muc = pl.suy_phan_loai("Lich su va Dia li 4.pptx")
        self.assertEqual(muc.mon_hoc, ["Lịch sử và Địa lí"])

    def test_van_ban_quy_pham_nhan_ra_tu_so_hieu_trong_ten_file(self):
        for ten in ("02_2026_TT-BGDDT_691246.doc", "159-ndcp.signed.pdf",
                    "2732qdttg.signed.pdf"):
            self.assertEqual(
                pl.suy_phan_loai(ten).loai_noi_dung, "van_ban_quy_pham", ten
            )

    def test_co_qppl_tu_ho_so_thi_khong_can_ten_file(self):
        muc = pl.suy_phan_loai("bản trình ký.docx", la_qppl=True)
        self.assertEqual(muc.loai_noi_dung, "van_ban_quy_pham")

    def test_noi_dung_chi_bo_sung_truong_con_trong(self):
        """Tên file đã nói môn Tin học thì một câu 'môn Toán' trong nội dung
        không được ghi đè - văn bản nào chẳng nhắc tên môn khác một lần."""
        muc = pl.suy_phan_loai(
            "Tin hoc 5.pptx", noi_dung="Bài này liên hệ với môn Toán lớp 5."
        )
        self.assertEqual(muc.mon_hoc, ["Tin học"])

    def test_noi_dung_dien_vao_khi_ten_file_khong_noi_gi(self):
        muc = pl.suy_phan_loai(
            "2345.signed.pdf",
            noi_dung="Quy định về giáo dục trung học phổ thông và giáo dục thường xuyên.",
        )
        self.assertIn("THPT", muc.cap_hoc)
        self.assertIn("noi_dung", muc.nguon)

    def test_ten_file_viet_lien_khong_dau_cach(self):
        """"Tinhoc5_Bai15.pptx" không có ranh giới hoa/thường nào để tách; thiếu
        biến thể viết liền thì tên file đã nói rõ môn mà vẫn phải đoán theo nội
        dung - nơi bài Tin học nào cũng lấy tên môn khác ra làm ví dụ."""
        muc = pl.suy_phan_loai("Tinhoc5_Bai15.pptx")
        self.assertEqual(muc.mon_hoc, ["Tin học"])
        self.assertEqual(muc.lop, [5])

    def test_noi_dung_liet_ke_nhieu_mon_thi_khong_gan_mon_nao(self):
        """Gặp thật: bài Tin học lớp 3 lấy ví dụ 'thư mục Tiếng Việt 3, Tin học
        3, Toán 3' - gắn cả ba thì lọc môn Toán lại ra bài Tin học."""
        muc = pl.suy_phan_loai(
            "b8_lam_quen_voi_thu_muc.pptx",
            noi_dung="Có những tệp là Tiếng Việt 3, Tin học 3, Toán 3 trong thư mục gốc.",
        )
        self.assertEqual(muc.mon_hoc, [])

    def test_noi_dung_noi_dung_mot_mon_thi_van_gan(self):
        muc = pl.suy_phan_loai("bai giang.pptx", noi_dung="Chuyên đề môn Toán lớp 5.")
        self.assertEqual(muc.mon_hoc, ["Toán"])

    def test_an_toan_hoc_khong_thanh_mon_toan(self):
        """Gặp thật trên kho: slide nghề nghiệp nói 'an toàn học đường' bị xếp
        vào môn Toán vì 'an toan hoc' chứa nguyên chuỗi 'toan hoc'."""
        muc = pl.suy_phan_loai(
            "b14 thuc hien cong viec.pptx",
            noi_dung="Bảo đảm an toàn học đường cho người học nghề.",
        )
        self.assertNotIn("Toán", muc.mon_hoc)

    def test_van_ban_quy_pham_khong_gan_mon_khi_chi_nhac_thoang_qua(self):
        """Đo trên kho thật: không chắn thì thông tư hành chính chui vào bộ lọc
        môn Công nghệ, mà người dùng lại đang tin là đã lọc đúng môn."""
        for ten in ("Thông tư quy định ứng dụng công nghệ trong giáo dục đại học.pdf",
                    "Phê duyệt đề án học bổng cho các nhà khoa học.pdf"):
            self.assertEqual(pl.suy_phan_loai(ten, la_qppl=True).mon_hoc, [], ten)

    def test_van_ban_quy_pham_ban_hanh_chuong_trinh_mon_thi_van_gan(self):
        muc = pl.suy_phan_loai(
            "Thông tư ban hành chương trình môn Tin học.pdf", la_qppl=True
        )
        self.assertEqual(muc.mon_hoc, ["Tin học"])

    def test_khong_co_dau_hieu_thi_de_trong(self):
        muc = pl.suy_phan_loai("Slide thuyet trinh.pptx")
        self.assertFalse(muc.da_phan_loai)
        self.assertEqual(muc.nguon, [])


class PhamViTests(unittest.TestCase):
    def test_chuan_hoa_bo_gia_tri_la_va_ep_lop_ve_so(self):
        self.assertEqual(
            pl.chuan_hoa_pham_vi({"mon_hoc": "Tin học", "lop": ["4", "99"], "xyz": 1}),
            {"mon_hoc": ["Tin học"], "lop": [4]},
        )

    def test_mon_khong_co_that_coi_nhu_khong_loc(self):
        """Phải rơi vào nhánh 'hỏi cả kho', không phải nhánh 'không tài liệu
        nào khớp' - hai thứ này khiến người dùng hiểu hoàn toàn khác nhau."""
        self.assertEqual(pl.chuan_hoa_pham_vi({"mon_hoc": "Bùa chú"}), {})

    def test_khop_can_moi_tieu_chi_deu_trung(self):
        meta = {"mon_hoc": ["Tin học"], "lop": [4], "loai_noi_dung": "bai_giang"}
        self.assertTrue(pl.khop(meta, {"mon_hoc": ["Tin học"], "lop": [4]}))
        self.assertFalse(pl.khop(meta, {"mon_hoc": ["Tin học"], "lop": [5]}))

    def test_tai_lieu_chua_phan_loai_khong_lot_qua_bo_loc(self):
        self.assertFalse(pl.khop({"mon_hoc": [], "lop": []}, {"lop": [4]}))

    def test_mo_ta_pham_vi_doc_duoc(self):
        self.assertEqual(
            pl.mo_ta_pham_vi({"mon_hoc": ["Tin học"], "lop": [4]}),
            "môn Tin học · lớp 4",
        )
        self.assertEqual(pl.mo_ta_pham_vi(None), "")


class _KhoGia:
    """Vector store giả: chỉ cần docstore và similarity_search_with_score."""

    class _Docstore:
        def __init__(self, docs):
            self._dict = {str(i): d for i, d in enumerate(docs)}

    def __init__(self, docs):
        self.docstore = self._Docstore(docs)

    def similarity_search_with_score(self, cau_hoi, k=4):
        return [(doc, 0.1) for doc in list(self.docstore._dict.values())[:k]]


def _kho_hai_mon():
    return _KhoGia([
        Document(page_content="Bài 2: Em làm quen với thư mục trên máy tính.",
                 metadata={"source_file": "Tin hoc 4 bai 2.pptx"}),
        Document(page_content="Bài 2: Động năng và thế năng của vật.",
                 metadata={"source_file": "Vat li 10 bai 2.pptx"}),
    ])


class GanVaoChunkTests(unittest.TestCase):
    def test_nhan_duoc_chep_xuong_tung_chunk(self):
        kho = _kho_hai_mon()
        bang = pl.xay_dung_tu_vector_store(kho)
        self.assertEqual(pl.gan_vao_chunk(kho, bang), 2)
        nhan = {
            d.metadata["source_file"]: d.metadata["mon_hoc"]
            for d in kho.docstore._dict.values()
        }
        self.assertEqual(nhan["Tin hoc 4 bai 2.pptx"], ["Tin học"])
        self.assertEqual(nhan["Vat li 10 bai 2.pptx"], ["Vật lí"])

    def test_tom_tat_dem_dung_va_bo_nhan_rong(self):
        kho = _kho_hai_mon()
        tom_tat = pl.tom_tat(pl.xay_dung_tu_vector_store(kho))
        self.assertEqual(tom_tat["tong_tai_lieu"], 2)
        self.assertEqual(
            {m["gia_tri"] for m in tom_tat["mon_hoc"]}, {"Tin học", "Vật lí"}
        )
        self.assertEqual(
            {l["gia_tri"] for l in tom_tat["lop"]}, {4, 10}
        )


class LocTrongTruyHoiTests(unittest.TestCase):
    """Đúng lỗi đã mô tả trong docstring của phan_loai_giao_duc: hai bài cùng
    tên 'Bài 2' khác môn, không lọc thì trả về cả hai."""

    def setUp(self):
        self.kho = _kho_hai_mon()
        bang = pl.xay_dung_tu_vector_store(self.kho)
        pl.gan_vao_chunk(self.kho, bang)
        self.bm25 = _Bm25Gia(list(self.kho.docstore._dict.values()))

    def test_khong_loc_thi_lay_ca_hai_mon(self):
        ket_qua = truy_hoi_hybrid("bài 2 nói về gì", self.kho, self.bm25, 4)
        self.assertEqual(len(ket_qua), 2)

    def test_loc_theo_mon_chi_con_dung_mon_do(self):
        ket_qua = truy_hoi_hybrid(
            "bài 2 nói về gì", self.kho, self.bm25, 4,
            pl.bo_loc_tu_pham_vi({"mon_hoc": ["Tin học"]}),
        )
        self.assertEqual(
            [d.metadata["source_file"] for d in ket_qua], ["Tin hoc 4 bai 2.pptx"]
        )

    def test_pham_vi_khong_co_tai_lieu_thi_tra_ve_rong(self):
        ket_qua = truy_hoi_hybrid(
            "bài 2 nói về gì", self.kho, self.bm25, 4,
            pl.bo_loc_tu_pham_vi({"mon_hoc": ["Âm nhạc"]}),
        )
        self.assertEqual(ket_qua, [])


class _Bm25Gia:
    """BM25 giả chấm điểm theo số token trùng, đủ để kiểm tra nhánh lọc."""

    def __init__(self, docs):
        self.docs = docs
        self.preprocess_func = lambda s: s.lower().split()
        self.vectorizer = self

    def get_scores(self, tokens):
        diem = []
        for doc in self.docs:
            noi_dung = doc.page_content.lower()
            diem.append(float(sum(1 for t in tokens if t in noi_dung)))
        return diem


if __name__ == "__main__":
    unittest.main()
