#!/usr/bin/env bash
# =====================================================================
#  CAI DAT VPS CHO HAI UNG DUNG   -   Debian 12 hoac Ubuntu 24.04
# =====================================================================
#    - Chatbot RAG Giao duc  (chay thang tren host: Python + Ollama)
#    - Nearby location-recommendation (11 container Docker)
#
#  Chay TREN VPS voi quyen root:  sudo bash 01_cai_dat_vps.sh
#  Chay lai bao nhieu lan cung duoc.
#
#  MOT CADDY DUY NHAT tren host giu 80/443 va lam cong vao cho ca hai:
#      chatbot.<IP-gach-noi>.sslip.io -> 127.0.0.1:8010  (chatbot)
#      <IP-gach-noi>.sslip.io         -> 127.0.0.1:8081  (gateway Nearby)
#  Dat IP that qua bien moi truong truoc khi chay, vi du:
#      sudo IP_VPS=203.0.113.10 bash 01_cai_dat_vps.sh
#  Nen khi chay Nearby PHAI bo container caddy cua no di, neu khong hai ben
#  tranh cong 443 va Docker se thang, Caddy tren host chet im.
# =====================================================================
set -euo pipefail

# IP cong khai cua VPS. Khong ghi IP that vao ma nguon (kho nay cong khai) -
# truyen luc chay: sudo IP_VPS=203.0.113.10 bash 01_cai_dat_vps.sh
IP_VPS="${IP_VPS:?Thieu IP_VPS. Vi du: sudo IP_VPS=203.0.113.10 bash $0}"
IP_GACH="${IP_VPS//./-}"
TEN_MIEN_CHATBOT="${TEN_MIEN_CHATBOT:-chatbot.$IP_GACH.sslip.io}"
TEN_MIEN_NEARBY="${TEN_MIEN_NEARBY:-$IP_GACH.sslip.io}"
CAI_NEARBY="${CAI_NEARBY:-1}"
NGUOI_DUNG="rag"
THU_MUC="/opt/chatbot-rag"
TEP_MOI_TRUONG="/etc/chatbot-rag.env"
CONG_UNG_DUNG="8010"
CONG_NEARBY="8081"
MODEL_TRA_LOI="${MODEL_TRA_LOI:-llama3.2:3b}"
MODEL_EMBEDDING="${MODEL_EMBEDDING:-bge-m3}"
CAI_LIBREOFFICE="${CAI_LIBREOFFICE:-1}"   # kho co Thong tu .doc doi cu, thieu soffice la doc khong duoc

buoc() { echo; echo "=============================================================="; echo ">>> $*"; echo "=============================================================="; }

[ "$(id -u)" -eq 0 ] || { echo "[LOI] Phai chay bang root: sudo bash $0"; exit 1; }

# ---------------------------------------------------------------------
buoc "1/10  Cap nhat he thong"
export DEBIAN_FRONTEND=noninteractive
apt-get -o DPkg::Lock::Timeout=900 update -y
apt-get -o DPkg::Lock::Timeout=900 -y -o Dpkg::Options::=--force-confold full-upgrade

# ---------------------------------------------------------------------
buoc "2/10  Cai goi he thong can thiet"
apt-get -o DPkg::Lock::Timeout=900 install -y --no-install-recommends \
  python3 python3-venv python3-dev python3-pip \
  build-essential git curl ca-certificates gnupg jq \
  ufw fail2ban \
  tesseract-ocr tesseract-ocr-vie \
  libgomp1 libglib2.0-0 \
  debian-keyring debian-archive-keyring apt-transport-https

if [ "$CAI_LIBREOFFICE" = "1" ]; then
  echo "--- Cai LibreOffice (doc file .doc doi cu, ~700 MB)"
  apt-get -o DPkg::Lock::Timeout=900 install -y --no-install-recommends libreoffice-writer libreoffice-impress libreoffice-calc
fi
echo "--- Python: $(python3 --version)"

# ---------------------------------------------------------------------
buoc "3/10  Cai Docker (cho Nearby)"
if ! command -v docker >/dev/null 2>&1; then
  curl -fsSL https://get.docker.com | sh
fi
systemctl enable --now docker
for u in debian ubuntu; do id -u "$u" >/dev/null 2>&1 && usermod -aG docker "$u"; done
docker --version && docker compose version

# ---------------------------------------------------------------------
buoc "4/10  Tao nguoi dung rag va thu muc ung dung"
id -u "$NGUOI_DUNG" >/dev/null 2>&1 || useradd --system --create-home --home-dir "/home/$NGUOI_DUNG" --shell /usr/sbin/nologin "$NGUOI_DUNG"
mkdir -p "$THU_MUC" "$THU_MUC/ollama-rag-desktop/data_giao_duc" "$THU_MUC/faiss_index_data_giao_duc" \
         "$THU_MUC/tep_dinh_kem" "$THU_MUC/ocr_cache" "$THU_MUC/transcripts" "$THU_MUC/.cache"
chown -R "$NGUOI_DUNG:$NGUOI_DUNG" "$THU_MUC"

# ---------------------------------------------------------------------
buoc "5/10  Tao moi truong Python (.venv)"
if [ ! -x "$THU_MUC/.venv/bin/python" ]; then
  sudo -u "$NGUOI_DUNG" python3 -m venv "$THU_MUC/.venv"
fi
sudo -u "$NGUOI_DUNG" "$THU_MUC/.venv/bin/python" -m pip install --upgrade pip wheel setuptools
if [ -f "$THU_MUC/requirements.txt" ]; then
  echo "--- Cai thu vien tu requirements.txt (mat vai phut)"
  sudo -u "$NGUOI_DUNG" "$THU_MUC/.venv/bin/python" -m pip install -r "$THU_MUC/requirements.txt"
else
  echo "--- Chua co requirements.txt (ma nguon day len sau). Bo qua."
fi

# ---------------------------------------------------------------------
buoc "6/10  Cai Ollama va tai model"
if ! command -v ollama >/dev/null 2>&1; then
  curl -fsSL https://ollama.com/install.sh | sh
fi
mkdir -p /etc/systemd/system/ollama.service.d
cat > /etc/systemd/system/ollama.service.d/override.conf <<'EOC'
[Service]
# Chi nghe localhost: khong bao gio de Ollama ra thang Internet.
Environment="OLLAMA_HOST=127.0.0.1:11434"
Environment="OLLAMA_KEEP_ALIVE=2h"
Environment="OLLAMA_NUM_PARALLEL=1"
Environment="OLLAMA_MAX_LOADED_MODELS=2"
# Nhuong CPU cho Nearby khi ca hai cung ban. CPUWeight chi co tac dung luc
# tranh chap - may ranh thi Ollama van dung het 8 nhan, tra loi van nhanh.
CPUWeight=50
EOC
systemctl daemon-reload
systemctl enable --now ollama
sleep 3
for m in "$MODEL_EMBEDDING" "$MODEL_TRA_LOI"; do
  echo "--- Tai model $m"
  ollama pull "$m"
done
ollama list

# ---------------------------------------------------------------------
buoc "7/10  Tep moi truong $TEP_MOI_TRUONG"
if [ ! -f "$TEP_MOI_TRUONG" ]; then
  cat > "$TEP_MOI_TRUONG" <<EOE
# RAG_MAT_KHAU do 02_day_ma_nguon.sh ghi vao. Thieu mat khau la ung dung
# TU CHOI khoi dong (RAG_CONG_KHAI=1) - co y nhu vay.
RAG_CONG_KHAI=1
RAG_TAI_KHOAN=giaovien
RAG_MAT_KHAU=
RAG_HOST=127.0.0.1
RAG_PORT=$CONG_UNG_DUNG
RAG_LLM_MODEL=$MODEL_TRA_LOI
RAG_EMBEDDING_MODEL=$MODEL_EMBEDDING
OLLAMA_BASE_URL=http://127.0.0.1:11434
PYTHONUNBUFFERED=1
PYTHONIOENCODING=utf-8
EOE
  echo "--- Da tao $TEP_MOI_TRUONG"
else
  echo "--- $TEP_MOI_TRUONG da co, giu nguyen."
fi
chown root:"$NGUOI_DUNG" "$TEP_MOI_TRUONG"
chmod 640 "$TEP_MOI_TRUONG"

# ---------------------------------------------------------------------
buoc "8/10  Dich vu systemd chatbot-rag"
cat > /etc/systemd/system/chatbot-rag.service <<EOS
[Unit]
Description=Chatbot RAG Giao duc (FastAPI + Ollama)
After=network-online.target ollama.service
Wants=network-online.target ollama.service

[Service]
Type=simple
User=$NGUOI_DUNG
Group=$NGUOI_DUNG
WorkingDirectory=$THU_MUC
EnvironmentFile=$TEP_MOI_TRUONG
# ProtectHome=true khoa /home/rag, nen tro HOME va cache vao thu muc ung dung -
# neu khong, thu vien nao ghi ~/.cache (faster-whisper...) se chet rat kho hieu.
Environment=HOME=$THU_MUC
Environment=XDG_CACHE_HOME=$THU_MUC/.cache
ExecStart=$THU_MUC/.venv/bin/python -m uvicorn api:app --host 127.0.0.1 --port $CONG_UNG_DUNG
Restart=on-failure
RestartSec=5
TimeoutStopSec=30
NoNewPrivileges=true
PrivateTmp=true
ProtectSystem=full
ProtectHome=true

[Install]
WantedBy=multi-user.target
EOS
systemctl daemon-reload
systemctl enable chatbot-rag
echo "--- Da dang ky dich vu (chua khoi dong: doi ma nguon va mat khau)."

# ---------------------------------------------------------------------
buoc "9/10  Caddy - cong vao chung cho ca hai site"
if ! command -v caddy >/dev/null 2>&1; then
  curl -1sLf https://dl.cloudsmith.io/public/caddy/stable/gpg.key \
    | gpg --dearmor --batch --yes --no-tty -o /usr/share/keyrings/caddy-stable-archive-keyring.gpg
  curl -1sLf https://dl.cloudsmith.io/public/caddy/stable/debian.deb.txt \
    > /etc/apt/sources.list.d/caddy-stable.list
  apt-get -o DPkg::Lock::Timeout=900 update -y
  apt-get -o DPkg::Lock::Timeout=900 install -y caddy
fi

cat > /etc/caddy/Caddyfile <<EOCADDY
# Cong vao cong khai cho ca hai ung dung. Caddy tu xin chung chi TLS.

$TEN_MIEN_CHATBOT {
	encode zstd gzip

	# Hoi dap mo cho moi nguoi. Rieng cac duong dan duoi day co the pha kho tri
	# thuc (dung lai chi muc, doi model, nap tep vao kho, xoa cache) nen phai
	# chan. Ung dung KHONG tu bao ve duoc: no sinh ra de chay o may ca nhan,
	# moi endpoint deu mo.
	@quantri path /api/reinitialize /api/index/* /api/model /api/drive/* /api/kho/* /api/cache /api/docs*
	# 02_day_ma_nguon.sh ghi mat khau vao tep nay. Khi chua co mat khau thi
	# mac dinh la CHAN HAN (403) - tha khoa nham con hon mo toang.
	import /etc/caddy/quantri.caddy

	# Tep dinh kem toi da 40 MB (RAG_GIOI_HAN_TEP_MB), chua thanh 64 MB.
	request_body {
		max_size 64MB
	}

	# flush_interval -1: day tung dong ra ngay, neu khong cau tra loi streaming
	# bi gom lai va nguoi dung tuong may treo.
	reverse_proxy 127.0.0.1:$CONG_UNG_DUNG {
		flush_interval -1
	}

	log {
		output file /var/log/caddy/chatbot-rag.log
		format console
	}
}
EOCADDY

if [ "$CAI_NEARBY" = "1" ]; then
cat >> /etc/caddy/Caddyfile <<EOCADDY2

# Nearby chay bang Docker, gateway nginx nghe o 127.0.0.1:$CONG_NEARBY
# (GATEWAY_PORT trong config/production.env). PHAI chay Nearby BO container
# caddy cua no, neu khong hai ben tranh cong 443.
$TEN_MIEN_NEARBY {
	encode zstd gzip

	reverse_proxy 127.0.0.1:$CONG_NEARBY {
		header_up X-Forwarded-Proto {scheme}
	}

	log {
		output file /var/log/caddy/nearby.log
		format console
	}
}
EOCADDY2
fi

mkdir -p /var/log/caddy
if [ ! -f /etc/caddy/quantri.caddy ]; then
  echo "# Khong chan duong dan nao. Xem 02_day_ma_nguon.sh, bien KHOA_QUAN_TRI." > /etc/caddy/quantri.caddy
  echo "--- Tao /etc/caddy/quantri.caddy (rong: khong chan gi)."
fi
caddy fmt --overwrite /etc/caddy/Caddyfile || true
caddy validate --config /etc/caddy/Caddyfile --adapter caddyfile
# caddy validate chay bang root nen NO TU TAO cac tep log voi chu la root,
# quyen 600 - dich vu chay bang user caddy se khong mo noi. Chown SAU khi
# validate, khong phai truoc.
chown -R caddy:caddy /var/log/caddy
chmod -f 644 /var/log/caddy/*.log 2>/dev/null || true
systemctl enable --now caddy
systemctl reload caddy || systemctl restart caddy

# ---------------------------------------------------------------------
buoc "10/10  Tuong lua va fail2ban"
ufw allow OpenSSH >/dev/null
ufw allow 80/tcp  >/dev/null
ufw allow 443/tcp >/dev/null
ufw --force enable
ufw status verbose
echo "--- Luu y: Docker tu mo cong bang iptables, ufw KHONG chan duoc cong ma"
echo "    Docker publish ra 0.0.0.0. Nearby da dat moi cong ve 127.0.0.1 trong"
echo "    config/production.env nen khong sao - dung sua thanh 0.0.0.0."

cat > /etc/fail2ban/jail.local <<'EOF2B'
[DEFAULT]
backend = systemd
bantime = 1h
findtime = 10m
maxretry = 5

[sshd]
enabled = true
EOF2B
systemctl enable --now fail2ban || echo "[canh bao] fail2ban khong khoi dong duoc - khong chan viec trien khai."

echo
echo "=============================================================="
echo " XONG PHAN MAY CHU."
echo "   Chatbot: https://$TEN_MIEN_CHATBOT"
[ "$CAI_NEARBY" = "1" ] && echo "   Nearby : https://$TEN_MIEN_NEARBY"
echo " Tiep theo tu may Windows: 02_day_ma_nguon.sh (chatbot)"
echo "=============================================================="
