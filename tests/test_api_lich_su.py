"""Các endpoint mới: lịch sử hội thoại, thống kê, xóa cache."""

import os
import tempfile
import unittest
from unittest.mock import patch

from fastapi.testclient import TestClient

import cache_ngu_nghia
import lich_su_chat
from api import app
from rag_service import service

CLIENT = {"X-RAG-Client": "trinh-duyet-test"}


def su_kien_tra_loi(tu_cache=False):
    """Chuỗi sự kiện y như stream_answer thật phát ra."""
    yield {"type": "sources", "sources": [{"name": "day-them.pdf", "evidence": 1}]}
    yield {"type": "token", "content": "Theo Thông tư [1], "}
    yield {"type": "token", "content": "không được dạy thêm học sinh tiểu học."}
    yield {
        "type": "done", "elapsed_seconds": 12.3, "citations_ok": True,
        "figures_ok": True, "tu_cache": tu_cache,
    }


class ApiLichSuTests(unittest.TestCase):
    def setUp(self):
        self.thu_muc = tempfile.TemporaryDirectory()
        self.patcher = patch.object(
            lich_su_chat, "DUONG_DAN_DB", os.path.join(self.thu_muc.name, "api.db")
        )
        self.patcher.start()
        lich_su_chat.dong_ket_noi()
        self.client = TestClient(app)
        service.status.state = "ready"

    def tearDown(self):
        lich_su_chat.dong_ket_noi()
        self.patcher.stop()
        self.thu_muc.cleanup()

    def _hoi(self, cau_hoi="Quy định về dạy thêm?", hoi_thoai_id=None, tu_cache=False):
        with patch.object(service, "stream_answer",
                          return_value=su_kien_tra_loi(tu_cache)):
            than = {"question": cau_hoi}
            if hoi_thoai_id:
                than["hoi_thoai_id"] = hoi_thoai_id
            return self.client.post("/api/chat/stream", json=than, headers=CLIENT)

    def test_moi_luot_chat_duoc_ghi_lai(self):
        self.assertEqual(self._hoi().status_code, 200)
        ds = self.client.get("/api/hoi-thoai", headers=CLIENT).json()["hoi_thoai"]
        self.assertEqual(len(ds), 1)
        self.assertEqual(ds[0]["so_luot"], 1)

    def test_luu_dung_noi_dung_va_nguon(self):
        self._hoi()
        ma = self.client.get("/api/hoi-thoai", headers=CLIENT).json()["hoi_thoai"][0]["id"]
        luot = self.client.get(f"/api/hoi-thoai/{ma}", headers=CLIENT).json()["luot"][0]
        self.assertIn("không được dạy thêm", luot["tra_loi"])
        self.assertEqual(luot["nguon"], ["day-them.pdf"])
        self.assertEqual(luot["giay"], 12.3)

    def test_cung_hoi_thoai_id_thi_gom_thanh_mot_cuoc(self):
        self._hoi("Câu một?", hoi_thoai_id="cuoc-tro-chuyen-1")
        self._hoi("Câu hai?", hoi_thoai_id="cuoc-tro-chuyen-1")
        ds = self.client.get("/api/hoi-thoai", headers=CLIENT).json()["hoi_thoai"]
        self.assertEqual(len(ds), 1)
        self.assertEqual(ds[0]["so_luot"], 2)

    def test_thieu_ma_trinh_duyet_thi_bao_loi_ro_rang(self):
        self.assertEqual(self.client.get("/api/hoi-thoai").status_code, 400)

    def test_khong_xem_duoc_hoi_thoai_cua_trinh_duyet_khac(self):
        self._hoi(hoi_thoai_id="cuoc-cua-nguoi-khac")
        khac = {"X-RAG-Client": "trinh-duyet-khac"}
        res = self.client.get("/api/hoi-thoai/cuoc-cua-nguoi-khac", headers=khac)
        self.assertEqual(res.status_code, 404)

    def test_khong_xoa_duoc_hoi_thoai_cua_trinh_duyet_khac(self):
        self._hoi(hoi_thoai_id="cuoc-can-giu-lai")
        khac = {"X-RAG-Client": "trinh-duyet-khac"}
        res = self.client.delete("/api/hoi-thoai/cuoc-can-giu-lai", headers=khac)
        self.assertEqual(res.status_code, 404)
        self.assertIsNotNone(lich_su_chat.chi_tiet_hoi_thoai("cuoc-can-giu-lai"))

    def test_xoa_mot_hoi_thoai(self):
        self._hoi(hoi_thoai_id="cuoc-se-xoa-di")
        res = self.client.delete("/api/hoi-thoai/cuoc-se-xoa-di", headers=CLIENT)
        self.assertEqual(res.status_code, 200)
        self.assertEqual(
            self.client.get("/api/hoi-thoai", headers=CLIENT).json()["hoi_thoai"], []
        )

    def test_xoa_toan_bo_lich_su_cua_minh(self):
        self._hoi("Câu một?", hoi_thoai_id="cuoc-mot-abc")
        self._hoi("Câu hai?", hoi_thoai_id="cuoc-hai-abc")
        res = self.client.delete("/api/hoi-thoai", headers=CLIENT)
        self.assertEqual(res.json()["da_xoa"], 2)
        self.assertEqual(
            self.client.get("/api/hoi-thoai", headers=CLIENT).json()["hoi_thoai"], []
        )

    def test_hoi_thoai_khong_ton_tai_tra_ve_404(self):
        res = self.client.get("/api/hoi-thoai/khong-co-that", headers=CLIENT)
        self.assertEqual(res.status_code, 404)


class ApiThongKeTests(unittest.TestCase):
    def setUp(self):
        self.thu_muc = tempfile.TemporaryDirectory()
        self.patcher = patch.object(
            lich_su_chat, "DUONG_DAN_DB", os.path.join(self.thu_muc.name, "tk.db")
        )
        self.patcher.start()
        lich_su_chat.dong_ket_noi()
        self.client = TestClient(app)

    def tearDown(self):
        lich_su_chat.dong_ket_noi()
        self.patcher.stop()
        self.thu_muc.cleanup()

    def test_thong_ke_tra_ve_ca_so_lieu_cache(self):
        lich_su_chat.ghi_luot("c", "Câu?", "Đáp.", giay=100.0)
        payload = self.client.get("/api/thong-ke").json()
        self.assertEqual(payload["so_luot"], 1)
        self.assertIn("cache", payload)
        self.assertIn("so_muc", payload["cache"])

    def test_xoa_cache_can_header_hanh_dong(self):
        self.assertEqual(self.client.delete("/api/cache").status_code, 403)

    def test_xoa_cache_voi_header_dung(self):
        with patch.object(cache_ngu_nghia.cache, "xoa_het", return_value=7):
            res = self.client.delete(
                "/api/cache", headers={"X-RAG-Action": "clear-cache"}
            )
        self.assertEqual(res.status_code, 200)
        self.assertEqual(res.json()["da_xoa"], 7)


if __name__ == "__main__":
    unittest.main()
