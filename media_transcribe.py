"""
PHIÊN ÂM VIDEO/ÂM THANH BẰNG FASTER-WHISPER (chạy offline trên máy)
===================================================================
Mỗi file media được phiên âm MỘT LẦN rồi lưu cache JSON theo hash nội dung,
nên build lại chỉ mục hay thêm tài liệu khác không phải phiên âm lại.

Kết quả trả về là danh sách đoạn (segment) kèm mốc thời gian, để chunk giữ
được "phút thứ mấy" - nhờ vậy câu trả lời trích dẫn được đúng thời điểm trong
video thay vì chỉ nói tên file.

Cài đặt (một lần):
    pip install faster-whisper
Không cần ffmpeg riêng: faster-whisper giải mã âm thanh bằng PyAV đi kèm.
"""

from __future__ import annotations

import json
import os
import time
from dataclasses import dataclass, asdict

THU_MUC_DU_AN = os.path.dirname(os.path.abspath(__file__))
THU_MUC_CACHE = os.path.abspath(os.getenv(
    "RAG_TRANSCRIPT_CACHE", os.path.join(THU_MUC_DU_AN, "transcripts")
))

# tiny/base/small/medium/large-v3. "small" là cân bằng tốt nhất cho CPU phổ thông.
MODEL_MAC_DINH = os.getenv("RAG_WHISPER_MODEL", "small")
NGON_NGU_MAC_DINH = os.getenv("RAG_WHISPER_LANGUAGE", "vi")

DINH_DANG_MEDIA = {
    ".mp4", ".mkv", ".mov", ".avi", ".webm", ".wmv", ".flv",
    ".mp3", ".wav", ".m4a", ".aac", ".flac", ".ogg", ".wma",
}

_model_dang_dung = None
_ten_model_dang_dung = None


class ThieuFasterWhisper(RuntimeError):
    """faster-whisper chưa được cài - thông báo rõ cách khắc phục."""


@dataclass
class DoanPhienAm:
    bat_dau: float
    ket_thuc: float
    noi_dung: str


def la_file_media(duong_dan: str) -> bool:
    return os.path.splitext(duong_dan)[1].lower() in DINH_DANG_MEDIA


def dinh_dang_thoi_gian(giay: float) -> str:
    """12.5 -> '00:12'; 3725 -> '1:02:05' (dùng cho nhãn trích dẫn)."""
    giay = max(0, int(giay))
    gio, con_lai = divmod(giay, 3600)
    phut, giay_le = divmod(con_lai, 60)
    if gio:
        return f"{gio}:{phut:02d}:{giay_le:02d}"
    return f"{phut:02d}:{giay_le:02d}"


def _duong_dan_cache(duong_dan_media: str, ten_model: str) -> str:
    """Cache theo hash nội dung: đổi tên/di chuyển file vẫn dùng lại được."""
    from chunking_utils import tinh_hash_file

    os.makedirs(THU_MUC_CACHE, exist_ok=True)
    ma_hash = tinh_hash_file(duong_dan_media)[:16]
    ten_an_toan = ten_model.replace("/", "-").replace("\\", "-")
    return os.path.join(THU_MUC_CACHE, f"{ma_hash}--{ten_an_toan}.json")


def doc_cache(duong_dan_media: str, ten_model: str | None = None):
    """Trả về danh sách DoanPhienAm đã phiên âm trước đó, hoặc None."""
    ten_model = ten_model or MODEL_MAC_DINH
    duong_dan = _duong_dan_cache(duong_dan_media, ten_model)
    if not os.path.exists(duong_dan):
        return None
    try:
        with open(duong_dan, encoding="utf-8") as f:
            du_lieu = json.load(f)
        return [DoanPhienAm(**doan) for doan in du_lieu.get("doan", [])]
    except (OSError, ValueError, TypeError):
        return None


def _tai_model(ten_model: str):
    global _model_dang_dung, _ten_model_dang_dung
    if _model_dang_dung is not None and _ten_model_dang_dung == ten_model:
        return _model_dang_dung
    try:
        from faster_whisper import WhisperModel
    except ImportError as exc:
        raise ThieuFasterWhisper(
            "Chưa cài faster-whisper nên không phiên âm được video. "
            "Chạy: pip install faster-whisper"
        ) from exc

    _model_dang_dung = WhisperModel(
        ten_model,
        device=os.getenv("RAG_WHISPER_DEVICE", "cpu"),
        compute_type=os.getenv("RAG_WHISPER_COMPUTE", "int8"),
        cpu_threads=int(os.getenv("RAG_WHISPER_THREADS", "0")) or 0,
    )
    _ten_model_dang_dung = ten_model
    return _model_dang_dung


def phien_am(
    duong_dan_media: str,
    ten_model: str | None = None,
    bat_buoc_lam_lai: bool = False,
    bao_tien_do=None,
) -> list[DoanPhienAm]:
    """
    Phiên âm một file media, ưu tiên đọc cache.
    bao_tien_do: hàm nhận (giay_da_xu_ly, tong_giay) để in tiến độ nếu cần.
    """
    ten_model = ten_model or MODEL_MAC_DINH
    if not bat_buoc_lam_lai:
        cache = doc_cache(duong_dan_media, ten_model)
        if cache is not None:
            return cache

    model = _tai_model(ten_model)
    bat_dau = time.perf_counter()
    cac_doan_iter, thong_tin = model.transcribe(
        duong_dan_media,
        language=NGON_NGU_MAC_DINH or None,
        vad_filter=True,                      # bỏ khoảng lặng, giảm ảo giác văn bản
        vad_parameters={"min_silence_duration_ms": 500},
        beam_size=int(os.getenv("RAG_WHISPER_BEAM", "5")),
        condition_on_previous_text=False,     # tránh lặp câu dây chuyền khi audio nhiễu
    )

    tong_giay = float(getattr(thong_tin, "duration", 0.0) or 0.0)
    cac_doan: list[DoanPhienAm] = []
    for doan in cac_doan_iter:
        noi_dung = (doan.text or "").strip()
        if noi_dung:
            cac_doan.append(DoanPhienAm(float(doan.start), float(doan.end), noi_dung))
        if bao_tien_do is not None:
            bao_tien_do(float(doan.end), tong_giay)

    duong_dan_cache = _duong_dan_cache(duong_dan_media, ten_model)
    with open(duong_dan_cache, "w", encoding="utf-8") as f:
        json.dump(
            {
                "nguon": os.path.basename(duong_dan_media),
                "model": ten_model,
                "ngon_ngu": getattr(thong_tin, "language", NGON_NGU_MAC_DINH),
                "thoi_luong_giay": tong_giay,
                "giay_phien_am": round(time.perf_counter() - bat_dau, 1),
                "doan": [asdict(d) for d in cac_doan],
            },
            f,
            ensure_ascii=False,
            indent=1,
        )
    return cac_doan


def doc_phu_de(duong_dan: str) -> list[DoanPhienAm]:
    """Đọc .srt/.vtt có sẵn - nhanh hơn và chính xác hơn phiên âm tự động."""
    import re

    with open(duong_dan, encoding="utf-8-sig", errors="replace") as f:
        noi_dung = f.read()

    mau_thoi_gian = re.compile(
        r"(\d{1,2}):(\d{2}):(\d{2})[,.](\d{1,3})\s*-->\s*"
        r"(\d{1,2}):(\d{2}):(\d{2})[,.](\d{1,3})"
    )
    cac_doan: list[DoanPhienAm] = []
    khoi_hien_tai: list[str] = []
    moc: tuple[float, float] | None = None

    def chot_khoi():
        if moc and khoi_hien_tai:
            van_ban = " ".join(dong.strip() for dong in khoi_hien_tai if dong.strip())
            van_ban = re.sub(r"<[^>]+>", "", van_ban).strip()
            if van_ban:
                cac_doan.append(DoanPhienAm(moc[0], moc[1], van_ban))

    for dong in noi_dung.splitlines():
        khop = mau_thoi_gian.search(dong)
        if khop:
            chot_khoi()
            khoi_hien_tai = []
            so = [int(x) for x in khop.groups()]
            moc = (
                so[0] * 3600 + so[1] * 60 + so[2] + so[3] / 1000,
                so[4] * 3600 + so[5] * 60 + so[6] + so[7] / 1000,
            )
        elif dong.strip() and not dong.strip().isdigit() and not dong.startswith("WEBVTT"):
            khoi_hien_tai.append(dong)
        elif not dong.strip():
            chot_khoi()
            khoi_hien_tai = []
    chot_khoi()
    return cac_doan
