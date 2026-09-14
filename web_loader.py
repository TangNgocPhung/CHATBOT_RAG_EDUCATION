"""Tải nội dung một URL công khai và nén ngữ cảnh theo câu hỏi."""

from __future__ import annotations

import ipaddress
import re
import socket
from dataclasses import dataclass
from urllib.parse import urljoin, urlparse

import requests
from langchain_core.documents import Document
from rank_bm25 import BM25Okapi


URL_PATTERN = re.compile(r"https?://[^\s<>\"']+", re.IGNORECASE)
USER_AGENT = "RAG-GiaoDuc/1.0 (local educational assistant)"
MAX_REDIRECTS = 5
MAX_BYTES = 4 * 1024 * 1024


@dataclass
class KetQuaTaiWeb:
    thanh_cong: bool
    url: str
    noi_dung: str = ""
    tieu_de: str = ""
    loi: str = ""


def tim_url_trong_cau_hoi(cau_hoi: str) -> str | None:
    match = URL_PATTERN.search(cau_hoi)
    if not match:
        return None
    return match.group(0).rstrip(".,;:!?)]}")


def _kiem_tra_url_cong_khai(url: str) -> None:
    parsed = urlparse(url)
    if parsed.scheme not in {"http", "https"} or not parsed.hostname:
        raise ValueError("URL phải dùng http hoặc https.")
    if parsed.username or parsed.password:
        raise ValueError("URL có thông tin đăng nhập không được hỗ trợ.")
    try:
        dia_chi = socket.getaddrinfo(
            parsed.hostname, parsed.port or (443 if parsed.scheme == "https" else 80)
        )
    except socket.gaierror as exc:
        raise ValueError("Không phân giải được tên miền.") from exc
    for item in dia_chi:
        ip = ipaddress.ip_address(item[4][0])
        if not ip.is_global:
            raise ValueError("Không cho phép truy cập địa chỉ nội bộ hoặc cục bộ.")


def _tai_co_kiem_soat(url: str, timeout: int) -> tuple[requests.Response, bytes]:
    session = requests.Session()
    current = url
    for _ in range(MAX_REDIRECTS + 1):
        _kiem_tra_url_cong_khai(current)
        response = session.get(
            current,
            headers={
                "User-Agent": USER_AGENT,
                "Accept": "text/html,text/plain;q=0.9,*/*;q=0.2",
            },
            timeout=(5, timeout),
            allow_redirects=False,
            stream=True,
        )
        if 300 <= response.status_code < 400 and response.headers.get("Location"):
            current = urljoin(current, response.headers["Location"])
            response.close()
            continue
        response.raise_for_status()
        data = bytearray()
        for chunk in response.iter_content(64 * 1024):
            data.extend(chunk)
            if len(data) > MAX_BYTES:
                response.close()
                raise ValueError("Trang web lớn hơn giới hạn 4 MB.")
        return response, bytes(data)
    raise ValueError("URL chuyển hướng quá nhiều lần.")


def tai_va_trich_noi_dung(url: str, timeout: int = 20) -> KetQuaTaiWeb:
    try:
        response, raw = _tai_co_kiem_soat(url, timeout)
        final_url = response.url
        content_type = response.headers.get("Content-Type", "").lower()
        if "pdf" in content_type or final_url.lower().split("?")[0].endswith(".pdf"):
            return KetQuaTaiWeb(False, final_url, loi="Chưa hỗ trợ đọc PDF trực tiếp từ URL.")
        if "html" not in content_type and "text/plain" not in content_type:
            return KetQuaTaiWeb(False, final_url, loi="URL không trả về trang HTML hoặc văn bản.")

        response.encoding = response.encoding or response.apparent_encoding or "utf-8"
        html = raw.decode(response.encoding, errors="replace")
        import trafilatura

        noi_dung = trafilatura.extract(
            html,
            include_comments=False,
            include_tables=True,
            no_fallback=False,
        )
        metadata = trafilatura.extract_metadata(html)
        tieu_de = metadata.title if metadata and metadata.title else urlparse(final_url).netloc
        if not noi_dung or len(noi_dung.strip()) < 80:
            return KetQuaTaiWeb(
                False,
                final_url,
                loi="Trang không có đủ nội dung văn bản hoặc được render bằng JavaScript.",
            )
        return KetQuaTaiWeb(True, final_url, noi_dung=noi_dung.strip(), tieu_de=tieu_de)
    except requests.Timeout:
        return KetQuaTaiWeb(False, url, loi="Trang web phản hồi quá thời gian cho phép.")
    except requests.RequestException as exc:
        return KetQuaTaiWeb(False, url, loi=f"Không tải được trang web: {exc}")
    except (ValueError, OSError) as exc:
        return KetQuaTaiWeb(False, url, loi=str(exc))
    except Exception as exc:
        return KetQuaTaiWeb(False, url, loi=f"Không thể đọc nội dung trang: {exc}")


def _tokenize(text: str) -> list[str]:
    return re.findall(r"\w+", text.lower(), flags=re.UNICODE)


def nen_ngu_canh_theo_cau_hoi(
    noi_dung: str, cau_hoi: str, so_doan: int = 3
) -> tuple[str, int]:
    cac_doan = [
        p.strip() for p in re.split(r"\n\s*\n", noi_dung) if len(p.strip()) >= 30
    ]
    if len(cac_doan) <= so_doan:
        return "\n\n".join(cac_doan) or noi_dung, len(cac_doan)
    corpus = [_tokenize(p) for p in cac_doan]
    bm25 = BM25Okapi(corpus)
    scores = bm25.get_scores(_tokenize(cau_hoi))
    vi_tri = sorted(range(len(cac_doan)), key=lambda i: scores[i], reverse=True)[:so_doan]
    vi_tri.sort()
    return "\n\n".join(cac_doan[i] for i in vi_tri), len(vi_tri)


def ket_qua_thanh_document(ket_qua: KetQuaTaiWeb) -> Document:
    return Document(
        page_content=ket_qua.noi_dung,
        metadata={
            "source_file": ket_qua.tieu_de or ket_qua.url,
            "source_url": ket_qua.url,
            "loai_thu_muc": "web",
        },
    )
