# Đưa hai ứng dụng lên cùng một VPS OVH

| Mục | Giá trị |
|---|---|
| Gói | VPS-4 — 8 vCPU, 24 GB RAM, 200 GB đĩa (amd64) |
| Hostname OVH | `<hostname OVH>` |
| IPv4 | `<IP_VPS>` |
| IPv6 | `<IPv6 của bạn>` |
| Vị trí | Canada — độ trễ từ Việt Nam ~280 ms |
| Hệ điều hành | Debian 12 (cài lại; OVH cài sẵn Ubuntu 24.04) |

> Kho này công khai nên mọi địa chỉ máy chủ trong tài liệu đều để dạng
> `<IP_VPS>` / `<IP-VPS>` (dạng gạch nối dùng cho tên miền sslip.io). Thay bằng
> IP thật của bạn khi gõ lệnh; script không chứa IP nào cả.

Hai ứng dụng chạy chung:

- **Chatbot RAG Giáo dục** — chạy thẳng trên host: Python + FastAPI + Ollama + FAISS
- **Nearby** (`location-recommendation`) — 11 container Docker: PostGIS, OpenSearch,
  Neo4j, Redis, backend, frontend, gateway nginx, 3 máy chủ định tuyến OSRM

## Sơ đồ

```
                    ┌──────── Caddy trên host (80/443) ────────┐
                    │  một cổng vào duy nhất, tự xin chứng chỉ  │
                    └───────────┬──────────────────┬───────────┘
      chatbot.<IP-VPS>   │                  │   <IP-VPS>
             .sslip.io          │                  │       .sslip.io
                                ▼                  ▼
                     127.0.0.1:8010        127.0.0.1:8081
                     uvicorn api:app       gateway nginx (Docker)
                                │                  │
                     127.0.0.1:11434        10 container còn lại
                     Ollama                 (mọi cổng đều 127.0.0.1)
                 bge-m3 + llama3.2:3b
```

Chỉ 22, 80, 443 ra Internet. Ollama, uvicorn và toàn bộ container Nearby chỉ
nghe ở 127.0.0.1. Chatbot còn thêm một lớp mật khẩu HTTP Basic chặn mọi đường
dẫn, kể cả `/api/status`.

**Quy tắc quan trọng nhất: chỉ một Caddy được giữ 80/443.** Nearby vốn có
container Caddy riêng; trên máy này phải tắt nó bằng lớp phủ
`deploy/khong-dung-caddy.yml`. Hai bên cùng đòi 443 thì Docker thắng, Caddy trên
host chết im, cả hai site cùng hỏng.

## Tài nguyên — đo, không đoán

| | Nearby | Chatbot | Tổng / Có |
|---|---|---|---|
| RAM | ~3,6 GB (OpenSearch 1,4 + Neo4j 0,5 + 3×OSRM 1,2 + còn lại) | Ollama 2 model ~4 GB + Python/FAISS ~2 GB | ~12 / 24 GB |
| Đĩa | ảnh Docker + đồ thị 2,6 GB + CSDL | tài liệu 4,9 GB + model ~4 GB | ~25 / 200 GB |
| CPU | truy vấn ngắn | ăn hết nhân mỗi câu trả lời | 8 vCPU |

Số RAM của Nearby lấy từ `deploy/RUNBOOK.md` — đo bằng `docker stats` trên máy
dev. CPU là chỗ duy nhất hai bên chen nhau: `ollama.service` được đặt
`CPUWeight=50` nên lúc tranh chấp thì Nearby được ưu tiên, còn lúc máy rảnh
Ollama vẫn dùng hết 8 nhân.

---

## Cách vào máy (đã dựng xong, ghi lại để khỏi mò)

```bash
ssh -i ~/.ssh/ovh_vps root@<IP_VPS>
```

Khóa riêng nằm ở `C:/Users/Phung/.ssh/ovh_vps`, không đặt mật khẩu bảo vệ để
kịch bản chạy tự động. Tài khoản `debian` cũng vào được bằng mật khẩu bạn đặt.

### Cái bẫy đã mất một tiếng để gỡ

Ảnh VPS của OVH — cả Ubuntu 24.04 lẫn Debian 12 — đặt tài khoản mặc định ở trạng
thái **bắt buộc đổi mật khẩu ngay lần đăng nhập đầu**. Khi cài *kèm khóa SSH*,
OVH không sinh mật khẩu nào cả, nên rơi vào vòng chết:

```
You are required to change your password immediately (administrator enforced).
Current password:
passwd: Authentication token manipulation error
```

Muốn đặt mật khẩu mới thì `passwd` đòi mật khẩu **hiện tại**, mà mật khẩu hiện
tại không tồn tại — không câu trả lời nào đúng, kể cả để trống. Vào bằng khóa
cũng vô ích vì SSH bắt đổi mật khẩu trước khi cho chạy bất cứ lệnh nào.

**Cách gỡ:** cài lại VPS **không chọn khóa SSH**. Khi đó OVH buộc phải sinh mật
khẩu thật cho tài khoản `debian` và gửi qua link bí mật. Đăng nhập bằng mật khẩu
đó → lần này `passwd` có mật khẩu hiện tại để đối chiếu nên đổi được → vào được
shell → tự tay chép khóa công khai vào `/root/.ssh/authorized_keys`.

Lưu ý thêm: `root` **không** đăng nhập bằng mật khẩu qua SSH được, vì Debian đặt
`PermitRootLogin prohibit-password` — root chỉ vào bằng khóa. Mật khẩu root chỉ
dùng được ở console KVM.

Cài lại hệ điều hành cũng đổi luôn khóa danh tính máy chủ, nên máy bạn sẽ báo
`REMOTE HOST IDENTIFICATION HAS CHANGED`. Xóa bản ghi cũ rồi vào lại:

```bash
ssh-keygen -R <IP_VPS>
```

---

## Bước 1 — Trong OVH Manager (bạn tự làm)

### 1a. Thêm khóa SSH

Menu tài khoản (góc phải trên) → **My offers and services** → mục **My services**
→ **SSH keys** → **Add an SSH key** → category **Dedicated**. Tên `chatbot-rag`,
dán dòng này:

```
ssh-ed25519 AAAAC3NzaC1lZDI1NTE5AAAAIJrppln3C8wVbuFf8XVe+U7lK7qG1RJt7rzrq7UmmWln chatbot-rag-deploy
```

Khóa riêng ở `C:\Users\Phung\.ssh\ovh_vps`, không đặt mật khẩu bảo vệ để kịch
bản chạy tự động. Đừng gửi file đó cho ai.

### 1b. Cài lại VPS

**Bare Metal Cloud** → `<hostname OVH>` → **⚙ / Actions** →
**Reinstall my VPS** → **Debian 12** → chọn SSH key `chatbot-rag` → xác nhận.

Phải cài lại vì lúc đặt hàng bạn chọn không nhận mật khẩu root mà tài khoản khi
đó chưa có khóa nào, nên máy hiện không có đường nào vào được.

Ubuntu 24.04 cũng chạy được cả hai (Nearby nằm gọn trong Docker, chatbot có bản
thư viện dựng sẵn cho Python 3.12). Debian 12 hơn ở chỗ có đúng Python 3.11 mà
dự án chatbot đang dùng.

---

## Bước 2 — Cài đặt nền máy chủ

```bash
scp -i ~/.ssh/ovh_vps trien_khai_vps/01_cai_dat_vps.sh debian@<IP_VPS>:/tmp/
ssh -i ~/.ssh/ovh_vps debian@<IP_VPS> "sudo IP_VPS=<IP_VPS> bash /tmp/01_cai_dat_vps.sh"
```

Cài: Python, Docker, Ollama + 2 model (~3,5 GB), Caddy với sẵn hai khối site,
ufw, fail2ban, người dùng `rag`, dịch vụ `chatbot-rag`. Mất 20–30 phút.
`IP_VPS` là bắt buộc — script lấy nó để dựng hai tên miền sslip.io.

## Bước 3 — Chatbot lên trước (nhẹ, xong là có cái để xem)

```bash
bash trien_khai_vps/02_day_ma_nguon.sh <IP_VPS> debian
```

Đẩy mã nguồn + chỉ mục FAISS (~150 MB) + mật khẩu từ `mat_khau.bat`, cài thư
viện, khởi động, chờ nạp xong kho tri thức.
→ `https://chatbot.<IP-VPS>.sslip.io`

## Bước 4 — Nearby

```bash
bash trien_khai_vps/04_day_nearby.sh <IP_VPS> debian
```

Chỉ đẩy ~10 MB mã nguồn + `config/production.env`. **Không** đẩy 2,6 GB đồ thị
OSRM: VPS là amd64 nên dựng lại ngay trên máy chủ bằng chính
`osrm/osrm-backend:latest` — cùng dòng phiên bản với đồ thị máy dev, nên không
dính cái bẫy lệch phiên bản mà RUNBOOK cảnh báo (bẫy đó chỉ xảy ra trên arm64,
nơi phải dựng image từ nguồn ở v26.9.0).

Rồi chạy trên VPS, theo `deploy/RUNBOOK.md` mục 5–9:

```bash
cd ~/nearby
export OSRM_IMAGE=osrm/osrm-backend:latest
export COMPOSE="docker compose --env-file config/production.env -f docker-compose.yml -f deploy/docker-compose.prod.yml -f deploy/khong-dung-caddy.yml"
bash scripts/build_osrm.sh && bash scripts/build_osrm_foot.sh && bash scripts/build_osrm_motorbike.sh
$COMPOSE up -d database redis opensearch neo4j && $COMPOSE run --rm migrate
$COMPOSE --profile data run --rm osm-import
$COMPOSE --profile data run --rm search-index
$COMPOSE --profile data run --rm graph-sync
$COMPOSE --profile data run --rm feature-store
bash scripts/preflight_production.sh && $COMPOSE up -d
```

→ `https://<IP-VPS>.sslip.io`

## Bước 5 — Kho tài liệu gốc của chatbot (4,9 GB, chạy nền)

```bash
bash trien_khai_vps/03_day_tai_lieu.sh <IP_VPS> debian
```

Đẩy nhỏ trước lớn sau, đứt mạng chạy lại là đi tiếp. Kho này chỉ phục vụ nút
"mở tài liệu gốc"; chưa đẩy xong thì chatbot vẫn trả lời và trích dẫn đủ vì chỉ
mục đã có.

---

## Vận hành

| Việc | Lệnh trên VPS |
|---|---|
| Trạng thái chatbot | `sudo systemctl status chatbot-rag` |
| Log chatbot | `sudo journalctl -u chatbot-rag -f` |
| Trạng thái Nearby | `cd ~/nearby && $COMPOSE ps` |
| Log Nearby | `$COMPOSE logs -f --tail=100 backend` |
| Log Caddy / chứng chỉ | `sudo journalctl -u caddy -n 50` |
| RAM đang dùng thật | `free -h` và `docker stats --no-stream` |
| Đổi mật khẩu chatbot | sửa `mat_khau.bat` ở máy Windows rồi chạy lại Bước 3 |
| Cập nhật mã chatbot | chạy lại Bước 3 |

Chỉ mục chatbot vẫn nên dựng ở máy Windows (nơi có OCR, Word, kho gốc) rồi đẩy
lên. Dựng lại 4,9 GB tài liệu bằng CPU của VPS mất nhiều giờ và sẽ giành CPU với
Nearby.

## Rủi ro đã biết: chứng chỉ cho sslip.io

`config/production.env` của Nearby đã đặt `PUBLIC_HOST=<IP-VPS>.sslip.io`,
và tên `chatbot.<IP-VPS>.sslip.io` cũng phân giải đúng về IP này (đã thử).

Nhưng **sslip.io không nằm trong Public Suffix List** (tôi tải danh sách về kiểm
tra: có `duckdns.org`, không có `sslip.io`). Nghĩa là hạn mức 50 chứng chỉ mỗi
tuần của Let’s Encrypt bị chia chung cho toàn bộ người dùng sslip.io trên thế
giới — có thể bị từ chối. Kiểm bằng:

```bash
sudo journalctl -u caddy | grep -i "certificate obtained\|rateLimited\|too many"
```

Bị chặn thì đổi sang một trong ba, chỉ sửa tên miền ở đầu khối site trong
`/etc/caddy/Caddyfile` rồi `sudo systemctl reload caddy`:

1. **DuckDNS** — miễn phí, có trong PSL nên hạn mức tính riêng từng tên. Đăng ký
   hai tên, trỏ cùng về `<IP_VPS>`.
2. **Tên miền riêng** — vài chục nghìn đồng/năm, trỏ hai bản ghi A về IP. Gọn
   nhất về lâu dài, địa chỉ dễ đọc cho giáo viên.
3. **`tls internal`** — chứng chỉ tự ký, vẫn mã hóa nhưng trình duyệt cảnh báo.

Đổi tên miền của Nearby thì phải sửa cả `PUBLIC_HOST`, `PUBLIC_URL` và
`ALLOWED_ORIGINS` trong `config/production.env` rồi dựng lại frontend, vì URL API
được nhúng vào lúc build.

## Chi phí

29,20 USD cho 14/09 → 13/10/2026 (hóa đơn ASIA422217): VPS 27,50 + snapshot 1,70
+ autobackup 1,20 − khuyến mãi 1,20.

---

## Trạng thái sau khi triển khai (14/09/2026)

| | Chatbot | Nearby |
|---|---|---|
| Địa chỉ | https://chatbot.<IP-VPS>.sslip.io | https://<IP-VPS>.sslip.io |
| Xem / dùng | mở, không cần mật khẩu | mở |
| Nút quản trị | 401, mật khẩu trong `mat_khau.bat` | — |
| Dữ liệu | 25.761 vector, 576 tệp, 5,2 GB | 15.977 POI, 3 đồ thị OSRM |
| Chứng chỉ | Let's Encrypt, cấp tự động cho cả hai tên sslip.io |
| Tài nguyên | RAM 9/22 GB, đĩa 30/197 GB | |

Cả `caddy`, `ollama`, `chatbot-rag`, `docker` đều `enabled`, container Nearby đặt
`restart: unless-stopped`, nên khởi động lại máy là mọi thứ tự lên.

### Vì sao chỉ mục chỉ cập nhật ban đêm

Đo thật trên máy này, cùng một câu hỏi mới:

| | Thời gian | Tốc độ |
|---|---|---|
| Máy rảnh | 44 giây / 191 token | ~4,3 token/giây |
| Đang OCR | 248 giây / 38 token | ~0,15 token/giây |

Chậm 30 lần, và **không phải vì thiếu nhân CPU** — lúc đo, OCR đã bị giới hạn 3
nhân mà vẫn còn 5 nhân rảnh. Nguyên nhân là **băng thông bộ nhớ**: sinh chữ bằng
CPU và OCR 300 DPI cùng giành đúng tài nguyên đó, siết CPU không cứu được.

Nên việc này chạy bằng timer của systemd:

```bash
systemctl list-timers | grep capnhat
```

- **02:00** giờ VN: `capnhat-chi-muc-dem.timer` bật cập nhật chỉ mục
- **06:30** giờ VN: `dung-capnhat-chi-muc.timer` dừng hẳn và khởi động lại dịch vụ

Kết quả OCR được cache theo từng tệp trong `ocr_cache/`, nên dừng giữa chừng
không mất công: đêm sau chạy tiếp từ chỗ dở. Muốn chạy ngay (chấp nhận trang
chậm):

```bash
ssh -i ~/.ssh/ovh_vps root@<IP_VPS> /usr/local/bin/capnhat_chi_muc_dem.sh
```

## Những cái bẫy đã gặp — và cách kịch bản xử lý

1. **Sổ ghi chép khóa theo đường dẫn Windows.** `data_giao_duc_da_xu_ly.json`
   khóa theo `D:\Mr_Hai\...` nên trên VPS *mọi* tệp đều trông như mới — lần cập
   nhật đầu định embed lại toàn bộ 575 tệp thay vì 33. `02_day_ma_nguon.sh` nay
   tự đổi đường dẫn sang dạng Linux sau khi giải nén.
2. **Thiếu `tessdata/` thì PDF scan im lặng trả về rỗng.** `ocr_pdf.py` tìm
   `vie.traineddata` trong thư mục `tessdata/` của dự án, không phải của hệ
   thống; thiếu nó thì `san_sang()` trả False và loader **không báo lỗi**, chỉ
   trả tài liệu trống. Kịch bản nay đẩy kèm `tessdata/`.
3. **Thiếu LibreOffice thì mất các Thông tư `.doc` đời cũ.** Máy Windows có Word
   nên không lộ ra. `01_cai_dat_vps.sh` nay cài `libreoffice-writer` mặc định.
4. **`caddy validate` chạy bằng root tạo sẵn tệp log quyền 600 của root**, sau
   đó dịch vụ chạy bằng user `caddy` không mở nổi và chết im. Phải `chown` SAU
   khi validate.
5. **`unattended-upgrades` của Debian giữ khóa dpkg** ngay sau khi cài máy. Mọi
   lệnh `apt-get` nay có `-o DPkg::Lock::Timeout=900` để chờ thay vì bỏ cuộc.
6. **`gpg --dearmor` cần tty.** Chạy kịch bản kiểu nền (`setsid`, `< /dev/null`)
   thì nó chết; phải thêm `--batch --no-tty`.
7. **`pkill -f <tên tệp>` khớp luôn dòng lệnh đang chạy nó** — tự giết phiên SSH
   của mình. Dùng mẹo ngoặc vuông: `pkill -f "[c]apnhat_tailieu_moi"`, và đừng
   để tên tệp xuất hiện chỗ khác trong cùng dòng lệnh.
8. **Ảnh VPS của OVH bắt đổi mật khẩu mà không có mật khẩu nào** — xem mục
   "Cách vào máy" ở trên.

---

## Model trả lời

Model của Ollama nằm ngoài dự án nên **không đi theo lúc đẩy mã nguồn** — phải
tải riêng trên VPS:

```bash
ssh -i ~/.ssh/ovh_vps root@<IP_VPS> "ollama pull <ten-model>"
```

Đo trên chính CPU của VPS này (sinh 120 token, prompt tiếng Việt):

| Model | Nạp | Tốc độ sinh | Thời gian một câu hỏi thật |
|---|---|---|---|
| llama3.2:3b | 0,6 s | 13,6 tok/s | ~42 giây |
| qwen2.5:3b-instruct | 7,1 s | 13,8 tok/s | — |
| qwen3.5:4b | 12,0 s | 5,2 tok/s | — |
| **qwen3.5:9b** (đang dùng) | 20,4 s | 5,0 tok/s | ~70 giây |

`qwen3.5:9b` gần như không chậm hơn bản 4b dù lớn gấp đôi — dấu hiệu kiến trúc
MoE, mỗi token chỉ kích hoạt một phần tham số. Nên chọn 4b là thiệt.

Chọn 9b vì nó **không bịa khi thiếu căn cứ**. Cùng câu hỏi về Thông tư 27:

- `llama3.2:3b`: "Thông tư 27 quy định đánh giá bằng hình thức tự đánh giá và
  đánh giá theo quy định" — bịa hoàn toàn.
- `qwen3.5:9b`: "Tôi không tìm thấy thông tin này... Tài liệu chỉ nêu lộ trình
  áp dụng cho từng lớp" — đúng với bằng chứng được đưa vào.

Đổi model cố định: sửa `RAG_LLM_MODEL` trong `/etc/chatbot-rag.env` rồi
`systemctl restart chatbot-rag`. Đổi tạm trong giao diện cũng được nhưng khởi
động lại là mất, vì biến môi trường thắng `cai_dat.json`.

## Điểm yếu đã đo được: khâu chọn đoạn bằng chứng

Kho **có đủ** nội dung Thông tư 27 (41 đoạn trong chỉ mục: 8 đoạn chứa "thường
xuyên", 13 đoạn chứa "định kỳ", Điều 2 định nghĩa rõ ràng). Nhưng hỏi "Thông tư
27 quy định đánh giá bằng những hình thức nào?" thì hệ thống lấy nhầm các đoạn
**tiêu đề và điều khoản ban hành**, vì câu hỏi chứa đúng chữ "Thông tư 27" nên cả
BM25 lẫn vector đều kéo những đoạn lặp lại cụm đó lên đầu — còn đoạn Điều 2 chứa
câu trả lời thì không có chữ "Thông tư 27" nào.

Đã thử nâng `RAG_SO_BANG_CHUNG` từ 4 lên 8: **không giúp gì**, chỉ chậm thêm 40
giây mỗi câu (70 → 113 giây), nên đã trả về mặc định.

Đây là chỗ đáng cải thiện nhất nếu muốn chatbot trả lời tốt hơn — đáng đánh giá
bằng `benchmark_chatbot.py` với `bo_cau_hoi_benchmark.json` chứ không nên chỉnh
mò theo vài câu lẻ.
