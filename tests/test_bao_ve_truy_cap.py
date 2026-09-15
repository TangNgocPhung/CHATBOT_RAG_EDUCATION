"""Lớp mật khẩu phải chặn được TRƯỚC khi mở đường hầm ra Internet.

Các test ở đây kiểm đúng một điều: khi đã đặt RAG_MAT_KHAU thì không có đường
nào vào được nếu thiếu mật khẩu đúng - kể cả endpoint ghi/xóa, kể cả trang
tĩnh, kể cả /api/status (endpoint này lộ liên kết thư mục Google Drive).
"""

import base64
import os
import unittest
from unittest.mock import patch

from fastapi.testclient import TestClient

import bao_ve_truy_cap
from api import app


MAT_KHAU = "mat-khau-thu-nghiem"


def _dau(tai_khoan: str, mat_khau: str) -> dict:
    ma = base64.b64encode(f"{tai_khoan}:{mat_khau}".encode()).decode()
    return {"Authorization": f"Basic {ma}"}


class KhongDatMatKhauTests(unittest.TestCase):
    """Chạy trên máy cá nhân: giữ nguyên nếp cũ, không bắt đăng nhập."""

    def test_khong_dat_thi_vao_duoc_binh_thuong(self):
        with patch.dict(os.environ, {"RAG_MAT_KHAU": ""}):
            with TestClient(app) as client:
                self.assertNotEqual(client.get("/api/status").status_code, 401)


class DatMatKhauTests(unittest.TestCase):
    def setUp(self):
        self.moi_truong = patch.dict(os.environ, {"RAG_MAT_KHAU": MAT_KHAU})
        self.moi_truong.start()
        self.addCleanup(self.moi_truong.stop)

    def test_khong_co_mat_khau_thi_bi_chan(self):
        with TestClient(app) as client:
            phan_hoi = client.get("/api/status")
        self.assertEqual(phan_hoi.status_code, 401)
        self.assertIn("Basic", phan_hoi.headers.get("WWW-Authenticate", ""))

    def test_dung_mat_khau_thi_vao_duoc(self):
        with TestClient(app) as client:
            phan_hoi = client.get("/api/status", headers=_dau("giaovien", MAT_KHAU))
        self.assertNotEqual(phan_hoi.status_code, 401)

    def test_sai_mat_khau_bi_chan(self):
        with TestClient(app) as client:
            phan_hoi = client.get("/api/status", headers=_dau("giaovien", "sai"))
        self.assertEqual(phan_hoi.status_code, 401)

    def test_sai_tai_khoan_bi_chan(self):
        with TestClient(app) as client:
            phan_hoi = client.get("/api/status", headers=_dau("nguoila", MAT_KHAU))
        self.assertEqual(phan_hoi.status_code, 401)

    def test_header_hong_khong_lam_sap_may_chu(self):
        with TestClient(app) as client:
            for xau in ("Basic !!!khong-phai-base64", "Basic", "Bearer abc", ""):
                phan_hoi = client.get("/api/status", headers={"Authorization": xau})
                self.assertEqual(phan_hoi.status_code, 401, xau)

    def test_endpoint_ghi_xoa_deu_bi_chan(self):
        """Đây mới là phần nguy hiểm: tải tệp vào kho, xóa lịch sử, đổi model."""
        with TestClient(app) as client:
            truong_hop = [
                client.post("/api/kho/tep?ten=x.txt", content=b"noi dung",
                            headers={"X-RAG-Action": "upload-library"}),
                client.post("/api/index/update",
                            headers={"X-RAG-Action": "update-index"}),
                client.post("/api/model", json={"model": "llama3.2:3b"}),
                client.post("/api/drive/sync"),
                client.delete("/api/hoi-thoai",
                              headers={"X-RAG-Action": "clear-history"}),
                client.delete("/api/cache", headers={"X-RAG-Action": "clear-cache"}),
                client.post("/api/chat/stream", json={"question": "xin chao"}),
            ]
        for phan_hoi in truong_hop:
            self.assertEqual(
                phan_hoi.status_code, 401,
                f"{phan_hoi.request.method} {phan_hoi.request.url.path} lọt lưới",
            )

    def test_trang_tinh_va_tep_nguon_deu_bi_chan(self):
        with TestClient(app) as client:
            for duong_dan in ("/", "/app.js", "/api/source?name=abc.pdf",
                              "/api/documents", "/api/tep"):
                self.assertEqual(
                    client.get(duong_dan).status_code, 401, duong_dan
                )


class CheDoCongKhaiTests(unittest.TestCase):
    """Mở ra Internet mà quên mật khẩu là hỏng nặng, nên phải dừng hẳn."""

    def test_cong_khai_thieu_mat_khau_thi_tu_choi_chay(self):
        with patch.dict(os.environ, {"RAG_CONG_KHAI": "1", "RAG_MAT_KHAU": ""}):
            with self.assertRaises(bao_ve_truy_cap.LoiThieuMatKhau):
                bao_ve_truy_cap.kiem_tra_cau_hinh()

    def test_cong_khai_co_mat_khau_thi_chay(self):
        with patch.dict(os.environ, {"RAG_CONG_KHAI": "1", "RAG_MAT_KHAU": MAT_KHAU}):
            bao_ve_truy_cap.kiem_tra_cau_hinh()

    def test_chay_rieng_thieu_mat_khau_van_chay_binh_thuong(self):
        with patch.dict(os.environ, {"RAG_CONG_KHAI": "0", "RAG_MAT_KHAU": ""}):
            bao_ve_truy_cap.kiem_tra_cau_hinh()


if __name__ == "__main__":
    unittest.main()
