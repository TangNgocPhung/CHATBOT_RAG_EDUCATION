#!/usr/bin/env bash
# =====================================================================
#  DAY MA NGUON + CHI MUC + KHOA NUT QUAN TRI
# =====================================================================
#  Chay TREN MAY WINDOWS nay (Git Bash):
#      bash trien_khai_vps/02_day_ma_nguon.sh <IP_VPS> [nguoi_dung_ssh]
#
#  Khong day: kho tai lieu 4,9 GB (dung 03_day_tai_lieu.sh), .venv,
#  __pycache__, lich su chat, cac ban sao luu *.truoc-khi-*.
#
#  MO HINH BAO VE (khac ban chay o may ca nhan):
#    - Ung dung chay KHONG mat khau: ai co dia chi cung hoi dap duoc.
#    - Caddy chan rieng cac duong dan quan tri bang HTTP Basic, mat khau
#      lay tu mat_khau.bat va bam bcrypt ngay tren VPS.
#  Mat khau khong bao gio in ra man hinh va khong nam tren dong lenh.
# =====================================================================
set -euo pipefail

MAY_CHU="${1:-${VPS_HOST:-}}"
NGUOI_SSH="${2:-${SSH_USER:-root}}"
KHOA="${SSH_KEY:-$HOME/.ssh/ovh_vps}"
THU_MUC_XA="/opt/chatbot-rag"

[ -n "$MAY_CHU" ] || { echo "[LOI] Thieu dia chi VPS. Vi du: bash $0 203.0.113.10 root"; exit 1; }
cd "$(dirname "$0")/.."
[ -f mat_khau.bat ] || { echo "[LOI] Khong thay mat_khau.bat - can co de khoa cac nut quan tri."; exit 1; }
[ -f "$KHOA" ] || { echo "[LOI] Khong thay khoa SSH $KHOA"; exit 1; }

SSH="ssh -i $KHOA -o StrictHostKeyChecking=accept-new -o ConnectTimeout=15 $NGUOI_SSH@$MAY_CHU"
SCP="scp -i $KHOA -o StrictHostKeyChecking=accept-new"
NHU_ROOT="sudo"
NHU_RAG="sudo -u rag"

buoc() { echo; echo "--- $*"; }

buoc "Kiem tra ket noi toi $NGUOI_SSH@$MAY_CHU"
$SSH 'echo "Dang nhap OK voi $(id -un)"
      . /etc/os-release 2>/dev/null && echo "He dieu hanh: $PRETTY_NAME"
      sudo -n true 2>/dev/null || { echo "[LOI] Tai khoan nay khong co quyen sudo khong mat khau."; exit 1; }
      [ -d /opt/chatbot-rag ] || { echo "[LOI] Chua chay 01_cai_dat_vps.sh tren VPS."; exit 1; }'

# ---------------------------------------------------------------------
buoc "Doc mat khau tu mat_khau.bat (khong in ra)"
doc_bien_bat() {  # doc dong dang:  set "TEN=gia tri"   trong file .bat
  local ten="$1" tep="$2"
  grep -i "set \"\?$ten=" "$tep" 2>/dev/null | tail -1 | sed "s/.*$ten=//I; s/\"[[:space:]]*$//" | tr -d '\r'
}
TAI_KHOAN="$(doc_bien_bat RAG_TAI_KHOAN mat_khau.bat)"; TAI_KHOAN="${TAI_KHOAN:-giaovien}"
MAT_KHAU="$(doc_bien_bat RAG_MAT_KHAU mat_khau.bat)"
[ -n "$MAT_KHAU" ] && [ "$MAT_KHAU" != "DAT_MAT_KHAU_VAO_DAY" ] \
  || { echo "[LOI] mat_khau.bat chua dat mat khau that."; exit 1; }
KHOA_DRIVE=""
[ -f khoa_api.bat ] && KHOA_DRIVE="$(doc_bien_bat RAG_DRIVE_API_KEY khoa_api.bat)"

umask 077
TEP_TAM="$(mktemp)"; TEP_MK="$(mktemp)"
trap 'rm -f "$TEP_TAM" "$TEP_MK"' EXIT
printf '%s' "$MAT_KHAU" > "$TEP_MK"
{
  echo "# Sinh tu 02_day_ma_nguon.sh - sua mat_khau.bat roi chay lai, dung sua tay."
  echo "# Lop mat khau CUA UNG DUNG tat han: Caddy lo viec chan, va chi chan cac"
  echo "# duong dan quan tri. Xem /etc/caddy/quantri.caddy."
  echo "RAG_CONG_KHAI=0"
  echo "RAG_TAI_KHOAN=$TAI_KHOAN"
  echo "RAG_MAT_KHAU="
  echo "RAG_HOST=127.0.0.1"
  echo "RAG_PORT=8010"
  echo "RAG_LLM_MODEL=${RAG_LLM_MODEL:-llama3.2:3b}"
  echo "RAG_EMBEDDING_MODEL=${RAG_EMBEDDING_MODEL:-bge-m3}"
  echo "OLLAMA_BASE_URL=http://127.0.0.1:11434"
  echo "PYTHONUNBUFFERED=1"
  echo "PYTHONIOENCODING=utf-8"
  [ -n "$KHOA_DRIVE" ] && echo "RAG_DRIVE_API_KEY=$KHOA_DRIVE"
} > "$TEP_TAM"
unset MAT_KHAU KHOA_DRIVE
$SCP "$TEP_TAM" "$NGUOI_SSH@$MAY_CHU:/tmp/chatbot-rag.env" >/dev/null
$SCP "$TEP_MK"  "$NGUOI_SSH@$MAY_CHU:/tmp/mk.txt" >/dev/null
$SSH "$NHU_ROOT install -o root -g rag -m 640 /tmp/chatbot-rag.env /etc/chatbot-rag.env && rm -f /tmp/chatbot-rag.env && echo 'Da ghi /etc/chatbot-rag.env'"

# KHOA_QUAN_TRI=1 thi dat mat khau cho cac duong dan quan tri; mac dinh 0 =
# khong chan gi, dung yeu cau "bo het cho hoi mat khau" ngay 15/09/2026.
if [ "${KHOA_QUAN_TRI:-0}" = "1" ]; then
buoc "Khoa cac nut quan tri trong Caddy (bam bcrypt ngay tren VPS)"
$SSH "$NHU_ROOT bash -s -- '$TAI_KHOAN'" <<'REMOTE_MK'
set -eu
TAI_KHOAN="$1"
BAM=$(caddy hash-password --plaintext "$(cat /tmp/mk.txt)")
shred -u /tmp/mk.txt 2>/dev/null || rm -f /tmp/mk.txt
printf 'basic_auth @quantri {\n\t%s %s\n}\n' "$TAI_KHOAN" "$BAM" > /etc/caddy/quantri.caddy
chmod 644 /etc/caddy/quantri.caddy
caddy validate --config /etc/caddy/Caddyfile --adapter caddyfile >/dev/null 2>&1 \
  && systemctl reload caddy && echo "Da khoa nut quan tri cho tai khoan $TAI_KHOAN" \
  || { echo "[LOI] Caddyfile khong hop le - xem: caddy validate --config /etc/caddy/Caddyfile"; exit 1; }
REMOTE_MK
else
buoc "Khong dat mat khau cho nut quan tri (dat KHOA_QUAN_TRI=1 neu muon bat lai)"
$SSH "$NHU_ROOT bash -c 'rm -f /tmp/mk.txt; printf \"# Khong chan duong dan nao. Dat KHOA_QUAN_TRI=1 khi chay 02_day_ma_nguon.sh de bat lai.\n\" > /etc/caddy/quantri.caddy; caddy validate --config /etc/caddy/Caddyfile --adapter caddyfile >/dev/null 2>&1 && systemctl reload caddy && echo \"Moi duong dan deu mo\"'"
fi

# ---------------------------------------------------------------------
buoc "Day ma nguon + giao dien + chi muc FAISS + tessdata (khoang 115 MB)"
# tessdata PHAI di kem: ocr_pdf.py tim vie.traineddata trong thu muc tessdata
# cua du an, thieu no thi PDF scan im lang tra ve rong, khong bao loi gi.
tar -czf - \
  --exclude='__pycache__' \
  --exclude='*.pyc' \
  --exclude='*.truoc-khi-*' \
  *.py requirements.txt README.md HUONG_DAN_*.md \
  static tests trien_khai_vps tessdata \
  cai_dat.json bo_cau_hoi_benchmark.json \
  data_giao_duc_da_xu_ly.json ho_so_van_ban.json phan_loai_tai_lieu.json \
  tinh_trang_hieu_luc.json meta_llm.json drive_state.json drive_manifest.json \
  faiss_index_data_giao_duc/index.faiss faiss_index_data_giao_duc/index.pkl \
| $SSH "$NHU_ROOT tar -xzf - -C $THU_MUC_XA && $NHU_ROOT chown -R rag:rag $THU_MUC_XA && echo 'Da giai nen tren VPS'"

# ---------------------------------------------------------------------
buoc "Doi duong dan trong so ghi chep tu Windows sang Linux"
# data_giao_duc_da_xu_ly.json khoa theo duong dan TUYET DOI. Giu nguyen dang
# "D:\Mr_Hai\..." thi tren VPS moi tep deu trong nhu tep moi, va lan cap nhat
# chi muc dau tien se embed lai TOAN BO kho - nhieu gio CPU khong can thiet.
$SSH "$NHU_ROOT python3 - <<'PYEOF'
import json, pathlib, shutil, datetime
p = pathlib.Path('/opt/chatbot-rag/data_giao_duc_da_xu_ly.json')
d = json.loads(p.read_text(encoding='utf-8'))
GOC = '/opt/chatbot-rag/ollama-rag-desktop/data_giao_duc'
moi, doi = {}, 0
for khoa, gt in d.items():
    if 'data_giao_duc' in khoa and ('\\' in khoa or khoa[1:3] == ':\\'):
        moi[GOC + '/' + khoa.replace('\\', '/').split('data_giao_duc/', 1)[-1]] = gt
        doi += 1
    else:
        moi[khoa] = gt
if doi:
    shutil.copy2(p, p.with_name(p.name + datetime.datetime.now().strftime('.truoc-khi-doi-duong-dan-%Y%m%d-%H%M%S')))
    p.write_text(json.dumps(moi, ensure_ascii=False, indent=1), encoding='utf-8')
tep = {str(x) for x in pathlib.Path(GOC).rglob('*') if x.is_file()} if pathlib.Path(GOC).exists() else set()
print(f'Da doi {doi} duong dan. Tep tren dia: {len(tep)}, khop so ghi chep: {len(tep & set(moi))}, chua co chi muc: {len(tep - set(moi))}')
PYEOF
$NHU_ROOT chown rag:rag /opt/chatbot-rag/data_giao_duc_da_xu_ly.json*"

# ---------------------------------------------------------------------
buoc "Cai thu vien Python theo requirements.txt (lan dau mat vai phut)"
$SSH "$NHU_RAG $THU_MUC_XA/.venv/bin/python -m pip install -q --upgrade pip wheel setuptools && \
      $NHU_RAG $THU_MUC_XA/.venv/bin/python -m pip install -r $THU_MUC_XA/requirements.txt"

buoc "Kiem tra OCR da san sang chua"
$SSH "cd $THU_MUC_XA && $NHU_RAG ./.venv/bin/python -c \"
import ocr_pdf
ok, thong_bao = ocr_pdf.san_sang()
print('Tesseract:', ocr_pdf.tim_tesseract(), '| OCR:', thong_bao)
\""

# ---------------------------------------------------------------------
buoc "Khoi dong dich vu va cho nap kho tri thuc (toi da 10 phut)"
$SSH "$NHU_ROOT bash -s" <<'REMOTE'
set -u
systemctl restart chatbot-rag
sleep 5
systemctl --no-pager --lines=8 status chatbot-rag || true
echo
for i in $(seq 1 120); do
  tt=$(curl -s http://127.0.0.1:8010/api/status 2>/dev/null | head -c 500)
  case "$tt" in
    *'"state":"ready"'*)  echo; echo "SAN SANG: $tt"; exit 0 ;;
    *'"state":"error"'*)  echo; echo "[LOI] $tt"; exit 1 ;;
    *) printf '.' ;;
  esac
  sleep 5
done
echo; echo "[canh bao] Qua 10 phut chua san sang. Xem: sudo journalctl -u chatbot-rag -n 50"
REMOTE

echo
echo "=============================================================="
echo " XONG PHAN MA NGUON."
echo " Tiep theo: bash trien_khai_vps/03_day_tai_lieu.sh <IP_VPS> root"
echo "=============================================================="
