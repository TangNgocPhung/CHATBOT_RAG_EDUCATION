#!/usr/bin/env bash
# =====================================================================
#  DAY KHO TAI LIEU GOC (4,9 GB) LEN VPS
# =====================================================================
#  Chay TREN MAY WINDOWS nay (Git Bash):
#      bash trien_khai_vps/03_day_tai_lieu.sh <IP_VPS> [nguoi_dung_ssh]
#
#  Cach lam: so sanh ten + kich thuoc hai ben, chi day nhung file VPS
#  chua co hoac khac kich thuoc. Day tu nho den lon theo tung me, nen
#  dut mang giua chung thi chay lai la di tiep, khong lam lai tu dau.
#
#  Tuy chon (dat truoc lenh):
#      BO_QUA_LON_HON_MB=200   bo qua file lon hon 200 MB (video nang)
#      ME_MB=250               kich thuoc moi me, mac dinh 250 MB
# =====================================================================
set -euo pipefail

MAY_CHU="${1:-${VPS_HOST:-}}"
NGUOI_SSH="${2:-${SSH_USER:-debian}}"
KHOA="${SSH_KEY:-$HOME/.ssh/ovh_vps}"
ME_MB="${ME_MB:-250}"
BO_QUA_LON_HON_MB="${BO_QUA_LON_HON_MB:-0}"

THU_MUC_XA="/opt/chatbot-rag/ollama-rag-desktop/data_giao_duc"

[ -n "$MAY_CHU" ] || { echo "[LOI] Thieu dia chi VPS. Vi du: bash $0 51.222.x.x debian"; exit 1; }
cd "$(dirname "$0")/.."
THU_MUC_CUC_BO="$PWD/ollama-rag-desktop/data_giao_duc"
[ -d "$THU_MUC_CUC_BO" ] || { echo "[LOI] Khong thay kho tai lieu $THU_MUC_CUC_BO"; exit 1; }

SSH="ssh -i $KHOA -o StrictHostKeyChecking=accept-new -o ServerAliveInterval=20 -o ServerAliveCountMax=3 $NGUOI_SSH@$MAY_CHU"

TAM="$(mktemp -d)"
trap 'rm -rf "$TAM"' EXIT

echo "--- Lay danh sach file dang co tren VPS"
$SSH "mkdir -p '$THU_MUC_XA' 2>/dev/null; cd '$THU_MUC_XA' && find . -type f -printf '%s\t%P\n' 2>/dev/null" > "$TAM/xa.txt" || true
echo "    VPS dang co: $(wc -l < "$TAM/xa.txt") file"

echo "--- Quet kho tai lieu tren may nay"
( cd "$THU_MUC_CUC_BO" && find . -type f -printf '%s\t%P\n' ) > "$TAM/cuc_bo.txt"
echo "    May nay co:  $(wc -l < "$TAM/cuc_bo.txt") file"

# So sanh: chi giu file VPS chua co, hoac co ma khac kich thuoc.
awk -F'\t' -v gioi_han_mb="$BO_QUA_LON_HON_MB" '
  # So theo TEN TEP chu khong dung NR==FNR: khi danh sach phia VPS rong,
  # NR==FNR van dung o dong dau tien cua tep thu hai va awk se nhet ca kho
  # cuc bo vao mang "da co" -> khong day gi het.
  FILENAME == ARGV[1] { co[$2]=$1; next }
  {
    if (gioi_han_mb > 0 && $1 > gioi_han_mb*1048576) { bo_qua++; next }
    if (!($2 in co) || co[$2] != $1) print $1 "\t" $2
  }
  END { if (bo_qua) printf("    Bo qua %d file lon hon %s MB\n", bo_qua, gioi_han_mb) > "/dev/stderr" }
' "$TAM/xa.txt" "$TAM/cuc_bo.txt" | sort -n > "$TAM/can_day.txt"

SO_FILE=$(wc -l < "$TAM/can_day.txt")
TONG_BYTE=$(awk -F'\t' '{s+=$1} END {printf "%.0f", s+0}' "$TAM/can_day.txt")
if [ "$SO_FILE" -eq 0 ]; then
  echo; echo "Kho tai lieu tren VPS da day du. Khong co gi de day."; exit 0
fi
echo
echo "=============================================================="
printf " Can day: %s file, tong %.2f GB\n" "$SO_FILE" "$(awk -v b="$TONG_BYTE" 'BEGIN{print b/1073741824}')"
echo " Day tu nho den lon. Dut mang thi chay lai lenh nay la di tiep."
echo "=============================================================="

BAT_DAU=$(date +%s)
DA_GUI_BYTE=0
ME_BYTE=$(( ME_MB * 1048576 ))
me_so=0

# Gom thanh tung me, ten file phan cach bang NUL de khong so ten co dau/khoang trang.
: > "$TAM/me_list"
me_byte=0
me_file=0

day_mot_me() {
  [ "$me_file" -eq 0 ] && return 0
  me_so=$(( me_so + 1 ))
  printf "\n[Me %d] %d file, %.1f MB ... " "$me_so" "$me_file" "$(awk -v b="$me_byte" 'BEGIN{print b/1048576}')"
  tar -cf - -C "$THU_MUC_CUC_BO" --null -T "$TAM/me_list" \
    | $SSH "sudo -u rag tar -xf - -C '$THU_MUC_XA'"
  DA_GUI_BYTE=$(( DA_GUI_BYTE + me_byte ))
  troi_qua=$(( $(date +%s) - BAT_DAU ))
  awk -v da="$DA_GUI_BYTE" -v tong="$TONG_BYTE" -v giay="$troi_qua" 'BEGIN{
    pt = tong>0 ? da*100/tong : 100
    toc = giay>0 ? da/giay/1048576 : 0
    con = toc>0 ? (tong-da)/1048576/toc/60 : 0
    printf "xong. Tien do %.1f%%  |  %.1f MB/s  |  con khoang %.0f phut\n", pt, toc, con
  }'
  : > "$TAM/me_list"
  me_byte=0
  me_file=0
}

while IFS=$'\t' read -r kich_thuoc duong_dan; do
  [ -n "$duong_dan" ] || continue
  printf '%s\0' "$duong_dan" >> "$TAM/me_list"
  me_byte=$(( me_byte + kich_thuoc ))
  me_file=$(( me_file + 1 ))
  if [ "$me_byte" -ge "$ME_BYTE" ]; then day_mot_me; fi
done < "$TAM/can_day.txt"
day_mot_me

echo
echo "--- Kiem tra lai tren VPS"
$SSH "cd '$THU_MUC_XA' && echo \"So file: \$(find . -type f | wc -l)  |  Dung luong: \$(du -sh . | cut -f1)\""
echo
echo "=============================================================="
echo " XONG. Nen khoi dong lai de ung dung dem lai so tai lieu:"
echo "   ssh -i $KHOA $NGUOI_SSH@$MAY_CHU 'sudo systemctl restart chatbot-rag'"
echo "=============================================================="
