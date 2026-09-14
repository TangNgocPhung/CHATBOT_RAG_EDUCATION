"""
Cách ly test khỏi dữ liệu thật.

Chạy bộ test từng ghi thẳng vào lich_su_chat.db và cache_cau_tra_loi.json của
dự án - câu hỏi giả trong test lẫn vào thống kê vận hành, còn cache thì có thể
trả lại một câu trả lời giả cho người dùng thật. Chuyển hướng cả hai sang thư
mục tạm cho toàn bộ phiên chạy test.

Đặt trong conftest.py chứ không trong từng test: chỉ cần một test mới quên cách
ly là dữ liệu thật lại bị bẩn, mà kiểu quên đó không ai phát hiện ra ngay.
"""

import os
import tempfile

import pytest

import cache_ngu_nghia
import lich_su_chat


@pytest.fixture(autouse=True, scope="session")
def cach_ly_du_lieu_that():
    with tempfile.TemporaryDirectory(prefix="rag-test-") as thu_muc:
        db_that = lich_su_chat.DUONG_DAN_DB
        cache_that = cache_ngu_nghia.cache.duong_dan

        lich_su_chat.DUONG_DAN_DB = os.path.join(thu_muc, "lich_su_test.db")
        lich_su_chat.dong_ket_noi()
        cache_ngu_nghia.cache.duong_dan = os.path.join(thu_muc, "cache_test.json")
        cache_ngu_nghia.cache._muc = []
        try:
            yield
        finally:
            lich_su_chat.dong_ket_noi()
            lich_su_chat.DUONG_DAN_DB = db_that
            cache_ngu_nghia.cache.duong_dan = cache_that
