"""
LƯU HỘI THOẠI PHÍA MÁY CHỦ
===========================
Trước module này, lịch sử chat chỉ nằm trong localStorage của trình duyệt: đổi
máy là mất, và quan trọng hơn - không ai biết người dùng thực sự hỏi gì, câu nào
bị từ chối, câu nào trả lời chậm. Với một sản phẩm tra cứu văn bản giáo dục, đó
là nguồn dữ liệu cải tiến giá trị nhất mà đang bị vứt đi sau mỗi phiên.

Lưu bằng SQLite chứ không phải JSON: mỗi lượt hỏi là một lần ghi thêm, chạy song
song nhiều luồng (uvicorn phục vụ endpoint đồng bộ trong threadpool, còn phần
sinh câu trả lời chạy trong luồng riêng), và về sau còn phải lọc/gộp để thống
kê. Ghi đè cả tệp JSON cho mỗi lượt vừa chậm vừa dễ mất dữ liệu khi tắt giữa chừng.

LƯU Ý VỀ ĐỊNH DANH: client_id chỉ là một chuỗi ngẫu nhiên do trình duyệt sinh ra
và tự gửi lên - nó KHÔNG phải xác thực. Bất kỳ ai cũng có thể gửi client_id của
người khác. Dùng nó để gom hội thoại theo trình duyệt cho tới khi có đăng nhập
thật, đừng dùng để phân quyền.
"""

from __future__ import annotations

import json
import os
import sqlite3
import threading
import time
import uuid

DUONG_DAN_DB = os.path.abspath(os.getenv(
    "RAG_LICH_SU_DB",
    os.path.join(os.path.dirname(os.path.abspath(__file__)), "lich_su_chat.db"),
))

# Tắt được để chạy benchmark hoặc khi đơn vị chưa duyệt việc lưu nội dung hỏi.
def bat_luu_lich_su() -> bool:
    return os.getenv("RAG_LUU_LICH_SU", "1") == "1"


DO_DAI_TIEU_DE = 80
_khoa_ghi = threading.Lock()
_ket_noi: sqlite3.Connection | None = None


def _connect() -> sqlite3.Connection:
    """Một kết nối dùng chung, khóa bằng _khoa_ghi khi ghi.

    check_same_thread=False vì luồng sinh câu trả lời khác luồng phục vụ HTTP;
    SQLite tự khóa ở mức tệp, phần còn lại do _khoa_ghi lo.
    """
    global _ket_noi
    if _ket_noi is None:
        _ket_noi = sqlite3.connect(DUONG_DAN_DB, check_same_thread=False)
        _ket_noi.row_factory = sqlite3.Row
        # WAL cho phép đọc trong khi đang ghi - giao diện tải danh sách hội thoại
        # không phải đợi lượt chat đang chạy ghi xong.
        _ket_noi.execute("PRAGMA journal_mode=WAL")
        _tao_bang(_ket_noi)
    return _ket_noi


def _tao_bang(conn: sqlite3.Connection) -> None:
    conn.executescript(
        """
        CREATE TABLE IF NOT EXISTS hoi_thoai (
            id            TEXT PRIMARY KEY,
            client_id     TEXT NOT NULL,
            tieu_de       TEXT NOT NULL,
            tao_luc       REAL NOT NULL,
            cap_nhat_luc  REAL NOT NULL
        );
        CREATE TABLE IF NOT EXISTS luot (
            id            INTEGER PRIMARY KEY AUTOINCREMENT,
            hoi_thoai_id  TEXT NOT NULL REFERENCES hoi_thoai(id) ON DELETE CASCADE,
            cau_hoi       TEXT NOT NULL,
            tra_loi       TEXT NOT NULL,
            nguon         TEXT NOT NULL DEFAULT '[]',
            model         TEXT NOT NULL DEFAULT '',
            giay          REAL NOT NULL DEFAULT 0,
            trich_dan_ok  INTEGER NOT NULL DEFAULT 1,
            so_lieu_ok    INTEGER NOT NULL DEFAULT 1,
            tu_choi       INTEGER NOT NULL DEFAULT 0,
            tu_cache      INTEGER NOT NULL DEFAULT 0,
            tao_luc       REAL NOT NULL
        );
        CREATE INDEX IF NOT EXISTS idx_hoi_thoai_client
            ON hoi_thoai(client_id, cap_nhat_luc DESC);
        CREATE INDEX IF NOT EXISTS idx_luot_hoi_thoai
            ON luot(hoi_thoai_id, id);
        CREATE INDEX IF NOT EXISTS idx_luot_tao_luc ON luot(tao_luc);
        """
    )
    conn.commit()


_KY_TU_MA_HOP_LE = set(
    "abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789-_"
)


def _ma_hop_le(ma: str | None) -> str | None:
    """Mã hội thoại do trình duyệt gửi lên, nên lọc trước khi đưa vào SQL.

    Truy vấn đã dùng tham số hóa nên không có chuyện tiêm SQL, nhưng mã lạ vẫn
    làm bẩn dữ liệu và làm khóa chính khó đọc khi tra cứu về sau.
    """
    ma = (ma or "").strip()
    if not 8 <= len(ma) <= 64:
        return None
    return ma if all(c in _KY_TU_MA_HOP_LE for c in ma) else None


def _tieu_de_tu_cau_hoi(cau_hoi: str) -> str:
    gon = " ".join(cau_hoi.split())
    return gon[:DO_DAI_TIEU_DE] if len(gon) <= DO_DAI_TIEU_DE else gon[:DO_DAI_TIEU_DE - 1] + "…"


def ghi_luot(
    client_id: str,
    cau_hoi: str,
    tra_loi: str,
    *,
    hoi_thoai_id: str | None = None,
    nguon: list | None = None,
    model: str = "",
    giay: float = 0.0,
    trich_dan_ok: bool = True,
    so_lieu_ok: bool = True,
    tu_choi: bool = False,
    tu_cache: bool = False,
) -> str | None:
    """
    Ghi một lượt hỏi-đáp, tạo hội thoại mới nếu chưa có. Trả về hoi_thoai_id,
    hoặc None nếu tính năng đang tắt.

    Không bao giờ ném lỗi ra ngoài: hỏng phần ghi lịch sử thì người dùng vẫn
    phải nhận được câu trả lời.
    """
    if not bat_luu_lich_su():
        return None
    client_id = (client_id or "").strip() or "khong-ro"
    bay_gio = time.time()
    try:
        with _khoa_ghi:
            conn = _connect()
            # Giao diện đặt mã cuộc trò chuyện của nó, máy chủ dùng lại chính mã
            # đó. Nhờ vậy hai bên khớp nhau mà không cần thêm một vòng gọi chỉ
            # để hỏi "hội thoại này id bao nhiêu". Mã do trình duyệt gửi lên nên
            # phải lọc ký tự trước khi tin, và luôn tra kèm client_id để mã của
            # người này không đụng vào hội thoại của người khác.
            ma = _ma_hop_le(hoi_thoai_id)
            chu_so_huu = None
            if ma:
                dong = conn.execute(
                    "SELECT client_id FROM hoi_thoai WHERE id = ?", (ma,)
                ).fetchone()
                chu_so_huu = dong["client_id"] if dong else None
                if chu_so_huu is not None and chu_so_huu != client_id:
                    # Mã đã thuộc về trình duyệt khác: tách ra hội thoại mới thay
                    # vì ghi đè lên hội thoại của người ta.
                    ma, chu_so_huu = None, None
            if not ma:
                ma = uuid.uuid4().hex
                chu_so_huu = None
            if chu_so_huu is None:
                conn.execute(
                    "INSERT INTO hoi_thoai (id, client_id, tieu_de, tao_luc, cap_nhat_luc)"
                    " VALUES (?, ?, ?, ?, ?)",
                    (ma, client_id, _tieu_de_tu_cau_hoi(cau_hoi), bay_gio, bay_gio),
                )
            else:
                conn.execute(
                    "UPDATE hoi_thoai SET cap_nhat_luc = ? WHERE id = ?", (bay_gio, ma)
                )
            conn.execute(
                "INSERT INTO luot (hoi_thoai_id, cau_hoi, tra_loi, nguon, model, giay,"
                " trich_dan_ok, so_lieu_ok, tu_choi, tu_cache, tao_luc)"
                " VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                (
                    ma, cau_hoi, tra_loi,
                    json.dumps(nguon or [], ensure_ascii=False),
                    model, float(giay),
                    int(trich_dan_ok), int(so_lieu_ok), int(tu_choi), int(tu_cache),
                    bay_gio,
                ),
            )
            conn.commit()
            return ma
    except sqlite3.Error as exc:
        print(f"⚠️  Không ghi được lịch sử chat: {exc}")
        return None


def danh_sach_hoi_thoai(client_id: str, gioi_han: int = 50) -> list[dict]:
    try:
        conn = _connect()
        dong = conn.execute(
            "SELECT h.id, h.tieu_de, h.tao_luc, h.cap_nhat_luc,"
            "       COUNT(l.id) AS so_luot"
            "  FROM hoi_thoai h LEFT JOIN luot l ON l.hoi_thoai_id = h.id"
            " WHERE h.client_id = ?"
            " GROUP BY h.id"
            " ORDER BY h.cap_nhat_luc DESC LIMIT ?",
            (client_id, max(1, min(gioi_han, 200))),
        ).fetchall()
        return [dict(d) for d in dong]
    except sqlite3.Error as exc:
        print(f"⚠️  Không đọc được danh sách hội thoại: {exc}")
        return []


def chi_tiet_hoi_thoai(hoi_thoai_id: str) -> dict | None:
    try:
        conn = _connect()
        dau = conn.execute(
            "SELECT id, client_id, tieu_de, tao_luc, cap_nhat_luc"
            "  FROM hoi_thoai WHERE id = ?",
            (hoi_thoai_id,),
        ).fetchone()
        if dau is None:
            return None
        cac_luot = conn.execute(
            "SELECT cau_hoi, tra_loi, nguon, model, giay, trich_dan_ok, so_lieu_ok,"
            "       tu_choi, tu_cache, tao_luc"
            "  FROM luot WHERE hoi_thoai_id = ? ORDER BY id",
            (hoi_thoai_id,),
        ).fetchall()
        return {
            **dict(dau),
            "luot": [
                {**dict(l), "nguon": json.loads(l["nguon"] or "[]")}
                for l in cac_luot
            ],
        }
    except (sqlite3.Error, ValueError) as exc:
        print(f"⚠️  Không đọc được hội thoại: {exc}")
        return None


def xoa_hoi_thoai(hoi_thoai_id: str) -> bool:
    try:
        with _khoa_ghi:
            conn = _connect()
            # ON DELETE CASCADE chỉ có tác dụng khi bật foreign_keys, mà bật
            # PRAGMA đó cho kết nối dùng chung dễ gây bất ngờ ở chỗ khác - xóa
            # tay hai bảng thì rõ ràng hơn.
            conn.execute("DELETE FROM luot WHERE hoi_thoai_id = ?", (hoi_thoai_id,))
            cur = conn.execute("DELETE FROM hoi_thoai WHERE id = ?", (hoi_thoai_id,))
            conn.commit()
            return cur.rowcount > 0
    except sqlite3.Error as exc:
        print(f"⚠️  Không xóa được hội thoại: {exc}")
        return False


def xoa_theo_client(client_id: str) -> int:
    """Người dùng bấm 'xóa lịch sử' thì phải xóa cả phía máy chủ, không chỉ localStorage."""
    try:
        with _khoa_ghi:
            conn = _connect()
            conn.execute(
                "DELETE FROM luot WHERE hoi_thoai_id IN"
                " (SELECT id FROM hoi_thoai WHERE client_id = ?)",
                (client_id,),
            )
            cur = conn.execute("DELETE FROM hoi_thoai WHERE client_id = ?", (client_id,))
            conn.commit()
            return cur.rowcount
    except sqlite3.Error as exc:
        print(f"⚠️  Không xóa được lịch sử: {exc}")
        return 0


def thong_ke(so_ngay: int = 30) -> dict:
    """
    Số liệu vận hành: hỏi bao nhiêu, chậm cỡ nào, từ chối bao nhiêu, câu nào hay
    hỏi lại, tài liệu nào hay được trích. Đây là thứ để biết nên cải tiến chỗ nào.
    """
    moc = time.time() - max(1, so_ngay) * 86400
    try:
        conn = _connect()
        tong = conn.execute(
            "SELECT COUNT(*) AS so_luot,"
            "       COUNT(DISTINCT hoi_thoai_id) AS so_hoi_thoai,"
            "       AVG(giay) AS giay_tb,"
            "       SUM(tu_choi) AS so_tu_choi,"
            "       SUM(tu_cache) AS so_tu_cache,"
            "       SUM(1 - trich_dan_ok) AS so_trich_dan_loi,"
            "       SUM(1 - so_lieu_ok) AS so_so_lieu_ngo"
            "  FROM luot WHERE tao_luc >= ?",
            (moc,),
        ).fetchone()

        cham_nhat = conn.execute(
            "SELECT cau_hoi, giay FROM luot WHERE tao_luc >= ?"
            " ORDER BY giay DESC LIMIT 10",
            (moc,),
        ).fetchall()
        hay_hoi = conn.execute(
            "SELECT cau_hoi, COUNT(*) AS so_lan FROM luot WHERE tao_luc >= ?"
            " GROUP BY LOWER(TRIM(cau_hoi)) HAVING so_lan > 1"
            " ORDER BY so_lan DESC LIMIT 15",
            (moc,),
        ).fetchall()
        bi_tu_choi = conn.execute(
            "SELECT cau_hoi, COUNT(*) AS so_lan FROM luot"
            " WHERE tao_luc >= ? AND tu_choi = 1"
            " GROUP BY LOWER(TRIM(cau_hoi)) ORDER BY so_lan DESC LIMIT 15",
            (moc,),
        ).fetchall()

        so_luot = tong["so_luot"] or 0
        return {
            "so_ngay": so_ngay,
            "so_luot": so_luot,
            "so_hoi_thoai": tong["so_hoi_thoai"] or 0,
            "giay_trung_binh": round(tong["giay_tb"] or 0.0, 1),
            "so_tu_choi": tong["so_tu_choi"] or 0,
            "ty_le_tu_choi": round((tong["so_tu_choi"] or 0) / so_luot, 3) if so_luot else 0.0,
            "so_tra_tu_cache": tong["so_tu_cache"] or 0,
            "ty_le_cache": round((tong["so_tu_cache"] or 0) / so_luot, 3) if so_luot else 0.0,
            "so_trich_dan_loi": tong["so_trich_dan_loi"] or 0,
            "so_so_lieu_dang_ngo": tong["so_so_lieu_ngo"] or 0,
            "cham_nhat": [dict(d) for d in cham_nhat],
            "cau_hay_hoi_lai": [dict(d) for d in hay_hoi],
            "cau_bi_tu_choi": [dict(d) for d in bi_tu_choi],
        }
    except sqlite3.Error as exc:
        print(f"⚠️  Không tính được thống kê: {exc}")
        return {"so_ngay": so_ngay, "so_luot": 0, "loi": str(exc)}


def dong_ket_noi() -> None:
    """Dùng trong test để đóng và mở lại DB ở đường dẫn khác."""
    global _ket_noi
    with _khoa_ghi:
        if _ket_noi is not None:
            _ket_noi.close()
            _ket_noi = None
