"""
LỚP MẬT KHẨU CHO BẢN CHẠY CÔNG KHAI
===================================

Ứng dụng vốn thiết kế để chạy trên máy cá nhân nên không có đăng nhập: mọi
endpoint đều mở, kể cả tải tệp vào kho, xóa lịch sử, đổi model, bắt máy lập
chỉ mục lại. Chừng nào còn nghe ở 127.0.0.1 thì không sao. Nhưng khi đưa ra
Internet qua đường hầm thì ai có địa chỉ cũng gọi được, nên phải chặn trước.

Dùng HTTP Basic: trình duyệt tự hiện hộp đăng nhập, giao diện không phải sửa
một dòng nào. Đường hầm Cloudflare đã là HTTPS nên mật khẩu không đi qua mạng
ở dạng trần.

KHÔNG chừa đường dẫn nào khỏi kiểm tra, kể cả /api/status: endpoint đó trả về
cả liên kết thư mục Google Drive và số liệu kho tài liệu. Đổi lại, khi đã đặt
mật khẩu thì run_ui.py không tự mở được trình duyệt (nó dò /api/status để biết
máy chủ đã sẵn sàng) - tự mở tab bằng tay, đây là cái giá rẻ.

Bật bằng cách đặt RAG_MAT_KHAU (xem mat_khau.mau.bat). Đặt thêm
RAG_CONG_KHAI=1 thì ứng dụng TỪ CHỐI khởi động nếu thiếu mật khẩu - để không
bao giờ có chuyện mở đường hầm ra mà quên khóa cửa.
"""

from __future__ import annotations

import base64
import binascii
import hmac
import os

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.responses import PlainTextResponse


def mat_khau_cau_hinh() -> str:
    return os.getenv("RAG_MAT_KHAU", "").strip()


def tai_khoan_cau_hinh() -> str:
    return os.getenv("RAG_TAI_KHOAN", "giaovien").strip() or "giaovien"


def dang_chay_cong_khai() -> bool:
    return os.getenv("RAG_CONG_KHAI", "0") == "1"


class LoiThieuMatKhau(RuntimeError):
    """Bật chế độ công khai mà quên đặt mật khẩu - dừng hẳn, không chạy tiếp."""


def kiem_tra_cau_hinh() -> None:
    """Gọi lúc khởi động. Thà không chạy còn hơn chạy mà mở toang."""
    if dang_chay_cong_khai() and not mat_khau_cau_hinh():
        raise LoiThieuMatKhau(
            "RAG_CONG_KHAI=1 nhưng chưa đặt RAG_MAT_KHAU. Ứng dụng sẽ mở ra "
            "Internet mà không có lớp bảo vệ nào, nên dừng tại đây. "
            "Xem mat_khau.mau.bat để đặt mật khẩu."
        )


def _dung_mat_khau(header_uy_quyen: str | None) -> bool:
    """So sánh bằng compare_digest để thời gian trả lời không rò rỉ mật khẩu."""
    if not header_uy_quyen or not header_uy_quyen.lower().startswith("basic "):
        return False
    try:
        giai_ma = base64.b64decode(header_uy_quyen[6:].strip()).decode("utf-8")
    except (binascii.Error, UnicodeDecodeError, ValueError):
        return False
    tai_khoan, _, mat_khau = giai_ma.partition(":")
    # So cả hai vế kể cả khi vế đầu đã sai, để không lộ vế nào sai qua thời gian.
    khop_tai_khoan = hmac.compare_digest(tai_khoan, tai_khoan_cau_hinh())
    khop_mat_khau = hmac.compare_digest(mat_khau, mat_khau_cau_hinh())
    return khop_tai_khoan and khop_mat_khau


class BaoVeBangMatKhau(BaseHTTPMiddleware):
    """Chặn mọi request chưa đăng nhập khi RAG_MAT_KHAU được đặt."""

    async def dispatch(self, request, call_next):
        if not mat_khau_cau_hinh():
            return await call_next(request)
        if _dung_mat_khau(request.headers.get("authorization")):
            return await call_next(request)
        return PlainTextResponse(
            "Cần đăng nhập để dùng trợ lý này.",
            status_code=401,
            headers={"WWW-Authenticate": 'Basic realm="Chatbot RAG Giao duc"'},
        )


def gan_vao(app) -> None:
    app.add_middleware(BaoVeBangMatKhau)


__all__ = [
    "BaoVeBangMatKhau",
    "LoiThieuMatKhau",
    "dang_chay_cong_khai",
    "gan_vao",
    "kiem_tra_cau_hinh",
    "mat_khau_cau_hinh",
    "tai_khoan_cau_hinh",
]
