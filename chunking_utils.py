"""
STRUCTURE-AWARE RECURSIVE CHUNKING
=====================================
Tách tài liệu theo cấu trúc "Chương / Điều" trước (giữ nguyên một Điều -
cùng các Khoản/Điểm bên trong nó - làm một chunk, để không bị cắt ngang
ý nghĩa như RecursiveCharacterTextSplitter thuần cắt theo ký tự).

Chỉ dùng RecursiveCharacterTextSplitter làm fallback khi:
  - Tài liệu không có cấu trúc "Điều" (đề cương, slide, văn bản tự do) -> chunk cả tài liệu.
  - Một Điều dài hơn CHUNK_SIZE -> chunk tiếp bên trong Điều đó.

Tài liệu không phải văn bản liền mạch (slide, sheet Excel, đoạn phiên âm video)
đã được loader tách sẵn thành từng phần tử độc lập - bộ chunk giữ nguyên ranh
giới đó thay vì gộp cả file rồi cắt lại theo ký tự.

Dùng chung cho main.py và capnhat_tailieu_moi.py để tránh 2 bản logic lệch nhau.
"""

import os
import re
import sys
import json
import subprocess
import hashlib
from collections import defaultdict
from langchain_core.documents import Document
from langchain_text_splitters import RecursiveCharacterTextSplitter

from document_loaders import (  # noqa: F401 - giữ tên cũ cho code đang import
    DINH_DANG_HO_TRO,
    suy_loai_tai_lieu,
    tao_loader_cho_file,
)

THOI_GIAN_CHO_TOI_DA_MOI_FILE = 180  # giây, cho subprocess load 1 file
_WORKER_SCRIPT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "_load_file_worker.py")

CHUNK_SIZE = 1200
CHUNK_OVERLAP = 150

MARKDOWN_SEPARATORS = [
    "\n#{1,6} ", "```\n", "\n\\*\\*\\*+\n", "\n---+\n", "\n___+\n",
    "\n\n", "\n", " ", "",
]

# "Chương I", "Chương 1", "CHƯƠNG II ..." ở đầu dòng
CHUONG_PATTERN = re.compile(
    r"(?:^|\n)[ \t]*(Chương\s+(?:[IVXLCDM]+|\d+)[^\n]{0,100})", re.IGNORECASE
)
# "Điều 1.", "Điều 12 ..." ở đầu dòng
DIEU_PATTERN = re.compile(
    r"(?:^|\n)[ \t]*(Điều\s+\d+\.?[^\n]{0,150})", re.IGNORECASE
)

# Độ dài tối thiểu của phần mở đầu (trước Điều 1) để coi là đáng giữ lại
DO_DAI_TOI_THIEU_PHAN_DAU = 50


def tao_text_splitter_fallback() -> RecursiveCharacterTextSplitter:
    return RecursiveCharacterTextSplitter(
        chunk_size=CHUNK_SIZE, chunk_overlap=CHUNK_OVERLAP, add_start_index=True,
        strip_whitespace=True, separators=MARKDOWN_SEPARATORS, is_separator_regex=True,
    )


def tinh_hash_file(duong_dan: str) -> str:
    """SHA-256 của nội dung file, dùng để phát hiện file bị sửa nội dung."""
    h = hashlib.sha256()
    with open(duong_dan, "rb") as f:
        for khoi in iter(lambda: f.read(8192), b""):
            h.update(khoi)
    return h.hexdigest()


def load_file_an_toan(duong_dan: str, timeout: int = THOI_GIAN_CHO_TOI_DA_MOI_FILE):
    """
    Load 1 file trong subprocess riêng (subprocess.run gọi _load_file_worker.py)
    để cô lập crash cấp thấp (segmentation fault trong UnstructuredFileLoader/
    thư viện native) - loại lỗi mà try/except thường không bắt được vì nó giết
    luôn tiến trình Python.

    Cố tình KHÔNG dùng multiprocessing.Process: trên Windows, "spawn" context
    tương tác lỗi với venv launcher (python.exe của venv), sinh ra một tiến
    trình con chạy nhầm bằng Python hệ thống thay vì venv - subprocess.run với
    đường dẫn interpreter tường minh (sys.executable) không gặp vấn đề này.

    Trả về (danh_sach_document, None) nếu OK, hoặc (None, thong_bao_loi) nếu thất bại.
    """
    try:
        ket_qua = subprocess.run(
            [sys.executable, _WORKER_SCRIPT, duong_dan],
            capture_output=True, timeout=timeout,
            env={**os.environ, "PYTHONIOENCODING": "utf-8"},
        )
    except subprocess.TimeoutExpired:
        return None, f"Timeout sau {timeout}s (có thể file quá lớn/phức tạp hoặc bị treo)"

    if ket_qua.returncode != 0:
        loi_stderr = ket_qua.stderr.decode("utf-8", errors="replace").strip().splitlines()
        goi_y = loi_stderr[-1] if loi_stderr else ""
        return None, (
            f"Tiến trình con crash (returncode={ket_qua.returncode}) - "
            f"có thể segmentation fault do file lỗi. {goi_y}"
        )

    try:
        du_lieu = json.loads(ket_qua.stdout.decode("utf-8"))
    except Exception as e:
        return None, f"Không đọc được kết quả từ tiến trình con: {e}"

    if not du_lieu.get("ok"):
        return None, du_lieu.get("error", "Lỗi không rõ")

    docs = [Document(page_content=d["page_content"], metadata=d["metadata"]) for d in du_lieu["docs"]]
    return docs, None


# Toàn bộ loader hiện dùng thư viện thuần Python đã kiểm chứng trên kho thật
# (xem document_loaders.py), không còn định dạng nào phải chạy qua
# UnstructuredFileLoader - thủ phạm của các lần crash/treo trước đây. Cơ chế cô
# lập subprocess vẫn giữ lại và bật được bằng RAG_CO_LAP_DINH_DANG=".pdf,.docx".
DINH_DANG_CAN_CO_LAP = {
    duoi.strip().lower()
    for duoi in os.getenv("RAG_CO_LAP_DINH_DANG", "").split(",")
    if duoi.strip()
}


def load_file_an_toan_neu_can(duong_dan: str, bao_tien_do_ocr=None):
    """
    Load trực tiếp trong tiến trình hiện tại, trừ các đuôi được liệt kê trong
    RAG_CO_LAP_DINH_DANG thì chạy qua subprocess cô lập (chậm hơn, chống crash).
    Trả về (danh_sach_document, None) nếu OK, hoặc (None, thong_bao_loi) nếu thất bại.
    """
    duoi = os.path.splitext(duong_dan)[1].lower()
    if duoi in DINH_DANG_CAN_CO_LAP:
        return load_file_an_toan(duong_dan)
    try:
        return load_file_truc_tiep(duong_dan, bao_tien_do_ocr), None
    except Exception as e:
        return None, str(e)


def load_file_truc_tiep(duong_dan: str, bao_tien_do_ocr=None):
    """
    Load trực tiếp trong tiến trình hiện tại (KHÔNG subprocess) - nhanh hơn
    nhiều so với load_file_an_toan(). Chỉ dùng cho file đã qua preflight scan
    (preflight.py) nên biết chắc không crash/treo.
    """
    return tao_loader_cho_file(
        duong_dan, bao_tien_do_ocr=bao_tien_do_ocr
    ).load()


def suy_metadata(file_path: str, goc: str) -> dict:
    duong_dan_tuong_doi = os.path.relpath(file_path, goc)
    cac_phan = duong_dan_tuong_doi.split(os.sep)
    return {
        "source_file": cac_phan[-1],
        "loai_thu_muc": cac_phan[0] if len(cac_phan) > 1 else "goc",
        # video / bang_du_lieu / trinh_chieu / van_ban - giao diện dùng để hiện
        # đúng biểu tượng và mở nguồn đúng cách (video thì tua tới mốc trích dẫn).
        "loai_tai_lieu": suy_loai_tai_lieu(file_path),
    }


def _don_gian_hoa(chuoi: str) -> str:
    return re.sub(r"\s+", " ", chuoi).strip()


def _chuong_gan_nhat(chuong_matches, vi_tri: int):
    ket_qua = None
    for cm in chuong_matches:
        if cm.start() <= vi_tri:
            ket_qua = _don_gian_hoa(cm.group(1))
        else:
            break
    return ket_qua


def _ban_do_trang(docs_cua_file) -> list[tuple[int, int]]:
    """
    [(vị trí bắt đầu trong văn bản ghép, số trang)] cho từng trang nguồn.

    Dựng đúng theo cách chunk_theo_cau_truc nối các trang lại (ngăn nhau bằng
    một dòng trống), nên cộng thêm 2 ký tự sau mỗi trang.
    """
    moc = []
    vi_tri = 0
    for doc in docs_cua_file:
        so_trang = doc.metadata.get("so_trang")
        if isinstance(so_trang, int):
            moc.append((vi_tri, so_trang))
        vi_tri += len(doc.page_content) + 2
    return moc


def _gan_trang(md: dict, moc: list, vi_tri: int) -> None:
    """Chunk nằm vắt qua hai trang thì ghi trang nó BẮT ĐẦU: người đọc mở đúng
    trang đó vẫn thấy được câu được trích, còn ghi trang cuối thì không."""
    trang = None
    for bat_dau, so_trang in moc:
        if bat_dau > vi_tri:
            break
        trang = so_trang
    if trang is not None:
        md["so_trang"] = trang


class _DoViTriChunk:
    """
    Bộ tách văn bản chỉ trả về chuỗi, không kèm vị trí, nên phải dò lại vị trí
    của từng chunk trong văn bản gốc mới biết nó thuộc trang nào. Các chunk đi
    theo đúng thứ tự nên chỉ cần một con trỏ chạy tới, không phải quét lại từ đầu.
    """

    DAI_MAU = 60

    def __init__(self, van_ban: str, goc: int = 0):
        self.van_ban = van_ban
        self.goc = goc
        self.con_tro = 0

    def vi_tri(self, doan: str) -> int:
        mau = doan[: self.DAI_MAU].strip()
        tim = self.van_ban.find(mau, self.con_tro) if mau else -1
        if tim < 0:
            tim = self.van_ban.find(mau) if mau else -1
        if tim < 0:
            # Bộ tách đã sửa khoảng trắng khiến dò không ra: giữ nguyên con trỏ
            # hiện tại, sai lệch nhiều nhất là một trang chứ không loạn cả file.
            return self.goc + self.con_tro
        # Các chunk chồng lấn nhau (CHUNK_OVERLAP) nên chỉ nhích một ký tự,
        # nhảy qua hết đoạn vừa tìm thấy sẽ bỏ sót chunk kế tiếp.
        self.con_tro = tim + 1
        return self.goc + tim


def _chunk_theo_phan_tu(docs_cua_file, text_splitter):
    """
    Slide, sheet Excel và đoạn phiên âm video đã là những đơn vị hoàn chỉnh:
    gộp chúng lại rồi cắt theo ký tự sẽ trộn slide 3 với slide 4, hoặc cắt mất
    dòng tiêu đề của bảng. Ở đây mỗi phần tử giữ nguyên ranh giới, chỉ phần tử
    nào dài hơn CHUNK_SIZE mới cắt tiếp và được đánh số "phần i/n".
    """
    cac_chunk = []
    for doc in docs_cua_file:
        noi_dung = doc.page_content.strip()
        if not noi_dung:
            continue
        if len(noi_dung) <= CHUNK_SIZE:
            phan = [noi_dung]
        else:
            phan = text_splitter.split_text(noi_dung)
        for thu_tu, van_ban in enumerate(phan, 1):
            md = dict(doc.metadata)
            md["format_type"] = "theo_phan_tu"
            md.pop("chunk_mode", None)
            if len(phan) > 1 and md.get("context_label"):
                md["context_label"] = f"{md['context_label']} (phần {thu_tu}/{len(phan)})"
            cac_chunk.append(Document(page_content=van_ban, metadata=md))
    return cac_chunk


def chunk_theo_cau_truc(documents, text_splitter=None):
    """
    Nhận vào danh sách Document (có thể gồm nhiều file, nhiều trang/phần tử
    mỗi file). Gộp lại theo file, phát hiện cấu trúc "Điều" bằng regex:
      - Phần tử độc lập (slide/sheet/phiên âm) -> giữ nguyên ranh giới phần tử.
      - Có cấu trúc  -> mỗi Điều là 1 chunk (kèm metadata "chapter"/"article"),
                        Điều nào quá dài thì chunk tiếp bằng fallback.
      - Không có cấu trúc -> chunk cả tài liệu bằng fallback (giống trước đây).
    """
    if text_splitter is None:
        text_splitter = tao_text_splitter_fallback()

    theo_file = defaultdict(list)
    thu_tu_file = []
    for doc in documents:
        khoa = doc.metadata.get("source") or doc.metadata.get("source_file", "")
        if khoa not in theo_file:
            thu_tu_file.append(khoa)
        theo_file[khoa].append(doc)

    tat_ca_chunks = []
    for khoa in thu_tu_file:
        docs_cua_file = theo_file[khoa]
        if any(d.metadata.get("chunk_mode") == "theo_phan_tu" for d in docs_cua_file):
            tat_ca_chunks.extend(_chunk_theo_phan_tu(docs_cua_file, text_splitter))
            continue

        text_day_du = "\n\n".join(d.page_content for d in docs_cua_file)
        metadata_goc = dict(docs_cua_file[0].metadata)
        # Trang của trang đầu tiên không đúng cho các chunk phía sau: bỏ ra
        # khỏi metadata dùng chung rồi gán lại theo vị trí thật của từng chunk.
        metadata_goc.pop("so_trang", None)
        metadata_goc.pop("page", None)
        moc_trang = _ban_do_trang(docs_cua_file)

        dieu_matches = list(DIEU_PATTERN.finditer(text_day_du))

        if not dieu_matches:
            # Không phát hiện cấu trúc Chương/Điều -> fallback recursive thuần
            do_vi_tri = _DoViTriChunk(text_day_du)
            for st in text_splitter.split_text(text_day_du):
                md = dict(metadata_goc)
                md["format_type"] = "van_ban"
                _gan_trang(md, moc_trang, do_vi_tri.vi_tri(st))
                tat_ca_chunks.append(Document(page_content=st, metadata=md))
            continue

        chuong_matches = list(CHUONG_PATTERN.finditer(text_day_du))

        # Phần mở đầu trước Điều 1 (mục lục, lời nói đầu...) nếu đủ dài để có ý nghĩa
        khoi_dau = text_day_du[: dieu_matches[0].start()]
        phan_dau = khoi_dau.strip()
        if len(phan_dau) > DO_DAI_TOI_THIEU_PHAN_DAU:
            do_vi_tri = _DoViTriChunk(
                phan_dau, len(khoi_dau) - len(khoi_dau.lstrip())
            )
            for st in text_splitter.split_text(phan_dau):
                md = dict(metadata_goc)
                md["format_type"] = "van_ban"
                _gan_trang(md, moc_trang, do_vi_tri.vi_tri(st))
                tat_ca_chunks.append(Document(page_content=st, metadata=md))

        for i, m in enumerate(dieu_matches):
            start = m.start()
            end = dieu_matches[i + 1].start() if i + 1 < len(dieu_matches) else len(text_day_du)
            khoi = text_day_du[start:end]
            noi_dung = khoi.strip()
            if not noi_dung:
                continue

            tieu_de_dieu = _don_gian_hoa(m.group(1))
            chuong_hien_tai = _chuong_gan_nhat(chuong_matches, start)

            if len(noi_dung) <= CHUNK_SIZE:
                phan_noi_dung = [noi_dung]
            else:
                phan_noi_dung = text_splitter.split_text(noi_dung)

            do_vi_tri = _DoViTriChunk(
                noi_dung, start + len(khoi) - len(khoi.lstrip())
            )
            for phan in phan_noi_dung:
                md = dict(metadata_goc)
                md["format_type"] = "structure_aware"
                md["article"] = tieu_de_dieu
                if chuong_hien_tai:
                    md["chapter"] = chuong_hien_tai
                _gan_trang(md, moc_trang, do_vi_tri.vi_tri(phan))
                tat_ca_chunks.append(Document(page_content=phan, metadata=md))

    return tat_ca_chunks
