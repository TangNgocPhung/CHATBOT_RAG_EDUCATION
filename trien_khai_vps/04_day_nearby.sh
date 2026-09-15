#!/usr/bin/env bash
# =====================================================================
#  DAY MA NGUON NEARBY (location-recommendation) LEN VPS
# =====================================================================
#  Chay TREN MAY WINDOWS nay (Git Bash):
#      bash trien_khai_vps/04_day_nearby.sh <IP_VPS> [nguoi_dung_ssh]
#
#  Day ~10 MB ma nguon + config/production.env (co mat khau CSDL, chmod 600).
#  KHONG day thu muc osrm/ 2,6 GB: do thi se dung lai tren VPS bang chinh
#  image osrm/osrm-backend:latest - VPS la amd64 nen khong dinh cai bay
#  phien ban arm64 ma RUNBOOK canh bao.
#  KHONG day du lieu POI: chay osm-import tren VPS keo thang tu OpenStreetMap.
# =====================================================================
set -euo pipefail

MAY_CHU="${1:-${VPS_HOST:-}}"
NGUOI_SSH="${2:-${SSH_USER:-debian}}"
KHOA="${SSH_KEY:-$HOME/.ssh/ovh_vps}"
NGUON="${NGUON_NEARBY:-/d/location-recommendation-1}"
THU_MUC_XA="/opt/nearby"

[ -n "$MAY_CHU" ] || { echo "[LOI] Thieu dia chi VPS. Vi du: bash $0 203.0.113.10 debian"; exit 1; }
[ -d "$NGUON" ] || { echo "[LOI] Khong thay thu muc nguon $NGUON"; exit 1; }
[ -f "$NGUON/config/production.env" ] || { echo "[LOI] Thieu $NGUON/config/production.env"; exit 1; }

SSH="ssh -i $KHOA -o StrictHostKeyChecking=accept-new -o ConnectTimeout=15 $NGUOI_SSH@$MAY_CHU"
SCP="scp -i $KHOA -o StrictHostKeyChecking=accept-new"
KIT="$(cd "$(dirname "$0")" && pwd)"

buoc() { echo; echo "--- $*"; }

buoc "Kiem tra VPS"
$SSH 'echo "Dang nhap: $(id -un)"; docker --version || { echo "[LOI] Chua co Docker - chay 01_cai_dat_vps.sh truoc."; exit 1; }
      docker ps >/dev/null 2>&1 || { echo "[LOI] Tai khoan chua dung duoc docker (can dang xuat vao lai sau khi vao nhom docker)."; exit 1; }'

buoc "Day ma nguon Nearby (bo osrm/, .git, node_modules)"
tar -czf - -C "$NGUON" \
  --exclude='./osrm/*.pbf'   --exclude='./osrm/*.osrm*' \
  --exclude='./.git' \
  --exclude='./.git-backups' \
  --exclude='./node_modules' \
  --exclude='./.pnpm-store' \
  --exclude='./previews' \
  --exclude='*.bak-*' \
  --exclude='__pycache__' \
  --exclude='*.pyc' \
  . \
| $SSH "mkdir -p $THU_MUC_XA && tar -xzf - -C $THU_MUC_XA && echo 'Da giai nen vao $THU_MUC_XA'"

buoc "Day lop phu tat container caddy"
$SCP "$KIT/nearby-khong-caddy.yml" "$NGUOI_SSH@$MAY_CHU:$THU_MUC_XA/deploy/khong-dung-caddy.yml" >/dev/null
echo "    -> $THU_MUC_XA/deploy/khong-dung-caddy.yml"

buoc "Day config/production.env (chua mat khau, dat quyen 600)"
$SCP "$NGUON/config/production.env" "$NGUOI_SSH@$MAY_CHU:$THU_MUC_XA/config/production.env" >/dev/null
$SSH "chmod 600 $THU_MUC_XA/config/production.env && echo 'Da dat quyen 600'"

buoc "Doi chieu cau hinh cong khai"
$SSH "cd $THU_MUC_XA && grep -E '^(PUBLIC_HOST|PUBLIC_URL|ALLOWED_ORIGINS|GATEWAY_PORT|OSM_BBOX)=' config/production.env"

echo
echo "=============================================================="
echo " Da day xong ma nguon Nearby."
echo " Cac buoc tiep theo chay TREN VPS (xem deploy/RUNBOOK.md):"
echo "   cd /opt/nearby"
echo "   export COMPOSE=\"docker compose --env-file config/production.env -f docker-compose.yml -f deploy/docker-compose.prod.yml -f deploy/khong-dung-caddy.yml\""
echo "   export OSRM_IMAGE=osrm/osrm-backend:latest"
echo "   bash scripts/build_osrm.sh && bash scripts/build_osrm_foot.sh && bash scripts/build_osrm_motorbike.sh"
echo "   \$COMPOSE up -d database redis opensearch neo4j && \$COMPOSE run --rm migrate"
echo "   \$COMPOSE --profile data run --rm osm-import"
echo "   \$COMPOSE --profile data run --rm search-index"
echo "   \$COMPOSE --profile data run --rm graph-sync"
echo "   \$COMPOSE --profile data run --rm feature-store"
echo "   bash scripts/preflight_production.sh && \$COMPOSE up -d"
echo "=============================================================="
