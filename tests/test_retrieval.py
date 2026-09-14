import unittest
from unittest.mock import patch

from langchain_core.documents import Document

from hybrid_retrieval import (
    rrf_fusion,
    tach_tu_tieng_viet,
    xep_hang_theo_lien_quan,
)
from rag_service import RAGService


class VietnameseRetrievalTests(unittest.TestCase):
    def test_tokenizer_normalizes_case_and_punctuation(self):
        self.assertEqual(
            tach_tu_tieng_viet("MIỄN học phí, sách giáo khoa?"),
            ["miễn", "học", "phí", "sách", "giáo", "khoa"],
        )

    def test_rrf_merges_same_chunk_from_dense_and_bm25(self):
        dense = Document(
            page_content="Nội dung gốc",
            metadata={"source_file": "nguon.pdf", "_chunk_key": "chunk-1"},
        )
        bm25 = Document(
            page_content="nguon.pdf\nNội dung gốc",
            metadata={
                "source_file": "nguon.pdf",
                "_chunk_key": "chunk-1",
                "_noi_dung_goc": "Nội dung gốc",
            },
        )
        result = rrf_fusion(("dense", [dense]), ("bm25", [bm25]))
        self.assertEqual(len(result), 1)
        self.assertEqual(result[0].page_content, "Nội dung gốc")
        self.assertEqual(result[0].metadata["_nguon"], "bm25+dense")

    def test_reranker_drops_duplicate_slide_content(self):
        trung_lap = "Mục tiêu bài học: nhận biết và vận dụng kiến thức về máy tính."
        documents = [
            Document(page_content=trung_lap, metadata={
                "source_file": "bai1.pptx", "_rrf_score": 0.02}),
            Document(page_content=trung_lap, metadata={
                "source_file": "bai2.pptx", "_rrf_score": 0.019}),
            Document(page_content="Máy tính gồm bốn thành phần cơ bản.", metadata={
                "source_file": "bai3.pptx", "_rrf_score": 0.018}),
        ]
        ket_qua = xep_hang_theo_lien_quan("máy tính gồm những gì", documents, 3)
        self.assertEqual(len(ket_qua), 2)
        self.assertEqual(
            [d.metadata["source_file"] for d in ket_qua], ["bai3.pptx", "bai1.pptx"]
        )

    def test_reranker_limits_chunks_from_one_source(self):
        documents = [
            Document(
                page_content="quy định chương trình giáo dục mầm non",
                metadata={"source_file": "a.pdf", "_rrf_score": 0.04 - i / 1000},
            )
            for i in range(3)
        ]
        documents.append(Document(
            page_content="chương trình giáo dục mầm non",
            metadata={"source_file": "b.pdf", "_rrf_score": 0.02},
        ))
        result = xep_hang_theo_lien_quan(
            "chương trình giáo dục mầm non", documents, so_ket_qua=4
        )
        self.assertLessEqual(
            sum(doc.metadata["source_file"] == "a.pdf" for doc in result), 2
        )
        self.assertIn("b.pdf", {doc.metadata["source_file"] for doc in result})

    def test_reranker_prioritizes_matching_article_title(self):
        documents = [
            Document(
                page_content="Quy định về hoạt động dạy thêm học thêm.",
                metadata={
                    "source_file": "thong-tu-day-them.pdf",
                    "article": "Điều 3. Nguyên tắc dạy thêm, học thêm",
                    "_rrf_score": 0.03,
                },
            ),
            Document(
                page_content="Quy định về hoạt động dạy thêm học thêm.",
                metadata={
                    "source_file": "thong-tu-day-them.pdf",
                    "article": "Điều 4. Các trường hợp không được tổ chức dạy thêm",
                    "_rrf_score": 0.03,
                },
            ),
        ]
        result = xep_hang_theo_lien_quan(
            "Những trường hợp nào không được tổ chức dạy thêm?", documents, 2
        )
        self.assertTrue(result[0].metadata["article"].startswith("Điều 4"))

    def test_broad_summary_can_use_more_chunks_from_one_source(self):
        documents = [
            Document(
                page_content=f"Nội dung chính phần {index}",
                metadata={
                    "source_file": "quy-che.pdf",
                    "_rrf_score": 0.04 - index / 1000,
                },
            )
            for index in range(4)
        ]
        result = xep_hang_theo_lien_quan(
            "Tóm tắt toàn bộ nội dung chính của quy chế", documents, 4
        )
        self.assertEqual(len(result), 4)


class DataQualityTests(unittest.TestCase):
    def test_detects_strong_match_in_pdf_needing_ocr(self):
        service = RAGService()
        service._no_text_sources = [
            "Nghị định quy định miễn phí sách giáo khoa giáo dục phổ thông và miễn học phí.pdf"
        ]
        matched = service._matching_no_text_source(
            "Quy định miễn học phí và miễn phí sách giáo khoa giáo dục phổ thông?"
        )
        self.assertIsNotNone(matched)

    def test_does_not_block_generic_short_question(self):
        service = RAGService()
        service._no_text_sources = ["Thông tư về giáo dục đại học.pdf"]
        self.assertIsNone(service._matching_no_text_source("Giáo dục là gì?"))

    def test_follow_up_question_uses_recent_user_context(self):
        retrieval, model_question = RAGService._conversation_inputs(
            "Còn giáo viên thì sao?",
            [
                {"role": "user", "content": "Chính sách hỗ trợ học sinh là gì?"},
                {"role": "assistant", "content": "Có các chính sách sau."},
            ],
        )
        self.assertIn("Chính sách hỗ trợ học sinh", retrieval)
        self.assertIn("Câu hỏi hiện tại: Còn giáo viên thì sao?", model_question)

    def test_independent_detailed_question_does_not_pollute_retrieval(self):
        question = (
            "Hãy trình bày đầy đủ các quy định về chuẩn chương trình đào tạo "
            "trình độ đại học và phạm vi áp dụng trong các cơ sở giáo dục"
        )
        retrieval, _ = RAGService._conversation_inputs(
            question,
            [{"role": "user", "content": "Chính sách cho học sinh mầm non?"}],
        )
        self.assertEqual(retrieval, question)

    def test_index_update_changes_state_and_starts_background_worker(self):
        service = RAGService()
        service.status.state = "ready"
        with patch("rag_service.threading.Thread") as thread:
            started, _ = service.start_index_update()
        self.assertTrue(started)
        self.assertEqual(service.status.state, "updating")
        self.assertTrue(service.status_dict()["index_progress"]["active"])
        self.assertEqual(service.status_dict()["index_progress"]["stage"], "starting")
        thread.return_value.start.assert_called_once_with()

    def test_index_progress_is_exposed_in_status(self):
        service = RAGService()
        service._bao_tien_do_chi_muc({
            "stage": "reading",
            "label": "Đang đọc và OCR tài liệu...",
            "percent": 27.5,
            "completed": 12,
            "total": 40,
            "unit": "tệp",
            "current_file": "sach.pdf",
            "detail": "OCR trang 35/120",
        })
        progress = service.status_dict()["index_progress"]
        self.assertTrue(progress["active"])
        self.assertEqual(progress["percent"], 27.5)
        self.assertEqual(progress["current_file"], "sach.pdf")

    def test_index_update_is_rejected_while_answering(self):
        service = RAGService()
        service.status.state = "ready"
        service._generation_lock.acquire()
        try:
            started, message = service.start_index_update()
        finally:
            service._generation_lock.release()
        self.assertFalse(started)
        self.assertIn("câu trả lời hiện tại", message)


if __name__ == "__main__":
    unittest.main()
