"""Tách các vector thuộc data_giao_duc từ chỉ mục cũ mà không embed lại."""

from __future__ import annotations

import json
import os
from collections import defaultdict

from langchain_community.vectorstores import FAISS
from langchain_ollama import OllamaEmbeddings

from chunking_utils import tinh_hash_file
from main import (
    DATA_PATH,
    DINH_DANG_HO_TRO,
    DUONG_DAN_LUU_INDEX,
    DUONG_DAN_SO_GHI_CHEP,
    THU_MUC_DU_AN,
)


INDEX_CU = os.path.join(THU_MUC_DU_AN, "faiss_index_giaoduc_ollama")
SO_GHI_CHEP_CU = os.path.join(THU_MUC_DU_AN, "file_da_xu_ly.json")


def quet_file_cuc_bo() -> dict[str, str]:
    ket_qua = {}
    for thu_muc, _, ten_files in os.walk(DATA_PATH):
        for ten_file in ten_files:
            duong_dan = os.path.join(thu_muc, ten_file)
            if os.path.splitext(ten_file)[1].lower() in DINH_DANG_HO_TRO:
                ket_qua[duong_dan] = tinh_hash_file(duong_dan)
    return ket_qua


def main() -> None:
    with open(SO_GHI_CHEP_CU, encoding="utf-8") as file:
        so_cu = json.load(file)

    file_cuc_bo = quet_file_cuc_bo()
    file_theo_hash = defaultdict(list)
    for duong_dan, file_hash in file_cuc_bo.items():
        file_theo_hash[file_hash].append(duong_dan)

    hash_theo_ten_cu = defaultdict(set)
    for duong_dan, ban_ghi in so_cu.items():
        file_hash = ban_ghi.get("hash")
        if file_hash:
            hash_theo_ten_cu[os.path.basename(duong_dan)].add(file_hash)

    embeddings = OllamaEmbeddings(
        model=os.getenv("RAG_EMBEDDING_MODEL", "bge-m3"),
        base_url=os.getenv("OLLAMA_BASE_URL", "http://localhost:11434"),
    )
    vector_store = FAISS.load_local(
        INDEX_CU, embeddings, allow_dangerous_deserialization=True
    )

    id_can_xoa = []
    for doc_id, document in vector_store.docstore._dict.items():
        ten_nguon_cu = document.metadata.get("source_file", "")
        hash_khop = sorted(hash_theo_ten_cu[ten_nguon_cu] & file_theo_hash.keys())
        if not hash_khop:
            id_can_xoa.append(doc_id)
            continue

        # Các tên quá dài có thể đã được rút gọn lúc giải nén. Metadata được
        # đổi sang đúng đường dẫn cục bộ để nguồn hiển thị không còn trỏ Drive.
        duong_dan_moi = sorted(file_theo_hash[hash_khop[0]])[0]
        document.metadata["source"] = duong_dan_moi
        document.metadata["source_file"] = os.path.basename(duong_dan_moi)
        document.metadata["loai_thu_muc"] = os.path.relpath(
            duong_dan_moi, DATA_PATH
        ).split(os.sep)[0]

    if id_can_xoa:
        vector_store.delete(id_can_xoa)
    if vector_store.index.ntotal == 0:
        raise RuntimeError("Không tìm thấy vector nào thuộc kho data_giao_duc.")

    vector_store.save_local(DUONG_DAN_LUU_INDEX)

    chunk_ids_theo_nguon = defaultdict(list)
    for doc_id, document in vector_store.docstore._dict.items():
        chunk_ids_theo_nguon[document.metadata.get("source", "")].append(doc_id)
    so_nguon_co_van_ban = len(chunk_ids_theo_nguon)

    so_moi = {}
    hash_da_ghi = set()
    for duong_dan, file_hash in sorted(file_cuc_bo.items()):
        la_ban_trung = file_hash in hash_da_ghi
        chunk_ids = [] if la_ban_trung else chunk_ids_theo_nguon.get(duong_dan, [])
        thong_tin = os.stat(duong_dan)
        so_moi[duong_dan] = {
            "hash": file_hash,
            "chunk_ids": chunk_ids,
            "status": (
                "duplicate" if la_ban_trung
                else "processed" if chunk_ids
                else "no_text"
            ),
            "size": thong_tin.st_size,
            "modified_ns": thong_tin.st_mtime_ns,
        }
        hash_da_ghi.add(file_hash)

    with open(DUONG_DAN_SO_GHI_CHEP, "w", encoding="utf-8") as file:
        json.dump(so_moi, file, ensure_ascii=False, indent=2)

    print(f"Tệp dữ liệu cục bộ: {len(file_cuc_bo)}")
    print(f"Vector được giữ lại: {vector_store.index.ntotal}")
    print(f"Nguồn có văn bản: {so_nguon_co_van_ban}")
    print(f"Đã lưu chỉ mục: {DUONG_DAN_LUU_INDEX}")
    print(f"Đã lưu sổ ghi chép: {DUONG_DAN_SO_GHI_CHEP}")


if __name__ == "__main__":
    main()
