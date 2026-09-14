# -*- coding: utf-8 -*-
"""
TRÍCH METADATA VĂN BẢN BẰNG LLM
================================
van_ban_meta.py trích số hiệu bằng regex trên khối tiêu đề. Cách đó chịu thua ở
hai chỗ, và cả hai đều rất phổ biến trong kho này:

  1. OCR làm nát chính dòng số hiệu: "Sốf92 /QĐ-TTg", "Sá:v4ố /2023/TT-BGDĐT",
     hoặc con dấu "CỔNG THÔNG TIN ĐIỆN TỬ CHÍNH PHỦ" đè lên ("...CHÍNH 3QĐ-TTg").
  2. Bản dự thảo bỏ trống ô số hiệu ("Số:    /2026/TT-BGDĐT"). Regex không phân
     biệt được "chưa có số" với "có số nhưng đọc không ra", nên hoặc bỏ sót,
     hoặc tệ hơn là bịa số từ tên file.

LLM đọc được cả hai. Nhưng LLM cũng bịa được, mà số hiệu bịa thì nguy hiểm hơn
số hiệu thiếu: nó đẻ ra quan hệ hiệu lực sai, và trong đồ thị Neo4j thì hai văn
bản khác nhau có thể bị MERGE thành một node. Nên mọi kết quả đều phải qua
_hop_le(): chữ số của số hiệu BẮT BUỘC phải xuất hiện trong chính đoạn text đã
đưa cho model. Không tìm thấy thì ghi null, chấp nhận thiếu.

Tên file KHÔNG được dùng làm nguồn: với các file .signed.pdf tải từ cổng thông
tin, số đầu tên file là ID tải về chứ không phải số hiệu ("1483-ttg.signed.pdf"
thật ra là Quyết định 92/QĐ-TTg).

Chạy:
    python trich_meta_llm.py                # toàn bộ file cần trích
    python trich_meta_llm.py --gioi-han 5   # thử 5 file
    python trich_meta_llm.py --tat-ca       # trích lại cả file đã có số hiệu chắc
Kết quả ghi dần vào meta_llm.json (dừng giữa chừng chạy lại không mất gì).
"""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
import time
from datetime import date

import requests

THU_MUC_DU_AN = os.path.dirname(os.path.abspath(__file__))
DUONG_DAN_KET_QUA = os.path.join(THU_MUC_DU_AN, "meta_llm.json")
OLLAMA_URL = os.getenv("OLLAMA_BASE_URL", "http://localhost:11434")
MODEL = os.getenv("RAG_META_MODEL", "qwen3.5:4b")

# Khối tiêu đề nằm gọn trong khoảng này. Lấy dài hơn chỉ tổ nhét thêm phần
# "Căn cứ ..." đầy số hiệu của văn bản KHÁC vào ngữ cảnh, làm model nhầm.
DO_DAI_TIEU_DE = 1400
THOI_GIAN_CHO = 240

HUONG_DAN = """Bạn đọc khối tiêu đề của một văn bản quy phạm pháp luật Việt Nam.
Văn bản này được quét từ ảnh nên chữ có thể sai, dính, mất dấu.

Trả về DUY NHẤT một JSON với các khóa:
  "so_hieu": số hiệu của CHÍNH văn bản này, ví dụ "27/2020/TT-BGDĐT", "92/QĐ-TTg",
             "81/2021/NĐ-CP". Nếu ô số hiệu bỏ trống hoặc không đọc ra được chữ số
             thì để null. TUYỆT ĐỐI không đoán, không lấy số hiệu của văn bản được
             viện dẫn ở phần "Căn cứ".
  "ngay_ban_hanh": "YYYY-MM-DD", không có thì null.
  "co_quan": cơ quan ban hành, ví dụ "Bộ Giáo dục và Đào tạo". Không có thì null.
  "loai": "Thông tư" | "Nghị định" | "Quyết định" | "Nghị quyết" | "Chỉ thị" |
          "Luật" | "Công văn" | "Thông báo" | null
  "la_du_thao": true nếu ô số hiệu hoặc ô ngày còn bỏ trống, hoặc có chữ
                "DỰ THẢO". Ngược lại false.

Chỉ trả JSON, không giải thích."""

MAU_CHU_SO = re.compile(r"\d+")


def _hop_le(so_hieu: str | None, nguon: str) -> tuple[str | None, str]:
    """
    Trả về (số hiệu đã nhận, lý do từ chối). Ba cửa phải qua hết:
      1. Đúng dạng số hiệu Việt Nam.
      2. Phần số đứng đầu phải THỰC SỰ có trong text - chặn model bịa.
      3. Không phải năm trá hình ("2025/TT-BGDĐT" khi ô số bỏ trống).

    Cửa 1 giao hẳn cho van_ban_meta.trich_so_hieu() chứ không tự viết regex:
    nó vừa kiểm dạng vừa chuẩn hoá, và quan trọng hơn là chuẩn hoá GIỐNG HỆT
    phía regex. Tự chuẩn hoá thì "92/QĐ-TTg" thành "92/QĐ-TTG", và tới bước
    dựng đồ thị sẽ đẻ ra hai node VanBan cho cùng một Quyết định.
    """
    import van_ban_meta as vbm

    if not so_hieu or not str(so_hieu).strip():
        return None, ""
    tho = re.sub(r"\s+", "", str(so_hieu)).replace("–", "-")
    cac_so_hieu = vbm.trich_so_hieu(tho)
    if len(cac_so_hieu) != 1:
        return None, f"sai dạng: {tho}"
    sh = cac_so_hieu[0]
    phan = sh.split("/")
    phan_so = phan[0]
    # Dò trong TỪNG cụm chữ số, không dò trong chuỗi đã nối liền: nối liền thì
    # "26" khớp bừa ở chỗ giáp ranh giữa "...2021" và "2026..." rồi nhận một số
    # hiệu chưa từng có trong văn bản. Vẫn dùng "in" chứ không "==" vì OCR hay
    # dính ký tự rác vào cụm số ("Sốf92" -> cụm "92", "CHÍNH 3QĐ" -> cụm "3").
    if not any(phan_so in cum for cum in MAU_CHU_SO.findall(nguon)):
        return None, f"không thấy '{phan_so}' trong text (nghi bịa)"
    # "Số: /2025/TT-BGDĐT" bỏ trống rất hay bị model đọc thành "2025/2025/...".
    # Chỉ chặn đúng ca đó, không chặn mọi số 4 chữ số: 1969/QĐ-TTg là số hiệu thật.
    if len(phan) == 3 and phan_so == phan[1]:
        return None, f"lấy năm làm số hiệu: {sh}"
    return sh, ""


def _ngay_hop_le(ngay: str | None) -> str | None:
    """
    OCR đọc "ngày 15" ra "ngày 45" thì model ngoan ngoãn trả về "2025-09-45".
    Ngày vô lý mà lọt vào hồ sơ thì mọi so sánh hiệu lực sau này đều sai, nên
    thà bỏ trống.
    """
    if not ngay:
        return None
    try:
        date.fromisoformat(str(ngay).strip())
    except (ValueError, TypeError):
        return None
    return str(ngay).strip()


def _la_du_thao(ten_file: str, kq: dict) -> bool:
    """
    Model không phân biệt được "ô số hiệu bỏ trống" (dự thảo thật) với "ô số
    hiệu bị con dấu đè mất" (bản đã ký, OCR thua) - cả hai đều nhìn ra ô trống.
    Tên file phân biệt hộ: cổng thông tin chỉ sinh đuôi .signed.pdf cho bản đã
    ký ban hành, mà đó là chữ gõ máy nên không bị OCR làm sai.
    """
    if ".signed." in ten_file.lower():
        return False
    return bool(kq.get("la_du_thao"))


def _goi_model(tieu_de: str) -> dict:
    r = requests.post(
        f"{OLLAMA_URL}/api/chat",
        json={
            "model": MODEL,
            "format": "json",
            "stream": False,
            "think": False,
            "messages": [
                {"role": "system", "content": HUONG_DAN},
                {"role": "user", "content": tieu_de},
            ],
            "options": {"temperature": 0, "num_ctx": 2048, "num_predict": 200},
        },
        timeout=THOI_GIAN_CHO,
    )
    r.raise_for_status()
    return json.loads(r.json()["message"]["content"])


def nap_tieu_de() -> dict[str, str]:
    """Khối tiêu đề của từng file, đọc từ chính các chunk đã lập chỉ mục."""
    from langchain_community.vectorstores import FAISS
    from main import DUONG_DAN_LUU_INDEX

    class _Rong:
        def embed_query(self, t):
            return [0.0]

        def embed_documents(self, ts):
            return [[0.0]] * len(ts)

    vs = FAISS.load_local(
        DUONG_DAN_LUU_INDEX, _Rong(), allow_dangerous_deserialization=True
    )
    gom: dict[str, list[str]] = {}
    for doc in vs.docstore._dict.values():
        ten = doc.metadata.get("source_file")
        if ten:
            gom.setdefault(ten, []).append(doc.page_content)
    return {ten: "\n".join(phan)[:DO_DAI_TIEU_DE] for ten, phan in gom.items()}


def chon_file_can_trich(tieu_de: dict[str, str], tat_ca: bool) -> list[str]:
    """
    Chỉ trích những file đáng trích:
      - Là văn bản quy phạm (có quốc hiệu hoặc "Căn cứ" ở tiêu đề). Giáo án
        .pptx, ma trận đề .docx, thời khoá biểu .xlsx không có số hiệu là đúng,
        đưa vào chỉ tốn mỗi file nửa phút để nhận về null.
      - Chưa có số hiệu, hoặc số hiệu hiện tại chỉ là suy đoán (uoc_doan).
    """
    import van_ban_meta as vbm

    mau_qppl = re.compile(
        r"C[ỘÔOQ][NC]G\s*H[OÒÓ]A\s*X[AÃ]\s*H[ỘÔO]I|C[ăâa]n\s*c[ứưu]\b",
        re.IGNORECASE,
    )
    ho_so = vbm.tai_ho_so()
    can_trich = []
    for ten, text in tieu_de.items():
        if not mau_qppl.search(text):
            continue
        muc = ho_so.get(ten)
        if tat_ca or muc is None or not muc.so_hieu or muc.so_hieu_uoc_doan:
            can_trich.append(ten)
    return can_trich


def main() -> int:
    bo_cuc = argparse.ArgumentParser(description="Trích metadata văn bản bằng LLM")
    bo_cuc.add_argument("--gioi-han", type=int, default=0, help="chỉ chạy N file đầu")
    bo_cuc.add_argument("--tat-ca", action="store_true", help="trích lại cả file đã chắc")
    bo_cuc.add_argument("--chi", nargs="*", help="chỉ chạy đúng các file này")
    tham_so = bo_cuc.parse_args()

    sys.path.insert(0, THU_MUC_DU_AN)
    print(f"Model: {MODEL}  |  Ollama: {OLLAMA_URL}")
    tieu_de = nap_tieu_de()
    print(f"Đã nạp tiêu đề của {len(tieu_de)} file từ chỉ mục.")

    da_co = {}
    if os.path.exists(DUONG_DAN_KET_QUA):
        with open(DUONG_DAN_KET_QUA, encoding="utf-8") as f:
            da_co = json.load(f)
        print(f"Đã có sẵn {len(da_co)} kết quả trong meta_llm.json.")

    if tham_so.chi:
        can_trich = [t for t in tieu_de if any(t.startswith(p) for p in tham_so.chi)]
    else:
        can_trich = chon_file_can_trich(tieu_de, tham_so.tat_ca)
        can_trich = [t for t in can_trich if t not in da_co]
    if tham_so.gioi_han:
        can_trich = can_trich[: tham_so.gioi_han]

    print(f"Cần trích: {len(can_trich)} file")
    print("=" * 72)
    thong_ke = {"co_so_hieu": 0, "du_thao": 0, "null": 0, "tu_choi": 0, "loi": 0}
    bat_dau = time.time()

    for i, ten in enumerate(can_trich, 1):
        text = tieu_de[ten]
        t0 = time.time()
        try:
            kq = _goi_model(text)
        except Exception as exc:
            print(f"[{i}/{len(can_trich)}] x {ten[:60]}  LOI: {exc}")
            thong_ke["loi"] += 1
            continue

        sh_tho = kq.get("so_hieu")
        sh, ly_do = _hop_le(sh_tho, text)
        if sh_tho and not sh:
            thong_ke["tu_choi"] += 1
        muc = {
            "so_hieu": sh,
            "ngay_ban_hanh": _ngay_hop_le(kq.get("ngay_ban_hanh")),
            "co_quan": kq.get("co_quan") or None,
            "loai": kq.get("loai") or None,
            "la_du_thao": _la_du_thao(ten, kq),
            "so_hieu_llm_tho": sh_tho if sh_tho != sh else None,
            "ly_do_tu_choi": ly_do or None,
        }
        da_co[ten] = muc
        with open(DUONG_DAN_KET_QUA, "w", encoding="utf-8") as f:
            json.dump(da_co, f, ensure_ascii=False, indent=1)

        if sh:
            thong_ke["co_so_hieu"] += 1
            nhan = f"OK {sh}"
        elif muc["la_du_thao"]:
            thong_ke["du_thao"] += 1
            nhan = "~  du thao (chua co so)"
        else:
            thong_ke["null"] += 1
            nhan = ".  khong doc duoc"
        canh_bao = f"   [tu choi: {ly_do}]" if ly_do else ""
        print(
            f"[{i}/{len(can_trich)}] {nhan:34s} {time.time()-t0:5.1f}s  "
            f"{ten[:52]}{canh_bao}"
        )

    print("=" * 72)
    tong = time.time() - bat_dau
    print(f"Xong {len(can_trich)} file trong {tong/60:.1f} phut.")
    print(f"  co so hieu : {thong_ke['co_so_hieu']}")
    print(f"  du thao    : {thong_ke['du_thao']}")
    print(f"  khong doc  : {thong_ke['null']}")
    print(f"  bi tu choi : {thong_ke['tu_choi']}  (model tra so nhung khong co trong text)")
    print(f"  loi goi    : {thong_ke['loi']}")
    print(f"-> {DUONG_DAN_KET_QUA}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
