# -*- coding: utf-8 -*-
"""Sinh hinh 'Cac cong nghe su dung' cho Chatbot RAG Giao duc.

Dung lai dung bang mau va nhip chu cua bieu_do_co_cau_kho.svg de cac hinh
trong bao cao nhin nhu mot bo.
"""
from xml.sax.saxutils import escape

FONT = "'Segoe UI','Helvetica Neue',Arial,sans-serif"
GROUND, PANEL, RULE = "#f4f6f8", "#ffffff", "#dfe5ec"
INK, INK2, INK3 = "#101720", "#4d5a68", "#7d8a97"
XANH, CAM, LUC = "#2a78d6", "#eb6834", "#1baf7a"
NEN = {XANH: "#eaf2fc", CAM: "#fdeee7", LUC: "#e7f7f1"}

W = 1120
LE = 40
COT_TRAI_W = 740
KHE = 24
COT_PHAI_X = LE + COT_TRAI_W + KHE
COT_PHAI_W = W - COT_PHAI_X - LE
DEM = 22
CHIP_H, CHIP_KHE, HANG_KHE = 26, 8, 9

out = []


def do_rong(text, size):
    w = 0.0
    for ch in text:
        if ch in "iIlj|.,:;'!()[]/ ":
            w += 0.31
        elif ch in "mwMW":
            w += 0.86
        elif ch.isdigit():
            w += 0.56
        elif ch.isupper():
            w += 0.66
        else:
            w += 0.535
    return w * size


def chu(x, y, text, size=12.5, weight=400, fill=INK2, anchor=None, spacing=None):
    extra = ' text-anchor="%s"' % anchor if anchor else ""
    extra += ' letter-spacing="%s"' % spacing if spacing else ""
    out.append(
        '<text x="%s" y="%s" font-family="%s" font-size="%s" font-weight="%s" '
        'fill="%s"%s>%s</text>' % (x, y, FONT, size, weight, fill, extra, escape(text))
    )


def khung(x, y, w, h, fill=PANEL, stroke=RULE, rx=10):
    s = ' stroke="%s" stroke-width="1"' % stroke if stroke else ""
    out.append('<rect x="%s" y="%s" width="%s" height="%s" rx="%s" fill="%s"%s/>'
               % (x, y, w, h, rx, fill, s))


def xep_chip(nhan, rong_toi_da):
    """Xep cac chip thanh tung hang theo be ngang cho phep."""
    hang, hien_tai, rong = [], [], 0.0
    for ten in nhan:
        w = do_rong(ten, 12.5) + 24
        them = w if not hien_tai else w + CHIP_KHE
        if hien_tai and rong + them > rong_toi_da:
            hang.append(hien_tai)
            hien_tai, rong = [ten], w
        else:
            hien_tai.append(ten)
            rong += them
    if hien_tai:
        hang.append(hien_tai)
    return hang


def xuong_dong(text, rong_toi_da, size=11.5):
    """Cat mo ta thanh nhieu dong cho vua be ngang panel."""
    dong, hien_tai = [], ""
    for tu in text.split(" "):
        thu = (hien_tai + " " + tu).strip()
        if hien_tai and do_rong(thu, size) > rong_toi_da:
            dong.append(hien_tai)
            hien_tai = tu
        else:
            hien_tai = thu
    if hien_tai:
        dong.append(hien_tai)
    return dong


def cao_panel(hang, so_dong_mo_ta=1):
    return (66 + (so_dong_mo_ta - 1) * 15 + len(hang) * CHIP_H
            + (len(hang) - 1) * HANG_KHE + 20)


def ve_lop(x, y, w, lop, so, hang, dong_mo_ta):
    mau = lop["mau"]
    cao = cao_panel(hang, len(dong_mo_ta))
    khung(x, y, w, cao)
    out.append('<rect x="%s" y="%s" width="4" height="%s" rx="2" fill="%s"/>'
               % (x, y + 14, cao - 28, mau))
    cx = x + DEM
    out.append('<rect x="%s" y="%s" width="22" height="22" rx="7" fill="%s"/>'
               % (cx, y + 18, NEN[mau]))
    chu(cx + 11, y + 33.5, str(so), 12, 600, mau, anchor="middle")
    chu(cx + 32, y + 34, lop["ten"], 15.5, 600, INK)
    for i, dong in enumerate(dong_mo_ta):
        chu(cx, y + 56 + i * 15, dong, 11.5, 400, INK3)

    cy = y + 66 + (len(dong_mo_ta) - 1) * 15
    for cac_chip in hang:
        cx2 = float(x + DEM)
        for ten in cac_chip:
            cw = do_rong(ten, 12.5) + 24
            out.append(
                '<rect x="%.1f" y="%s" width="%.1f" height="%s" rx="6" fill="%s" '
                'stroke="%s" stroke-width="0.7" stroke-opacity="0.35"/>'
                % (cx2, cy, cw, CHIP_H, NEN[mau], mau)
            )
            chu(round(cx2 + cw / 2, 1), cy + 17.5, ten, 12.5, 500, mau, anchor="middle")
            cx2 += cw + CHIP_KHE
        cy += CHIP_H + HANG_KHE
    return cao


TRAI = [
    {
        "ten": "Giao di\u1ec7n ng\u01b0\u1eddi d\u00f9ng",
        "mo_ta": "Trang t\u0129nh do ch\u00ednh FastAPI ph\u1ee5c v\u1ee5 \u00b7 kh\u00f4ng framework, kh\u00f4ng t\u1ea3i th\u01b0 vi\u1ec7n t\u1eeb CDN",
        "mau": XANH,
        "chip": ["HTML5", "CSS3 (bi\u1ebfn CSS, s\u00e1ng/t\u1ed1i)", "JavaScript ES6 thu\u1ea7n",
                 "Fetch + ReadableStream", "localStorage", "SVG n\u1ed9i tuy\u1ebfn",
                 "Responsive (desktop \u00b7 mobile)"],
    },
    {
        "ten": "M\u00e1y ch\u1ee7 & API",
        "mo_ta": "REST cho qu\u1ea3n tr\u1ecb kho, lu\u1ed3ng NDJSON ph\u00e1t c\u00e2u tr\u1ea3 l\u1eddi theo t\u1eebng token",
        "mau": XANH,
        "chip": ["Python 3.11", "FastAPI", "Uvicorn", "Pydantic v2",
                 "StreamingResponse (NDJSON)", "threading (n\u1ec1n)"],
    },
    {
        "ten": "L\u00f5i RAG",
        "mo_ta": "Truy h\u1ed3i lai FAISS + BM25, sinh c\u00e2u tr\u1ea3 l\u1eddi ho\u00e0n to\u00e0n c\u1ee5c b\u1ed9 qua Ollama",
        "mau": XANH,
        "chip": ["LangChain", "Ollama", "bge-m3 (nh\u00fang)", "llama3.2:3b (sinh)",
                 "FAISS (faiss-cpu)", "BM25 (rank_bm25)", "Truy h\u1ed3i lai",
                 "M\u1edf r\u1ed9ng truy v\u1ea5n ti\u1ebfng Vi\u1ec7t", "Cache ng\u1eef ngh\u0129a",
                 "trafilatura (\u0111\u1ecdc URL)", "Ki\u1ec3m tra tr\u00edch d\u1eabn & s\u1ed1 li\u1ec7u"],
    },
    {
        "ten": "N\u1ea1p & x\u1eed l\u00fd t\u00e0i li\u1ec7u",
        "mo_ta": "\u0110\u01b0a PDF, Office, \u1ea3nh scan v\u00e0 video v\u1ec1 v\u0103n b\u1ea3n r\u1ed3i chia \u0111o\u1ea1n theo c\u1ea5u tr\u00fac",
        "mau": CAM,
        "chip": ["pypdf", "docx2txt", "python-pptx", "openpyxl \u00b7 xlrd", "pandas",
                 "unstructured", "Tesseract OCR (vie)", "pypdfium2",
                 "faster-whisper", "PyAV", "pywin32 (COM Word)", "LibreOffice",
                 "Google Drive API v3", "Chia \u0111o\u1ea1n theo c\u1ea5u tr\u00fac"],
    },
    {
        "ten": "L\u01b0u tr\u1eef",
        "mo_ta": "Kh\u00f4ng c\u1ea7n m\u00e1y ch\u1ee7 CSDL: ch\u1ec9 m\u1ee5c, s\u1ed5 ghi ch\u00e9p v\u00e0 l\u1ecbch s\u1eed \u0111\u1ec1u n\u1eb1m tr\u00ean \u0111\u0129a",
        "mau": CAM,
        "chip": ["Ch\u1ec9 m\u1ee5c FAISS", "SQLite (l\u1ecbch s\u1eed chat)",
                 "JSON (h\u1ed3 s\u01a1 \u00b7 s\u1ed5 theo d\u00f5i)", "Cache OCR \u00b7 phi\u00ean \u00e2m",
                 "Th\u01b0 m\u1ee5c t\u1ec7p \u0111\u00ednh k\u00e8m", "Hash t\u1ec7p (c\u1eadp nh\u1eadt t\u0103ng d\u1ea7n)"],
    },
]

PHAI = [
    {
        "ten": "\u0110o l\u01b0\u1eddng ch\u1ea5t l\u01b0\u1ee3ng",
        "mo_ta": "B\u1ed9 127 c\u00e2u h\u1ecfi chu\u1ea9n, \u0111o b\u1eb1ng ch\u1ec9 s\u1ed1 IR kinh \u0111i\u1ec3n",
        "mau": LUC,
        "chip": ["MRR", "Hit@K", "Recall@K", "nDCG@K", "MAP",
                 "C\u1ed5ng ch\u1eb7n l\u1ea1c \u0111\u1ec1", "pytest \u00b7 unittest"],
    },
    {
        "ten": "V\u1eadn h\u00e0nh & tri\u1ec3n khai",
        "mo_ta": "Ch\u1ea1y \u0111\u01b0\u1ee3c tr\u00ean m\u00e1y c\u00e1 nh\u00e2n l\u1eabn m\u00e1y ch\u1ee7 ri\u00eang",
        "mau": LUC,
        "chip": ["Windows 10/11 (.bat)", "Ubuntu VPS", "systemd", "Caddy (HTTPS)",
                 "ufw \u00b7 fail2ban", "Cloudflare Tunnel", "Git \u00b7 GitHub"],
    },
    {
        "ten": "An to\u00e0n & quy\u1ec1n ri\u00eang t\u01b0",
        "mo_ta": "Kh\u00f3a c\u1eeda tr\u01b0\u1edbc khi \u0111\u01b0a ra Internet",
        "mau": LUC,
        "chip": ["HTTP Basic Auth", "hmac.compare_digest",
                 "Ch\u1eb7n IP n\u1ed9i b\u1ed9 khi t\u1ea3i URL", "Gi\u1edbi h\u1ea1n dung l\u01b0\u1ee3ng t\u1ec7p",
                 "T\u1eeb ch\u1ed1i ch\u1ea1y n\u1ebfu thi\u1ebfu m\u1eadt kh\u1ea9u", "D\u1eef li\u1ec7u ri\u00eang kh\u00f4ng l\u00ean Git"],
    },
]

rong_trai = COT_TRAI_W - 2 * DEM
rong_phai = COT_PHAI_W - 2 * DEM
hang_trai = [xep_chip(l["chip"], rong_trai) for l in TRAI]
hang_phai = [xep_chip(l["chip"], rong_phai) for l in PHAI]
mo_ta_trai = [xuong_dong(l["mo_ta"], rong_trai) for l in TRAI]
mo_ta_phai = [xuong_dong(l["mo_ta"], rong_phai) for l in PHAI]

# Canh bao som neu mot chip dai hon be ngang panel (se tran ra ngoai vien).
for cot, rong in ((TRAI, rong_trai), (PHAI, rong_phai)):
    for lop in cot:
        for ten in lop["chip"]:
            if do_rong(ten, 12.5) + 24 > rong:
                print("CANH BAO: chip qua dai -", ten)

Y0 = 196
cao_trai = sum(cao_panel(h, len(m)) for h, m in zip(hang_trai, mo_ta_trai)) + 16 * (len(TRAI) - 1)
cao_phai = sum(cao_panel(h, len(m)) for h, m in zip(hang_phai, mo_ta_phai)) + 16 * (len(PHAI) - 1)
H = Y0 + max(cao_trai, cao_phai) + 76

out.append('<svg xmlns="http://www.w3.org/2000/svg" width="%s" height="%s" viewBox="0 0 %s %s">'
           % (W, H, W, H))
out.append('<rect width="%s" height="%s" fill="%s"/>' % (W, H, GROUND))

chu(LE, 44, "C\u00d4NG NGH\u1ec6 S\u1eec D\u1ee4NG \u00b7 CHATBOT RAG GI\u00c1O D\u1ee4C", 11, 600, INK3, spacing="1.6")
chu(LE, 80, "C\u00e1c c\u00f4ng ngh\u1ec7 x\u00e2y d\u1ef1ng ph\u1ea7n m\u1ec1m", 27, 600, INK)
chu(LE, 106, "T\u00e1m l\u1edbp, t\u1eeb giao di\u1ec7n t\u1edbi h\u1ea1 t\u1ea7ng \u00b7 to\u00e0n b\u1ed9 m\u00f4 h\u00ecnh ch\u1ea1y c\u1ee5c b\u1ed9 tr\u00ean CPU",
    14, 400, INK2)

THONG_SO = [("8", "l\u1edbp c\u00f4ng ngh\u1ec7"),
            ("100%", "m\u00f4 h\u00ecnh ch\u1ea1y c\u1ee5c b\u1ed9"),
            ("0", "chi ph\u00ed g\u1ecdi API m\u00f4 h\u00ecnh")]
for i, (so, nhan) in enumerate(THONG_SO):
    x = LE + i * 240
    chu(x, 150, so, 23, 600, INK)
    chu(round(x + do_rong(so, 23) + 10, 1), 150, nhan, 12.5, 400, INK2)
out.append('<line x1="%s" y1="170" x2="%s" y2="170" stroke="%s" stroke-width="1"/>'
           % (LE, W - LE, RULE))

y = Y0
for i, (lop, hang, mo_ta) in enumerate(zip(TRAI, hang_trai, mo_ta_trai), start=1):
    y += ve_lop(LE, y, COT_TRAI_W, lop, i, hang, mo_ta) + 16

y = Y0
for i, (lop, hang, mo_ta) in enumerate(zip(PHAI, hang_phai, mo_ta_phai), start=6):
    y += ve_lop(COT_PHAI_X, y, COT_PHAI_W, lop, i, hang, mo_ta) + 16

chu(LE, H - 34,
    "Ch\u1ec9 \u0111\u1ed3ng b\u1ed9 Google Drive c\u1ea7n Internet; h\u1ecfi \u0111\u00e1p, nh\u00fang, OCR v\u00e0 phi\u00ean \u00e2m \u0111\u1ec1u ch\u1ea1y offline.",
    12, 400, INK3)
out.append("</svg>")

with open(r"D:\Mr_Hai\cong_nghe_su_dung.svg", "w", encoding="utf-8") as f:
    f.write("\n".join(out))
print("OK %sx%s" % (W, H))
