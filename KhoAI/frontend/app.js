const $ = (selector) => document.querySelector(selector);
let usbRetryTimer = null;
let usbRetryDelay = 5000;
const api = async (path, options = {}) => {
  const response = await fetch(path, {
    ...options,
    headers: { ...(options.body ? { 'Content-Type': 'application/json' } : {}), ...(options.headers || {}) },
  });
  const payload = await response.json().catch(() => ({}));
  if (!response.ok) {
    const detail = typeof payload.detail === 'string' ? payload.detail : `HTTP ${response.status}`;
    throw new Error(detail);
  }
  return payload;
};

function escapeHtml(value) {
  return String(value ?? '').replace(/[&<>"']/g, (character) => ({
    '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;',
  })[character]);
}

function showToast(message, isError = false) {
  const toast = $('#toast');
  toast.textContent = message;
  toast.classList.toggle('error', isError);
  toast.classList.add('show');
  window.clearTimeout(showToast.timer);
  showToast.timer = window.setTimeout(() => toast.classList.remove('show'), 3400);
}

function formatDateTime(value) {
  if (!value) return '—';
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return escapeHtml(value);
  return new Intl.DateTimeFormat('vi-VN', {
    day: '2-digit', month: '2-digit', year: 'numeric',
    hour: '2-digit', minute: '2-digit', second: '2-digit',
  }).format(date);
}

function setView(view) {
  const allowed = ['camera', 'history', 'cards', 'settings'];
  const selected = allowed.includes(view) ? view : 'camera';
  document.querySelectorAll('.view').forEach((section) => {
    section.classList.toggle('active', section.id === `view-${selected}`);
  });
  document.querySelectorAll('.nav-item').forEach((button) => {
    button.classList.toggle('active', button.dataset.view === selected);
  });
  const titles = { camera: 'Camera trực tiếp', history: 'Lịch sử ra vào', cards: 'Thẻ được cấp', settings: 'Thiết lập thiết bị' };
  $('#breadcrumb-current').textContent = titles[selected];
  if (location.hash !== `#${selected}`) history.replaceState(null, '', `#${selected}`);
  if (selected === 'history') loadLogs(true);
  if (selected === 'cards') loadCards();
}

document.querySelectorAll('[data-view]').forEach((button) => {
  button.addEventListener('click', () => setView(button.dataset.view));
});
document.querySelectorAll('[data-view-link]').forEach((button) => {
  button.addEventListener('click', () => setView(button.dataset.viewLink));
});
window.addEventListener('hashchange', () => setView(location.hash.slice(1)));

function renderLogRows(logs) {
  if (!logs.length) return '<tr><td colspan="4" class="empty-cell">Chưa có lượt quẹt nào.</td></tr>';
  return logs.map((log) => {
    const allowed = log.result === 'allow';
    return `<tr>
      <td class="person-cell">${escapeHtml(log.card_name || 'Thẻ chưa cấp')}</td>
      <td class="uid-cell">${escapeHtml(log.uid)}</td>
      <td class="time-cell">${formatDateTime(log.event_at)}</td>
      <td><span class="result-pill ${allowed ? 'allow' : 'deny'}">${allowed ? 'Cho phép' : 'Từ chối'}</span></td>
    </tr>`;
  }).join('');
}

async function loadLogs(showErrors = false) {
  try {
    const logs = await api('/api/logs?limit=500');
    $('#recent-logs').innerHTML = renderLogRows(logs.slice(0, 5));
    $('#all-logs').innerHTML = renderLogRows(logs);
    $('#history-count').textContent = `${logs.length} bản ghi gần nhất${logs.length === 500 ? ' (tối đa 500)' : ''}`;
  } catch (error) {
    $('#recent-logs').innerHTML = '<tr><td colspan="4" class="empty-cell">Không tải được lịch sử.</td></tr>';
    $('#all-logs').innerHTML = '<tr><td colspan="4" class="empty-cell">Không kết nối được API.</td></tr>';
    if (showErrors) showToast(error.message, true);
  }
}

async function loadCards() {
  try {
    const cards = await api('/api/cards');
    $('#card-count').textContent = `${cards.length} thẻ`;
    if (!cards.length) {
      $('#cards-table').innerHTML = '<tr><td colspan="4" class="empty-cell">Chưa có thẻ nào được cấp.</td></tr>';
      return;
    }
    $('#cards-table').innerHTML = cards.map((card) => `<tr>
      <td class="uid-cell">${escapeHtml(card.uid)}</td>
      <td class="person-cell">${escapeHtml(card.name)}</td>
      <td>${escapeHtml(card.age)}</td>
      <td><span class="result-pill ${card.active ? 'allow' : 'deny'}">${card.active ? 'Hoạt động' : 'Đã khóa'}</span></td>
    </tr>`).join('');
  } catch (error) {
    showToast(`Không tải được danh sách thẻ: ${error.message}`, true);
  }
}

async function loadStats() {
  try {
    const [stats] = await Promise.all([api('/api/stats')]);
    $('#stat-cards').textContent = stats.active_cards;
    $('#stat-scans').textContent = stats.scans_today;
    $('#stat-denied').textContent = stats.denied_today;
    $('#stat-api').textContent = 'Đang hoạt động';
    $('#api-state').textContent = 'API đang hoạt động';
    $('#api-latency').textContent = 'FastAPI · SQLite';
  } catch (error) {
    $('#stat-api').textContent = 'Ngoại tuyến';
    $('#api-state').textContent = 'Không kết nối được';
    $('#api-latency').textContent = 'Khởi chạy FastAPI để tiếp tục';
  }
}

function updateZoneStatus(available, personInZone = false, trackedIds = []) {
  const zoneState = $('#zone-state');
  zoneState.classList.toggle('alarm-zone', available && personInZone);
  zoneState.classList.toggle('safe-zone', available && !personInZone);
  zoneState.innerHTML = !available
    ? '<i class="zone-swatch"></i> AI CHƯA KẾT NỐI'
    : personInZone
      ? `<i class="zone-swatch"></i> CẢNH BÁO · NGƯỜI TRONG VÙNG CẤM${trackedIds.length ? ` · ID ${trackedIds.join(', ')}` : ''}`
      : `<i class="zone-swatch"></i> VÙNG CẤM ĐANG TRỐNG${trackedIds.length ? ` · ĐANG THEO DÕI ${trackedIds.length} NGƯỜI` : ''}`;
}

function scheduleUsbRetry() {
  if (usbRetryTimer !== null) return;
  const wait = usbRetryDelay;
  usbRetryDelay = Math.min(30000, usbRetryDelay * 2);
  usbRetryTimer = window.setTimeout(() => {
    usbRetryTimer = null;
    loadUsbCamera();
  }, wait);
}

function markUsbOffline() {
  const image = $('#usb-feed');
  image.dataset.streamActive = 'false';
  image.removeAttribute('src');
  image.hidden = true;
  $('#usb-placeholder').hidden = false;
  $('#usb-status').innerHTML = '<span class="tiny-dot muted-dot"></span> NGOẠI TUYẾN';
  updateZoneStatus(false);
  scheduleUsbRetry();
}

async function loadUsbCamera() {
  try {
    const status = await api('/api/camera/status');
    const image = $('#usb-feed');
    const placeholder = $('#usb-placeholder');
    const badge = $('#usb-status');
    if (!status.usb_available) {
      markUsbOffline();
      return;
    }
    if (usbRetryTimer !== null) window.clearTimeout(usbRetryTimer);
    usbRetryTimer = null;
    usbRetryDelay = 5000;
    placeholder.hidden = true;
    image.hidden = false;
    badge.innerHTML = '<span class="tiny-dot"></span> ĐANG PHÁT';
    updateZoneStatus(true, status.person_in_zone, status.tracked_person_ids || []);
    if (image.dataset.streamActive !== 'true') {
      image.onerror = markUsbOffline;
      image.dataset.streamActive = 'true';
      image.src = `/api/camera/stream.mjpg?t=${Date.now()}`;
    }
  } catch (_) {
    $('#usb-status').innerHTML = '<span class="tiny-dot muted-dot"></span> KHÔNG KẾT NỐI';
    updateZoneStatus(false);
    scheduleUsbRetry();
  }
}

async function refreshUsbStatus() {
  const image = $('#usb-feed');
  if (image.dataset.streamActive !== 'true') return;
  try {
    const status = await api('/api/camera/status');
    if (!status.usb_available) {
      markUsbOffline();
      return;
    }
    updateZoneStatus(true, status.person_in_zone, status.tracked_person_ids || []);
  } catch (_) {
    markUsbOffline();
  }
}

function normalizedEsp32Url() {
  return ($('#esp32-url').value || '').trim().replace(/\/+$/, '');
}

function applyEsp32Camera(url) {
  const image = $('#esp-feed');
  const placeholder = $('#esp-placeholder');
  const badge = $('#esp-status');
  if (!url) {
    image.removeAttribute('src');
    image.hidden = true;
    placeholder.hidden = false;
    badge.innerHTML = '<span class="tiny-dot muted-dot"></span> CHƯA CẤU HÌNH';
    return;
  }
  let streamUrl = url;
  if (!url.endsWith('/stream')) {
    const parsed = new URL(url);
    if (parsed.protocol === 'http:' && !parsed.port) parsed.port = '81';
    parsed.pathname = `${parsed.pathname.replace(/\/+$/, '')}/stream`;
    parsed.search = '';
    parsed.hash = '';
    streamUrl = parsed.toString();
  }
  image.onload = () => {
    placeholder.hidden = true;
    image.hidden = false;
    badge.innerHTML = '<span class="tiny-dot"></span> ĐANG PHÁT';
  };
  image.onerror = () => {
    image.hidden = true;
    placeholder.hidden = false;
    badge.innerHTML = '<span class="tiny-dot muted-dot"></span> KHÔNG KẾT NỐI';
  };
  image.src = streamUrl;
}

$('#card-form').addEventListener('submit', async (event) => {
  event.preventDefault();
  const form = new FormData(event.currentTarget);
  const submit = event.currentTarget.querySelector('button[type="submit"]');
  submit.disabled = true;
  try {
    const payload = await api('/api/cards', {
      method: 'POST',
      body: JSON.stringify({
        name: String(form.get('name')).trim(),
        age: Number(form.get('age')),
        uid: String(form.get('uid')).trim().toUpperCase(),
      }),
    });
    event.currentTarget.reset();
    showToast(`Đã cấp thẻ ${payload.uid} cho ${payload.name}.`);
    await Promise.all([loadCards(), loadStats()]);
  } catch (error) {
    showToast(error.message, true);
  } finally {
    submit.disabled = false;
  }
});

$('#refresh-button').addEventListener('click', async () => {
  await Promise.all([loadStats(), loadLogs(), loadUsbCamera()]);
  showToast('Đã làm mới dữ liệu.');
});
$('#history-refresh').addEventListener('click', () => loadLogs(true));
$('#save-camera-url').addEventListener('click', () => {
  const url = normalizedEsp32Url();
  if (!url || !/^https?:\/\//i.test(url)) {
    showToast('Nhập URL bắt đầu bằng http:// hoặc https://.', true);
    return;
  }
  localStorage.setItem('khoai-esp32-cam-url', url);
  applyEsp32Camera(url);
  showToast('Đã lưu URL camera trên trình duyệt này.');
});
$('#clear-camera-url').addEventListener('click', () => {
  localStorage.removeItem('khoai-esp32-cam-url');
  $('#esp32-url').value = '';
  applyEsp32Camera('');
  showToast('Đã xóa URL camera.');
});

$('#today-label').textContent = new Intl.DateTimeFormat('vi-VN', { weekday: 'short', day: '2-digit', month: 'short', year: 'numeric' }).format(new Date());
$('#feed-time').textContent = new Intl.DateTimeFormat('vi-VN', { hour: '2-digit', minute: '2-digit', second: '2-digit' }).format(new Date());
window.setInterval(() => {
  $('#feed-time').textContent = new Intl.DateTimeFormat('vi-VN', { hour: '2-digit', minute: '2-digit', second: '2-digit' }).format(new Date());
}, 1000);

$('#esp32-url').value = localStorage.getItem('khoai-esp32-cam-url') || '';
applyEsp32Camera($('#esp32-url').value);
setView(location.hash.slice(1) || 'camera');
Promise.all([loadStats(), loadLogs(), loadCards(), loadUsbCamera()]);
window.setInterval(loadStats, 15000);
window.setInterval(loadLogs, 15000);
window.setInterval(refreshUsbStatus, 2500);
