"""Chạy ứng dụng bằng: python run_ui.py"""

import json
import os
import socket
import sys
import threading
import time
import urllib.request
import webbrowser

import uvicorn


def chon_cong_trong(host: str) -> int:
    """Ưu tiên cổng cấu hình; nếu không có thì chọn cổng trống từ 8000."""
    configured = os.getenv("RAG_PORT")
    candidates = [int(configured)] if configured else list(range(8000, 8021))
    for candidate in candidates:
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
            try:
                sock.bind((host, candidate))
                return candidate
            except OSError:
                continue
    if configured:
        raise RuntimeError(f"Cổng {configured} đang được ứng dụng khác sử dụng.")
    raise RuntimeError("Không tìm được cổng trống trong khoảng 8000-8020.")


def mo_trinh_duyet_khi_dung_ung_dung(url: str) -> None:
    """Chỉ mở tab khi endpoint trạng thái xác nhận đúng ứng dụng này."""
    status_url = f"{url}/api/status"
    for _ in range(60):
        try:
            with urllib.request.urlopen(status_url, timeout=1) as response:
                payload = json.loads(response.read().decode("utf-8"))
            if "state" in payload and "model" in payload:
                webbrowser.open(url)
                return
        except (OSError, ValueError, json.JSONDecodeError):
            time.sleep(0.25)


if __name__ == "__main__":
    # Console Windows mặc định là cp1252 nên in tiếng Việt sẽ ném UnicodeEncodeError.
    for luong in (sys.stdout, sys.stderr):
        if hasattr(luong, "reconfigure"):
            luong.reconfigure(encoding="utf-8", errors="replace")
    host = os.getenv("RAG_HOST", "127.0.0.1")
    port = chon_cong_trong(host)
    url = f"http://{host}:{port}"
    print(f"Giao diện: {url}", flush=True)
    if os.getenv("RAG_OPEN_BROWSER", "1") == "1":
        threading.Thread(
            target=mo_trinh_duyet_khi_dung_ung_dung,
            args=(url,),
            daemon=True,
            name="open-browser",
        ).start()
    uvicorn.run(
        "api:app",
        host=host,
        port=port,
        reload=False,
    )
