"""Lớp dịch vụ dùng chung cho API, chỉ khởi tạo model và index một lần."""

from __future__ import annotations

import json
import os
import shutil
import tempfile
import threading
import time
from dataclasses import dataclass
from typing import Iterator
from urllib.parse import quote

import requests

import cache_ngu_nghia
import drive_sync
import goi_y_cau_hoi
import kiem_tra_tra_loi
import hieu_luc_bo_sung
import phan_loai_giao_duc
import tep_dinh_kem
import tinh_luong
import tu_vung_kho
import van_ban_meta
from capnhat_tailieu_moi import main as cap_nhat_chi_muc_tren_dia
from chunking_utils import tinh_hash_file
from hybrid_retrieval import (
    SO_KET_QUA_CUOI,
    tach_tu_tieng_viet,
    truy_hoi,
    xay_dung_bm25,
)
from document_loaders import suy_loai_tai_lieu
from main import (
    DATA_PATH,
    DINH_DANG_HO_TRO,
    DUONG_DAN_SO_GHI_CHEP,
    build_hoac_load_vector_store,
    tao_embeddings_va_llm,
    tao_llm,
    tao_rag_chain,
)
from tom_tat_tep import (
    SO_DOAN_TOM_TAT,
    gop_ngu_canh,
    la_yeu_cau_tom_tat,
    tao_chain_tom_tat,
)
from web_loader import (
    ket_qua_thanh_document,
    nen_ngu_canh_theo_cau_hoi,
    tai_va_trich_noi_dung,
    tim_url_trong_cau_hoi,
)


DUONG_DAN_CAI_DAT = os.path.abspath(os.getenv(
    "RAG_CAI_DAT", os.path.join(os.path.dirname(os.path.abspath(__file__)), "cai_dat.json")
))


# Tệp người dùng đính kèm trong chat được chép về đây để thành tài liệu lâu dài.
THU_MUC_TEP_TRONG_KHO = os.getenv(
    "RAG_THU_MUC_TEP_DINH_KEM_TRONG_KHO", "tai_lieu_dinh_kem"
)


def _luu_tep_dinh_kem_vao_kho() -> bool:
    return os.getenv("RAG_LUU_TEP_DINH_KEM", "1") == "1"


def _thu_muc_nong() -> str:
    """Thư mục "nóng" (vd Google Drive for Desktop kéo tệp về đây): tệp thả vào
    được tự chép vào kho và lập chỉ mục, không cần thao tác gì trên giao diện.
    Biến môi trường RAG_THU_MUC_NONG thắng; mặc định đọc cai_dat.json."""
    tu_env = os.getenv("RAG_THU_MUC_NONG", "").strip()
    if tu_env:
        return tu_env
    try:
        with open(DUONG_DAN_CAI_DAT, encoding="utf-8") as f:
            gia_tri = json.load(f).get("thu_muc_nong")
        if isinstance(gia_tri, str):
            return gia_tri.strip()
    except (OSError, ValueError, TypeError):
        pass
    return ""


def _phut_quet_thu_muc_nong() -> int:
    try:
        return max(1, int(os.getenv("RAG_PHUT_QUET_THU_MUC_NONG", "5")))
    except ValueError:
        return 5


def _giay_cho_truoc_khi_nap() -> int:
    """Đợi bao lâu sau câu hỏi cuối mới nạp tệp mới vào chỉ mục (0 = nạp ngay
    khi rảnh). Embedding khóa chat vài phút nên không được cắt ngang lúc người
    dùng vừa đính kèm tệp và đang hỏi về chính tệp đó."""
    try:
        return max(0, int(os.getenv("RAG_CHO_NAP_TEP_GIAY", "90")))
    except ValueError:
        return 90


def _phut_tu_dong_dong_bo() -> int:
    """0 = tắt tự động. Mặc định 15 phút: đủ nhanh để 'upload xong là hỏi được'."""
    try:
        return max(0, int(os.getenv("RAG_DRIVE_AUTO_SYNC_PHUT", "15")))
    except ValueError:
        return 15


@dataclass
class ServiceStatus:
    state: str = "starting"
    message: str = "Đang khởi tạo hệ thống..."
    vector_count: int = 0
    document_count: int = 0
    source_count: int = 0
    data_file_count: int = 0
    no_text_file_count: int = 0
    duplicate_file_count: int = 0
    error_file_count: int = 0
    data_stale: bool = False
    started_at: float = 0.0


@dataclass
class TrangThaiDrive:
    """Trạng thái đồng bộ Drive - tách khỏi ServiceStatus vì ServiceStatus bị
    tạo mới sau mỗi lần nạp lại chỉ mục, sẽ xóa mất lịch sử đồng bộ."""

    trang_thai: str = "idle"  # idle | syncing | error
    thong_bao: str = ""
    lan_cuoi: float = 0.0
    so_file_moi: int = 0


class RAGService:
    def __init__(self):
        self.status = ServiceStatus()
        self.vector_store = None
        # Giữ lại model nhúng: cache ngữ nghĩa cần nhúng câu hỏi mới
        # bằng đúng model đã nhúng kho.
        self.embeddings = None
        self.bm25_retriever = None
        # Từ vựng kho, dựng cùng lúc với BM25; dùng để chặn câu hỏi lạc đề.
        self.tu_vung = None
        self.rag_chain = None
        # Model trả lời hiện hành; đổi được lúc đang chạy qua giao diện.
        self.llm_model = self._tai_lua_chon_model()
        self.chain_tom_tat = None
        self.format_docs = None
        self._no_text_sources: list[str] = []
        self._initialization_lock = threading.Lock()
        self._generation_lock = threading.Lock()
        self._update_lock = threading.Lock()
        self._index_progress_lock = threading.Lock()
        self.index_progress = {
            "active": False,
            "stage": "idle",
            "label": "",
            "percent": 0.0,
            "completed": 0,
            "total": 0,
            "unit": "tệp",
            "current_file": "",
            "detail": "",
            "started_at": 0.0,
        }
        self.ho_so_van_ban: dict = {}
        # Nhãn môn/cấp học/lớp của từng file, dùng cho bộ lọc phạm vi truy xuất.
        self.phan_loai: dict = {}
        self.tinh_trang_hieu_luc: dict = {}
        self.drive = TrangThaiDrive()
        self._drive_lock = threading.Lock()
        self._drive_auto_started = False
        # Tệp đính kèm đã chép vào kho nhưng chưa embed vào FAISS.
        self.tep_cho_nap: list[str] = []
        self._hen_lock = threading.Lock()
        self._dang_hen_nap = False
        self.thoi_diem_chat_cuoi = 0.0
        # Vòng quét thư mục nóng: nhớ (mtime, size) đã xử lý để không băm lại
        # cả thư mục mỗi lượt.
        self._nong_da_quet: dict[str, tuple[float, int]] = {}
        self._nong_auto_started = False

    def initialize(self, force: bool = False) -> None:
        if self.status.state == "ready" and not force:
            return
        with self._initialization_lock:
            if self.status.state == "ready" and not force:
                return
            self.status = ServiceStatus(
                state="loading",
                message="Đang kết nối Ollama và nạp kho tri thức...",
                started_at=time.time(),
            )
            try:
                self._check_ollama()
                embeddings, llm = tao_embeddings_va_llm(self.llm_model)
                self.embeddings = embeddings
                self.vector_store, _ = build_hoac_load_vector_store(embeddings)
                self.status.message = "Đang lập hồ sơ văn bản và quan hệ hiệu lực..."
                self._lap_ho_so_van_ban()
                self.status.message = "Đang phân loại tài liệu theo môn và cấp học..."
                self._lap_phan_loai()
                self.status.message = "Đang dựng chỉ mục tìm kiếm từ khóa..."
                self.bm25_retriever = xay_dung_bm25(self.vector_store)
                # Từ vựng dựng từ chính tập BM25 để "kho có biết từ này không"
                # khớp đúng với thứ đang tìm kiếm được.
                self.tu_vung = tu_vung_kho.xay_dung_tu_vung(self.bm25_retriever.docs)
                self.rag_chain, self.format_docs = tao_rag_chain(self.vector_store, llm)
                self.chain_tom_tat = tao_chain_tom_tat(self._llm_tom_tat(self.llm_model))
                thong_ke = self._data_inventory()
                message = (
                    "Sẵn sàng trả lời · dữ liệu nguồn đã thay đổi, cần cập nhật chỉ mục"
                    if thong_ke["data_stale"] else "Sẵn sàng trả lời"
                )
                self.status = ServiceStatus(
                    state="ready",
                    message=message,
                    vector_count=int(self.vector_store.index.ntotal),
                    document_count=len(self.vector_store.docstore._dict),
                    source_count=thong_ke["source_count"],
                    data_file_count=thong_ke["data_file_count"],
                    no_text_file_count=thong_ke["no_text_file_count"],
                    duplicate_file_count=thong_ke["duplicate_file_count"],
                    error_file_count=thong_ke["error_file_count"],
                    data_stale=thong_ke["data_stale"],
                    started_at=self.status.started_at,
                )
                self._ham_nong_model()
                self.start_drive_auto_sync()
                self.start_quet_thu_muc_nong()
            except Exception as exc:
                self.status.state = "error"
                self.status.message = self._friendly_startup_error(exc)

    @staticmethod
    def _llm_tom_tat(ten_model: str):
        """Bản tóm tắt cần 5-8 gạch đầu dòng, dài hơn hạn mức của câu trả lời
        thường - dùng chung num_predict sẽ cắt cụt giữa chừng."""
        return tao_llm(
            ten_model,
            so_token_toi_da=int(os.getenv("RAG_MAX_OUTPUT_TOKENS_TOM_TAT", "700")),
        )

    def _ham_nong_model(self) -> None:
        """Nạp sẵn model vào RAM ngay sau khi khởi động.

        Câu hỏi đầu tiên trong ngày vốn phải chờ Ollama đọc 3,4 GB từ ổ đĩa trước
        khi xử lý được chữ nào; làm việc đó lúc người dùng còn đang mở giao diện
        thì họ không phải ngồi đợi.
        """
        def chay():
            base_url = os.getenv("OLLAMA_BASE_URL", "http://localhost:11434").rstrip("/")
            try:
                requests.post(
                    f"{base_url}/api/generate",
                    json={
                        "model": self.llm_model,
                        "prompt": "xin chào",
                        "stream": False,
                        "options": {"num_predict": 1},
                        "keep_alive": os.getenv("RAG_KEEP_ALIVE", "2h"),
                    },
                    timeout=300,
                )
            except requests.RequestException:
                pass  # Hâm nóng thất bại chỉ làm câu hỏi đầu chậm như trước.

        threading.Thread(target=chay, daemon=True, name="rag-ham-nong").start()

    def _lap_ho_so_van_ban(self) -> None:
        """
        Rút số hiệu, ngày ban hành và quan hệ thay thế/sửa đổi từ chính nội dung
        đã lập chỉ mục, rồi đánh dấu thẳng vào metadata của chunk. Nhờ dấu này,
        bộ xếp hạng hạ bậc được văn bản đã hết hiệu lực mà không cần biết gì về
        pháp luật - và phải làm TRƯỚC khi dựng BM25 vì BM25 sao chép metadata.
        """
        try:
            self.ho_so_van_ban = van_ban_meta.xay_dung_tu_vector_store(self.vector_store)
            van_ban_meta.luu_ho_so(self.ho_so_van_ban)
            # Dự thảo và ngày hiệu lực - hai tình trạng mà quan hệ giữa các văn
            # bản không nói lên được, nhưng lại quyết định đoạn trích có dùng
            # làm căn cứ được hay không.
            self.tinh_trang_hieu_luc = hieu_luc_bo_sung.xay_dung_tu_vector_store(
                self.vector_store, self.ho_so_van_ban
            )
            hieu_luc_bo_sung.luu(self.tinh_trang_hieu_luc)
        except Exception as exc:
            # Hồ sơ văn bản là lớp thông tin thêm; hỏng thì chatbot vẫn phải chạy.
            self.ho_so_van_ban = {}
            self.tinh_trang_hieu_luc = {}
            print(f"⚠️  Không lập được hồ sơ văn bản: {exc}")
            return

        for doc in self.vector_store.docstore._dict.values():
            muc = self.ho_so_van_ban.get(doc.metadata.get("source_file"))
            if muc and muc.bi_thay_the_boi:
                doc.metadata["_het_hieu_luc"] = True

    def _lap_phan_loai(self) -> None:
        """
        Gắn nhãn môn/cấp học/lớp cho từng file rồi chép xuống mọi chunk của nó.

        Đặt sau hồ sơ văn bản (cần cờ la_qppl để biết đâu là văn bản quy phạm)
        và trước khi dựng BM25 - BM25 sao chép metadata sang tài liệu riêng,
        gắn nhãn sau thì nhánh BM25 lọc hụt.
        """
        try:
            self.phan_loai = phan_loai_giao_duc.xay_dung_tu_vector_store(
                self.vector_store, self.ho_so_van_ban
            )
            phan_loai_giao_duc.gan_vao_chunk(self.vector_store, self.phan_loai)
            phan_loai_giao_duc.luu(self.phan_loai)
        except Exception as exc:
            # Cũng như hồ sơ văn bản: mất nhãn thì chỉ mất bộ lọc, không được
            # phép làm hỏng cả chatbot.
            self.phan_loai = {}
            print(f"⚠️  Không phân loại được tài liệu: {exc}")

    def bo_loc_phan_loai(self) -> dict:
        """Danh sách lựa chọn phạm vi cho giao diện."""
        return phan_loai_giao_duc.tom_tat(self.phan_loai or phan_loai_giao_duc.tai())

    def _data_inventory(self) -> dict:
        """Thống kê nhanh dữ liệu và phát hiện chỉ mục cũ hơn kho nguồn."""
        files = {}
        for thu_muc, _, ten_files in os.walk(DATA_PATH):
            for ten_file in ten_files:
                if os.path.splitext(ten_file)[1].lower() not in DINH_DANG_HO_TRO:
                    continue
                duong_dan = os.path.normcase(os.path.abspath(os.path.join(thu_muc, ten_file)))
                thong_tin = os.stat(duong_dan)
                files[duong_dan] = (thong_tin.st_size, thong_tin.st_mtime_ns)

        try:
            with open(DUONG_DAN_SO_GHI_CHEP, encoding="utf-8") as file:
                ledger_raw = json.load(file)
        except (OSError, ValueError, TypeError):
            ledger_raw = {}

        ledger = {
            os.path.normcase(os.path.abspath(path)): record
            for path, record in ledger_raw.items()
            if isinstance(record, dict)
        }
        data_stale = set(files) != set(ledger)
        if not data_stale:
            for path, (size, modified_ns) in files.items():
                record = ledger[path]
                if record.get("size") is not None and record["size"] != size:
                    data_stale = True
                    break
                if (
                    record.get("modified_ns") is not None
                    and record["modified_ns"] != modified_ns
                ):
                    data_stale = True
                    break

        source_count = len({
            doc.metadata.get("source_file")
            for doc in self.vector_store.docstore._dict.values()
            if doc.metadata.get("source_file")
        })
        self._no_text_sources = [
            os.path.basename(path)
            for path, record in ledger.items()
            if record.get("status") == "no_text"
        ]
        return {
            "source_count": source_count,
            "data_file_count": len(files),
            "no_text_file_count": sum(
                record.get("status") == "no_text" for record in ledger.values()
            ),
            "duplicate_file_count": sum(
                record.get("status") == "duplicate" for record in ledger.values()
            ),
            "error_file_count": sum(
                record.get("status") == "error" for record in ledger.values()
            ),
            "data_stale": data_stale,
        }

    def _matching_no_text_source(self, question: str) -> str | None:
        """Tìm PDF quét có tiêu đề khớp mạnh để tránh trả lời từ nguồn nhiễu."""
        query_tokens = set(tach_tu_tieng_viet(question))
        if len(query_tokens) < 4:
            return None
        best_name = None
        best_score = 0.0
        for source_name in self._no_text_sources:
            title_tokens = set(tach_tu_tieng_viet(os.path.splitext(source_name)[0]))
            overlap = len(query_tokens & title_tokens)
            coverage = overlap / len(query_tokens)
            if overlap >= 4 and coverage > best_score:
                best_name = source_name
                best_score = coverage
        return best_name if best_score >= 0.7 else None

    def _check_ollama(self) -> None:
        base_url = os.getenv("OLLAMA_BASE_URL", "http://localhost:11434").rstrip("/")
        response = requests.get(f"{base_url}/api/tags", timeout=4)
        response.raise_for_status()
        installed = {item.get("name", "") for item in response.json().get("models", [])}
        required = {
            os.getenv("RAG_EMBEDDING_MODEL", "bge-m3"),
            self.llm_model,
        }
        missing = [
            model for model in required
            if model not in installed and f"{model}:latest" not in installed
        ]
        if missing:
            raise RuntimeError(f"Ollama chưa có model: {', '.join(sorted(missing))}")

    # ============================================================
    # CHỌN MODEL TRẢ LỜI
    # ============================================================
    # Model nhúng chỉ sinh vector, không trò chuyện được - đưa vào danh sách
    # chọn thì người dùng bấm vào là hỏng cả phiên.
    DAU_HIEU_MODEL_NHUNG = ("embed", "bge-", "gte-", "e5-")

    @staticmethod
    def _tai_lua_chon_model() -> str:
        """
        Nhớ model người dùng đã chọn qua các lần mở lại ứng dụng. Biến môi
        trường RAG_LLM_MODEL vẫn thắng, để người triển khai ép được model.
        """
        if os.getenv("RAG_LLM_MODEL"):
            return os.environ["RAG_LLM_MODEL"]
        try:
            with open(DUONG_DAN_CAI_DAT, encoding="utf-8") as f:
                ten = json.load(f).get("llm_model")
            if isinstance(ten, str) and ten.strip():
                return ten.strip()
        except (OSError, ValueError, TypeError):
            pass
        return "qwen3.5:4b"

    @staticmethod
    def _luu_lua_chon_model(ten_model: str) -> None:
        try:
            with open(DUONG_DAN_CAI_DAT, "w", encoding="utf-8") as f:
                json.dump({"llm_model": ten_model}, f, ensure_ascii=False, indent=1)
        except OSError:
            pass  # Không ghi được thì chỉ mất phần ghi nhớ, không ảnh hưởng chat.

    @staticmethod
    def _la_model_tra_loi(ten: str) -> bool:
        ten_thuong = ten.lower()
        if ten_thuong.startswith(os.getenv("RAG_EMBEDDING_MODEL", "bge-m3").lower()):
            return False
        return not any(dau in ten_thuong for dau in RAGService.DAU_HIEU_MODEL_NHUNG)

    def danh_sach_model(self) -> dict:
        """Các model Ollama đang có trên máy, để giao diện hiện thành danh sách chọn."""
        base_url = os.getenv("OLLAMA_BASE_URL", "http://localhost:11434").rstrip("/")
        try:
            response = requests.get(f"{base_url}/api/tags", timeout=4)
            response.raise_for_status()
            cac_model = response.json().get("models", [])
        except requests.RequestException as exc:
            return {"models": [], "current": self.llm_model, "error": str(exc)}

        danh_sach = []
        for muc in cac_model:
            ten = muc.get("name", "")
            if not ten or not self._la_model_tra_loi(ten):
                continue
            danh_sach.append({
                "name": ten,
                "size_gb": round(int(muc.get("size", 0)) / 1e9, 1),
                "parameter_size": (muc.get("details") or {}).get("parameter_size"),
                "family": (muc.get("details") or {}).get("family"),
            })
        danh_sach.sort(key=lambda m: m["name"])
        return {"models": danh_sach, "current": self.llm_model}

    def doi_model(self, ten_model: str) -> tuple[bool, str]:
        """
        Đổi model trả lời ngay lúc đang chạy. Chỉ dựng lại chuỗi sinh câu trả
        lời - vector store và BM25 giữ nguyên vì chúng phụ thuộc model nhúng,
        không phụ thuộc model trả lời.
        """
        ten_model = (ten_model or "").strip()
        if not ten_model:
            return False, "Chưa chọn model."
        if ten_model == self.llm_model:
            return True, f"Đang dùng {ten_model}."
        if self.status.state != "ready":
            return False, "Hệ thống chưa sẵn sàng để đổi model."

        co_san = {m["name"] for m in self.danh_sach_model()["models"]}
        if co_san and ten_model not in co_san:
            return False, f"Ollama chưa có model {ten_model}."

        # Chặn đổi giữa chừng một câu trả lời đang stream dở.
        if not self._generation_lock.acquire(timeout=1):
            return False, "Hãy đợi câu trả lời hiện tại xong rồi đổi model."
        try:
            llm = tao_llm(ten_model)
            self.rag_chain, self.format_docs = tao_rag_chain(self.vector_store, llm)
            # Chuỗi tóm tắt tệp đính kèm cũng dùng LLM, phải dựng lại theo model
            # mới - nếu quên, giao diện báo model A nhưng tóm tắt vẫn chạy model B.
            self.chain_tom_tat = tao_chain_tom_tat(self._llm_tom_tat(ten_model))
            self.llm_model = ten_model
            self._luu_lua_chon_model(ten_model)
        except Exception as exc:
            return False, f"Không đổi được model: {exc}"
        finally:
            self._generation_lock.release()
        self._ham_nong_model()  # Model mới cũng cần nạp sẵn, đừng bắt câu hỏi kế chờ.
        return True, f"Đã chuyển sang {ten_model}."

    @staticmethod
    def _friendly_startup_error(exc: Exception) -> str:
        message = str(exc)
        lowered = message.lower()
        if "chưa có model" in lowered:
            return message
        if "connection" in lowered or "11434" in lowered or "ollama" in lowered:
            return "Không kết nối được Ollama. Hãy mở Ollama rồi tải model bge-m3 và qwen3.5:4b."
        if "faiss" in lowered or "index" in lowered:
            return f"Không nạp được kho tri thức: {message}"
        return f"Khởi tạo thất bại: {message}"

    def status_dict(self) -> dict:
        with self._index_progress_lock:
            index_progress = dict(self.index_progress)
        bat_dau = index_progress.get("started_at") or 0
        index_progress["elapsed_seconds"] = (
            round(max(0.0, time.time() - bat_dau), 1) if bat_dau else 0.0
        )
        return {
            "state": self.status.state,
            "message": self.status.message,
            "vector_count": self.status.vector_count,
            "document_count": self.status.document_count,
            "source_count": self.status.source_count,
            "data_file_count": self.status.data_file_count,
            "no_text_file_count": self.status.no_text_file_count,
            "duplicate_file_count": self.status.duplicate_file_count,
            "error_file_count": self.status.error_file_count,
            "data_stale": self.status.data_stale,
            "model": self.llm_model,
            "reasoning": os.getenv("RAG_REASONING", "0") == "1",
            "busy": self._generation_lock.locked(),
            "tep_cho_nap": len(self.tep_cho_nap),
            "index_progress": index_progress,
            "drive": self.drive_dict(),
            "thu_muc_nong": {
                "dang_theo_doi": self._nong_auto_started,
                "duong_dan": _thu_muc_nong(),
                "phut_quet": _phut_quet_thu_muc_nong(),
            },
        }

    def start_index_update(self) -> tuple[bool, str]:
        """Khởi chạy cập nhật tăng dần, đồng thời chặn chat dùng index đang đổi."""
        with self._update_lock:
            if self.status.state == "updating":
                return False, "Chỉ mục đang được cập nhật."
            if self.status.state != "ready":
                return False, "Hệ thống chưa sẵn sàng để cập nhật chỉ mục."
            if self._generation_lock.locked():
                return False, "Hãy đợi câu trả lời hiện tại hoàn tất rồi cập nhật."

            self.status.state = "updating"
            self.status.message = "Đang cập nhật tài liệu mới vào kho tri thức..."
            with self._index_progress_lock:
                self.index_progress = {
                    "active": True,
                    "stage": "starting",
                    "label": "Đang chuẩn bị cập nhật...",
                    "percent": 0.0,
                    "completed": 0,
                    "total": 0,
                    "unit": "tệp",
                    "current_file": "",
                    "detail": "",
                    "started_at": time.time(),
                }
            threading.Thread(
                target=self._run_index_update,
                daemon=True,
                name="rag-index-update",
            ).start()
            return True, self.status.message

    def _run_index_update(self) -> None:
        try:
            with self._generation_lock:
                # Từ lúc này mọi tệp đã chép vào kho đều nằm trong lượt quét của
                # trình cập nhật, không còn chờ lượt nào nữa.
                self.tep_cho_nap.clear()
                cap_nhat_chi_muc_tren_dia(self._bao_tien_do_chi_muc)
            # Nạp lại FAISS, BM25 và thống kê sau khi bản trên đĩa đã hoàn tất.
            self.initialize(force=True)
            # Kho đã đổi thì câu trả lời cũ có thể đã sai căn cứ. Vân tay mới
            # khiến chúng không khớp nữa, nhưng xóa hẳn thì chắc chắn hơn là
            # trông vào việc so vân tay ở mọi đường dẫn tra cứu.
            da_xoa = cache_ngu_nghia.cache.xoa_theo_van_tay_khac(self._van_tay_chi_muc())
            if da_xoa:
                print(f"🧹 Đã xóa {da_xoa} mục cache thuộc chỉ mục cũ.")
            with self._index_progress_lock:
                self.index_progress.update({
                    "active": False,
                    "stage": "complete",
                    "label": "Đã cập nhật xong",
                    "percent": 100.0,
                    "current_file": "",
                    "detail": "Kho tri thức đã sẵn sàng",
                })
        except Exception as exc:
            self.status.state = "error"
            self.status.message = f"Cập nhật chỉ mục thất bại: {exc}"
            with self._index_progress_lock:
                self.index_progress.update({
                    "active": False,
                    "stage": "error",
                    "label": "Cập nhật thất bại",
                    "detail": str(exc)[:300],
                })

    def _bao_tien_do_chi_muc(self, tien_do: dict) -> None:
        """Nhận tiến độ từ worker và công khai qua /api/status cho giao diện."""
        with self._index_progress_lock:
            bat_dau = self.index_progress.get("started_at") or time.time()
            self.index_progress = {
                **self.index_progress,
                **tien_do,
                "active": tien_do.get("stage") != "complete",
                "started_at": bat_dau,
            }
        if tien_do.get("label"):
            self.status.message = tien_do["label"]

    # ============================================================
    # TỆP ĐÍNH KÈM -> KHO TÀI LIỆU
    # ============================================================
    def luu_tep_vao_kho(self, duong_dan: str, ten: str) -> tuple[str, str]:
        """Chép tệp vừa đính kèm vào kho tài liệu chung rồi hẹn nạp vào chỉ mục.

        Gọi từ luồng đọc tệp của tep_dinh_kem (qua hook) nên chỉ làm việc rẻ:
        băm, chép, hẹn giờ. Phần embedding đắt tiền để dành cho lúc máy rảnh.
        """
        if not _luu_tep_dinh_kem_vao_kho():
            return "tat", ""

        ma_bam = tinh_hash_file(duong_dan)
        trung = self._tim_tep_trung_trong_kho(ma_bam)
        if trung is not None:
            return "da_co", f"Kho tài liệu đã có tệp này ({os.path.basename(trung)})."

        dich = self._duong_dan_trong_kho(ten)
        os.makedirs(os.path.dirname(dich), exist_ok=True)
        shutil.copy2(duong_dan, dich)
        self.tep_cho_nap.append(os.path.basename(dich))
        self._hen_cap_nhat_chi_muc()
        return "da_luu", (
            f"Đã thêm vào kho tài liệu ({THU_MUC_TEP_TRONG_KHO}), "
            "sẽ nạp vào chỉ mục khi máy rảnh."
        )

    def nhap_tep_tu_giao_dien(self, ten: str, du_lieu: bytes) -> tuple[str, str]:
        """Nhận tệp tải lên từ nút "+" trong Kho tài liệu.

        Khác luu_tep_vao_kho (đi qua tệp đính kèm chat), ở đây byte đến thẳng
        từ trình duyệt nên phải ghi ra tệp tạm NGOÀI kho trước khi băm - băm
        ngay trong kho thì _tim_tep_trung_trong_kho sẽ thấy chính nó và báo trùng.
        """
        ten_goc = os.path.basename(ten.replace("\\", "/")).strip()
        if not ten_goc:
            return "loi", "Tên tệp không hợp lệ."
        duoi = os.path.splitext(ten_goc)[1].lower()
        if duoi not in DINH_DANG_HO_TRO:
            return "khong_ho_tro", (
                f"Định dạng {duoi or '(không có đuôi)'} chưa được hỗ trợ."
            )
        if not du_lieu:
            return "loi", "Tệp rỗng, không có gì để nạp."

        fd, tam = tempfile.mkstemp(suffix=duoi, prefix="kho-upload-")
        try:
            with os.fdopen(fd, "wb") as file:
                file.write(du_lieu)
            ma_bam = tinh_hash_file(tam)
            trung = self._tim_tep_trung_trong_kho(ma_bam)
            if trung is not None:
                return "da_co", (
                    f"Kho tài liệu đã có tệp này ({os.path.basename(trung)})."
                )
            dich = self._duong_dan_trong_kho(ten_goc)
            os.makedirs(os.path.dirname(dich), exist_ok=True)
            shutil.move(tam, dich)
        finally:
            if os.path.isfile(tam):
                os.remove(tam)

        self.tep_cho_nap.append(os.path.basename(dich))
        self._hen_cap_nhat_chi_muc()
        return "da_luu", f"Đã thêm {os.path.basename(dich)} vào kho tài liệu."

    @staticmethod
    def _tim_tep_trung_trong_kho(ma_bam: str) -> str | None:
        """Cùng nội dung thì không chép lần hai, dù người dùng đổi tên tệp."""
        try:
            with open(DUONG_DAN_SO_GHI_CHEP, encoding="utf-8") as file:
                so_ghi_chep = json.load(file)
        except (OSError, ValueError, TypeError):
            so_ghi_chep = {}

        da_co_trong_so = set()
        if isinstance(so_ghi_chep, dict):
            for duong_dan, ban_ghi in so_ghi_chep.items():
                da_co_trong_so.add(os.path.normcase(os.path.abspath(duong_dan)))
                if not isinstance(ban_ghi, dict) or ban_ghi.get("hash") != ma_bam:
                    continue
                if os.path.isfile(duong_dan):
                    return duong_dan

        # Tệp đính kèm của lượt trước có thể chưa kịp vào sổ (chỉ mục chạy sau),
        # nên phải băm thêm chính thư mục này - vài chục tệp, đủ rẻ.
        thu_muc = os.path.join(DATA_PATH, THU_MUC_TEP_TRONG_KHO)
        if not os.path.isdir(thu_muc):
            return None
        for ten_file in sorted(os.listdir(thu_muc)):
            duong_dan = os.path.join(thu_muc, ten_file)
            if os.path.normcase(os.path.abspath(duong_dan)) in da_co_trong_so:
                continue
            if not os.path.isfile(duong_dan):
                continue
            try:
                if tinh_hash_file(duong_dan) == ma_bam:
                    return duong_dan
            except OSError:
                continue
        return None

    @staticmethod
    def _duong_dan_trong_kho(ten: str) -> str:
        """Tên phải là duy nhất trong cả kho: resolve_source_file từ chối mở
        nguồn khi hai thư mục có tệp trùng tên, trích dẫn sẽ mất liên kết."""
        da_dung = set()
        for _, _, ten_files in os.walk(DATA_PATH):
            da_dung.update(os.path.normcase(ten_file) for ten_file in ten_files)

        goc, duoi = os.path.splitext(ten)
        ten_chon = ten
        lan = 1
        while os.path.normcase(ten_chon) in da_dung:
            lan += 1
            ten_chon = f"{goc} ({lan}){duoi}"
        return os.path.join(DATA_PATH, THU_MUC_TEP_TRONG_KHO, ten_chon)

    def _hen_cap_nhat_chi_muc(self) -> None:
        """Một luồng chờ duy nhất cho mọi tệp đang xếp hàng."""
        with self._hen_lock:
            if self._dang_hen_nap:
                return
            self._dang_hen_nap = True
        threading.Thread(
            target=self._vong_cho_nap_chi_muc, daemon=True, name="rag-hen-nap-tep"
        ).start()

    def _vong_cho_nap_chi_muc(self) -> None:
        """Đợi hệ thống thật sự rảnh rồi mới chạy cập nhật chỉ mục tăng dần."""
        cho = _giay_cho_truoc_khi_nap()
        try:
            while True:
                time.sleep(5)
                if not self.tep_cho_nap:
                    return
                if self.status.state != "ready" or self._generation_lock.locked():
                    continue
                if self.drive.trang_thai == "syncing":
                    continue
                if time.time() - self.thoi_diem_chat_cuoi < cho:
                    continue
                da_chay, _ = self.start_index_update()
                if da_chay:
                    return
        finally:
            with self._hen_lock:
                self._dang_hen_nap = False

    # ============================================================
    # THƯ MỤC NÓNG (Google Drive for Desktop, OneDrive...)
    # ============================================================
    def start_quet_thu_muc_nong(self) -> None:
        if not _thu_muc_nong() or self._nong_auto_started:
            return
        self._nong_auto_started = True
        threading.Thread(
            target=self._vong_quet_thu_muc_nong,
            daemon=True,
            name="rag-quet-thu-muc-nong",
        ).start()

    def _vong_quet_thu_muc_nong(self) -> None:
        print(f"👀 Đang theo dõi thư mục nóng: {_thu_muc_nong()}")
        while True:
            try:
                self._quet_thu_muc_nong_mot_lan()
            except Exception as exc:
                print(f"⚠️ Quét thư mục nóng lỗi: {exc}")
            time.sleep(_phut_quet_thu_muc_nong() * 60)

    def _quet_thu_muc_nong_mot_lan(self) -> None:
        thu_muc = _thu_muc_nong()
        if not thu_muc or not os.path.isdir(thu_muc):
            return
        for goc, _, ten_files in os.walk(thu_muc):
            for ten in sorted(ten_files):
                duong_dan = os.path.join(goc, ten)
                if os.path.splitext(ten)[1].lower() not in DINH_DANG_HO_TRO:
                    continue
                try:
                    thong_tin = os.stat(duong_dan)
                except OSError:
                    continue
                # Drive có thể còn đang tải tệp về dở; đợi tệp yên 60 giây
                # rồi mới chép, kẻo băm và nạp phải nửa tệp.
                if time.time() - thong_tin.st_mtime < 60:
                    continue
                dau_van = (thong_tin.st_mtime, thong_tin.st_size)
                if self._nong_da_quet.get(duong_dan) == dau_van:
                    continue
                trang_thai, thong_bao = self.luu_tep_vao_kho(duong_dan, ten)
                self._nong_da_quet[duong_dan] = dau_van
                if trang_thai == "da_luu":
                    print(f"📥 Thư mục nóng: {ten} - {thong_bao}")

    # ============================================================
    # ĐỒNG BỘ GOOGLE DRIVE
    # ============================================================
    def drive_dict(self) -> dict:
        san_sang, mo_ta = drive_sync.da_cau_hinh()
        return {
            "configured": san_sang,
            "mode": mo_ta,
            "state": self.drive.trang_thai,
            "message": self.drive.thong_bao,
            "last_sync_at": self.drive.lan_cuoi or None,
            "new_files": self.drive.so_file_moi,
            "auto_minutes": _phut_tu_dong_dong_bo(),
            "folder_url": (
                f"https://drive.google.com/drive/folders/{drive_sync.THU_MUC_DRIVE}"
            ),
        }

    def start_drive_sync(self) -> tuple[bool, str]:
        with self._drive_lock:
            if self.drive.trang_thai == "syncing":
                return False, "Đang đồng bộ Drive."
            if self.status.state == "updating":
                return False, "Chỉ mục đang được cập nhật, hãy đợi xong rồi đồng bộ."
            san_sang, mo_ta = drive_sync.da_cau_hinh()
            if not san_sang:
                return False, mo_ta
            self.drive.trang_thai = "syncing"
            self.drive.thong_bao = "Đang kiểm tra tài liệu mới trên Google Drive..."
            threading.Thread(
                target=self._run_drive_sync, daemon=True, name="rag-drive-sync"
            ).start()
            return True, self.drive.thong_bao

    def _run_drive_sync(self) -> None:
        """Tải phần thay đổi từ Drive rồi tự nạp vào chỉ mục - người dùng chỉ
        cần upload lên Drive, không phải đụng tới máy chạy chatbot."""
        try:
            ket_qua = drive_sync.dong_bo(
                bao_tien_do=lambda dong: setattr(self.drive, "thong_bao", dong)
            )
            self.drive.lan_cuoi = time.time()
            self.drive.so_file_moi = len(ket_qua.da_tai)
            self.drive.thong_bao = ket_qua.tom_tat()
            self.drive.trang_thai = "idle"
            if ket_qua.co_thay_doi and self.status.state == "ready":
                self.start_index_update()
        except Exception as exc:
            self.drive.trang_thai = "error"
            self.drive.thong_bao = f"Đồng bộ Drive thất bại: {exc}"

    def start_drive_auto_sync(self) -> None:
        """Hẹn giờ nền: cứ N phút kiểm tra Drive một lần (0 = tắt)."""
        so_phut = _phut_tu_dong_dong_bo()
        if so_phut <= 0 or self._drive_auto_started:
            return
        san_sang, _ = drive_sync.da_cau_hinh()
        if not san_sang:
            return
        self._drive_auto_started = True

        def vong_lap():
            while True:
                time.sleep(so_phut * 60)
                if self.status.state == "ready" and self.drive.trang_thai != "syncing":
                    self.start_drive_sync()

        threading.Thread(target=vong_lap, daemon=True, name="rag-drive-auto").start()

    def _retrieve(self, question: str, pham_vi: dict | None = None):
        url = tim_url_trong_cau_hoi(question)
        if url:
            result = tai_va_trich_noi_dung(url)
            if not result.thanh_cong:
                raise ValueError(result.loi)
            result.noi_dung, _ = nen_ngu_canh_theo_cau_hoi(
                result.noi_dung, question, so_doan=3
            )
            return [ket_qua_thanh_document(result)]
        no_text_source = self._matching_no_text_source(question)
        if no_text_source:
            if suy_loai_tai_lieu(no_text_source) in {"video", "am_thanh"}:
                raise ValueError(
                    f"Tài liệu phù hợp nhất là {no_text_source}, nhưng file này không có "
                    "lời thoại để phiên âm nên chưa tra cứu được nội dung."
                )
            raise ValueError(
                "Có tài liệu rất phù hợp với câu hỏi nhưng PDF chưa có lớp văn bản để tra cứu: "
                f"{no_text_source}. Hãy OCR tài liệu này rồi cập nhật lại chỉ mục."
            )
        return truy_hoi(
            question, self.vector_store, self.bm25_retriever, SO_KET_QUA_CUOI,
            phan_loai_giao_duc.bo_loc_tu_pham_vi(pham_vi),
        )

    @staticmethod
    def _sources(documents, ho_so: dict | None = None, tinh_trang: dict | None = None) -> list[dict]:
        sources = []
        for evidence_number, doc in enumerate(documents, 1):
            source_name = doc.metadata.get("source_file", "Không rõ nguồn")
            source_url = doc.metadata.get("source_url")
            url = source_url or f"/api/source?name={quote(source_name)}"
            time_start = doc.metadata.get("time_start")
            so_trang = doc.metadata.get("so_trang")
            # Tệp người dùng đính kèm cũng do máy chủ này phục vụ, dù đã có
            # sẵn source_url trỏ tới endpoint tải tệp.
            cuc_bo = source_url is None or bool(doc.metadata.get("tep_dinh_kem"))
            if source_url is None and time_start is not None:
                # Mở video đúng giây được trích dẫn thay vì phát lại từ đầu.
                url += f"#t={int(float(time_start))}"
            elif cuc_bo and so_trang and source_name.lower().endswith(".pdf"):
                # Trình xem PDF của trình duyệt nhảy thẳng tới trang qua neo này,
                # thay vì bắt người đọc tự dò trong tài liệu vài chục trang.
                url += f"#page={so_trang}"
            muc_ho_so = ho_so.get(source_name) if ho_so else None
            muc_thoi_gian = tinh_trang.get(source_name) if tinh_trang else None
            source = {
                "evidence": evidence_number,
                "name": source_name,
                "van_ban": {
                    "so_hieu": muc_ho_so.so_hieu,
                    "uoc_doan": muc_ho_so.so_hieu_uoc_doan,
                    "loai": muc_ho_so.loai,
                    "co_quan": muc_ho_so.co_quan,
                    "ngay": muc_ho_so.ngay_ban_hanh,
                    "nhan": muc_ho_so.nhan(),
                    "con_hieu_luc": muc_ho_so.con_hieu_luc,
                    "thay_the": muc_ho_so.thay_the,
                    "sua_doi": muc_ho_so.sua_doi,
                } if muc_ho_so and muc_ho_so.so_hieu else None,
                # Nhãn ngắn để giao diện gắn ngay cạnh chip nguồn.
                "validity": hieu_luc_bo_sung.nhan_hieu_luc(
                    muc_ho_so, muc_thoi_gian, doc.page_content
                ),
                "page": so_trang,
                "chapter": doc.metadata.get("chapter"),
                "article": doc.metadata.get("article"),
                "context": doc.metadata.get("context_label"),
                "excerpt": " ".join(doc.page_content.split())[:280],
                "url": url,
                "external": bool(source_url),
                "kind": doc.metadata.get("loai_tai_lieu", "van_ban"),
                "time_start": time_start,
            }
            sources.append(source)
        return sources

    def goi_y_mo_dau(self, so_luong: int = goi_y_cau_hoi.SO_GOI_Y_MO_DAU) -> list[str]:
        """Câu hỏi gợi ý cho màn hình chào.

        Chưa nạp xong chỉ mục thì đọc hồ sơ văn bản đã lưu trên đĩa: người dùng
        mở trang lúc Ollama còn chưa chạy vẫn phải thấy gợi ý, không thì hàng
        gợi ý trống hoác đúng lúc cần biết hỏi được những gì.
        """
        ho_so = self.ho_so_van_ban or van_ban_meta.tai_ho_so()
        return goi_y_cau_hoi.goi_y_mo_dau(ho_so, so_luong)

    @staticmethod
    def resolve_source_file(source_name: str) -> str | None:
        """Ánh xạ tên nguồn công khai sang đúng một tệp nằm trong kho dữ liệu."""
        if not source_name or source_name != os.path.basename(source_name):
            return None

        data_root = os.path.realpath(DATA_PATH)
        matches = []
        for directory, _, filenames in os.walk(data_root):
            if source_name not in filenames:
                continue
            candidate = os.path.realpath(os.path.join(directory, source_name))
            try:
                inside_data_root = os.path.commonpath([data_root, candidate]) == data_root
            except ValueError:
                inside_data_root = False
            if (
                inside_data_root
                and os.path.splitext(candidate)[1].lower() in DINH_DANG_HO_TRO
                and os.path.isfile(candidate)
            ):
                matches.append(candidate)

        # Không tự chọn khi hai thư mục có tệp trùng tên vì có thể mở sai nguồn.
        return matches[0] if len(matches) == 1 else None

    @staticmethod
    def document_inventory() -> dict:
        """Liệt kê kho nguồn cùng tình trạng lập chỉ mục, không lộ đường dẫn máy."""
        try:
            with open(DUONG_DAN_SO_GHI_CHEP, encoding="utf-8") as ledger_file:
                ledger_raw = json.load(ledger_file)
        except (OSError, ValueError, TypeError):
            ledger_raw = {}
        if not isinstance(ledger_raw, dict):
            ledger_raw = {}

        ledger = {
            os.path.normcase(os.path.abspath(path)): record
            for path, record in ledger_raw.items()
            if isinstance(path, str) and isinstance(record, dict)
        }
        source_files = []
        for directory, _, filenames in os.walk(DATA_PATH):
            for filename in filenames:
                if os.path.splitext(filename)[1].lower() not in DINH_DANG_HO_TRO:
                    continue
                path = os.path.normcase(os.path.abspath(os.path.join(directory, filename)))
                stat = os.stat(path)
                source_files.append((path, filename, stat))

        name_counts: dict[str, int] = {}
        for _, filename, _ in source_files:
            name_counts[filename] = name_counts.get(filename, 0) + 1

        documents = []
        status_counts = {
            "processed": 0, "no_text": 0, "duplicate": 0, "error": 0, "pending": 0,
        }
        current_paths = set()
        for path, filename, stat in source_files:
            current_paths.add(path)
            record = ledger.get(path)
            status = "pending"
            if record:
                status = record.get("status", "processed")
                if (
                    (record.get("size") is not None and record["size"] != stat.st_size)
                    or (
                        record.get("modified_ns") is not None
                        and record["modified_ns"] != stat.st_mtime_ns
                    )
                ):
                    status = "pending"
            if status not in status_counts:
                status = "pending"
            status_counts[status] += 1
            relative_folder = os.path.dirname(os.path.relpath(path, DATA_PATH))
            documents.append({
                "name": filename,
                "folder": "Kho chính" if relative_folder in {"", "."} else relative_folder,
                "extension": os.path.splitext(filename)[1].lower().lstrip("."),
                "kind": suy_loai_tai_lieu(filename),
                "size_bytes": stat.st_size,
                "modified_at": stat.st_mtime,
                "status": status,
                "url": (
                    f"/api/source?name={quote(filename)}"
                    if name_counts[filename] == 1 else None
                ),
            })

        documents.sort(key=lambda item: item["name"].casefold())
        return {
            "documents": documents,
            "summary": {
                "total": len(documents),
                **status_counts,
                "removed": len(set(ledger) - current_paths),
            },
        }

    @staticmethod
    def _conversation_inputs(question: str, history: list[dict] | None) -> tuple[str, str]:
        """Tạo truy vấn nối tiếp và phần hội thoại ngắn gọn cho mô hình."""
        history = (history or [])[-6:]
        previous_user_question = next(
            (
                item.get("content", "").strip()
                for item in reversed(history)
                if item.get("role") == "user" and item.get("content", "").strip()
            ),
            "",
        )
        follow_up_markers = {
            "còn", "vậy", "đó", "này", "trên", "thì", "sao", "tiếp", "trường hợp"
        }
        question_tokens = tach_tu_tieng_viet(question)
        is_likely_follow_up = (
            len(question_tokens) <= 12
            or bool(follow_up_markers.intersection(question_tokens))
        )
        retrieval_question = question
        if previous_user_question and is_likely_follow_up:
            retrieval_question = f"{previous_user_question}\n{question}"
        if not history:
            return retrieval_question, question

        labels = {"user": "Người dùng", "assistant": "Trợ lý"}
        conversation_lines = []
        for item in history:
            role = labels.get(item.get("role"))
            content = item.get("content", "").strip()
            if role and content:
                conversation_lines.append(f"{role}: {content[:1200]}")
        model_question = (
            "Hội thoại gần đây (chỉ dùng để hiểu câu hỏi nối tiếp):\n"
            + "\n".join(conversation_lines)
            + f"\n\nCâu hỏi hiện tại: {question}"
        )
        return retrieval_question, model_question

    def _tra_loi_theo_tep(
        self, question: str, history: list[dict] | None, tep_ids: list[str]
    ) -> Iterator[dict]:
        """Hỏi đáp hoặc tóm tắt trong phạm vi đúng các tệp người dùng vừa đính kèm.

        Cố tình KHÔNG trộn với kho tri thức chung: người dùng đính kèm tệp là để
        hỏi về tệp đó, trộn thêm văn bản khác chỉ làm câu trả lời khó kiểm chứng.
        """
        cac_tep = [tep_dinh_kem.kho_tep.lay_san_sang(ma) for ma in tep_ids[:4]]
        with self._generation_lock:
            started = time.perf_counter()
            retrieval_question, model_question = self._conversation_inputs(
                question, history
            )
            tom_tat = la_yeu_cau_tom_tat(question)
            yield {
                "type": "phase",
                "phase": "retrieving",
                "message": "Đang đọc tệp đính kèm" if tom_tat
                else "Đang tìm trong tệp đính kèm",
            }

            documents = []
            for tep in cac_tep:
                if tom_tat:
                    documents.extend(tep_dinh_kem.kho_tep.doan_dai_dien(
                        tep, max(3, SO_DOAN_TOM_TAT // len(cac_tep))
                    ))
                else:
                    documents.extend(tep_dinh_kem.kho_tep.truy_hoi(
                        tep, retrieval_question, max(2, SO_KET_QUA_CUOI // len(cac_tep))
                    ))
            if not documents:
                yield {"type": "sources", "sources": []}
                yield {
                    "type": "token",
                    "content": "Tệp đính kèm không có nội dung đọc được.",
                }
                yield {
                    "type": "done",
                    "elapsed_seconds": round(time.perf_counter() - started, 1),
                    "citations_ok": True,
                    "figures_ok": True,
                    "abstained": True,
                }
                return

            cac_nguon = self._sources(
                documents, self.ho_so_van_ban, self.tinh_trang_hieu_luc
            )
            for nguon in cac_nguon:
                # Nguồn nằm trên máy chủ này chứ không phải trang web ngoài, dù
                # đã có sẵn source_url trỏ tới endpoint tải tệp.
                nguon["external"] = False
                nguon["dinh_kem"] = True
            yield {"type": "sources", "sources": cac_nguon}
            yield {
                "type": "phase",
                "phase": "generating",
                "message": "Đang tóm tắt tệp" if tom_tat else "Đang soạn câu trả lời",
            }

            if tom_tat:
                dong_token = self.chain_tom_tat.stream({
                    "ten_tep": ", ".join(tep.ten for tep in cac_tep),
                    "context": gop_ngu_canh(documents),
                    "question": model_question,
                })
            else:
                dong_token = self.rag_chain.stream({
                    "context": self.format_docs(documents),
                    "question": model_question,
                })
            cau_tra_loi = ""
            for token in dong_token:
                if token:
                    cau_tra_loi += token
                    yield {"type": "token", "content": token}

            kiem_tra = kiem_tra_tra_loi.kiem_tra(cau_tra_loi, documents)
            if tom_tat:
                # Bản tóm tắt không bắt buộc trích dẫn [n], nhưng số liệu tự bịa
                # thì vẫn phải báo.
                canh_bao = (
                    "Cần đối chiếu lại: số liệu "
                    + ", ".join(kiem_tra.so_khong_tim_thay[:3])
                    + " không thấy trong đoạn được trích."
                ) if kiem_tra.so_khong_tim_thay else ""
            else:
                canh_bao = "" if kiem_tra.dat else kiem_tra.canh_bao()
            if canh_bao:
                yield {"type": "warning", "message": canh_bao}
            yield {
                "type": "goi_y",
                "goi_y": goi_y_cau_hoi.goi_y_theo_tep(
                    question, [tep.ten for tep in cac_tep]
                ),
            }
            yield {
                "type": "done",
                "elapsed_seconds": round(time.perf_counter() - started, 1),
                "citations_ok": tom_tat or kiem_tra.trich_dan_hop_le,
                "figures_ok": kiem_tra.so_lieu_co_can_cu,
                "unverified_figures": kiem_tra.so_khong_tim_thay,
            }

    # ============================================================
    # CACHE NGỮ NGHĨA
    # ============================================================
    def _van_tay_chi_muc(self) -> str:
        return cache_ngu_nghia.van_tay_chi_muc(
            self.status.vector_count, self.status.document_count
        )

    @staticmethod
    def _cache_duoc(question: str, history: list[dict] | None,
                    pham_vi: dict | None = None) -> bool:
        """
        Chỉ cache câu hỏi tự đứng một mình.

        Câu nối tiếp ("Còn giáo viên thì sao?") phụ thuộc lượt trước nên hai
        người hỏi đúng chữ đó vẫn cần hai câu trả lời khác nhau. Câu chứa URL thì
        nội dung trang có thể đã đổi. Cả hai đều không có gì đảm bảo cache còn đúng.
        """
        if not cache_ngu_nghia.bat_cache():
            return False
        if history:
            return False
        # Cùng một câu hỏi nhưng khác phạm vi là hai câu hỏi khác nhau: phát
        # lại câu trả lời dựng từ tài liệu ngoài phạm vi chính là thứ mà bộ
        # lọc sinh ra để ngăn.
        if pham_vi:
            return False
        return not tim_url_trong_cau_hoi(question)

    def _vector_cau_hoi(self, question: str) -> list[float] | None:
        """Nhúng câu hỏi bằng chính model nhúng đang dùng cho kho (bge-m3)."""
        if self.embeddings is None:
            return None
        try:
            return self.embeddings.embed_query(question)
        except Exception as exc:
            # Cache là tính năng tăng tốc; hỏng thì đi đường thường, không báo lỗi.
            print(f"⚠️  Không nhúng được câu hỏi để tra cache: {exc}")
            return None

    def _tra_tu_cache(self, muc: dict, diem: float) -> Iterator[dict]:
        """Phát lại một câu trả lời đã cache theo đúng thứ tự sự kiện như khi
        sinh mới, để giao diện không cần biết câu này đến từ đâu."""
        yield {"type": "sources", "sources": muc.get("nguon", [])}
        yield from muc.get("canh_bao_hieu_luc", [])
        yield {"type": "token", "content": muc.get("tra_loi", "")}
        yield {
            "type": "goi_y",
            "goi_y": goi_y_cau_hoi.goi_y_tiep_theo(
                muc.get("cau_hoi", ""), muc.get("nguon", [])
            ),
        }
        yield {
            "type": "done",
            "elapsed_seconds": 0.0,
            "citations_ok": True,
            "figures_ok": True,
            "tu_cache": True,
            # Để giao diện nói được "câu này lấy lại từ câu hỏi tương tự" thay vì
            # âm thầm trả lời chữ khác với câu vừa gõ.
            "cache_cau_hoi_goc": muc.get("cau_hoi", ""),
            "cache_do_giong": round(diem, 4),
        }

    @staticmethod
    def _tra_loi_tinh_luong(
        question: str, van_ban: str, nguon: list[dict]
    ) -> Iterator[dict]:
        """Phát phiếu tính lương theo đúng thứ tự sự kiện của một câu trả lời
        thường, để giao diện không cần biết câu này đến từ công cụ tính."""
        bat_dau = time.perf_counter()
        yield {"type": "sources", "sources": nguon}
        yield {"type": "token", "content": van_ban}
        yield {
            "type": "goi_y",
            "goi_y": goi_y_cau_hoi.goi_y_tiep_theo(question, nguon),
        }
        yield {
            "type": "done",
            "elapsed_seconds": round(time.perf_counter() - bat_dau, 1),
            # Hậu kiểm của kiem_tra_tra_loi đối chiếu từng con số với đoạn được
            # trích - đúng cho câu do mô hình sinh, nhưng vô nghĩa ở đây: mọi
            # con số đều do Python tính và đã in kèm công thức ngay trong phiếu,
            # nên người đọc kiểm lại được trực tiếp, không cần đối chiếu chuỗi.
            "citations_ok": True,
            "figures_ok": True,
            "tinh_luong": True,
        }

    def stream_answer(
        self,
        question: str,
        history: list[dict] | None = None,
        tep_ids: list[str] | None = None,
        pham_vi: dict | None = None,
    ) -> Iterator[dict]:
        """Ghi mốc hoạt động quanh mỗi lượt hỏi để trình hẹn nạp tệp mới vào chỉ
        mục biết khi nào người dùng thật sự ngừng hỏi."""
        self.thoi_diem_chat_cuoi = time.time()
        try:
            yield from self._sinh_cau_tra_loi(question, history, tep_ids, pham_vi)
        finally:
            self.thoi_diem_chat_cuoi = time.time()

    def _sinh_cau_tra_loi(
        self,
        question: str,
        history: list[dict] | None = None,
        tep_ids: list[str] | None = None,
        pham_vi: dict | None = None,
    ) -> Iterator[dict]:
        if self.status.state != "ready":
            raise RuntimeError(self.status.message)
        if tep_ids:
            yield from self._tra_loi_theo_tep(question, history, tep_ids)
            return

        # Câu hỏi tính lương rẽ sang công cụ tính (tinh_luong.py) trước cả cache.
        # Hai lý do phải đặt ở đây chứ không đặt sau:
        #   - Cache ngữ nghĩa sẽ coi "GV THPT hạng III bậc 1" và "GV THPT hạng
        #     III bậc 5" là gần như cùng một câu, rồi phát lại phiếu lương của
        #     người này cho người kia. Phiếu lương sai người còn tệ hơn chậm.
        #   - Phép tính chạy trong micro giây, không cần xếp hàng sau câu đang
        #     sinh dở 150 giây trên CPU.
        phieu_luong = tinh_luong.tra_loi(question)
        if phieu_luong is not None:
            yield from self._tra_loi_tinh_luong(question, *phieu_luong)
            return

        # Tra cache TRƯỚC khi giành khóa sinh câu trả lời: một câu đã có sẵn
        # trong cache không nên phải xếp hàng sau câu đang chạy dở 150 giây.
        vector_cau_hoi = (
            self._vector_cau_hoi(question)
            if self._cache_duoc(question, history, pham_vi) else None
        )
        ung_vien_cache, diem_cache = (None, 0.0)
        if vector_cau_hoi:
            ung_vien_cache, diem_cache = cache_ngu_nghia.cache.tim(
                vector_cau_hoi, self.llm_model, self._van_tay_chi_muc()
            )
            # Rất giống thì trả ngay, không cần truy hồi lại.
            if ung_vien_cache and diem_cache >= cache_ngu_nghia.NGUONG_TUONG_DONG:
                cache_ngu_nghia.cache.ghi_nhan_dung(ung_vien_cache["cau_hoi"])
                yield from self._tra_tu_cache(ung_vien_cache, diem_cache)
                return

        with self._generation_lock:
            started = time.perf_counter()
            retrieval_question, model_question = self._conversation_inputs(question, history)
            yield {
                "type": "phase",
                "phase": "retrieving",
                "message": "Đang tìm tài liệu liên quan",
            }
            documents = self._retrieve(retrieval_question, pham_vi)

            # Ứng viên cache chỉ giống vừa phải: giờ đã có kết quả truy hồi thật,
            # đối chiếu bộ bằng chứng. Trùng khớp hoàn toàn nghĩa là câu trả lời
            # cũ được soạn từ đúng những đoạn này, nên vẫn đúng căn cứ.
            if ung_vien_cache and cache_ngu_nghia.cung_bang_chung(
                ung_vien_cache, documents
            ):
                cache_ngu_nghia.cache.ghi_nhan_dung(ung_vien_cache["cau_hoi"])
                yield from self._tra_tu_cache(ung_vien_cache, diem_cache)
                return

            # Không có gì thực sự dính tới câu hỏi: trả lời thẳng là không tìm
            # thấy, thay vì để mô hình diễn giải từ mấy đoạn lạc đề (và tiết
            # kiệm luôn ~30 giây sinh văn bản trên CPU).
            ly_do_chan = kiem_tra_tra_loi.ly_do_bo_qua(
                documents, retrieval_question, self.tu_vung
            )
            if os.getenv("RAG_TU_CHOI_KHI_LAC_DE", "1") == "1" and ly_do_chan:
                yield {"type": "sources", "sources": []}
                # Đang lọc phạm vi mà nói trống không "không có trong tài liệu"
                # thì người dùng kết luận nhầm là kho thiếu tài liệu, trong khi
                # thứ chặn họ là bộ lọc chính họ vừa bật.
                mo_ta = phan_loai_giao_duc.mo_ta_pham_vi(pham_vi)
                yield {
                    "type": "token",
                    "content": (
                        f"Trong phạm vi đang lọc ({mo_ta}) không có tài liệu trả lời "
                        "được câu này. Bỏ bớt bộ lọc rồi hỏi lại thì tôi tìm trên cả kho."
                        if mo_ta else
                        "Tôi không tìm thấy thông tin này trong tài liệu hiện có."
                    ),
                }
                # Không có nguồn nào để gợi ý hỏi sâu hơn, nên đổi sang gợi ý
                # những câu kho chắc chắn trả lời được.
                yield {"type": "goi_y", "goi_y": self.goi_y_mo_dau(3)}
                yield {
                    "type": "done",
                    "elapsed_seconds": round(time.perf_counter() - started, 1),
                    "citations_ok": True,
                    "figures_ok": True,
                    "abstained": True,
                    # Tín hiệu nào đã chặn - để log và benchmark chỉnh ngưỡng có
                    # căn cứ, thay vì chỉ biết "đã từ chối".
                    "ly_do_chan": ly_do_chan,
                }
                return

            cac_nguon = self._sources(
                documents, self.ho_so_van_ban, self.tinh_trang_hieu_luc
            )
            yield {"type": "sources", "sources": cac_nguon}

            # Điều mà một chatbot chỉ so khớp ngữ nghĩa không thể biết: văn bản
            # vừa trích dẫn đã bị một văn bản khác TRONG KHO thay thế hoặc sửa đổi.
            # Gom thành danh sách thay vì phát thẳng, để còn lưu kèm vào cache -
            # câu trả lời lấy lại từ cache mà thiếu cảnh báo hiệu lực thì nguy
            # hiểm hơn hẳn việc chờ lâu.
            cac_canh_bao_hieu_luc = [
                {
                    "type": "hieu_luc",
                    "message": canh_bao["thong_bao"],
                    "evidence": canh_bao["evidence"],
                    "kind": canh_bao["loai"],
                }
                for canh_bao in (
                    van_ban_meta.canh_bao_hieu_luc(self.ho_so_van_ban, cac_nguon)
                    + hieu_luc_bo_sung.canh_bao(self.tinh_trang_hieu_luc, cac_nguon)
                    + hieu_luc_bo_sung.canh_bao_doan(cac_nguon, documents)
                )
            ]
            yield from cac_canh_bao_hieu_luc
            yield {
                "type": "phase",
                "phase": "generating",
                "message": "Đang soạn câu trả lời",
            }
            context = self.format_docs(documents)
            cau_tra_loi = ""
            for token in self.rag_chain.stream({"context": context, "question": model_question}):
                if token:
                    cau_tra_loi += token
                    yield {"type": "token", "content": token}

            # Hậu kiểm bằng đối chiếu chuỗi: rẻ, không gọi thêm mô hình, và bắt
            # đúng hai lỗi nguy hiểm nhất (trích dẫn sai số, số liệu tự bịa).
            kiem_tra = kiem_tra_tra_loi.kiem_tra(cau_tra_loi, documents)
            if not kiem_tra.dat:
                yield {"type": "warning", "message": kiem_tra.canh_bao()}
            yield {
                "type": "goi_y",
                "goi_y": goi_y_cau_hoi.goi_y_tiep_theo(question, cac_nguon),
            }
            # Chỉ cache câu trả lời đã qua hậu kiểm. Câu có trích dẫn sai hoặc số
            # liệu không căn cứ được là câu cần sửa, không phải câu để phát lại
            # cho nhiều người khác.
            if vector_cau_hoi and kiem_tra.dat and cau_tra_loi.strip():
                cache_ngu_nghia.cache.them(
                    cau_hoi=question,
                    vector_cau_hoi=vector_cau_hoi,
                    tra_loi=cau_tra_loi,
                    nguon=cac_nguon,
                    model=self.llm_model,
                    van_tay=self._van_tay_chi_muc(),
                    canh_bao_hieu_luc=cac_canh_bao_hieu_luc,
                    khoa_chunk=cache_ngu_nghia.khoa_chunk_cua(documents),
                )
            yield {
                "type": "done",
                "elapsed_seconds": round(time.perf_counter() - started, 1),
                "citations_ok": kiem_tra.trich_dan_hop_le,
                "figures_ok": kiem_tra.so_lieu_co_can_cu,
                # Liệt kê con số bị nghi ngờ để đối chiếu được khi phân tích
                # benchmark, thay vì chỉ biết "có gì đó sai".
                "unverified_figures": kiem_tra.so_khong_tim_thay,
            }


service = RAGService()
# Tệp người dùng đính kèm trong chat sẽ được chép thẳng vào kho tài liệu.
tep_dinh_kem.dat_hook_luu_kho(service.luu_tep_vao_kho)
