const $ = (selector) => document.querySelector(selector);

const elements = {
  sidebar: $('#sidebar'),
  sidebarBackdrop: $('#sidebarBackdrop'),
  menuButton: $('#menuButton'),
  welcome: $('#welcomeScreen'),
  messages: $('#messages'),
  chatScroll: $('#chatScroll'),
  form: $('#chatForm'),
  input: $('#questionInput'),
  send: $('#sendButton'),
  newChat: $('#newChatButton'),
  libraryButton: $('#libraryButton'),
  libraryCount: $('#libraryCount'),
  documentDialog: $('#documentDialog'),
  closeDocumentDialog: $('#closeDocumentDialog'),
  documentSummary: $('#documentSummary'),
  documentSearch: $('#documentSearch'),
  documentList: $('#documentList'),
  documentFilters: $('#documentFilters'),
  uploadLibraryButton: $('#uploadLibraryButton'),
  libraryFileInput: $('#libraryFileInput'),
  uploadPopup: $('#uploadPopup'),
  uploadPopupList: $('#uploadPopupList'),
  uploadPopupFooter: $('#uploadPopupFooter'),
  closeUploadPopup: $('#closeUploadPopup'),
  attachButton: $('#attachButton'),
  fileInput: $('#fileInput'),
  attachmentRow: $('#attachmentRow'),
  suggestionMore: $('#suggestionMore'),
  suggestionChips: $('#suggestionChips'),
  refreshSuggestions: $('#refreshSuggestions'),
  clearHistory: $('#clearHistoryButton'),
  searchHistory: $('#searchHistoryButton'),
  historySearchBox: $('#historySearchBox'),
  historySearch: $('#historySearch'),
  history: $('#historyList'),
  statusDot: $('#statusDot'),
  statusTitle: $('#statusTitle'),
  statusMessage: $('#statusMessage'),
  systemMeta: $('#systemMeta'),
  indexProgress: $('#indexProgress'),
  indexProgressLabel: $('#indexProgressLabel'),
  indexProgressPercent: $('#indexProgressPercent'),
  indexProgressTrack: $('#indexProgressTrack'),
  indexProgressFill: $('#indexProgressFill'),
  indexProgressDetail: $('#indexProgressDetail'),
  indexProgressElapsed: $('#indexProgressElapsed'),
  indexProgressEta: $('#indexProgressEta'),
  indexProgressFile: $('#indexProgressFile'),
  retry: $('#retryButton'),
  updateIndex: $('#updateIndexButton'),
  driveSync: $('#driveSyncButton'),
  driveStatus: $('#driveStatus'),
  hotFolderStatus: $('#hotFolderStatus'),
  miniDot: $('#miniDot'),
  miniStatus: $('#miniStatus'),
  modelName: $('#modelName'),
  modelButton: $('#modelButton'),
  modelMenu: $('#modelMenu'),
  scopeButton: $('#scopeButton'),
  scopeSummary: $('#scopeSummary'),
  scopeClear: $('#scopeClear'),
  scopePanel: $('#scopePanel'),
  scopeMon: $('#scopeMon'),
  scopeCap: $('#scopeCap'),
  scopeLop: $('#scopeLop'),
  scopeLoai: $('#scopeLoai'),
  scopeNote: $('#scopeNote'),
  alert: $('#connectionAlert'),
  appShell: $('.app-shell'),
  themeButton: $('#themeButton'),
  collapseButton: $('#collapseButton'),
  scrollBottom: $('#scrollBottomButton'),
  toast: $('#toast'),
  confirmDialog: $('#confirmDialog'),
  confirmTitle: $('#confirmTitle'),
  confirmMessage: $('#confirmMessage'),
  confirmCancel: $('#confirmCancel'),
  confirmAccept: $('#confirmAccept'),
};

// Hộp thoại hỏi lại trước các thao tác không hoàn tác được (xóa lịch sử...).
let traLoiXacNhan = null;

// Đóng hộp thoại và trả lời cho lượt hỏi đang chờ. Gọi lại lần nữa cũng vô hại
// vì hàm trả lời xong là xóa luôn, tránh lượt hỏi bị trả lời hai lần.
function dongXacNhan(dongY) {
  const traLoi = traLoiXacNhan;
  traLoiXacNhan = null;
  if (elements.confirmDialog.open) elements.confirmDialog.close();
  if (traLoi) traLoi(dongY);
}

function hoiXacNhan({ tieuDe, moTa, nhanDongY = 'Xóa' }) {
  // Bấm liên tiếp thì lượt hỏi cũ coi như bị hủy, vì showModal() ném lỗi nếu
  // hộp thoại đang mở.
  dongXacNhan(false);
  elements.confirmTitle.textContent = tieuDe;
  elements.confirmMessage.textContent = moTa;
  elements.confirmAccept.textContent = nhanDongY;
  elements.confirmDialog.showModal();
  // Con trỏ đặt ở nút Hủy để lỡ bấm Enter cũng không xóa nhầm.
  elements.confirmCancel.focus();
  return new Promise((resolve) => {
    traLoiXacNhan = resolve;
  });
}

const STORAGE_KEY = 'rag-giao-duc-history-v1';
const KHOA_MA_TRINH_DUYET = 'rag-ma-trinh-duyet';

// Mã nhận dạng trình duyệt để máy chủ gom các lượt hỏi thành cuộc trò chuyện.
// KHÔNG phải xác thực - ai cũng gửi được mã của người khác. Nó chỉ thay cho việc
// đăng nhập cho tới khi có đăng nhập thật.
function maTrinhDuyet() {
  try {
    let ma = localStorage.getItem(KHOA_MA_TRINH_DUYET);
    if (!ma) {
      ma = (crypto.randomUUID?.() || `${Date.now()}-${Math.random().toString(16).slice(2)}`)
        .replace(/[^A-Za-z0-9_-]/g, '');
      localStorage.setItem(KHOA_MA_TRINH_DUYET, ma);
    }
    return ma;
  } catch {
    // Trình duyệt chặn localStorage: vẫn hỏi được, chỉ là lịch sử phía máy chủ
    // không gom theo người dùng.
    return '';
  }
}

function taoMaHoiThoai() {
  return `${Date.now()}-${Math.random().toString(16).slice(2)}`;
}
const LEGACY_STORAGE_KEY = 'rag-k35-history-v1';
let serviceState = 'starting';
let currentChat = null;
let inFlight = false;
let abortController = null;
let statusTimer = null;
let messageSequence = 0;
let documentsCache = [];
let documentKindFilter = 'tat_ca';
let modelsCache = [];
let currentModel = '';
let historyQuery = '';
// Các resolve đang chờ câu trả lời hiện tại dừng hẳn (xem doiTraLoiDung).
let ketThucTraLoi = [];
// Tệp người dùng đính kèm cho cuộc trò chuyện hiện tại: id máy chủ -> mô tả tệp.
const tepDinhKem = new Map();
const SO_TEP_TOI_DA = 4;

const assistantIcon = '<svg viewBox="0 0 24 24" aria-hidden="true"><path d="M5 4h10a4 4 0 0 1 4 4v11H9a4 4 0 0 1-4-4V4Z"/><path d="M9 9h6M9 13h4"/></svg>';
const copyIcon = '<svg viewBox="0 0 24 24" aria-hidden="true"><rect x="8" y="8" width="11" height="11" rx="2"/><path d="M16 8V6a2 2 0 0 0-2-2H6a2 2 0 0 0-2 2v8a2 2 0 0 0 2 2h2"/></svg>';
const stopIcon = '<svg viewBox="0 0 24 24" aria-hidden="true"><rect x="6" y="6" width="12" height="12" rx="2"/></svg>';

function loadHistory() {
  try {
    const current = localStorage.getItem(STORAGE_KEY);
    if (current) return JSON.parse(current) || [];
    const legacy = JSON.parse(localStorage.getItem(LEGACY_STORAGE_KEY)) || [];
    if (legacy.length) localStorage.setItem(STORAGE_KEY, JSON.stringify(legacy));
    return legacy;
  } catch {
    return [];
  }
}

function saveHistory(chat) {
  const history = loadHistory().filter((item) => item.id !== chat.id);
  history.unshift(chat);
  let saved = false;
  for (const limit of [20, 12, 6]) {
    try {
      localStorage.setItem(STORAGE_KEY, JSON.stringify(history.slice(0, limit)));
      saved = true;
      break;
    } catch {
      // Thử lại với ít cuộc trò chuyện hơn nếu trình duyệt đã gần đầy bộ nhớ.
    }
  }
  if (!saved) showToast('Không còn đủ bộ nhớ trình duyệt để lưu lịch sử');
  renderHistory();
}

// Xóa một cuộc trò chuyện khỏi lịch sử trình duyệt VÀ khỏi máy chủ.
function xoaMotCuocTroChuyen(chatId) {
  // Không chờ kết quả: xóa phía máy chủ hỏng cũng không được chặn thao tác trên
  // giao diện, và lần "xóa toàn bộ lịch sử" sau sẽ dọn nốt.
  fetch(`/api/hoi-thoai/${encodeURIComponent(chatId)}`, {
    method: 'DELETE',
    headers: { 'X-RAG-Client': maTrinhDuyet() },
  }).catch(() => {});
  const conLai = loadHistory().filter((item) => item.id !== chatId);
  try {
    if (conLai.length) localStorage.setItem(STORAGE_KEY, JSON.stringify(conLai));
    else localStorage.removeItem(STORAGE_KEY);
  } catch {
    showToast('Không ghi được lịch sử lên trình duyệt');
    return;
  }
  // Khóa cũ chỉ dùng để chuyển dữ liệu sang khóa mới; nếu lịch sử mới đã trống
  // mà còn khóa cũ thì loadHistory() sẽ khôi phục lại cuộc vừa xóa.
  if (!conLai.length) localStorage.removeItem(LEGACY_STORAGE_KEY);
  if (currentChat?.id === chatId) newChat();
  else renderHistory();
  showToast('Đã xóa cuộc trò chuyện');
}

function boDau(text) {
  return String(text ?? '')
    .normalize('NFD')
    .replace(/[̀-ͯ]/g, '')
    .replace(/đ/g, 'd')
    .replace(/Đ/g, 'D');
}

// Chuỗi đã bỏ dấu kèm bảng ánh xạ về vị trí ký tự gốc, để tô sáng đúng đoạn khớp.
function taoChiMucTimKiem(text) {
  const source = String(text ?? '');
  let folded = '';
  const map = [];
  for (let i = 0; i < source.length; i += 1) {
    const piece = boDau(source[i]).toLocaleLowerCase('vi-VN');
    for (let k = 0; k < piece.length; k += 1) map.push(i);
    folded += piece;
  }
  return { source, folded, map };
}

function chuanHoaTuKhoa(query) {
  return boDau(query).toLocaleLowerCase('vi-VN').trim();
}

function noiDungChat(chat) {
  return [chat.title, ...(chat.messages || []).map((item) => item.content || '')].join(' ');
}

function taoNhanTimKiem(text, query) {
  const label = document.createElement('span');
  const { source, folded, map } = taoChiMucTimKiem(text);
  const at = query ? folded.indexOf(query) : -1;
  if (at < 0) {
    label.textContent = source;
    return label;
  }
  const start = map[at];
  const last = at + query.length - 1;
  const end = last < map.length ? map[last] + 1 : source.length;
  const mark = document.createElement('mark');
  mark.textContent = source.slice(start, end);
  label.append(source.slice(0, start), mark, source.slice(end));
  return label;
}

function renderHistory() {
  const history = loadHistory();
  const query = chuanHoaTuKhoa(historyQuery);
  const ketQua = query
    ? history.filter((chat) => taoChiMucTimKiem(noiDungChat(chat)).folded.includes(query))
    : history;
  elements.history.replaceChildren();
  if (!ketQua.length) {
    const empty = document.createElement('div');
    empty.className = 'history-empty';
    if (query) empty.textContent = 'Không tìm thấy cuộc trò chuyện phù hợp.';
    else empty.textContent = 'Các câu hỏi gần đây sẽ xuất hiện tại đây.';
    elements.history.append(empty);
    return;
  }
  for (const chat of ketQua) {
    const row = document.createElement('div');
    row.className = 'history-row';
    const button = document.createElement('button');
    button.type = 'button';
    button.className = `history-item${currentChat?.id === chat.id ? ' active' : ''}`;
    button.innerHTML = '<svg viewBox="0 0 24 24" aria-hidden="true"><path d="M5 5h14v11H9l-4 3V5Z"/></svg>';
    button.title = chat.title;
    button.append(taoNhanTimKiem(chat.title, query));
    button.addEventListener('click', () => openChat(chat));
    const nutXoa = document.createElement('button');
    nutXoa.type = 'button';
    nutXoa.className = 'history-remove';
    nutXoa.title = 'Xóa cuộc trò chuyện này';
    nutXoa.setAttribute('aria-label', `Xóa cuộc trò chuyện: ${chat.title}`);
    nutXoa.innerHTML = '<svg viewBox="0 0 24 24" aria-hidden="true"><path d="M4 7h16M9 7V4h6v3M7 7l1 13h8l1-13M10 11v5M14 11v5"/></svg>';
    nutXoa.addEventListener('click', async (event) => {
      event.stopPropagation();
      const dongY = await hoiXacNhan({
        tieuDe: 'Xóa cuộc trò chuyện này?',
        moTa: `"${chat.title}" sẽ bị xóa khỏi lịch sử và không khôi phục lại được.`,
        nhanDongY: 'Xóa',
      });
      if (dongY) xoaMotCuocTroChuyen(chat.id);
    });
    row.append(button, nutXoa);
    elements.history.append(row);
  }
}

function toggleHistorySearch(force) {
  const willOpen = force ?? elements.historySearchBox.classList.contains('hidden');
  elements.historySearchBox.classList.toggle('hidden', !willOpen);
  elements.searchHistory.classList.toggle('active', willOpen);
  elements.searchHistory.setAttribute('aria-expanded', String(willOpen));
  if (willOpen) {
    elements.historySearch.focus();
    elements.historySearch.select();
    return;
  }
  elements.historySearch.value = '';
  historyQuery = '';
  renderHistory();
}

const tepIcon = '<svg viewBox="0 0 24 24" aria-hidden="true"><path d="M7 3h8l4 4v14H7V3Z"/><path d="M15 3v5h4"/></svg>';
const tepLoiIcon = '<svg viewBox="0 0 24 24" aria-hidden="true"><path d="M12 4.5 3 20h18L12 4.5Z"/><path d="M12 10v4.5M12 17.5v.01"/></svg>';

function dinhDangKichThuoc(bytes) {
  if (!bytes) return '';
  if (bytes < 1024) return `${bytes} B`;
  if (bytes < 1048576) return `${Math.round(bytes / 1024)} KB`;
  return `${(bytes / 1048576).toFixed(1)} MB`;
}

// Tệp đính kèm còn được chép sang kho tài liệu chung để lần sau hỏi không phải
// tải lên lại; chỉ mục thì nạp sau nên ở đây chỉ báo tình trạng chép.
function nhanLuuKho(trangThai) {
  return {
    da_luu: 'đã thêm vào kho tài liệu',
    da_co: 'kho tài liệu đã có',
    loi: 'chưa thêm được vào kho tài liệu',
  }[trangThai] || '';
}

function tepSanSang() {
  return [...tepDinhKem.values()].filter((tep) => tep.trang_thai === 'san_sang');
}

function dangDocTep() {
  return [...tepDinhKem.values()].some((tep) => tep.trang_thai === 'dang_xu_ly');
}

function renderAttachments() {
  const row = elements.attachmentRow;
  row.replaceChildren();
  row.classList.toggle('hidden', tepDinhKem.size === 0);
  for (const tep of tepDinhKem.values()) {
    const chip = document.createElement('div');
    chip.className = `attachment-chip ${tep.trang_thai}`;
    chip.innerHTML = tep.trang_thai === 'loi' ? tepLoiIcon : tepIcon;

    const info = document.createElement('div');
    info.className = 'attachment-info';
    const ten = document.createElement('strong');
    ten.textContent = tep.ten;
    ten.title = tep.ten;
    const meta = document.createElement('small');
    if (tep.trang_thai === 'san_sang') {
      meta.textContent = [
        dinhDangKichThuoc(tep.kich_thuoc),
        `${tep.so_chunk} đoạn nội dung`,
        nhanLuuKho(tep.luu_kho),
      ].filter(Boolean).join(' · ');
      if (tep.thong_bao_kho) meta.title = tep.thong_bao_kho;
    } else {
      meta.textContent = tep.thong_bao || 'Đang đọc nội dung tệp...';
    }
    info.append(ten, meta);
    chip.append(info);

    if (tep.trang_thai === 'san_sang') {
      const tomTat = document.createElement('button');
      tomTat.type = 'button';
      tomTat.className = 'attachment-action';
      tomTat.textContent = 'Tóm tắt';
      tomTat.title = `Tóm tắt nội dung ${tep.ten}`;
      tomTat.addEventListener('click', () => submitQuestion(`Tóm tắt tệp ${tep.ten}`));
      chip.append(tomTat);
    }

    const xoa = document.createElement('button');
    xoa.type = 'button';
    xoa.className = 'attachment-remove';
    xoa.title = 'Bỏ tệp này';
    xoa.setAttribute('aria-label', `Bỏ tệp ${tep.ten}`);
    xoa.innerHTML = '<svg viewBox="0 0 24 24" aria-hidden="true"><path d="m6 6 12 12M18 6 6 18"/></svg>';
    xoa.addEventListener('click', () => boTepDinhKem(tep.id));
    chip.append(xoa);
    row.append(chip);
  }
  capNhatGoiYTheoTep();
  updateSendButton();
}

function capNhatGoiYTheoTep() {
  const sanSang = tepSanSang();
  if (sanSang.length) {
    elements.input.placeholder = sanSang.length === 1
      ? `Hỏi về ${sanSang[0].ten}...`
      : `Hỏi về ${sanSang.length} tệp đã đính kèm...`;
  } else {
    elements.input.placeholder = 'Nhập câu hỏi về tài liệu...';
  }
}

async function boTepDinhKem(tepId, imLang = false) {
  tepDinhKem.delete(tepId);
  renderAttachments();
  if (tepId.startsWith('tam-')) return;
  try {
    await fetch(`/api/tep/${tepId}`, { method: 'DELETE' });
  } catch {
    // Tệp tạm sẽ bị máy chủ dọn theo lượt, không cần báo lỗi cho người dùng.
  }
  if (!imLang) showToast('Đã bỏ tệp đính kèm');
}

async function xoaMoiTepDinhKem() {
  for (const tepId of [...tepDinhKem.keys()]) await boTepDinhKem(tepId, true);
}

async function themTepDinhKem(fileList) {
  const files = [...(fileList || [])];
  if (!files.length) return;
  if (tepDinhKem.size + files.length > SO_TEP_TOI_DA) {
    showToast(`Chỉ đính kèm tối đa ${SO_TEP_TOI_DA} tệp cùng lúc`);
    return;
  }
  for (const file of files) {
    const maTam = `tam-${Date.now()}-${Math.random().toString(16).slice(2)}`;
    tepDinhKem.set(maTam, {
      id: maTam,
      ten: file.name,
      kich_thuoc: file.size,
      trang_thai: 'dang_xu_ly',
      thong_bao: 'Đang tải tệp lên...',
    });
    renderAttachments();
    try {
      const response = await fetch(`/api/tep?ten=${encodeURIComponent(file.name)}`, {
        method: 'POST',
        headers: { 'X-RAG-Action': 'upload-file', 'Content-Type': 'application/octet-stream' },
        body: file,
      });
      const payload = await response.json().catch(() => ({}));
      if (!response.ok) {
        throw new Error(payload.detail || `Máy chủ trả về lỗi ${response.status}.`);
      }
      tepDinhKem.delete(maTam);
      tepDinhKem.set(payload.id, payload);
      renderAttachments();
      theoDoiTep(payload.id);
    } catch (error) {
      tepDinhKem.set(maTam, {
        id: maTam,
        ten: file.name,
        kich_thuoc: file.size,
        trang_thai: 'loi',
        thong_bao: error.message || 'Không tải được tệp lên.',
      });
      renderAttachments();
    }
  }
}

// Đọc tệp chạy nền trên máy chủ (PDF scan phải OCR, video phải phiên âm) nên
// giao diện hỏi trạng thái cho tới khi tệp sẵn sàng hoặc báo lỗi.
async function theoDoiTep(tepId) {
  for (let lan = 0; lan < 900; lan += 1) {
    await new Promise((resolve) => window.setTimeout(resolve, 1000));
    if (!tepDinhKem.has(tepId)) return;
    let payload = null;
    try {
      const response = await fetch(`/api/tep/${tepId}`);
      if (!response.ok) throw new Error();
      payload = await response.json();
    } catch {
      continue;
    }
    tepDinhKem.set(tepId, payload);
    renderAttachments();
    if (payload.trang_thai === 'san_sang') {
      showToast(payload.luu_kho === 'da_luu'
        ? `Đã đọc xong ${payload.ten} và thêm vào kho tài liệu`
        : `Đã đọc xong ${payload.ten}`);
      return;
    }
    if (payload.trang_thai !== 'dang_xu_ly') return;
  }
}

// Trước đây hai nút này im lặng không làm gì khi đang trả lời, người dùng
// tưởng giao diện bị treo. Giờ chúng dừng câu trả lời đang chạy (phần đã sinh
// ra vẫn được lưu vào lịch sử) rồi mới chuyển.
function doiTraLoiDung() {
  if (!inFlight) return Promise.resolve();
  const cho = new Promise((resolve) => ketThucTraLoi.push(resolve));
  stopGeneration();
  return cho;
}

async function openChat(chat) {
  await doiTraLoiDung();
  currentChat = chat;
  showMessages();
  elements.messages.replaceChildren();
  for (const item of chat.messages || []) {
    if (item.role === 'user') addUserMessage(item.content, item.tep || []);
    else addCompletedAssistantMessage(item.content, item.sources || [], item.elapsed, item.warning, item.hieuLuc, item.goiY);
  }
  renderHistory();
  closeSidebar();
  scrollToBottom(false);
}

async function newChat() {
  await doiTraLoiDung();
  currentChat = null;
  elements.messages.replaceChildren();
  elements.messages.classList.remove('visible');
  elements.welcome.classList.remove('hidden');
  elements.input.value = '';
  resizeInput();
  xoaMoiTepDinhKem();
  renderHistory();
  closeSidebar();
  elements.input.focus();
  taiGoiYMoDau();
}

// ============================================================
// GỢI Ý CÂU HỎI
// ============================================================
// Bốn thẻ chủ đề chỉ mở ra bốn hướng và mãi không đổi. Hàng gợi ý này lấy từ
// máy chủ - dựng theo tên tài liệu đang có trong kho - nên người mới biết hỏi
// được những gì, kho thêm tài liệu thì gợi ý cũng đổi theo. Cuối mỗi câu trả
// lời có thêm một hàng gợi ý hỏi tiếp dựng từ chính nguồn vừa trích.
const SO_GOI_Y_MO_DAU = 6;

// Thẻ chủ đề chỉ điền vào khung hỏi để người dùng sửa thành câu của mình; còn
// gợi ý ở đây đã là câu hỏi trọn vẹn nên bấm là gửi luôn. Chưa gửi được thì
// vẫn giữ câu trong khung hỏi chứ không bỏ đi im lặng.
function dungGoiY(cauHoi) {
  elements.input.value = cauHoi;
  resizeInput();
  if (serviceState === 'ready' && !inFlight && !dangDocTep()) {
    submitQuestion(cauHoi);
    return;
  }
  elements.input.focus();
  showToast(
    inFlight
      ? 'Đang trả lời câu trước - câu này đã điền vào khung hỏi'
      : 'Chưa sẵn sàng trả lời - câu này đã điền vào khung hỏi',
  );
}

function taoChipGoiY(cauHoi) {
  const chip = document.createElement('button');
  chip.type = 'button';
  chip.className = 'suggestion-chip';
  chip.title = cauHoi;
  const chu = document.createElement('span');
  chu.textContent = cauHoi;
  chip.append(chu);
  chip.addEventListener('click', () => dungGoiY(cauHoi));
  return chip;
}

function renderGoiYMoDau(danhSach) {
  if (!elements.suggestionChips) return;
  elements.suggestionChips.replaceChildren();
  elements.suggestionMore.classList.toggle('hidden', !danhSach?.length);
  for (const cauHoi of danhSach || []) {
    elements.suggestionChips.append(taoChipGoiY(cauHoi));
  }
}

async function taiGoiYMoDau() {
  // Mở bằng file:// thì không có máy chủ để gọi; còn nếu trình duyệt đang giữ
  // bản index.html cũ trong bộ nhớ đệm thì cũng không có hàng gợi ý để vẽ vào.
  if (!elements.suggestionChips || window.location.protocol === 'file:') return;
  elements.refreshSuggestions.disabled = true;
  try {
    const response = await fetch(`/api/goi-y?so_luong=${SO_GOI_Y_MO_DAU}`, { cache: 'no-store' });
    if (!response.ok) throw new Error('goi-y');
    const payload = await response.json();
    renderGoiYMoDau(payload.goi_y || []);
  } catch (error) {
    // Không lấy được gợi ý thì ẩn hẳn hàng này: bốn thẻ chủ đề vẫn dùng bình
    // thường, không cần báo lỗi cho một thứ chỉ để bấm cho nhanh.
    renderGoiYMoDau([]);
  } finally {
    elements.refreshSuggestions.disabled = false;
  }
}

function renderGoiYTiepTheo(body, danhSach) {
  body.querySelector('.goi-y-tiep')?.remove();
  if (!danhSach?.length) return;
  const khoi = document.createElement('div');
  khoi.className = 'goi-y-tiep';
  const tieuDe = document.createElement('div');
  tieuDe.className = 'goi-y-title';
  tieuDe.textContent = 'Hỏi tiếp';
  const hang = document.createElement('div');
  hang.className = 'suggestion-chips';
  for (const cauHoi of danhSach) hang.append(taoChipGoiY(cauHoi));
  khoi.append(tieuDe, hang);
  body.append(khoi);
}

function showMessages() {
  elements.welcome.classList.add('hidden');
  elements.messages.classList.add('visible');
}

function addUserMessage(content, tepDaGui = []) {
  const article = document.createElement('article');
  article.className = 'message user';
  const bubble = document.createElement('div');
  bubble.className = 'user-bubble';
  bubble.textContent = content;
  article.append(bubble);
  if (tepDaGui.length) {
    const hang = document.createElement('div');
    hang.className = 'user-attachments';
    for (const ten of tepDaGui) {
      const nhan = document.createElement('span');
      nhan.className = 'user-attachment';
      nhan.innerHTML = tepIcon;
      const chu = document.createElement('span');
      chu.textContent = ten;
      nhan.append(chu);
      hang.append(nhan);
    }
    article.append(hang);
  }
  elements.messages.append(article);
}

function createAssistantMessage() {
  const article = document.createElement('article');
  article.className = 'message assistant';
  article.dataset.messageId = `answer-${++messageSequence}`;
  const avatar = document.createElement('div');
  avatar.className = 'avatar';
  avatar.innerHTML = assistantIcon;
  const body = document.createElement('div');
  body.className = 'message-body';
  const label = document.createElement('p');
  label.className = 'message-label';
  label.textContent = 'Trợ lý giáo dục';
  const thinking = document.createElement('div');
  thinking.className = 'thinking';
  thinking.innerHTML = '<span class="thinking-dots"><i></i><i></i><i></i></span><span class="phase-text">Đang chuẩn bị</span><span class="elapsed">00:00</span>';
  const answer = document.createElement('div');
  answer.className = 'answer-text';
  const sources = document.createElement('div');
  sources.className = 'sources';
  const actions = document.createElement('div');
  actions.className = 'response-actions';
  const stop = document.createElement('button');
  stop.type = 'button';
  stop.className = 'action-button stop';
  stop.innerHTML = `${stopIcon}<span>Dừng trả lời</span>`;
  stop.addEventListener('click', stopGeneration);
  actions.append(stop);
  body.append(label, thinking, answer, sources, actions);
  article.append(avatar, body);
  elements.messages.append(article);
  return { article, body, thinking, answer, sources, actions, stop };
}

function addCompletedAssistantMessage(content, sourceList, elapsed, warning, hieuLuc, goiY) {
  const ui = createAssistantMessage();
  renderAnswer(ui.answer, content, ui.article.dataset.messageId, sourceList.length);
  renderHieuLuc(ui.answer, hieuLuc);
  renderWarning(ui.answer, warning);
  ui.thinking.classList.add('hidden');
  renderSources(ui.sources, sourceList);
  renderCompletedActions(ui, content, elapsed);
  renderGoiYTiepTheo(ui.body, goiY);
}

const kindIcons = {
  video: '<svg viewBox="0 0 24 24" aria-hidden="true"><rect x="3" y="6" width="12" height="12" rx="2"/><path d="m15 12 6-4v8l-6-4Z"/></svg>',
  am_thanh: '<svg viewBox="0 0 24 24" aria-hidden="true"><path d="M4 10v4h3l4 3V7L7 10H4Z"/><path d="M15.5 9.5a4 4 0 0 1 0 5M18 7a8 8 0 0 1 0 10"/></svg>',
  bang_du_lieu: '<svg viewBox="0 0 24 24" aria-hidden="true"><rect x="3" y="4" width="18" height="16" rx="2"/><path d="M3 9h18M3 14h18M9 4v16"/></svg>',
  trinh_chieu: '<svg viewBox="0 0 24 24" aria-hidden="true"><rect x="3" y="4" width="18" height="11" rx="2"/><path d="M12 15v5M8 20h8"/></svg>',
  van_ban: '<svg viewBox="0 0 24 24" aria-hidden="true"><path d="M6 3h9l4 4v14H6V3Z"/><path d="M15 3v5h4"/></svg>',
  anh: '<svg viewBox="0 0 24 24" aria-hidden="true"><rect x="3" y="5" width="18" height="14" rx="2"/><circle cx="8.5" cy="10" r="1.5"/><path d="m5 17 4.5-4.5L13 16l2.5-2.5L19 17"/></svg>',
};

function formatTimestamp(seconds) {
  const total = Math.max(0, Math.floor(seconds));
  const hours = Math.floor(total / 3600);
  const mins = Math.floor((total % 3600) / 60);
  const secs = total % 60;
  const pad = (value) => value.toString().padStart(2, '0');
  return hours ? `${hours}:${pad(mins)}:${pad(secs)}` : `${pad(mins)}:${pad(secs)}`;
}

// Nguồn là video thì mở trình phát ngay trong khung chat và tua tới đúng giây
// được trích dẫn - người dùng kiểm chứng tại chỗ, không phải tải file về dò tay.
function togglePlayer(chip, source) {
  const existing = chip.nextElementSibling;
  if (existing?.classList.contains('source-player')) {
    existing.remove();
    return;
  }
  const wrapper = document.createElement('div');
  wrapper.className = 'source-player';
  const player = document.createElement(source.kind === 'am_thanh' ? 'audio' : 'video');
  player.controls = true;
  player.preload = 'metadata';
  player.src = source.url;
  wrapper.append(player);
  chip.after(wrapper);
  player.play().catch(() => {});
}

function renderSources(container, sourceList) {
  container.replaceChildren();
  if (!sourceList?.length) return;
  const title = document.createElement('div');
  title.className = 'sources-title';
  title.textContent = `Bằng chứng đã dùng · ${sourceList.length}`;
  container.append(title);
  const messageId = container.closest('.message')?.dataset.messageId || 'answer';
  sourceList.forEach((source, index) => {
    const isMedia = !source.external
      && (source.kind === 'video' || source.kind === 'am_thanh');
    const chip = document.createElement(source.url && !isMedia ? 'a' : 'div');
    chip.className = `source-chip kind-${source.kind || 'van_ban'}`;
    chip.id = `${messageId}-source-${index + 1}`;
    if (source.url && !isMedia) {
      chip.href = source.url;
      chip.target = '_blank';
      chip.rel = 'noopener noreferrer';
      const action = source.external ? 'Mở trang nguồn' : 'Mở tài liệu gốc';
      chip.title = source.excerpt ? `${action}\n${source.excerpt}` : action;
    } else if (isMedia) {
      chip.classList.add('playable');
      chip.tabIndex = 0;
      chip.title = 'Phát từ đúng đoạn được trích dẫn';
      chip.addEventListener('click', () => togglePlayer(chip, source));
      chip.addEventListener('keydown', (event) => {
        if (event.key === 'Enter' || event.key === ' ') {
          event.preventDefault();
          togglePlayer(chip, source);
        }
      });
    }
    chip.innerHTML = kindIcons[source.kind] || kindIcons.van_ban;
    const text = document.createElement('span');
    const viTri = source.page ? `Trang ${source.page}` : '';
    const detail = [source.chapter, source.article, viTri, source.context].filter(Boolean).join(' · ');
    const evidence = source.evidence || index + 1;
    text.textContent = detail
      ? `[${evidence}] ${source.name} — ${detail}`
      : `[${evidence}] ${source.name}`;
    chip.append(text);
    if (source.validity && source.validity.code !== 'khong_ro') {
      const nhan = document.createElement('em');
      nhan.className = `source-validity muc-${source.validity.level || 'thap'}`;
      nhan.textContent = source.validity.label;
      if (source.validity.note) nhan.title = source.validity.note;
      chip.append(nhan);
      if (source.validity.level === 'cao') chip.classList.add('canh-bao-cao');
    }
    if (isMedia && source.time_start != null) {
      const badge = document.createElement('em');
      badge.className = 'source-time';
      badge.textContent = `▶ ${formatTimestamp(source.time_start)}`;
      chip.append(badge);
    }
    if (source.van_ban?.so_hieu) {
      const hoSo = document.createElement('em');
      hoSo.className = `source-vanban${source.van_ban.con_hieu_luc ? '' : ' het-hieu-luc'}`;
      hoSo.textContent = source.van_ban.so_hieu + (source.van_ban.uoc_doan ? ' (?)' : '');
      hoSo.title = [
        source.van_ban.nhan,
        source.van_ban.co_quan,
        source.van_ban.thay_the?.length
          ? `Thay thế: ${source.van_ban.thay_the.join(', ')}` : '',
        source.van_ban.sua_doi?.length
          ? `Sửa đổi: ${source.van_ban.sua_doi.join(', ')}` : '',
        source.van_ban.uoc_doan ? 'Số hiệu suy đoán từ tên file, cần đối chiếu' : '',
      ].filter(Boolean).join('\n');
      chip.append(hoSo);
    }
    container.append(chip);
  });
}

function renderHieuLuc(container, cacCanhBao) {
  if (!cacCanhBao?.length) return;
  for (const canhBao of cacCanhBao) {
    const box = document.createElement('div');
    box.className = `answer-notice${canhBao.kind === 'thay_the' ? ' nghiem-trong' : ''}`;
    box.innerHTML = '<svg viewBox="0 0 24 24" aria-hidden="true"><circle cx="12" cy="12" r="9"/><path d="M12 8v5M12 16h.01"/></svg>';
    const text = document.createElement('span');
    text.textContent = canhBao.message;
    box.append(text);
    container.append(box);
  }
}

function renderWarning(container, message) {
  if (!message) return;
  const box = document.createElement('div');
  box.className = 'answer-warning';
  box.innerHTML = '<svg viewBox="0 0 24 24" aria-hidden="true"><path d="M12 4 3 19h18L12 4Z"/><path d="M12 10v4M12 17h.01"/></svg>';
  const text = document.createElement('span');
  text.textContent = message;
  box.append(text);
  container.append(box);
}

function appendInlineContent(container, text, messageId, sourceCount) {
  const pattern = /(\*\*[^*\n]+\*\*|`[^`\n]+`|\[(\d+)\])/g;
  let cursor = 0;
  for (const match of text.matchAll(pattern)) {
    container.append(document.createTextNode(text.slice(cursor, match.index)));
    const token = match[0];
    if (token.startsWith('**')) {
      const strong = document.createElement('strong');
      strong.textContent = token.slice(2, -2);
      container.append(strong);
    } else if (token.startsWith('`')) {
      const code = document.createElement('code');
      code.textContent = token.slice(1, -1);
      container.append(code);
    } else {
      const citationNumber = Number(match[2]);
      if (citationNumber >= 1 && citationNumber <= sourceCount) {
        const citation = document.createElement('a');
        citation.className = 'citation-link';
        citation.href = `#${messageId}-source-${citationNumber}`;
        citation.textContent = token;
        citation.title = `Xem nguồn ${citationNumber}`;
        container.append(citation);
      } else {
        container.append(document.createTextNode(token));
      }
    }
    cursor = match.index + token.length;
  }
  container.append(document.createTextNode(text.slice(cursor)));
}

// Bảng markdown: "| Môn | Số tiết |" kèm dòng ngăn cách "| --- | --- |".
const laDongBang = (line) => line.startsWith('|') && line.length > 1;
const laDongNganCach = (line) => line.includes('-') && /^\|[\s:|-]+$/.test(line);
const tachO = (line) => line.replace(/^\|/, '').replace(/\|$/, '').split('|').map((o) => o.trim());

function dungBang(khoi, messageId, sourceCount) {
  // Không có dòng ngăn cách thì đây chỉ là văn bản có dấu gạch đứng, không phải bảng.
  if (khoi.length < 2 || !laDongNganCach(khoi[1])) return null;
  const wrapper = document.createElement('div');
  wrapper.className = 'answer-table';
  const table = document.createElement('table');
  const thead = document.createElement('thead');
  const headRow = document.createElement('tr');
  for (const o of tachO(khoi[0])) {
    const th = document.createElement('th');
    appendInlineContent(th, o, messageId, sourceCount);
    headRow.append(th);
  }
  thead.append(headRow);
  const tbody = document.createElement('tbody');
  for (const dong of khoi.slice(2)) {
    const row = document.createElement('tr');
    for (const o of tachO(dong)) {
      const td = document.createElement('td');
      appendInlineContent(td, o, messageId, sourceCount);
      row.append(td);
    }
    tbody.append(row);
  }
  table.append(thead, tbody);
  wrapper.append(table);
  return wrapper;
}

function renderAnswer(container, content, messageId, sourceCount = 0) {
  container.replaceChildren();
  const lines = content.replace(/\r\n?/g, '\n').split('\n');
  let list = null;

  for (let viTri = 0; viTri < lines.length; viTri += 1) {
    const line = lines[viTri].trim();

    if (laDongBang(line)) {
      const khoi = [];
      while (viTri < lines.length && laDongBang(lines[viTri].trim())) {
        khoi.push(lines[viTri].trim());
        viTri += 1;
      }
      viTri -= 1;
      list = null;
      const bang = dungBang(khoi, messageId, sourceCount);
      if (bang) {
        container.append(bang);
      } else {
        // Bảng mới gõ được nửa chừng trong lúc chữ đang chạy: hiện tạm thành đoạn văn.
        for (const dong of khoi) {
          const doan = document.createElement('p');
          appendInlineContent(doan, dong, messageId, sourceCount);
          container.append(doan);
        }
      }
      continue;
    }

    const unordered = line.match(/^[-*]\s+(.+)/);
    const ordered = line.match(/^\d+[.)]\s+(.+)/);
    if (unordered || ordered) {
      const tag = unordered ? 'UL' : 'OL';
      if (!list || list.tagName !== tag) {
        list = document.createElement(tag.toLowerCase());
        container.append(list);
      }
      const item = document.createElement('li');
      appendInlineContent(item, (unordered || ordered)[1], messageId, sourceCount);
      list.append(item);
      continue;
    }

    list = null;
    if (!line) continue;
    const heading = line.match(/^(#{1,3})\s+(.+)/);
    const block = document.createElement(heading ? `h${Math.min(heading[1].length + 2, 5)}` : 'p');
    appendInlineContent(block, heading ? heading[2] : line, messageId, sourceCount);
    container.append(block);
  }
}

function renderCompletedActions(ui, content, elapsed, tuCache = null) {
  ui.actions.replaceChildren();
  const copy = document.createElement('button');
  copy.type = 'button';
  copy.className = 'action-button';
  copy.innerHTML = `${copyIcon}<span>Sao chép</span>`;
  copy.addEventListener('click', async () => {
    await navigator.clipboard.writeText(content);
    showToast('Đã sao chép câu trả lời');
  });
  ui.actions.append(copy);
  if (tuCache) {
    // Nói rõ câu này lấy lại từ câu hỏi tương tự, kèm nguyên văn câu hỏi cũ.
    // Trả lời tức thì mà không giải thích gì sẽ khiến người dùng tưởng hệ thống
    // bỏ qua chữ họ vừa gõ.
    const nhan = document.createElement('span');
    nhan.className = 'action-button';
    nhan.textContent = 'Trả lời tức thì từ câu hỏi tương tự đã hỏi';
    if (tuCache.cauHoiGoc) nhan.title = `Câu đã hỏi trước: ${tuCache.cauHoiGoc}`;
    ui.actions.append(nhan);
  } else if (elapsed) {
    const duration = document.createElement('span');
    duration.className = 'action-button';
    duration.textContent = `Hoàn tất sau ${elapsed} giây`;
    ui.actions.append(duration);
  }
}

function renderError(ui, message) {
  ui.thinking.classList.add('hidden');
  ui.answer.className = 'error-box';
  ui.answer.textContent = message;
  ui.actions.replaceChildren();
}

function scrollToBottom(smooth = true) {
  elements.chatScroll.scrollTo({
    top: elements.chatScroll.scrollHeight,
    behavior: smooth ? 'smooth' : 'auto',
  });
}

function resizeInput() {
  elements.input.style.height = 'auto';
  elements.input.style.height = `${Math.min(elements.input.scrollHeight, 150)}px`;
  updateSendButton();
}

function updateSendButton() {
  elements.send.disabled = serviceState !== 'ready'
    || inFlight
    || dangDocTep()
    || elements.input.value.trim().length < 2;
}

function formatTime(seconds) {
  const mins = Math.floor(seconds / 60).toString().padStart(2, '0');
  const secs = Math.floor(seconds % 60).toString().padStart(2, '0');
  return `${mins}:${secs}`;
}

async function submitQuestion(question) {
  question = question.trim();
  if (question.length < 2 || inFlight || serviceState !== 'ready') return;
  if (dangDocTep()) {
    showToast('Đang đọc tệp đính kèm, vui lòng đợi giây lát');
    return;
  }
  const tepDangDung = tepSanSang();
  const tepIds = tepDangDung.map((tep) => tep.id);
  const tenTep = tepDangDung.map((tep) => tep.ten);
  inFlight = true;
  abortController = new AbortController();
  updateSendButton();
  showMessages();
  addUserMessage(question, tenTep);
  elements.input.value = '';
  resizeInput();
  const ui = createAssistantMessage();
  scrollToBottom();

  const started = performance.now();
  const elapsedNode = ui.thinking.querySelector('.elapsed');
  const phaseNode = ui.thinking.querySelector('.phase-text');
  const timer = window.setInterval(() => {
    elapsedNode.textContent = formatTime((performance.now() - started) / 1000);
  }, 500);

  let answer = '';
  let sources = [];
  let elapsed = null;
  let warning = '';
  let hieuLuc = [];
  let goiY = [];
  let tuCache = null;
  const history = (currentChat?.messages || [])
    .filter((item) => item.role === 'user' || item.role === 'assistant')
    .slice(-6)
    .map((item) => ({ role: item.role, content: item.content.slice(0, 4000) }));
  try {
    // Chốt mã hội thoại TRƯỚC khi gửi, rồi dùng lại đúng mã đó cho bản ghi
    // localStorage bên dưới - nhờ vậy lịch sử trên máy và trên máy chủ trỏ về
    // cùng một cuộc trò chuyện mà không cần thêm vòng gọi nào.
    const hoiThoaiId = currentChat?.id || taoMaHoiThoai();
    const response = await fetch('/api/chat/stream', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json', 'X-RAG-Client': maTrinhDuyet() },
      body: JSON.stringify({
        question, history, tep_ids: tepIds, hoi_thoai_id: hoiThoaiId,
        pham_vi: phamViDangChon(),
      }),
      signal: abortController.signal,
    });
    if (!response.ok) {
      const detail = await response.json().catch(() => ({}));
      throw new Error(detail.detail || `Máy chủ trả về lỗi ${response.status}.`);
    }
    const reader = response.body.getReader();
    const decoder = new TextDecoder();
    let buffer = '';
    while (true) {
      const { value, done } = await reader.read();
      buffer += decoder.decode(value || new Uint8Array(), { stream: !done });
      const lines = buffer.split('\n');
      buffer = lines.pop() || '';
      for (const line of lines) {
        if (!line.trim()) continue;
        const event = JSON.parse(line);
        if (event.type === 'phase') {
          phaseNode.textContent = event.message;
        } else if (event.type === 'sources') {
          sources = event.sources || [];
          renderSources(ui.sources, sources);
        } else if (event.type === 'token') {
          answer += event.content;
          renderAnswer(ui.answer, answer, ui.article.dataset.messageId, sources.length);
          phaseNode.textContent = 'Đang trả lời';
          scrollToBottom(false);
        } else if (event.type === 'hieu_luc') {
          hieuLuc.push({ message: event.message, kind: event.kind });
        } else if (event.type === 'warning') {
          warning = event.message;
        } else if (event.type === 'goi_y') {
          goiY = event.goi_y || [];
        } else if (event.type === 'done') {
          elapsed = event.elapsed_seconds;
          tuCache = event.tu_cache ? { cauHoiGoc: event.cache_cau_hoi_goc || '' } : null;
        } else if (event.type === 'error') {
          throw new Error(event.message);
        }
      }
      if (done) break;
    }
    ui.thinking.classList.add('hidden');
    renderAnswer(ui.answer, answer, ui.article.dataset.messageId, sources.length);
    renderHieuLuc(ui.answer, hieuLuc);
    renderWarning(ui.answer, warning);
    renderCompletedActions(ui, answer, elapsed, tuCache);
    renderGoiYTiepTheo(ui.body, goiY);
    const chat = currentChat || {
      id: hoiThoaiId,
      title: question.slice(0, 62),
      messages: [],
    };
    chat.messages.push({ role: 'user', content: question, tep: tenTep });
    chat.messages.push({ role: 'assistant', content: answer, sources, elapsed, warning, hieuLuc, goiY });
    currentChat = chat;
    saveHistory(chat);
  } catch (error) {
    if (error.name === 'AbortError') {
      if (answer) {
        ui.thinking.classList.add('hidden');
        renderCompletedActions(ui, answer, null);
        const chat = currentChat || {
          id: hoiThoaiId,
          title: question.slice(0, 62),
          messages: [],
        };
        chat.messages.push({ role: 'user', content: question, tep: tenTep });
        chat.messages.push({ role: 'assistant', content: answer, sources, interrupted: true });
        currentChat = chat;
        saveHistory(chat);
        showToast('Đã dừng tạo câu trả lời');
      } else {
        renderError(ui, 'Đã dừng câu trả lời theo yêu cầu.');
      }
    } else {
      renderError(ui, error.message || 'Không thể nhận câu trả lời.');
    }
  } finally {
    window.clearInterval(timer);
    inFlight = false;
    abortController = null;
    updateSendButton();
    pollStatus();
    scrollToBottom();
    const dangCho = ketThucTraLoi;
    ketThucTraLoi = [];
    for (const bao of dangCho) bao();
  }
}

function stopGeneration() {
  abortController?.abort();
}

async function pollStatus() {
  if (window.location.protocol === 'file:') {
    serviceState = 'error';
    const message = 'Bạn đang mở file HTML trực tiếp. Hãy đóng tab này và nhấp đúp start_ui.bat trong thư mục Mr_Hai.';
    elements.statusTitle.textContent = 'Chưa chạy máy chủ';
    elements.statusMessage.textContent = message;
    elements.miniStatus.textContent = 'Chưa chạy máy chủ';
    elements.statusDot.className = 'status-dot error';
    elements.miniDot.className = 'mini-dot error';
    renderIndexProgress(null);
    elements.alert.textContent = message;
    elements.alert.className = 'connection-alert error';
    elements.retry.classList.add('hidden');
    elements.updateIndex.classList.add('hidden');
    updateSendButton();
    return;
  }
  try {
    const response = await fetch('/api/status', { cache: 'no-store' });
    if (!response.ok) throw new Error('status');
    const status = await response.json();
    serviceState = status.state;
    currentModel = status.model || currentModel;
    elements.modelName.textContent = currentModel || 'qwen3.5:4b';
    const stateLabel = status.state === 'ready'
      ? (status.busy ? 'Đang xử lý một câu hỏi' : 'Sẵn sàng')
      : status.state === 'error'
        ? 'Cần kiểm tra'
        : status.state === 'updating' ? 'Đang cập nhật' : 'Đang khởi tạo';
    elements.statusTitle.textContent = stateLabel;
    elements.statusMessage.textContent = status.message;
    renderIndexProgress(status.index_progress, status.state);
    elements.miniStatus.textContent = stateLabel;
    elements.statusDot.className = `status-dot ${status.state}`;
    elements.miniDot.className = `mini-dot ${status.state}`;
    if (status.vector_count) {
      const parts = [
        `${status.vector_count.toLocaleString('vi-VN')} vector`,
        `${(status.source_count || 0).toLocaleString('vi-VN')}/${(status.data_file_count || 0).toLocaleString('vi-VN')} nguồn đọc được`,
      ];
      if (status.no_text_file_count) parts.push(`${status.no_text_file_count.toLocaleString('vi-VN')} cần OCR`);
      if (status.duplicate_file_count) parts.push(`${status.duplicate_file_count.toLocaleString('vi-VN')} tệp trùng`);
      if (status.error_file_count) parts.push(`${status.error_file_count.toLocaleString('vi-VN')} không đọc được`);
      if (status.tep_cho_nap) parts.push(`${status.tep_cho_nap.toLocaleString('vi-VN')} tệp chờ nạp chỉ mục`);
      elements.systemMeta.textContent = parts.join(' · ');
      elements.libraryCount.textContent = (status.data_file_count || 0).toLocaleString('vi-VN');
    } else {
      elements.systemMeta.textContent = '';
    }
    renderDriveStatus(status.drive);
    renderHotFolderStatus(status.thu_muc_nong);
    if (status.state === 'ready' && !status.data_stale) {
      elements.alert.classList.add('hidden');
      elements.retry.classList.add('hidden');
      elements.updateIndex.classList.add('hidden');
    } else if (status.state === 'ready' && status.data_stale) {
      elements.alert.textContent = 'Kho tài liệu đã thay đổi. Hãy cập nhật chỉ mục để dùng dữ liệu mới nhất.';
      elements.alert.className = 'connection-alert';
      elements.retry.classList.add('hidden');
      elements.updateIndex.classList.remove('hidden');
    } else {
      elements.alert.textContent = status.message;
      elements.alert.className = `connection-alert${status.state === 'error' ? ' error' : ''}`;
      elements.retry.classList.toggle('hidden', status.state !== 'error');
      elements.updateIndex.classList.add('hidden');
    }
  } catch {
    serviceState = 'error';
    elements.statusTitle.textContent = 'Mất kết nối';
    elements.statusMessage.textContent = 'Không kết nối được với máy chủ ứng dụng.';
    elements.miniStatus.textContent = 'Mất kết nối';
    elements.statusDot.className = 'status-dot error';
    elements.miniDot.className = 'mini-dot error';
    renderIndexProgress(null);
    elements.alert.textContent = 'Không kết nối được với máy chủ. Hãy kiểm tra cửa sổ chạy ứng dụng.';
    elements.alert.className = 'connection-alert error';
    elements.retry.classList.remove('hidden');
    elements.updateIndex.classList.add('hidden');
  }
  updateSendButton();
}

// ============================================================
// TIẾN ĐỘ LẬP CHỈ MỤC
// ============================================================
// Máy chủ chỉ trả trạng thái mỗi 4 giây, mà một tệp SGK có thể mất vài phút
// mới nhích phần trăm. Nếu chỉ vẽ lại theo nhịp poll thì người dùng nhìn thấy
// một thanh đứng im và tưởng ứng dụng treo, nên đồng hồ được chạy tại chỗ.
const tienDoChiMuc = {
  moc: 0,          // thời điểm (ms, đồng hồ máy khách) lượt cập nhật bắt đầu
  conLai: null,    // giây còn lại, đã làm mượt
  troiLucUoc: 0,   // số giây đã trôi tại lần ước tính gần nhất
  dangChay: false,
  giaiDoan: '',    // stage đang chạy; đổi giai đoạn là đặt lại mốc đo nhịp
  mocTroi: 0,      // số giây đã trôi khi bước vào giai đoạn hiện tại
  mocPercent: 0,   // phần trăm tại thời điểm bước vào giai đoạn đó
  phanTram: 0,     // phần trăm ở lần poll gần nhất, để đồng hồ tự biết sắp xong
};
let dongHoChiMuc = null;

function dinhDangKhoangThoiGian(giay) {
  const tong = Math.max(0, Math.round(giay));
  const gio = Math.floor(tong / 3600);
  const phut = Math.floor((tong % 3600) / 60);
  const giay_le = tong % 60;
  const dem = (value) => value.toString().padStart(2, '0');
  return gio ? `${gio}:${dem(phut)}:${dem(giay_le)}` : `${dem(phut)}:${dem(giay_le)}`;
}

// "Còn 3 phút 20" dễ đọc hơn "còn 00:03:20" khi người dùng chỉ liếc qua.
function dinhDangUocTinh(giay) {
  const tong = Math.max(0, Math.round(giay));
  if (tong < 45) return 'chưa tới 1 phút';
  const gio = Math.floor(tong / 3600);
  const phut = Math.round((tong % 3600) / 60);
  if (gio) return `khoảng ${gio} giờ ${phut ? `${phut} phút` : ''}`.trim();
  return `khoảng ${Math.max(1, phut)} phút`;
}

function veDongHoChiMuc() {
  if (!tienDoChiMuc.dangChay || !tienDoChiMuc.moc) return;
  const troi = (Date.now() - tienDoChiMuc.moc) / 1000;
  elements.indexProgressElapsed.textContent = `Đã chạy ${dinhDangKhoangThoiGian(troi)}`;
  if (tienDoChiMuc.conLai == null) {
    // Các giai đoạn cuối (lưu chỉ mục, nạp lại kho) mỗi cái chỉ vài phần trăm
    // và luôn bị đặt lại mốc đo, nên sẽ không bao giờ kịp có ước tính. Nói
    // thẳng "sắp xong" đúng hơn là bắt người dùng đọc "đang ước tính".
    elements.indexProgressEta.textContent = tienDoChiMuc.phanTram >= 95
      ? 'Sắp xong'
      : 'Đang ước tính thời gian còn lại...';
    return;
  }
  // Trừ dần theo giây thật để con số đếm ngược mượt giữa hai lần poll.
  const conLai = Math.max(0, tienDoChiMuc.conLai - (troi - tienDoChiMuc.troiLucUoc));
  elements.indexProgressEta.textContent = conLai < 5
    ? 'Sắp xong'
    : `Còn ${dinhDangUocTinh(conLai)}`;
}

function batDongHoChiMuc() {
  if (dongHoChiMuc) return;
  dongHoChiMuc = window.setInterval(veDongHoChiMuc, 1000);
}

function dungDongHoChiMuc() {
  if (!dongHoChiMuc) return;
  window.clearInterval(dongHoChiMuc);
  dongHoChiMuc = null;
  tienDoChiMuc.dangChay = false;
}

// Ước tính thời gian còn lại theo nhịp CỦA GIAI ĐOẠN ĐANG CHẠY, làm mượt để
// con số không nhảy giật mỗi lần một tệp lớn xong.
//
// Bản trước ngoại suy thẳng từ tổng thời gian: troi * (100 - percent) / percent.
// Cách đó sai nặng vì các giai đoạn chạy ở tốc độ khác hẳn nhau - đọc/OCR nằm
// trong dải 5-50%, nhúng vector nằm trong dải 50-95% - nên nhịp của giai đoạn
// trước không nói được gì về giai đoạn sau. Đo thực tế: sau 13 giờ OCR, vừa
// bước sang phần nhúng ở 50,5% thì công thức cũ báo "còn 12 giờ 47 phút", tức
// chỉ đang nói "nửa sau lâu bằng nửa đầu" chứ chưa hề đo tốc độ nhúng.
function capNhatUocTinh(percent, troi, giaiDoan) {
  if (giaiDoan !== tienDoChiMuc.giaiDoan) {
    tienDoChiMuc.giaiDoan = giaiDoan;
    tienDoChiMuc.mocTroi = troi;
    tienDoChiMuc.mocPercent = percent;
    // Nhịp của giai đoạn cũ không còn giá trị: thà hiện "đang ước tính" vài
    // chục giây còn hơn hiện một con số sai.
    tienDoChiMuc.conLai = null;
    return;
  }
  const dtTroi = troi - tienDoChiMuc.mocTroi;
  const dtPercent = percent - tienDoChiMuc.mocPercent;
  // Phải đi đủ xa trong chính giai đoạn này mới có nhịp đáng tin. Ngưỡng lấy
  // theo thời gian là chính: một tệp SGK chỉ chiếm 0,26% của dải nhúng, đòi
  // hỏi nhiều phần trăm thì người dùng phải chờ hàng giờ mới thấy con số đầu
  // tiên. Một phút mẫu kèm bộ làm mượt 0,7/0,3 là đủ để số không nhảy loạn.
  if (dtTroi < 60 || dtPercent < 0.05) return;
  const thoNhap = dtTroi * (100 - percent) / dtPercent;
  tienDoChiMuc.conLai = tienDoChiMuc.conLai == null
    ? thoNhap
    : tienDoChiMuc.conLai * 0.7 + thoNhap * 0.3;
  tienDoChiMuc.troiLucUoc = troi;
}

function renderIndexProgress(progress, state = '') {
  const legacyUpdate = state === 'updating' && !progress;
  if (!progress?.active && !legacyUpdate) {
    elements.indexProgress.classList.add('hidden');
    elements.indexProgressTrack.classList.remove('indeterminate');
    dungDongHoChiMuc();
    tienDoChiMuc.moc = 0;
    tienDoChiMuc.conLai = null;
    tienDoChiMuc.giaiDoan = '';
    tienDoChiMuc.mocTroi = 0;
    tienDoChiMuc.mocPercent = 0;
    tienDoChiMuc.phanTram = 0;
    return;
  }
  if (legacyUpdate) {
    elements.indexProgress.classList.remove('hidden');
    elements.indexProgressTrack.classList.add('indeterminate');
    elements.indexProgressLabel.textContent = 'Đang lập chỉ mục...';
    elements.indexProgressPercent.textContent = 'Đang chạy';
    elements.indexProgressFill.style.width = '35%';
    elements.indexProgressTrack.removeAttribute('aria-valuenow');
    elements.indexProgressElapsed.textContent = 'Lượt hiện tại chạy bằng phiên bản cũ';
    elements.indexProgressEta.textContent = '';
    elements.indexProgressDetail.textContent = 'Mở lại ứng dụng sau lượt này để xem thời gian và số tệp';
    elements.indexProgressFile.textContent = '';
    elements.indexProgressFile.title = '';
    dungDongHoChiMuc();
    return;
  }
  const percent = Math.max(0, Math.min(100, Number(progress.percent) || 0));
  const completed = Number(progress.completed) || 0;
  const total = Number(progress.total) || 0;
  const troi = Math.max(0, Number(progress.elapsed_seconds) || 0);
  const countText = total ? `${completed}/${total} ${progress.unit || 'tệp'}` : '';
  const detail = [countText, progress.detail].filter(Boolean).join(' · ');

  // Neo mốc bắt đầu theo đồng hồ máy khách: đồng hồ máy chủ có thể lệch, còn
  // hiệu số elapsed_seconds thì luôn đúng.
  tienDoChiMuc.moc = Date.now() - troi * 1000;
  tienDoChiMuc.dangChay = true;
  tienDoChiMuc.phanTram = percent;
  capNhatUocTinh(percent, troi, String(progress.stage || ''));

  elements.indexProgress.classList.remove('hidden');
  elements.indexProgressTrack.classList.remove('indeterminate');
  elements.indexProgressTrack.classList.toggle('done', percent >= 100);
  elements.indexProgressLabel.textContent = progress.label || 'Đang cập nhật...';
  elements.indexProgressPercent.textContent = `${Math.round(percent)}%`;
  elements.indexProgressFill.style.width = `${percent}%`;
  elements.indexProgressTrack.setAttribute('aria-valuenow', String(Math.round(percent)));
  elements.indexProgressDetail.textContent = detail;
  elements.indexProgressFile.textContent = progress.current_file || '';
  elements.indexProgressFile.title = progress.current_file || '';
  veDongHoChiMuc();
  batDongHoChiMuc();
}

// Dòng "đang theo dõi thư mục nóng" để người dùng biết tệp thả vào thư mục
// Drive trên máy sẽ tự được nạp, không phải đoán mò tính năng có chạy hay không.
function renderHotFolderStatus(thuMucNong) {
  if (!elements.hotFolderStatus) return;
  const dangTheoDoi = thuMucNong?.dang_theo_doi && thuMucNong?.duong_dan;
  elements.hotFolderStatus.classList.toggle('hidden', !dangTheoDoi);
  if (!dangTheoDoi) return;
  // Chỉ hiện tên thư mục cuối cho gọn; đường dẫn đầy đủ nằm ở tooltip.
  const tenThuMuc = thuMucNong.duong_dan.split(/[\\/]/).filter(Boolean).pop();
  elements.hotFolderStatus.textContent =
    `👀 Đang theo dõi thư mục "${tenThuMuc}" · quét mỗi ${thuMucNong.phut_quet} phút`;
  elements.hotFolderStatus.title =
    `${thuMucNong.duong_dan}\nTệp thả vào đây được tự thêm vào kho và lập chỉ mục khi máy rảnh.`;
}

function renderDriveStatus(drive) {
  if (!drive) return;
  if (!drive.configured) {
    elements.driveSync.disabled = true;
    elements.driveStatus.textContent = drive.mode;
    return;
  }
  const dangChay = drive.state === 'syncing';
  elements.driveSync.disabled = dangChay || serviceState === 'updating';
  elements.driveSync.classList.toggle('syncing', dangChay);
  const phan = [];
  if (drive.message) {
    phan.push(drive.message);
  } else if (drive.last_sync_at) {
    phan.push(`Lần cuối ${new Date(drive.last_sync_at * 1000).toLocaleString('vi-VN')}`);
  } else {
    phan.push('Chưa đồng bộ lần nào');
  }
  if (drive.auto_minutes > 0 && !dangChay) {
    phan.push(`tự kiểm tra mỗi ${drive.auto_minutes} phút`);
  }
  elements.driveStatus.textContent = phan.join(' · ');
}

// ===== Chọn mô hình trả lời =====
// Đổi model chỉ dựng lại chuỗi sinh câu trả lời, không đụng tới vector store
// (vector đã embed bằng bge-m3), nên chuyển model chỉ mất khoảng một giây.
function closeModelMenu() {
  elements.modelMenu.classList.add('hidden');
  elements.modelButton.setAttribute('aria-expanded', 'false');
}

function renderModelMenu() {
  elements.modelMenu.replaceChildren();
  if (!modelsCache.length) {
    const empty = document.createElement('div');
    empty.className = 'model-empty';
    empty.textContent = 'Không đọc được danh sách model từ Ollama.';
    elements.modelMenu.append(empty);
    return;
  }
  const title = document.createElement('div');
  title.className = 'model-menu-title';
  title.textContent = 'Mô hình trả lời';
  elements.modelMenu.append(title);

  for (const model of modelsCache) {
    const item = document.createElement('button');
    item.type = 'button';
    item.className = `model-option${model.name === currentModel ? ' active' : ''}`;
    item.setAttribute('role', 'option');
    item.setAttribute('aria-selected', String(model.name === currentModel));
    const info = document.createElement('span');
    const name = document.createElement('strong');
    name.textContent = model.name;
    const meta = document.createElement('small');
    meta.textContent = [model.parameter_size, `${model.size_gb} GB`]
      .filter(Boolean).join(' · ');
    info.append(name, meta);
    item.append(info);
    if (model.name === currentModel) {
      item.insertAdjacentHTML('beforeend',
        '<svg class="tick" viewBox="0 0 24 24" aria-hidden="true"><path d="m5 13 4 4 10-10"/></svg>');
    }
    item.addEventListener('click', () => selectModel(model.name));
    elements.modelMenu.append(item);
  }
}

async function loadModels() {
  try {
    const response = await fetch('/api/models', { cache: 'no-store' });
    if (!response.ok) throw new Error('models');
    const payload = await response.json();
    modelsCache = payload.models || [];
    currentModel = payload.current || currentModel;
  } catch {
    modelsCache = [];
  }
  renderModelMenu();
}

async function selectModel(name) {
  if (name === currentModel) {
    closeModelMenu();
    return;
  }
  elements.modelButton.disabled = true;
  try {
    const response = await fetch('/api/model', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json', 'X-RAG-Action': 'switch-model' },
      body: JSON.stringify({ model: name }),
    });
    const payload = await response.json().catch(() => ({}));
    if (!response.ok) throw new Error(payload.detail || 'Không đổi được model.');
    currentModel = payload.model;
    elements.modelName.textContent = currentModel;
    showToast(payload.message || `Đã chuyển sang ${currentModel}`);
    renderModelMenu();
    closeModelMenu();
  } catch (error) {
    showToast(error.message);
  } finally {
    elements.modelButton.disabled = false;
  }
}

function showToast(message, thoiGianMs = 1800) {
  elements.toast.textContent = message;
  elements.toast.classList.add('show');
  window.clearTimeout(showToast._henTat);
  showToast._henTat = window.setTimeout(
    () => elements.toast.classList.remove('show'), thoiGianMs,
  );
}

function formatFileSize(bytes) {
  if (bytes < 1024) return `${bytes} B`;
  if (bytes < 1024 ** 2) return `${(bytes / 1024).toFixed(1)} KB`;
  return `${(bytes / 1024 ** 2).toFixed(1)} MB`;
}

const kindLabels = {
  tat_ca: 'Tất cả',
  van_ban: 'Văn bản',
  trinh_chieu: 'Trình chiếu',
  bang_du_lieu: 'Bảng biểu',
  video: 'Video',
  am_thanh: 'Âm thanh',
  phu_de: 'Phụ đề',
  anh: 'Ảnh',
};

function renderDocumentFilters() {
  if (!elements.documentFilters) return;
  const counts = new Map();
  for (const item of documentsCache) {
    const kind = item.kind || 'van_ban';
    counts.set(kind, (counts.get(kind) || 0) + 1);
  }
  const kinds = ['tat_ca', ...[...counts.keys()].sort()];
  elements.documentFilters.replaceChildren();
  for (const kind of kinds) {
    const button = window.document.createElement('button');
    button.type = 'button';
    button.className = `filter-chip${documentKindFilter === kind ? ' active' : ''}`;
    const total = kind === 'tat_ca' ? documentsCache.length : counts.get(kind);
    button.textContent = `${kindLabels[kind] || kind} ${total}`;
    button.addEventListener('click', () => {
      documentKindFilter = kind;
      renderDocumentFilters();
      renderDocuments(elements.documentSearch.value);
    });
    elements.documentFilters.append(button);
  }
}

function renderDocuments(query = '') {
  const normalizedQuery = query.trim().toLocaleLowerCase('vi-VN');
  const documents = documentsCache.filter((document) =>
    `${document.name} ${document.folder}`.toLocaleLowerCase('vi-VN').includes(normalizedQuery)
    && (documentKindFilter === 'tat_ca' || (document.kind || 'van_ban') === documentKindFilter)
  );
  elements.documentList.replaceChildren();
  if (!documents.length) {
    const empty = document.createElement('div');
    empty.className = 'document-empty';
    empty.textContent = normalizedQuery ? 'Không tìm thấy tài liệu phù hợp.' : 'Kho tài liệu đang trống.';
    elements.documentList.append(empty);
    return;
  }

  const statusLabels = {
    processed: 'Đã lập chỉ mục',
    no_text: 'Cần OCR',
    duplicate: 'Tệp trùng',
    error: 'Không đọc được',
    pending: 'Chờ cập nhật',
  };
  // Video không đọc được là do không có lời thoại, không phải thiếu OCR.
  const nhanKhongCoChu = (tai_lieu) => (
    tai_lieu.kind === 'video' || tai_lieu.kind === 'am_thanh'
      ? 'Không có lời thoại'
      : statusLabels.no_text
  );
  for (const document of documents) {
    const item = window.document.createElement(document.url ? 'a' : 'div');
    item.className = 'document-row';
    if (document.url) {
      item.href = document.url;
      item.target = '_blank';
      item.rel = 'noopener noreferrer';
    }
    const icon = window.document.createElement('span');
    icon.className = 'document-type';
    icon.textContent = document.extension || 'FILE';
    const info = window.document.createElement('span');
    info.className = 'document-info';
    const name = window.document.createElement('strong');
    name.textContent = document.name;
    const meta = window.document.createElement('small');
    meta.textContent = `${document.folder} · ${formatFileSize(document.size_bytes)}`;
    info.append(name, meta);
    const status = window.document.createElement('span');
    status.className = `document-status ${document.status}`;
    status.textContent = document.status === 'no_text'
      ? nhanKhongCoChu(document)
      : (statusLabels[document.status] || document.status);
    item.append(icon, info, status);
    elements.documentList.append(item);
  }
}

async function openDocumentLibrary() {
  closeSidebar();
  elements.documentSearch.value = '';
  elements.documentList.innerHTML = '<div class="document-empty">Đang đọc danh sách tài liệu...</div>';
  if (!elements.documentDialog.open) elements.documentDialog.showModal();
  try {
    const response = await fetch('/api/documents', { cache: 'no-store' });
    if (!response.ok) throw new Error('Không đọc được kho tài liệu.');
    const payload = await response.json();
    documentsCache = payload.documents || [];
    const summary = payload.summary || {};
    elements.libraryCount.textContent = (summary.total || 0).toLocaleString('vi-VN');
    const summaryParts = [
      `${summary.total || 0} tài liệu`,
      `${summary.processed || 0} đã lập chỉ mục`,
    ];
    if (summary.no_text) summaryParts.push(`${summary.no_text} cần OCR`);
    if (summary.pending) summaryParts.push(`${summary.pending} chờ cập nhật`);
    if (summary.duplicate) summaryParts.push(`${summary.duplicate} tệp trùng`);
    if (summary.error) summaryParts.push(`${summary.error} không đọc được`);
    elements.documentSummary.textContent = summaryParts.join(' · ');
    renderDocuments();
    renderDocumentFilters();
    elements.documentSearch.focus();
  } catch (error) {
    elements.documentList.innerHTML = '';
    const message = window.document.createElement('div');
    message.className = 'document-empty error';
    message.textContent = error.message || 'Không đọc được kho tài liệu.';
    elements.documentList.append(message);
  }
}

// Nút "+" trong Kho tài liệu: tải tệp thẳng vào kho rồi lập chỉ mục.
// Phải khớp DINH_DANG_HO_TRO phía máy chủ; .zip và các định dạng lạ bị chặn ngay.
const DUOI_KHO_HO_TRO = new Set([
  '.pdf', '.docx', '.doc', '.txt', '.md', '.html', '.htm', '.epub',
  '.jpg', '.jpeg', '.png', '.tif', '.tiff', '.bmp', '.webp',
  '.xlsx', '.xlsm', '.xls', '.csv', '.tsv', '.pptx', '.srt', '.vtt',
  '.mp4', '.mkv', '.mov', '.avi', '.webm', '.wmv', '.flv',
  '.mp3', '.wav', '.m4a', '.aac', '.flac', '.ogg', '.wma',
]);

// Popup ở góc phải: mỗi tệp một dòng, trạng thái đổi ngay khi tệp đó xử lý xong,
// không đợi cả loạt như toast (toast chỉ hiện được một thông báo nên tin trước
// bị tin sau đè mất).
let henDongPopupUpload = 0;
let vongTheoDoiChiMuc = 0;

function moPopupUpload() {
  window.clearTimeout(henDongPopupUpload);
  window.clearInterval(vongTheoDoiChiMuc);
  elements.uploadPopupList.innerHTML = '';
  elements.uploadPopupFooter.textContent = '';
  elements.uploadPopup.classList.remove('hidden');
  // showPopover đưa popup lên top layer, hiện được cả khi modal Kho tài liệu đang mở.
  try {
    if (!elements.uploadPopup.matches(':popover-open')) elements.uploadPopup.showPopover();
  } catch { /* trình duyệt cũ không có Popover API thì position:fixed vẫn đủ dùng */ }
}

function anPopupUpload() {
  elements.uploadPopup.classList.add('hidden');
  try { elements.uploadPopup.hidePopover(); } catch { /* như trên */ }
  window.clearInterval(vongTheoDoiChiMuc);
}

function themDongPopupUpload(ten, trangThai, kieu = '') {
  const dong = window.document.createElement('li');
  const nhan = window.document.createElement('span');
  nhan.className = 'upload-popup-name';
  nhan.textContent = ten;
  nhan.title = ten;
  const trang_thai = window.document.createElement('span');
  trang_thai.className = 'upload-popup-state' + (kieu ? ` ${kieu}` : '');
  trang_thai.textContent = trangThai;
  dong.append(nhan, trang_thai);
  elements.uploadPopupList.append(dong);
  return trang_thai;
}

function dongPopupUploadSau(ms) {
  window.clearTimeout(henDongPopupUpload);
  henDongPopupUpload = window.setTimeout(anPopupUpload, ms);
}

// Đợi chỉ mục chạy xong để đổi dòng chân popup thành "hoàn tất" rồi tự đóng.
function theoDoiLapChiMuc(soTep, phutDuKien) {
  elements.uploadPopupFooter.textContent =
    `Đang lập chỉ mục ${soTep} tệp, dự kiến xong sau khoảng ${phutDuKien} phút. `
    + 'Trong lúc đó bạn vẫn hỏi đáp bình thường được.';
  window.clearInterval(vongTheoDoiChiMuc);
  let daThayChay = false;
  vongTheoDoiChiMuc = window.setInterval(async () => {
    try {
      const status = await fetch('/api/status', { cache: 'no-store' }).then((r) => r.json());
      if (status.state === 'updating') { daThayChay = true; return; }
      if (status.state === 'ready' && daThayChay && !status.data_stale) {
        elements.uploadPopupFooter.textContent = '✅ Đã lập chỉ mục xong, tài liệu mới dùng được ngay.';
        window.clearInterval(vongTheoDoiChiMuc);
        dongPopupUploadSau(8000);
      }
    } catch { /* mất mạng tạm thời thì lượt sau thử lại */ }
  }, 5000);
}

async function taiTepVaoKho(danhSach) {
  if (!danhSach.length) return;
  moPopupUpload();
  const hopLe = [];
  for (const tep of danhSach) {
    const duoi = ('.' + tep.name.split('.').pop()).toLowerCase();
    if (DUOI_KHO_HO_TRO.has(duoi)) {
      hopLe.push(tep);
    } else {
      themDongPopupUpload(tep.name, 'Không hỗ trợ định dạng này', 'loi');
    }
  }
  if (!hopLe.length) {
    elements.uploadPopupFooter.textContent =
      'Chỉ hỗ trợ tài liệu (PDF, Word, Excel, PowerPoint...), ảnh, video/âm thanh — không nhận file nén.';
    dongPopupUploadSau(10000);
    return;
  }

  let daThem = 0;
  for (const tep of hopLe) {
    const trangThai = themDongPopupUpload(tep.name, 'Đang tải lên...');
    try {
      const response = await fetch(`/api/kho/tep?ten=${encodeURIComponent(tep.name)}`, {
        method: 'POST',
        headers: { 'X-RAG-Action': 'upload-library', 'Content-Type': 'application/octet-stream' },
        body: tep,
      });
      const payload = await response.json().catch(() => ({}));
      if (!response.ok) throw new Error(payload.detail || 'Không tải được.');
      if (payload.trang_thai === 'da_luu') {
        daThem += 1;
        trangThai.textContent = '✅ Đã thêm vào kho';
        trangThai.className = 'upload-popup-state thanh-cong';
      } else {
        trangThai.textContent = 'Kho đã có tệp này';
        trangThai.className = 'upload-popup-state canh-bao';
        trangThai.title = payload.thong_bao || '';
      }
    } catch (error) {
      trangThai.textContent = error.message || 'Không tải được';
      trangThai.className = 'upload-popup-state loi';
    }
  }

  if (!daThem) {
    dongPopupUploadSau(10000);
    return;
  }
  // Embedding trên CPU đo được khoảng 1 phút/tệp; báo trước để người dùng khỏi đợi mù.
  const phutDuKien = Math.max(1, Math.round(daThem * 1.5));
  // Rảnh thì lập chỉ mục ngay; đang bận thì máy chủ đã hẹn tự chạy khi rảnh.
  try {
    await fetch('/api/index/update', {
      method: 'POST',
      headers: { 'X-RAG-Action': 'update-index' },
    });
  } catch {
    // Mất mạng tạm thời: vòng hẹn phía máy chủ vẫn tự nạp tệp đã lưu.
  }
  theoDoiLapChiMuc(daThem, phutDuKien);
  await pollStatus();
  if (elements.documentDialog.open) await openDocumentLibrary();
}

function closeSidebar() {
  elements.sidebar.classList.remove('open');
  elements.sidebarBackdrop.classList.remove('open');
}

elements.form.addEventListener('submit', (event) => {
  event.preventDefault();
  submitQuestion(elements.input.value);
});
elements.input.addEventListener('input', resizeInput);
elements.input.addEventListener('keydown', (event) => {
  if (event.key === 'Enter' && !event.shiftKey) {
    event.preventDefault();
    elements.form.requestSubmit();
  }
});
elements.newChat.addEventListener('click', newChat);
elements.attachButton.addEventListener('click', () => elements.fileInput.click());
elements.fileInput.addEventListener('change', async () => {
  // Phải sao chép trước: gán value = '' sẽ xóa luôn FileList đang tham chiếu.
  const danh_sach = [...elements.fileInput.files];
  elements.fileInput.value = '';
  await themTepDinhKem(danh_sach);
});
// Kéo tệp thả thẳng vào khung soạn câu hỏi.
for (const su_kien of ['dragenter', 'dragover']) {
  elements.form.addEventListener(su_kien, (event) => {
    if (!event.dataTransfer?.types?.includes('Files')) return;
    event.preventDefault();
    elements.form.classList.add('dang-keo');
  });
}
for (const su_kien of ['dragleave', 'dragend']) {
  elements.form.addEventListener(su_kien, (event) => {
    if (event.target === elements.form) elements.form.classList.remove('dang-keo');
  });
}
elements.form.addEventListener('drop', (event) => {
  if (!event.dataTransfer?.files?.length) return;
  event.preventDefault();
  event.daXuLyTepKeo = true;
  elements.form.classList.remove('dang-keo');
  themTepDinhKem(event.dataTransfer.files);
});
// Thả ra ngoài khung soạn thảo vẫn đính kèm, thay vì để trình duyệt mở tệp và
// làm mất cuộc trò chuyện đang dở.
window.addEventListener('dragover', (event) => {
  if (event.dataTransfer?.types?.includes('Files')) event.preventDefault();
});
window.addEventListener('drop', (event) => {
  if (event.daXuLyTepKeo || !event.dataTransfer?.files?.length) return;
  event.preventDefault();
  elements.form.classList.remove('dang-keo');
  themTepDinhKem(event.dataTransfer.files);
});
elements.refreshSuggestions?.addEventListener('click', taiGoiYMoDau);
elements.libraryButton.addEventListener('click', openDocumentLibrary);
elements.closeDocumentDialog.addEventListener('click', () => elements.documentDialog.close());
elements.uploadLibraryButton.addEventListener('click', () => elements.libraryFileInput.click());
elements.closeUploadPopup.addEventListener('click', anPopupUpload);
elements.libraryFileInput.addEventListener('change', async () => {
  // Phải sao chép trước: gán value = '' sẽ xóa luôn FileList đang tham chiếu.
  const danhSach = [...elements.libraryFileInput.files];
  elements.libraryFileInput.value = '';
  await taiTepVaoKho(danhSach);
});
elements.documentDialog.addEventListener('click', (event) => {
  if (event.target === elements.documentDialog) elements.documentDialog.close();
});
elements.documentSearch.addEventListener('input', () => renderDocuments(elements.documentSearch.value));
elements.clearHistory.addEventListener('click', async () => {
  const soCuoc = loadHistory().length;
  if (!soCuoc) {
    showToast('Chưa có cuộc trò chuyện nào để xóa');
    return;
  }
  const dongY = await hoiXacNhan({
    tieuDe: 'Xóa lịch sử trò chuyện?',
    moTa: `Toàn bộ ${soCuoc} cuộc trò chuyện sẽ bị xóa khỏi trình duyệt và khỏi máy chủ, không khôi phục lại được.`,
    nhanDongY: 'Xóa lịch sử',
  });
  if (!dongY) return;
  localStorage.removeItem(STORAGE_KEY);
  // Xóa luôn khóa cũ, nếu không loadHistory() sẽ khôi phục lại lịch sử từ đó.
  localStorage.removeItem(LEGACY_STORAGE_KEY);
  // Người dùng bấm "xóa lịch sử" là muốn xóa thật. Bản trên máy chủ mà còn lại
  // thì lời hứa trong hộp xác nhận thành sai.
  let xoaMayChu = true;
  try {
    const res = await fetch('/api/hoi-thoai', {
      method: 'DELETE',
      headers: { 'X-RAG-Client': maTrinhDuyet() },
    });
    xoaMayChu = res.ok;
  } catch {
    xoaMayChu = false;
  }
  toggleHistorySearch(false);
  newChat();
  showToast(xoaMayChu
    ? 'Đã xóa lịch sử trên trình duyệt và máy chủ'
    : 'Đã xóa trên trình duyệt, nhưng chưa xóa được bản trên máy chủ');
});
elements.confirmAccept.addEventListener('click', () => dongXacNhan(true));
elements.confirmCancel.addEventListener('click', () => dongXacNhan(false));
// Bấm ra ngoài hoặc bấm Esc đều tính là không xóa.
elements.confirmDialog.addEventListener('click', (event) => {
  if (event.target === elements.confirmDialog) dongXacNhan(false);
});
elements.confirmDialog.addEventListener('cancel', () => dongXacNhan(false));
elements.confirmDialog.addEventListener('close', () => dongXacNhan(false));
elements.searchHistory.addEventListener('click', () => toggleHistorySearch());
elements.historySearch.addEventListener('input', () => {
  historyQuery = elements.historySearch.value;
  renderHistory();
});
elements.historySearch.addEventListener('keydown', (event) => {
  if (event.key !== 'Escape') return;
  event.preventDefault();
  toggleHistorySearch(false);
});
document.addEventListener('keydown', (event) => {
  if (!(event.ctrlKey || event.metaKey) || event.key.toLowerCase() !== 'k') return;
  event.preventDefault();
  if (window.matchMedia('(max-width: 800px)').matches) {
    elements.sidebar.classList.add('open');
    elements.sidebarBackdrop.classList.add('open');
  }
  toggleHistorySearch(true);
});
elements.menuButton.addEventListener('click', () => {
  elements.sidebar.classList.add('open');
  elements.sidebarBackdrop.classList.add('open');
});
elements.sidebarBackdrop.addEventListener('click', closeSidebar);
elements.driveSync.addEventListener('click', async () => {
  elements.driveSync.disabled = true;
  elements.driveStatus.textContent = 'Đang kết nối Google Drive...';
  try {
    const response = await fetch('/api/drive/sync', {
      method: 'POST',
      headers: { 'X-RAG-Action': 'drive-sync' },
    });
    const payload = await response.json().catch(() => ({}));
    if (!response.ok) throw new Error(payload.detail || 'Không đồng bộ được.');
    showToast('Đang tải tài liệu mới từ Drive');
    renderDriveStatus(payload);
  } catch (error) {
    elements.driveStatus.textContent = error.message;
    showToast(error.message);
  } finally {
    elements.driveSync.disabled = false;
  }
});

elements.modelButton.addEventListener('click', async (event) => {
  event.stopPropagation();
  const dangMo = !elements.modelMenu.classList.contains('hidden');
  if (dangMo) {
    closeModelMenu();
    return;
  }
  elements.modelMenu.classList.remove('hidden');
  elements.modelButton.setAttribute('aria-expanded', 'true');
  await loadModels();
});
document.addEventListener('click', (event) => {
  if (!elements.modelMenu.contains(event.target)) closeModelMenu();
});
document.addEventListener('keydown', (event) => {
  if (event.key === 'Escape') closeModelMenu();
});

elements.retry.addEventListener('click', async () => {
  elements.retry.classList.add('hidden');
  serviceState = 'loading';
  updateSendButton();
  await fetch('/api/reinitialize', { method: 'POST' }).catch(() => null);
  window.setTimeout(pollStatus, 600);
});
elements.updateIndex.addEventListener('click', async () => {
  elements.updateIndex.disabled = true;
  serviceState = 'updating';
  updateSendButton();
  try {
    const response = await fetch('/api/index/update', {
      method: 'POST',
      headers: { 'X-RAG-Action': 'update-index' },
    });
    const payload = await response.json().catch(() => ({}));
    if (!response.ok) throw new Error(payload.detail || 'Không thể cập nhật chỉ mục.');
    showToast('Đã bắt đầu cập nhật kho tri thức');
    await pollStatus();
  } catch (error) {
    showToast(error.message || 'Không thể cập nhật chỉ mục');
    await pollStatus();
  } finally {
    elements.updateIndex.disabled = false;
  }
});
document.querySelectorAll('[data-question]').forEach((button) => {
  button.addEventListener('click', () => {
    elements.input.value = button.dataset.question;
    resizeInput();
    elements.input.focus();
  });
});

// ============================================================
// GIAO DIỆN SÁNG / TỐI
// ============================================================
// Ba trạng thái chứ không phải hai: chưa chọn gì thì đi theo hệ thống, chọn rồi
// thì giữ nguyên lựa chọn đó. Luôn ghi hẳn data-theme (kể cả "light") vì bảng
// màu tối theo hệ thống được viết dưới dạng :root:not([data-theme="light"]).
const KHOA_GIAO_DIEN = 'rag-giao-dien';
const heThongDungNenToi = window.matchMedia('(prefers-color-scheme: dark)');

function docLuaChonGiaoDien() {
  try {
    const luu = localStorage.getItem(KHOA_GIAO_DIEN);
    return luu === 'dark' || luu === 'light' ? luu : null;
  } catch (error) {
    return null;
  }
}

function ghiLuaChonGiaoDien(gia_tri) {
  try {
    localStorage.setItem(KHOA_GIAO_DIEN, gia_tri);
  } catch (error) {
    /* chế độ riêng tư chặn lưu trữ - vẫn đổi được trong phiên hiện tại */
  }
}

function apDungGiaoDien() {
  const luaChon = docLuaChonGiaoDien();
  const dungNenToi = luaChon ? luaChon === 'dark' : heThongDungNenToi.matches;
  document.documentElement.dataset.theme = dungNenToi ? 'dark' : 'light';
  elements.themeButton?.setAttribute('aria-pressed', String(dungNenToi));
}

elements.themeButton?.addEventListener('click', () => {
  const dangToi = document.documentElement.dataset.theme === 'dark';
  ghiLuaChonGiaoDien(dangToi ? 'light' : 'dark');
  apDungGiaoDien();
  showToast(dangToi ? 'Đã chuyển sang giao diện sáng' : 'Đã chuyển sang giao diện tối');
});

heThongDungNenToi.addEventListener('change', () => {
  if (!docLuaChonGiaoDien()) apDungGiaoDien();
});

// ============================================================
// THU GỌN THANH BÊN (chỉ trên màn hình rộng)
// ============================================================
const KHOA_GAP_THANH_BEN = 'rag-gap-thanh-ben';

function apDungGapThanhBen(dangGap) {
  elements.appShell?.classList.toggle('sidebar-collapsed', dangGap);
  if (!elements.collapseButton) return;
  elements.collapseButton.setAttribute('aria-pressed', String(dangGap));
  const nhan = dangGap ? 'Mở rộng thanh điều hướng' : 'Thu gọn thanh điều hướng';
  elements.collapseButton.title = nhan;
  elements.collapseButton.setAttribute('aria-label', nhan);
}

elements.collapseButton?.addEventListener('click', () => {
  const dangGap = !elements.appShell.classList.contains('sidebar-collapsed');
  try {
    localStorage.setItem(KHOA_GAP_THANH_BEN, dangGap ? '1' : '0');
  } catch (error) {
    /* không lưu được thì thôi, vẫn gập được trong phiên này */
  }
  apDungGapThanhBen(dangGap);
});

// ============================================================
// NÚT CUỘN XUỐNG CUỐI
// ============================================================
function capNhatNutCuonXuong() {
  if (!elements.scrollBottom || !elements.chatScroll) return;
  const khung = elements.chatScroll;
  const conCach = khung.scrollHeight - khung.scrollTop - khung.clientHeight;
  elements.scrollBottom.classList.toggle('hien', conCach > 240);
}

elements.chatScroll?.addEventListener('scroll', capNhatNutCuonXuong, { passive: true });
elements.scrollBottom?.addEventListener('click', () => {
  elements.chatScroll.scrollTo({ top: elements.chatScroll.scrollHeight, behavior: 'smooth' });
});

apDungGiaoDien();
try {
  apDungGapThanhBen(localStorage.getItem(KHOA_GAP_THANH_BEN) === '1');
} catch (error) {
  apDungGapThanhBen(false);
}

renderHistory();
resizeInput();
taiGoiYMoDau();
taiBoLocPhamVi();
pollStatus();
statusTimer = window.setInterval(pollStatus, 4000);

// ============================================================
// PHẠM VI TRUY XUẤT (môn / cấp học / lớp / loại tài liệu)
// ============================================================
// Bộ lọc nằm ở máy chủ, phía này chỉ dựng hộp chọn từ /api/bo-loc rồi gửi kèm
// câu hỏi. Nhãn kèm số tài liệu ngay trong option: chọn "Vật lí (1)" mà biết
// trước kho chỉ có 1 tài liệu thì không ai ngồi thắc mắc sao trả lời sơ sài.
const KHOA_PHAM_VI = 'rag-pham-vi';
let boLocPhamVi = null;

function docPhamViDaLuu() {
  try {
    return JSON.parse(localStorage.getItem(KHOA_PHAM_VI) || '{}');
  } catch (error) {
    return {};
  }
}

function luuPhamVi(pham_vi) {
  try {
    localStorage.setItem(KHOA_PHAM_VI, JSON.stringify(pham_vi));
  } catch (error) {
    /* Chặn cookie/localStorage thì vẫn phải hỏi được, chỉ là không nhớ bộ lọc. */
  }
}

function phamViDangChon() {
  const pham_vi = {};
  if (elements.scopeMon?.value) pham_vi.mon_hoc = [elements.scopeMon.value];
  if (elements.scopeCap?.value) pham_vi.cap_hoc = [elements.scopeCap.value];
  if (elements.scopeLop?.value) pham_vi.lop = [Number(elements.scopeLop.value)];
  if (elements.scopeLoai?.value) pham_vi.loai_noi_dung = [elements.scopeLoai.value];
  return pham_vi;
}

function dienLuaChon(select, cacMuc, nhanTatCa) {
  if (!select) return;
  const dangChon = select.value;
  select.replaceChildren();
  const tatCa = document.createElement('option');
  tatCa.value = '';
  tatCa.textContent = nhanTatCa;
  select.append(tatCa);
  for (const muc of cacMuc || []) {
    const option = document.createElement('option');
    option.value = String(muc.gia_tri);
    option.textContent = `${muc.nhan} (${muc.so_tai_lieu})`;
    select.append(option);
  }
  // Giữ lại lựa chọn cũ nếu nhãn đó vẫn còn sau khi kho đổi.
  if (dangChon && select.querySelector(`option[value="${CSS.escape(dangChon)}"]`)) {
    select.value = dangChon;
  }
}

function capNhatTomTatPhamVi() {
  const phan = [];
  if (elements.scopeMon?.value) phan.push(elements.scopeMon.value);
  if (elements.scopeLop?.value) phan.push(`lớp ${elements.scopeLop.value}`);
  if (elements.scopeCap?.value) phan.push(elements.scopeCap.value);
  if (elements.scopeLoai?.value) {
    const chon = elements.scopeLoai.selectedOptions[0];
    phan.push((chon?.textContent || '').replace(/\s*\(\d+\)$/, '').toLowerCase());
  }
  const dangLoc = phan.length > 0;
  elements.scopeSummary.textContent = dangLoc ? phan.join(' · ') : 'Hỏi trên cả kho';
  elements.scopeButton.classList.toggle('active', dangLoc);
  elements.scopeClear.classList.toggle('hidden', !dangLoc);
  if (elements.scopeNote) {
    const chuaPhanLoai = boLocPhamVi?.chua_phan_loai || 0;
    elements.scopeNote.textContent = dangLoc
      ? `Chỉ tìm trong nhóm đã chọn. ${chuaPhanLoai} tài liệu chưa gắn nhãn sẽ không được xét.`
      : 'Chưa lọc gì thì câu hỏi chạy trên toàn bộ kho tài liệu.';
  }
  luuPhamVi(phamViDangChon());
}

async function taiBoLocPhamVi() {
  if (!elements.scopeButton) return;
  try {
    const response = await fetch('/api/bo-loc');
    if (!response.ok) throw new Error('không tải được bộ lọc');
    boLocPhamVi = await response.json();
  } catch (error) {
    // Không có bộ lọc thì ẩn hẳn thanh này đi, đừng để một nút bấm vào không ra gì.
    elements.scopeButton.closest('.scope-bar')?.classList.add('hidden');
    return;
  }
  dienLuaChon(elements.scopeMon, boLocPhamVi.mon_hoc, 'Tất cả môn');
  dienLuaChon(elements.scopeCap, boLocPhamVi.cap_hoc, 'Tất cả cấp học');
  dienLuaChon(elements.scopeLop, boLocPhamVi.lop, 'Tất cả lớp');
  dienLuaChon(elements.scopeLoai, boLocPhamVi.loai_noi_dung, 'Tất cả loại');

  const daLuu = docPhamViDaLuu();
  const datLai = (select, gia_tri) => {
    if (!select || gia_tri === undefined) return;
    const muon = String(Array.isArray(gia_tri) ? gia_tri[0] : gia_tri);
    if (select.querySelector(`option[value="${CSS.escape(muon)}"]`)) select.value = muon;
  };
  datLai(elements.scopeMon, daLuu.mon_hoc);
  datLai(elements.scopeCap, daLuu.cap_hoc);
  datLai(elements.scopeLop, daLuu.lop);
  datLai(elements.scopeLoai, daLuu.loai_noi_dung);
  capNhatTomTatPhamVi();
}

function dongBangPhamVi() {
  elements.scopePanel?.classList.add('hidden');
  elements.scopeButton?.setAttribute('aria-expanded', 'false');
}

elements.scopeButton?.addEventListener('click', (event) => {
  event.stopPropagation();
  const dangMo = !elements.scopePanel.classList.contains('hidden');
  if (dangMo) {
    dongBangPhamVi();
    return;
  }
  elements.scopePanel.classList.remove('hidden');
  elements.scopeButton.setAttribute('aria-expanded', 'true');
});

for (const select of [elements.scopeMon, elements.scopeCap, elements.scopeLop, elements.scopeLoai]) {
  select?.addEventListener('change', capNhatTomTatPhamVi);
}

elements.scopeClear?.addEventListener('click', () => {
  for (const select of [elements.scopeMon, elements.scopeCap, elements.scopeLop, elements.scopeLoai]) {
    if (select) select.value = '';
  }
  capNhatTomTatPhamVi();
  dongBangPhamVi();
});

document.addEventListener('click', (event) => {
  if (!elements.scopePanel) return;
  if (elements.scopePanel.contains(event.target) || elements.scopeButton.contains(event.target)) return;
  dongBangPhamVi();
});
document.addEventListener('keydown', (event) => {
  if (event.key === 'Escape') dongBangPhamVi();
});
