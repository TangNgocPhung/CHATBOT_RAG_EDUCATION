import unittest
from unittest.mock import call, patch

from fastapi.testclient import TestClient

from api import app
from rag_service import RAGService, service


class LocModelTests(unittest.TestCase):
    """Model nhúng không trò chuyện được, lọt vào danh sách chọn là hỏng phiên."""

    def test_bo_model_nhung(self):
        for ten in ("bge-m3:latest", "nomic-embed-text:latest", "mxbai-embed-large"):
            self.assertFalse(RAGService._la_model_tra_loi(ten), ten)

    def test_giu_model_tra_loi(self):
        for ten in ("qwen3.5:9b", "qwen3.5:4b", "llama3.2:3b", "qwen2.5:3b-instruct"):
            self.assertTrue(RAGService._la_model_tra_loi(ten), ten)


class DoiModelTests(unittest.TestCase):
    def setUp(self):
        self.service = RAGService()
        self.service.status.state = "ready"
        self.service.llm_model = "qwen3.5:4b"
        self.co_san = {"models": [{"name": "qwen3.5:4b"}, {"name": "llama3.2:3b"}]}

    def test_doi_sang_model_khac_dung_lai_chuoi_tra_loi(self):
        with patch.object(self.service, "danh_sach_model", return_value=self.co_san), \
             patch("rag_service.tao_llm") as tao_llm, \
             patch("rag_service.tao_rag_chain", return_value=("chain", "fmt")), \
             patch("rag_service.tao_chain_tom_tat", return_value="chain_tom_tat"):
            thanh_cong, thong_bao = self.service.doi_model("llama3.2:3b")

        self.assertTrue(thanh_cong)
        self.assertIn("llama3.2:3b", thong_bao)
        self.assertEqual(self.service.llm_model, "llama3.2:3b")
        self.assertEqual(self.service.rag_chain, "chain")
        # Tóm tắt tệp đính kèm cũng chạy LLM nên phải đổi theo, nếu không giao
        # diện báo một model mà phần tóm tắt vẫn dùng model cũ.
        self.assertEqual(self.service.chain_tom_tat, "chain_tom_tat")
        # Hai LLM cho cùng một model: một cho câu trả lời, một cho tóm tắt tệp
        # (tóm tắt cần hạn mức token dài hơn nên không dùng chung được).
        self.assertEqual(
            tao_llm.call_args_list,
            [call("llama3.2:3b"), call("llama3.2:3b", so_token_toi_da=700)],
        )

    def test_tu_choi_model_ollama_khong_co(self):
        with patch.object(self.service, "danh_sach_model", return_value=self.co_san):
            thanh_cong, thong_bao = self.service.doi_model("gpt-4o")
        self.assertFalse(thanh_cong)
        self.assertIn("chưa có model", thong_bao)
        self.assertEqual(self.service.llm_model, "qwen3.5:4b")

    def test_chon_lai_chinh_model_dang_dung_thi_khong_lam_gi(self):
        with patch("rag_service.tao_llm") as tao_llm:
            thanh_cong, _ = self.service.doi_model("qwen3.5:4b")
        self.assertTrue(thanh_cong)
        tao_llm.assert_not_called()

    def test_khong_doi_model_giua_chung_mot_cau_tra_loi(self):
        self.service._generation_lock.acquire()
        try:
            with patch.object(self.service, "danh_sach_model", return_value=self.co_san):
                thanh_cong, thong_bao = self.service.doi_model("llama3.2:3b")
        finally:
            self.service._generation_lock.release()
        self.assertFalse(thanh_cong)
        self.assertIn("đợi", thong_bao.lower())
        self.assertEqual(self.service.llm_model, "qwen3.5:4b")

    def test_chua_san_sang_thi_khong_doi(self):
        self.service.status.state = "loading"
        thanh_cong, _ = self.service.doi_model("llama3.2:3b")
        self.assertFalse(thanh_cong)


class ApiModelTests(unittest.TestCase):
    def setUp(self):
        self.client = TestClient(app)

    def test_liet_ke_model(self):
        with patch.object(
            service, "danh_sach_model",
            return_value={"models": [{"name": "llama3.2:3b"}], "current": "llama3.2:3b"},
        ):
            response = self.client.get("/api/models")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["current"], "llama3.2:3b")

    def test_doi_model_can_header_hanh_dong(self):
        response = self.client.post("/api/model", json={"model": "llama3.2:3b"})
        self.assertEqual(response.status_code, 403)

    def test_doi_model_thanh_cong(self):
        with patch.object(service, "doi_model", return_value=(True, "Đã chuyển sang llama3.2:3b")):
            service.llm_model = "llama3.2:3b"
            response = self.client.post(
                "/api/model",
                json={"model": "llama3.2:3b"},
                headers={"X-RAG-Action": "switch-model"},
            )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["model"], "llama3.2:3b")

    def test_doi_model_that_bai_tra_ve_409(self):
        with patch.object(service, "doi_model", return_value=(False, "Đang bận")):
            response = self.client.post(
                "/api/model",
                json={"model": "llama3.2:3b"},
                headers={"X-RAG-Action": "switch-model"},
            )
        self.assertEqual(response.status_code, 409)
        self.assertEqual(response.json()["detail"], "Đang bận")


if __name__ == "__main__":
    unittest.main()
