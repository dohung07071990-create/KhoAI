import { ZN, REASON, KIND, CAMERA_EVENT_LABEL, esc } from './core/constants.js';
import { createStore } from './core/state.js';
import { emit, Events } from './core/events.js';
import { initStreamController } from './camera/stream-controller.js';
import { initStreamMetrics } from './camera/stream-metrics.js';
import { createHistoryManager } from './dashboard/history-manager.js';
import { createAuthManager } from './auth/auth-manager.js';
import { createApiClient } from './core/api.js';
const $ = s => document.querySelector(s);
const appState = createStore({ currentUserRole: 'admin' });
function setHtmlIfChanged(element, html) {
  if (!element || element.dataset.renderedHtml === html) return false;
  element.innerHTML = html;
  element.dataset.renderedHtml = html;
  return true;
}
let currentUserRole = "admin";
appState.setState({ currentUserRole });
function applyRole(user) {
  currentUserRole = user?.role || "admin";
  appState.setState({ currentUserRole });
  emit(Events.AUTH_ROLE_CHANGED, { role: currentUserRole, user: user || null });
  if (document.body) document.body.dataset.role = currentUserRole;
  const label = document.querySelector(".operator b");
  if (label && user) label.textContent = String(user.display_name || user.username || "Người dùng").toLocaleUpperCase("vi-VN");
  const viewer = currentUserRole === "viewer";
  const preview = currentUserRole === "preview";
  const viewOnly = viewer || preview;
  const sessionButton = document.querySelector("#btn-logout");
  if (sessionButton) sessionButton.textContent = preview ? "Đăng nhập" : "Đăng xuất";
  const adminTab = document.querySelector('#tabs [data-t="admin"]');
  const adminSection = document.querySelector('#admin');
  if (adminTab) adminTab.hidden = viewer;
  if (adminSection && viewer) adminSection.hidden = true;
  let shortcutIndex = 0;
  document.querySelectorAll("#tabs button[data-t]").forEach(button => {
    if (button.hidden) { button.removeAttribute("aria-keyshortcuts"); return; }
    shortcutIndex += 1;
    button.title = `${button.textContent.trim()} · Alt+Shift+${shortcutIndex}`;
    button.setAttribute("aria-keyshortcuts", `Alt+Shift+${shortcutIndex}`);
  });
  const systemHistoryTab = document.querySelector('[data-history-tab="system"]');
  const systemHistoryPanel = document.querySelector('#history-system-panel');
  const rfidHistoryPanel = document.querySelector('#history-rfid-panel');
  let selectedHistory = document.querySelector('[data-history-tab].on')?.dataset.historyTab || "system";
  if (viewer) selectedHistory = "rfid";
  if (systemHistoryTab) systemHistoryTab.hidden = viewer;
  document.querySelectorAll('[data-history-tab]').forEach(item => {
    const active = item.dataset.historyTab === selectedHistory;
    item.classList.toggle("on", active);
    item.setAttribute("aria-selected", String(active));
  });
  if (systemHistoryPanel) systemHistoryPanel.hidden = viewer || selectedHistory !== "system";
  if (rfidHistoryPanel) rfidHistoryPanel.hidden = selectedHistory !== "rfid";
  if(viewer && location.hash==="#admin" && typeof activateTab==="function")activateTab("overview");
  (document.querySelectorAll ? document.querySelectorAll('[data-write], #admin-user-form, #cam-anti-theft-toggle, #cam-zone-edit, #cam-zone-save, #cam-zone-undo, #cam-zone-cancel, #cam-heatmap-toggle, #track-association-form, #card-form, #rfid-roi-edit, #rfid-roi-save, #rfid-roi-undo, #rfid-roi-cancel') : []).forEach(el => {
    if (el.matches('form')) el.querySelectorAll('input,select,button').forEach(control => control.disabled = viewOnly);
    else el.disabled = viewOnly;
    if (viewOnly) el.setAttribute('aria-disabled','true'); else el.removeAttribute('aria-disabled');
  });
}
function toast(message, type="info", duration=4200) {
  let host=document.getElementById("khoai-toast-region");
  if(!host){host=document.createElement("div");host.id="khoai-toast-region";host.className="toast-region";host.setAttribute("role","status");host.setAttribute("aria-live","polite");document.body.appendChild(host);}
  const item=document.createElement("div");item.className=`toast toast-${type}`;item.textContent=String(message);host.appendChild(item);
  window.setTimeout(()=>{item.classList.add("is-leaving");window.setTimeout(()=>item.remove(),250);},duration);
}
function confirmAction(message, title="Xác nhận thao tác") {
  return new Promise(resolve=>{
    let dialog=document.getElementById("khoai-confirm-dialog");
    if(!dialog){dialog=document.createElement("div");dialog.id="khoai-confirm-dialog";dialog.className="confirm-overlay";dialog.innerHTML='<section class="confirm-card" role="dialog" aria-modal="true" aria-labelledby="khoai-confirm-title"><h3 id="khoai-confirm-title"></h3><p></p><div><button type="button" data-confirm-cancel>Hủy</button><button type="button" class="primary" data-confirm-ok>Tiếp tục</button></div></section>';document.body.appendChild(dialog);}
    dialog.querySelector("h3").textContent=title;dialog.querySelector("p").textContent=message;dialog.hidden=false;
    const finish=value=>{dialog.hidden=true;dialog.querySelector('[data-confirm-ok]').onclick=null;dialog.querySelector('[data-confirm-cancel]').onclick=null;resolve(value);};
    dialog.querySelector('[data-confirm-ok]').onclick=()=>finish(true);dialog.querySelector('[data-confirm-cancel]').onclick=()=>finish(false);dialog.querySelector('[data-confirm-cancel]').focus();
  });
}
function formatDate(value) {
  if(!value) return "–"; const d=new Date(value); return Number.isNaN(d.getTime())?String(value):d.toLocaleString("vi-VN");
}

const auth = createAuthManager({
  onUser: applyRole,
  onLegacyToken: () => {}
});
const apiClient = createApiClient({
  getToken: auth.getToken,
  clearTokenIf: auth.clearTokenIf,
  requestAdminToken: auth.requestAdminToken
});
const api = apiClient.api;
const post = apiClient.post;
const requestAdminToken = auth.requestAdminToken;
const withCameraToken = url => url;
// Tab
function activateTab(tab, updateHash=true) {
  const button=document.querySelector(`#tabs button[data-t="${CSS.escape(tab)}"]`); if(!button) return;
  document.querySelectorAll("#tabs button").forEach(x=>{const active=x===button;x.classList.toggle("on",active);if(active)x.setAttribute("aria-current","page");else x.removeAttribute("aria-current");});
  document.querySelectorAll("main > section").forEach(section=>section.hidden=section.id!==tab);
  if(updateHash && location.hash!==`#${tab}`) history.replaceState(null,"",`#${tab}`);
  window.dispatchEvent(new CustomEvent("khoai-tab-changed",{detail:{tab}}));refresh();
  if(tab==="overview" || tab==="outside") refreshUsbCamera();
}
document.querySelectorAll("#tabs button").forEach(b=>b.onclick=()=>activateTab(b.dataset.t));
document.addEventListener("keydown", event => {
  if (!event.altKey || !event.shiftKey || event.ctrlKey || event.metaKey) return;
  if (event.target instanceof HTMLElement && (event.target.isContentEditable || /^(INPUT|TEXTAREA|SELECT)$/.test(event.target.tagName))) return;
  const tabs = [...document.querySelectorAll("#tabs button[data-t]")].filter(button => !button.hidden);
  const digit = /^Digit([1-9])$/.exec(event.code);
  if (!digit) return;
  const index = Number(digit[1]) - 1;
  if (index < 0 || index >= tabs.length) return;
  event.preventDefault();
  activateTab(tabs[index].dataset.t);
  tabs[index].focus();
});
window.addEventListener("hashchange",()=>activateTab(location.hash.slice(1)||"overview",false));
activateTab(location.hash.slice(1)||"overview",false);

document.querySelectorAll("[data-history-tab]").forEach(button => button.addEventListener("click", () => {
  const selected = button.dataset.historyTab;
  document.querySelectorAll("[data-history-tab]").forEach(item => {
    const active = item === button;
    item.classList.toggle("on", active);
    item.setAttribute("aria-selected", String(active));
  });
  $("#history-system-panel").hidden = selected !== "system";
  $("#history-rfid-panel").hidden = selected !== "rfid";
}));

const logoutButton = $("#btn-logout");
if (logoutButton) logoutButton.addEventListener("click", async () => {
  if (currentUserRole === "preview") {
    try {
      const user = await auth.beginLogin();
      if (user) applyRole(user);
    } catch (_) { /* Login remains open so the user can retry. */ }
    return;
  }
  try { await fetch("/api/logout", {method:"POST", credentials:"same-origin"}); }
  finally { location.reload(); }
});

// Địa chỉ camera: nhớ trong trình duyệt
let heatmapEnabled = false;
const heatmapButton = $("#cam-heatmap-toggle");
[["out","cam-out"]].forEach(([k,id]) => {
  const inp = $("#cam-"+k+"-url"), img = $("#"+id+" img");
  // Camera ngoài mặc định lấy trực tiếp luồng USB đã được YOLO xử lý từ backend KhoAI.
  // Người dùng vẫn có thể thay bằng URL MJPEG của một camera IP nếu cần.
  const defaultUrl = "/api/camera/stream";
  inp.value = localStorage.getItem("cam-"+k) || defaultUrl;
  const apply = () => {
    localStorage.setItem("cam-"+k, inp.value);
    if (k === "out") {
      heatmapEnabled = false;
      if (heatmapButton) { heatmapButton.setAttribute("aria-pressed", "false"); heatmapButton.textContent = "Heatmap chuyển động"; }
    }
    img.src = k === "out" && inp.value.startsWith("/api/camera/") ? withCameraToken(inp.value) : inp.value;
  };
  inp.onchange = apply;
  if (k === "out" && !localStorage.getItem("cam-out")) img.src = withCameraToken(defaultUrl);
  else if (inp.value) img.src = k === "out" && inp.value.startsWith("/api/camera/") ? withCameraToken(inp.value) : inp.value;
});

// Camera trong ESP32-CAM: truyền MJPEG trực tiếp, độc lập với AI camera USB ngoài.
(() => {
  const input = $("#cam-in-url");
  const image = $("#cam-in img");
  const status = $("#cam-in-status");
  const reload = $("#cam-in-reload");
  if (!input || !image) return;
  const defaultUrl = "/api/camera/inside/stream";
  input.value = defaultUrl;
  input.readOnly = true;
  const apply = () => {
    const url = "/api/camera/inside/stream";
    if (!url) {
      image.removeAttribute("src");
      if (status) status.textContent = "Chưa cấu hình địa chỉ camera trong.";
      return;
    }
    if (status) status.textContent = "Đang kết nối camera trong…";
    const separator = url.includes("?") ? "&" : "?";
    image.src = url + separator + "_ts=" + Date.now();
  };
  input.addEventListener("change", apply);
  if (reload) reload.addEventListener("click", apply);
  image.addEventListener("load", () => { if (status) status.textContent = "Camera trong đang truyền hình ảnh."; });
  image.addEventListener("error", () => { if (status) status.textContent = "Không nhận được hình ảnh. Kiểm tra KHOAI_ESP32_CAM_STREAM_URL và kết nối backend tới ESP32-CAM."; });
  if (input.value) apply();
})();

// Camera USB ngoài: thống kê pipeline, vẽ vùng bảo vệ và lịch sử sự kiện.
const outOverlay = $("#cam-out-overlay");
const outImage = $("#cam-out img");
let cameraZone = [];

if (heatmapButton && outImage) {
  heatmapButton.onclick = () => {
    heatmapEnabled = !heatmapEnabled;
    heatmapButton.setAttribute("aria-pressed", String(heatmapEnabled));
    heatmapButton.textContent = heatmapEnabled ? "Quay lại video AI" : "Heatmap chuyển động";
    if (heatmapEnabled) {
      outImage.src = withCameraToken(`/api/camera/heatmap?t=${Date.now()}`);
    } else {
      const saved = localStorage.getItem("cam-out") || "/api/camera/stream";
      outImage.src = saved.startsWith("/api/camera/") ? withCameraToken(saved) : saved;
    }
  };
  setInterval(() => {
    if (heatmapEnabled && !document.querySelector("#outside").hidden) {
      outImage.src = withCameraToken(`/api/camera/heatmap?t=${Date.now()}`);
    }
  }, 1500);
}
let zoneDraft = [];
let zoneEditing = false;
let cameraFrameSize = null;

function cameraImageRect(rect) {
  const frameW = Number(cameraFrameSize?.[0]) || 4;
  const frameH = Number(cameraFrameSize?.[1]) || 3;
  const imageRatio = frameW / frameH;
  const boxRatio = rect.width / rect.height;
  if (imageRatio > boxRatio) {
    const height = rect.width / imageRatio;
    return {left: 0, top: (rect.height - height) / 2, width: rect.width, height};
  }
  const width = rect.height * imageRatio;
  return {left: (rect.width - width) / 2, top: 0, width, height: rect.height};
}

function drawCameraZone() {
  if (!outOverlay) return;
  const rect = outOverlay.getBoundingClientRect();
  if (!rect.width || !rect.height) return;
  const dpr = window.devicePixelRatio || 1;
  outOverlay.width = Math.round(rect.width * dpr);
  outOverlay.height = Math.round(rect.height * dpr);
  const ctx = outOverlay.getContext("2d");
  ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
  ctx.clearRect(0, 0, rect.width, rect.height);
  const basePoints = zoneEditing ? zoneDraft : cameraZone;
  const activeFactor = (!zoneEditing && window.cameraZonePeriod === "night") ? 1.15 : 1.0;
  const baseCx = cameraZone.reduce((sum, p) => sum + p[0], 0) / Math.max(1, cameraZone.length);
  const baseCy = cameraZone.reduce((sum, p) => sum + p[1], 0) / Math.max(1, cameraZone.length);
  const pts = (!zoneEditing && activeFactor !== 1)
    ? basePoints.map(([x, y]) => [Math.max(0, Math.min(1, baseCx + (x - baseCx) * activeFactor)), Math.max(0, Math.min(1, baseCy + (y - baseCy) * activeFactor))])
    : basePoints;
  $("#cam-zone-edit").disabled = zoneEditing;
  $("#cam-zone-undo").disabled = !zoneEditing || !zoneDraft.length;
  $("#cam-zone-save").disabled = !zoneEditing || zoneDraft.length < 3;
  $("#cam-zone-cancel").disabled = !zoneEditing;
  if (!pts.length) return;
  const content = cameraImageRect(rect);
  const px = pts.map(([x, y]) => [content.left + x * content.width, content.top + y * content.height]);
  ctx.lineWidth = 2.5;
  ctx.strokeStyle = zoneEditing ? "#00e5ff" : "rgba(255,255,255,.92)";
  ctx.fillStyle = zoneEditing ? "rgba(0,229,255,.12)" : "rgba(255,255,255,.04)";
  ctx.beginPath();
  ctx.moveTo(px[0][0], px[0][1]);
  for (let i = 1; i < px.length; i++) ctx.lineTo(px[i][0], px[i][1]);
  if (px.length >= 3) { ctx.closePath(); ctx.fill(); }
  ctx.stroke();
  // Vùng WARNING mở rộng quanh vùng ALARM; ban đêm nới rộng thêm theo lịch.
  const factor = 1.12;
  const cx = baseCx;
  const cy = baseCy;
  const warningPx = cameraZone.map(([x, y]) => [
    content.left + Math.max(0, Math.min(1, cx + (x - cx) * factor)) * content.width,
    content.top + Math.max(0, Math.min(1, cy + (y - cy) * factor)) * content.height
  ]);
  ctx.save(); ctx.strokeStyle = "#ffd43b"; ctx.lineWidth = 2; ctx.setLineDash([7, 5]);
  ctx.beginPath(); ctx.moveTo(warningPx[0][0], warningPx[0][1]);
  warningPx.slice(1).forEach(([x, y]) => ctx.lineTo(x, y));
  ctx.closePath(); ctx.stroke(); ctx.restore();
  px.forEach(([x, y], i) => {
    ctx.beginPath(); ctx.arc(x, y, 5, 0, Math.PI * 2);
    ctx.fillStyle = zoneEditing ? "#00e5ff" : "#fff"; ctx.fill();
    ctx.fillStyle = "#111"; ctx.font = "12px sans-serif";
    ctx.fillText(String(i + 1), x + 7, y - 7);
  });
}

function setZoneMessage(message, isError = false) {
  const el = $("#cam-zone-msg");
  if (el) { el.textContent = message; el.classList.toggle("on-bad", isError); }
}

async function loadCameraZone() {
  try {
    const data = await api("/api/camera/zone");
    cameraZone = Array.isArray(data.points) ? data.points : [];
    if (!zoneEditing) drawCameraZone();
    setZoneMessage(`Đã tải vùng bảo vệ (${cameraZone.length} điểm). Chọn “Vẽ vùng bảo vệ” để thay đổi.`);
  } catch (err) {
    setZoneMessage(`Không tải được vùng bảo vệ: ${err.message}`, true);
  }
}

if (outOverlay) {
  outOverlay.addEventListener("click", e => {
    if (!zoneEditing) return;
    const r = outOverlay.getBoundingClientRect();
    if (!r.width || !r.height) return;
    const content = cameraImageRect(r);
    const x = Math.min(1, Math.max(0, (e.clientX - r.left - content.left) / content.width));
    const y = Math.min(1, Math.max(0, (e.clientY - r.top - content.top) / content.height));
    zoneDraft.push([Number(x.toFixed(5)), Number(y.toFixed(5))]);
    drawCameraZone();
    setZoneMessage(`Đang vẽ vùng: ${zoneDraft.length} điểm. Cần ít nhất 3 điểm, sau đó bấm “Lưu vùng”.`);
  });
  if (window.ResizeObserver) new ResizeObserver(drawCameraZone).observe(outOverlay.parentElement);
  window.addEventListener("resize", drawCameraZone);
}

$("#cam-zone-edit").onclick = () => {
  zoneDraft = [];
  zoneEditing = true;
  outOverlay.classList.add("editing");
  drawCameraZone();
  setZoneMessage("Bấm lần lượt ít nhất 3 điểm bao quanh khu vực cần bảo vệ. Điểm được nối theo thứ tự bạn bấm.");
};
$("#cam-zone-undo").onclick = () => {
  zoneDraft.pop(); drawCameraZone();
  setZoneMessage(`Đã bỏ điểm cuối. Hiện có ${zoneDraft.length} điểm.`);
};
$("#cam-zone-cancel").onclick = () => {
  zoneEditing = false; zoneDraft = [];
  outOverlay.classList.remove("editing"); drawCameraZone();
  setZoneMessage("Đã hủy thay đổi; vùng đang lưu không bị ảnh hưởng.");
};
$("#cam-zone-save").onclick = async () => {
  if (zoneDraft.length < 3) return setZoneMessage("Vùng cần ít nhất 3 điểm.", true);
  try {
    const result = await api("/api/camera/zone", {
      method: "PUT", headers: {"Content-Type":"application/json"},
      body: JSON.stringify({points: zoneDraft})
    });
    cameraZone = result.points || zoneDraft;
    zoneDraft = []; zoneEditing = false;
    outOverlay.classList.remove("editing"); drawCameraZone();
    setZoneMessage("Đã lưu vùng bảo vệ. AI sẽ áp dụng vùng mới mà không cần khởi động lại server.");
  } catch (err) {
    setZoneMessage(`Không lưu được vùng: ${err.message}`, true);
  }
};

// RFID door-entry ROI is independent from the protected-zone polygon.
const rfidRoiOverlay = $("#rfid-roi-overlay");
const rfidRoiImage = $("#rfid-roi-image");
let rfidEntryRoi = [];
let rfidRoiDraft = [];
let rfidRoiEditing = false;
function drawRfidEntryRoi() {
  if (!rfidRoiOverlay) return;
  const rect = rfidRoiOverlay.getBoundingClientRect();
  if (!rect.width || !rect.height) return;
  const dpr = window.devicePixelRatio || 1;
  rfidRoiOverlay.width = Math.round(rect.width * dpr);
  rfidRoiOverlay.height = Math.round(rect.height * dpr);
  const ctx = rfidRoiOverlay.getContext("2d");
  ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
  ctx.clearRect(0, 0, rect.width, rect.height);
  const points = rfidRoiEditing ? rfidRoiDraft : rfidEntryRoi;
  $("#rfid-roi-edit").disabled = rfidRoiEditing;
  $("#rfid-roi-undo").disabled = !rfidRoiEditing || !rfidRoiDraft.length;
  $("#rfid-roi-save").disabled = !rfidRoiEditing || rfidRoiDraft.length < 3;
  $("#rfid-roi-cancel").disabled = !rfidRoiEditing;
  if (!points.length) return;
  const content = cameraImageRect(rect);
  const px = points.map(([x, y]) => [content.left + x * content.width, content.top + y * content.height]);
  ctx.lineWidth = 2.5;
  ctx.strokeStyle = rfidRoiEditing ? "#00e5ff" : "#f2c230";
  ctx.fillStyle = rfidRoiEditing ? "rgba(0,229,255,.16)" : "rgba(242,194,48,.12)";
  ctx.beginPath(); ctx.moveTo(px[0][0], px[0][1]);
  px.slice(1).forEach(([x, y]) => ctx.lineTo(x, y));
  if (px.length >= 3) { ctx.closePath(); ctx.fill(); }
  ctx.stroke();
  px.forEach(([x, y], index) => {
    ctx.beginPath(); ctx.arc(x, y, 5, 0, Math.PI * 2); ctx.fillStyle = "#fff"; ctx.fill();
    ctx.fillStyle = "#111"; ctx.font = "12px sans-serif"; ctx.fillText(String(index + 1), x + 7, y - 7);
  });
}
function setRfidRoiMessage(message, bad = false) {
  const el = $("#rfid-roi-msg");
  if (el) { el.textContent = message; el.classList.toggle("on-bad", bad); }
}
async function loadRfidEntryRoi() {
  try {
    const data = await api("/api/rfid/entry-roi");
    rfidEntryRoi = Array.isArray(data.points) ? data.points : [];
    drawRfidEntryRoi();
    setRfidRoiMessage(rfidEntryRoi.length ? `Đã tải ROI cửa (${rfidEntryRoi.length} điểm).` : "Chưa cấu hình ROI cửa. Vẽ ít nhất 3 điểm để bật ghép tự động.");
  } catch (err) { setRfidRoiMessage(`Không tải được ROI cửa: ${err.message}`, true); }
}
function reloadRfidRoiImage() {
  if (rfidRoiImage) rfidRoiImage.src = withCameraToken(`/api/camera/snapshot?t=${Date.now()}`);
}
if (rfidRoiOverlay) {
  rfidRoiOverlay.addEventListener("click", event => {
    if (!rfidRoiEditing) return;
    const rect = rfidRoiOverlay.getBoundingClientRect();
    const content = cameraImageRect(rect);
    const x = Math.min(1, Math.max(0, (event.clientX - rect.left - content.left) / content.width));
    const y = Math.min(1, Math.max(0, (event.clientY - rect.top - content.top) / content.height));
    rfidRoiDraft.push([Number(x.toFixed(5)), Number(y.toFixed(5))]);
    drawRfidEntryRoi();
    setRfidRoiMessage(`Đang vẽ ROI cửa: ${rfidRoiDraft.length} điểm; cần ít nhất 3 điểm.`);
  });
  if (window.ResizeObserver) new ResizeObserver(drawRfidEntryRoi).observe(rfidRoiOverlay.parentElement);
  window.addEventListener("resize", drawRfidEntryRoi);
}
$("#rfid-roi-reload").onclick = reloadRfidRoiImage;
$("#rfid-roi-edit").onclick = () => {
  rfidRoiDraft = []; rfidRoiEditing = true; rfidRoiOverlay.classList.add("editing");
  drawRfidEntryRoi(); setRfidRoiMessage("Bấm lần lượt ít nhất 3 điểm bao quanh khu vực quẹt thẻ.");
  reloadRfidRoiImage();
};
$("#rfid-roi-undo").onclick = () => { rfidRoiDraft.pop(); drawRfidEntryRoi(); };
$("#rfid-roi-cancel").onclick = () => {
  rfidRoiDraft = []; rfidRoiEditing = false; rfidRoiOverlay.classList.remove("editing");
  drawRfidEntryRoi(); setRfidRoiMessage("Đã hủy; ROI đã lưu không thay đổi.");
};
$("#rfid-roi-save").onclick = async () => {
  if (rfidRoiDraft.length < 3) return setRfidRoiMessage("ROI cửa cần ít nhất 3 điểm.", true);
  try {
    const result = await api("/api/rfid/entry-roi", {method:"PUT", headers:{"Content-Type":"application/json"}, body:JSON.stringify({points:rfidRoiDraft})});
    rfidEntryRoi = result.points || rfidRoiDraft; rfidRoiDraft = []; rfidRoiEditing = false;
    rfidRoiOverlay.classList.remove("editing"); drawRfidEntryRoi();
    setRfidRoiMessage("Đã lưu ROI cửa. Không cần sửa .env hoặc khởi động lại server.");
  } catch (err) { setRfidRoiMessage(`Không lưu được ROI cửa: ${err.message}`, true); }
};
if (rfidRoiImage) rfidRoiImage.addEventListener("load", drawRfidEntryRoi);
loadRfidEntryRoi().then(reloadRfidRoiImage);

async function refreshPendingRfidBindings() {
  const host = $("#rfid-pending-list");
  if (!host) return;
  try {
    const data = await api("/api/rfid/pending");
    const tickets = data.tickets || [];
    const tracks = data.tracks || [];
    if (!tickets.length) { host.innerHTML = "<p>Chưa có vé RFID đang chờ.</p>"; return; }
    host.innerHTML = tickets.map(ticket => `
      <div class="rfid-pending-ticket"><b>${esc(ticket.name || "Thẻ")} · UID ${esc(ticket.uid)}</b>
        <small>Hết hạn sau ${esc(ticket.expires_in)} giây · Quyền: ${esc((ticket.allowed_zones || []).join(", ") || "không có vùng Camera USB")}</small>
        <div class="rfid-track-options">${tracks.length ? tracks.map(track => `
          <div class="rfid-track-option"><img loading="lazy" src="${esc(track.thumbnail_url)}?t=${Date.now()}" alt="Ảnh Track ${esc(track.track_id)}">
            <span><b>Track ${esc(track.track_id)}</b><small>${esc(track.state)}</small>
            <button type="button" data-bind-rfid="${esc(ticket.uid)}" data-track-id="${esc(track.track_id)}">Ghép thẻ này</button></span>
          </div>`).join("") : "<p>Chưa có Track đang hiển thị.</p>"}</div>
      </div>`).join("");
  } catch (err) { host.innerHTML = `<p class="on-warn">Không tải được danh sách ghép RFID: ${esc(err.message)}</p>`; }
}

const antiTheftButton = $("#cam-anti-theft-toggle");
if (antiTheftButton) {
  antiTheftButton.onclick = async () => {
    antiTheftButton.disabled = true;
    try {
      const enabled = antiTheftButton.getAttribute("aria-pressed") !== "true";
      if (!enabled && !(await confirmAction("Tắt chống trộm sẽ ngừng giám sát xâm nhập bằng vùng bảo vệ. Bạn có chắc chắn?", "Xác nhận tắt chống trộm"))) return;
      const result = await api("/api/camera/anti-theft", {
        method: "PUT", headers: {"Content-Type":"application/json"},
        body: JSON.stringify({enabled})
      });
      antiTheftButton.setAttribute("aria-pressed", String(result.anti_theft_enabled));
      antiTheftButton.textContent = result.anti_theft_enabled ? "Tắt chống trộm" : "Bật chống trộm";
      setZoneMessage(result.alarm_state === "ALARM"
        ? "Đã bật chống trộm: phát hiện người đang ở trong vùng ALARM."
        : `Chống trộm ${result.anti_theft_enabled ? "đã bật" : "đã tắt"}. Trạng thái: ${result.alarm_state}.`);
      await refreshUsbCamera(); toast(`Đã ${result.anti_theft_enabled ? "bật" : "tắt"} chống trộm.`, "success");
    } catch (err) { setZoneMessage(`Không đổi được trạng thái chống trộm: ${err.message}`, true); toast(`Không đổi được trạng thái chống trộm: ${err.message}`, "error"); }
    finally { antiTheftButton.disabled = false; }
  };
}

function updateTwinStatusFromApp(data={}) {
  const state=data.frame_stale?"UNKNOWN":data.anti_theft_enabled===false?"DISABLED":data.alarm_state||"UNKNOWN";
  const tracks=Object.values(data.decision_tracks||{});
  const people=Number(data.people_in_zone??data.outside?.people??0);
  const set=(id,value)=>{const el=document.getElementById(id);if(el)el.textContent=value;};
  const stateLabels={SAFE:"An toàn",PASSERBY:"Người đi qua",AUTHORIZED:"Đã xác thực",WARNING:"Cảnh báo",REVIEW:"Cần kiểm tra",SUSPICIOUS:"Đáng ngờ",ALARM:"Báo động",UNKNOWN:"Chưa xác định",DISABLED:"Đã tắt",OFFLINE:"Mất kết nối"};
  set("twin-state",stateLabels[state]||"Chưa xác định");set("twin-people",Number.isFinite(people)?people:"–");set("twin-tracks",tracks.length);
  set("twin-fps",data.process_fps==null?"–":Number(data.process_fps).toFixed(1));
  set("twin-latency",data.process_latency_ms==null?"–":`${Math.round(data.process_latency_ms)} ms`);
  set("twin-state-reason",data.frame_stale?"Khung hình đã cũ · trạng thái an ninh hiện tại chưa xác định":data.anti_theft_enabled===false?"Chống trộm đang tắt · vùng bảo vệ không được giám sát":data.camera_ok===false?"Camera USB ngoại tuyến":data.ai_ok===false?"Pipeline AI chưa có frame mới":people>0?`${people} người đang được ghi nhận trong vùng bảo vệ`:`${tracks.length} Track đang được theo dõi`);
  set("twin-camera-status",data.camera_ok===false?"Ngoại tuyến":data.frame_stale?"Dữ liệu cũ":data.ai_ok===false?"AI gián đoạn":"Trực tuyến");
  set("twin-tracker-status",data.tracking_enabled?"Đang chạy":"Không khả dụng");
  const stateCard=document.getElementById("twin-state-card");if(stateCard){stateCard.dataset.state=state;stateCard.dataset.antiTheft=data.anti_theft_enabled===false?"disabled":"enabled";}
  const sync=document.getElementById("twin-sync-label");if(sync)sync.textContent=data.camera_ok===false?"CAMERA NGOẠI TUYẾN":data.frame_stale?"DỮ LIỆU CŨ":data.ai_ok===false?"AI GIÁN ĐOẠN":(stateLabels[state]||"CHƯA XÁC ĐỊNH").toLocaleUpperCase("vi-VN");
  set("twin-data-age",data.frame_age_ms!=null?`ĐỘ TRỄ KHUNG HÌNH: ${Math.round(Number(data.frame_age_ms))} ms${data.last_frame_at?` · ${formatDate(data.last_frame_at)}`:""}`:data.last_frame_at?`KHUNG HÌNH CUỐI: ${formatDate(data.last_frame_at)}`:"DỮ LIỆU VỪA CẬP NHẬT");
}
let lastNotifiedSecurityState = null;
let alarmNotificationsEnabled = false;
let alarmAudioContext = null;
const alarmNotifyButton=document.getElementById("alarm-notify-toggle");
if(alarmNotifyButton) alarmNotifyButton.addEventListener("click",async()=>{
  alarmNotificationsEnabled=!alarmNotificationsEnabled;
  if(alarmNotificationsEnabled && "Notification" in window && Notification.permission==="default") await Notification.requestPermission();
  if(alarmNotificationsEnabled){try{const AudioCtx=window.AudioContext||window.webkitAudioContext;if(AudioCtx){alarmAudioContext=alarmAudioContext||new AudioCtx();await alarmAudioContext.resume();}}catch(_){}}
  alarmNotifyButton.setAttribute("aria-pressed",String(alarmNotificationsEnabled));
  alarmNotifyButton.textContent=alarmNotificationsEnabled?"Tắt thông báo ALARM":"Bật thông báo ALARM";
  toast(alarmNotificationsEnabled?"Đã bật thông báo ALARM trên trình duyệt.":"Đã tắt thông báo ALARM.","success");
});
function updateGlobalStatus(data={}, incidents=null) {
  const state=data.alarm_state||({off:"SAFE",warning:"WARNING",severe:"ALARM",unknown:"UNKNOWN"}[data.alarm]||"UNKNOWN");
  const label=({SAFE:"An toàn",WARNING:"Cảnh báo",ALARM:"Báo động",UNKNOWN:"Chưa xác định",DISABLED:"Chống trộm tắt"})[state]||state;
  const el=document.getElementById("global-security-state");if(el){el.textContent=label;el.dataset.state=state;}
  const count=document.getElementById("global-open-incidents");
  if(count) count.textContent=Array.isArray(incidents)?String(incidents.filter(item=>item.status==="OPEN").length):"–";
  if(state==="ALARM" && lastNotifiedSecurityState!=="ALARM" && alarmNotificationsEnabled){
    toast("KhoAI đang ở trạng thái BÁO ĐỘNG.","error",7000);
    if("Notification" in window && Notification.permission==="granted") new Notification("KhoAI · Báo động",{body:"Bộ phân tích AI đang báo động. Hãy kiểm tra sự cố và camera."});
    try{if(alarmAudioContext && alarmAudioContext.state==="running"){const osc=alarmAudioContext.createOscillator();const gain=alarmAudioContext.createGain();osc.connect(gain);gain.connect(alarmAudioContext.destination);osc.frequency.value=880;gain.gain.value=.08;osc.start();osc.stop(alarmAudioContext.currentTime+.22);}}catch(_){}
  }
  lastNotifiedSecurityState=state;
}
let outReconnectDelay = 2000;
let outReconnectTimer = null;
let outReconnectAttempts = 0;
const maxOutReconnectAttempts = 5;
function installImageFallback(img, message, retry) {
  if(!img || img.dataset.fallbackInstalled) return;img.dataset.fallbackInstalled="1";
  const host=img.parentElement;const box=document.createElement("div");box.className="camera-fallback";box.hidden=true;box.innerHTML=`<strong>${esc(message)}</strong><span>Không nhận được luồng hình ảnh.</span><button type="button">Thử kết nối lại</button>`;host.appendChild(box);
  img.addEventListener("error",()=>{box.hidden=false;img.classList.add("is-broken");if(img===outImage&&outReconnectAttempts>=maxOutReconnectAttempts)box.querySelector("span").textContent="Đã tạm dừng kết nối lại tự động. Bấm thử lại để tiếp tục.";});img.addEventListener("load",()=>{box.hidden=true;img.classList.remove("is-broken");});box.querySelector("button").addEventListener("click",()=>{if(img===outImage){outReconnectAttempts=0;outReconnectDelay=2000;}retry?.();});
  if(img.complete && img.naturalWidth===0 && img.currentSrc) {box.hidden=false;img.classList.add("is-broken");}
}
installImageFallback(document.querySelector("#cam-in img"),"Camera trong mất tín hiệu",()=>document.querySelector("#cam-in-reload")?.click());
installImageFallback(document.querySelector("#cam-out img"),"Camera ngoài mất tín hiệu",()=>{const image=document.querySelector("#cam-out img");const src=localStorage.getItem("cam-out")||"/api/camera/stream";image.src=src+(src.includes("?")?"&":"?")+"retry="+Date.now();});
installImageFallback(document.querySelector("#rfid-roi-image"),"Không tải được ảnh ROI cửa",()=>reloadRfidRoiImage());

async function refreshUsbCamera() {
  try {
    const s = await api("/api/camera/status");
    if (Array.isArray(s.frame_size)) cameraFrameSize = s.frame_size;
    const decisionTracks = Object.values(s.decision_tracks || {});
    const frameAge = s.frame_age_ms == null ? Number.NaN : Number(s.frame_age_ms);
    const captureFps = Number(s.capture_fps);
    const staleAfterMs = Number.isFinite(captureFps) && captureFps > 0 ? Math.max(5000, 3000 / captureFps) : 5000;
    const frameStale = Number.isFinite(frameAge) && frameAge > staleAfterMs;
    const liveStatus = {...s, frame_stale: frameStale};
    updateTwinStatusFromApp(liveStatus);
    if (window.KhoAIWarehouseTwin?.update) window.KhoAIWarehouseTwin.update(liveStatus);
    window.KhoAIBackendLastSuccess = Date.now();
    const visionState = $("#vision-state");
    if (visionState) { visionState.textContent = s.alarm_state || "UNKNOWN"; visionState.dataset.state = s.alarm_state || "UNKNOWN"; }
    const visionPeople = $("#vision-zone-people"); if (visionPeople) visionPeople.textContent = s.people_in_zone ?? 0;
    const visionTracks = $("#vision-track-count"); if (visionTracks) visionTracks.textContent = decisionTracks.length;
    const visionLatency = $("#vision-latency"); if (visionLatency) visionLatency.textContent = s.process_latency_ms == null ? "–" : `${Math.round(s.process_latency_ms)} ms`;
    const visionHealth = $("#vision-feed-health"); if (visionHealth) visionHealth.textContent = !s.camera_ok ? "CAMERA NGOẠI TUYẾN" : frameStale ? "KHUNG HÌNH CŨ · TRẠNG THÁI CHƯA XÁC ĐỊNH" : !s.ai_ok ? "AI CHƯA CẬP NHẬT" : "CAMERA + AI ĐANG HOẠT ĐỘNG";
    const trackList = $("#decision-track-list");
    if (trackList) {
      const stateLabels = {PASSERBY:"Người đi qua", WARNING:"Cảnh báo", SUSPICIOUS:"Đáng ngờ", ALARM:"Báo động", AUTHORIZED:"Đã xác thực", REVIEW:"Cần kiểm tra", SAFE:"An toàn"};
      const stateClasses = {PASSERBY:"passerby", WARNING:"warning", SUSPICIOUS:"suspicious", ALARM:"alarm", AUTHORIZED:"authorized", REVIEW:"review", SAFE:"safe"};
      trackList.innerHTML = decisionTracks.length ? decisionTracks.map(track => {
        const state = String(track.state || "UNKNOWN");
        const badgeClass = stateClasses[state] || "unknown";
        const label = stateLabels[state] || state;
        return `
        <li class="${state === "ALARM" ? "severe" : state === "SUSPICIOUS" || state === "WARNING" ? "warning" : ""}">
          <span><b>Track ${esc(track.track_id)}</b><em class="state-badge state-badge--${badgeClass}">${esc(label)}</em>
          <small>Vùng ${esc(ZN[track.zone] || track.zone || "–")} · Hiện diện ${esc(track.elapsed_seconds ?? 0)} giây${track.grace_remaining != null ? ` · Còn ${esc(track.grace_remaining)} giây ân hạn` : ""}${track.proximity_seconds > 0 ? ` · Vùng đệm ${esc(track.proximity_seconds)} giây` : ""}${track.approach_count > 0 ? ` · Tiến sát ${esc(track.approach_count)} lần` : ""}</small></span>
        </li>`;
      }).join("") : "<li>Chưa có Track đang được theo dõi.</li>";
    }
    const trackSelect = $("#associate-track");
    if (trackSelect) {
      const selected = trackSelect.value;
      const ids = Array.isArray(s.tracked_person_ids) ? s.tracked_person_ids.map(String) : [];
      const currentIds = Array.from(trackSelect.options).slice(1).map(option => option.value);
      if (ids.length !== currentIds.length || ids.some((id, i) => id !== currentIds[i])) {
        trackSelect.replaceChildren(new Option("Chọn Track ID", ""), ...ids.map(id => new Option(`ID ${id}`, id)));
        if (ids.includes(selected)) trackSelect.value = selected;
      }
    }
    window.cameraZonePeriod = s.zone_period || "day";
    if (antiTheftButton) {
      antiTheftButton.setAttribute("aria-pressed", String(Boolean(s.anti_theft_enabled)));
      antiTheftButton.textContent = s.anti_theft_enabled ? "Tắt chống trộm" : "Bật chống trộm";
    }
    const securityState = $("#cam-security-state");
    if (securityState) { securityState.textContent = ({SAFE:"An toàn",WARNING:"Cảnh báo",ALARM:"Báo động",UNKNOWN:"Chưa xác định"})[s.alarm_state] || s.alarm_state || "Chưa xác định"; securityState.className = s.alarm_state === "ALARM" ? "on-bad" : s.alarm_state === "WARNING" ? "on-warn" : s.alarm_state === "SAFE" ? "on-ok" : "on-warn"; }
    const antiState=$("#cam-anti-theft-state");if(antiState){antiState.textContent=s.anti_theft_enabled===true?"Đang bật":s.anti_theft_enabled===false?"Đang tắt":"Chưa xác minh";antiState.className=s.anti_theft_enabled===true?"on-ok":s.anti_theft_enabled===false?"on-warn":"";}
    const zonePeriod = $("#cam-zone-period");
    if (zonePeriod) zonePeriod.textContent = s.zone_period === "night" ? "Ban đêm (18:00–05:59)" : "Ban ngày (06:00–17:59)";
    drawCameraZone();
    $("#cam-read-fps").textContent = s.capture_fps == null ? "–" : s.capture_fps;
    $("#cam-ai-fps").textContent = s.process_fps == null ? (s.fps ?? "–") : s.process_fps;
    $("#cam-latency").textContent = s.process_latency_ms == null ? "–" : `${s.process_latency_ms} ms`;
    $("#cam-age").textContent = s.frame_age_ms == null ? "–" : `${s.frame_age_ms} ms`;
    $("#cam-detections").textContent = s.detections ?? 0;
    const aiStatus = !s.camera_ok ? (s.camera_error || "Camera chưa sẵn sàng")
      : frameStale ? `Không có khung hình mới trong ${Math.round(frameAge)} ms`
      : !s.model_loaded ? (s.model_error || "Model YOLO chưa sẵn sàng")
      : !s.ai_ok ? (s.ai_error || "Luồng xử lý AI bị gián đoạn")
      : !s.tracking_enabled ? "YOLO hoạt động · Tracker không khả dụng"
      : s.model_loading ? "Đang tải model" : "YOLO + ByteTrack";
    $("#cam-ai-status").textContent = aiStatus;
    $("#cam-ai-status").className = s.camera_ok && s.ai_ok && s.tracking_enabled ? "on-ok" : "on-warn";
    if (s.zone_warning) setZoneMessage(s.zone_warning, true);
  } catch (err) {
    updateTwinStatusFromApp({alarm_state:"OFFLINE",camera_ok:false,ai_ok:false,tracking_enabled:false});
    window.KhoAIWarehouseTwin?.markOffline?.(err.message || "Không xác định");
    $("#cam-ai-status").textContent = `Backend camera lỗi: ${err.message || "Không xác định"}`;
    $("#cam-ai-status").className = "on-bad";
    const visionHealth = $("#vision-feed-health"); if (visionHealth) visionHealth.textContent = "MẤT KẾT NỐI HỆ THỐNG";
    const visionState = $("#vision-state"); if (visionState) { visionState.textContent = "MẤT KẾT NỐI"; visionState.dataset.state = "OFFLINE"; }
    ["#vision-zone-people", "#vision-track-count", "#vision-latency"].forEach(sel => { const el=$(sel); if(el) el.textContent="–"; });
  }
  await refreshPendingRfidBindings();
  try {
    const events = await api("/api/camera/events?limit=12");
    const twinEvents = $("#twin-event-list");
    if (twinEvents) twinEvents.innerHTML = events.length ? events.slice(0,5).map(ev => {
      const state = String(ev.severity || "info").toLowerCase();
      const label = CAMERA_EVENT_LABEL[ev.type] || ev.type || "Sự kiện camera";
      return `<li class="twin-event ${["high","critical","severe"].includes(state) ? "is-alarm" : state === "medium" || state === "warning" ? "is-warning" : ""}"><i></i><span><b>${esc(label)}</b><small>${esc(String(ev.event_at || "").replace("T", " "))} · Track ${esc(ev.track_id ?? "–")}</small></span></li>`;
    }).join("") : "<li>Chưa ghi nhận sự kiện camera.</li>";
    $("#cam-event-list").innerHTML = events.length ? events.map(ev => `
      <li class="${["high", "critical", "severe"].includes(String(ev.severity || "").toLowerCase()) ? "severe" : ""}">
        <span><b>${esc(CAMERA_EVENT_LABEL[ev.type] || ev.type || "Sự kiện camera")}</b>
        <small>${esc(String(ev.event_at || "").replace("T", " "))} · ID ${esc(ev.track_id ?? "chưa có ID")} · ${esc(ev.message || "")}</small>
        ${ev.dwell_seconds != null ? `<small>Thời gian trong vùng: ${esc(ev.dwell_seconds)} giây</small>` : ""}
        ${ev.evidence_url ? `<a class="camera-evidence-link" href="${esc(withCameraToken(ev.evidence_url))}" target="_blank" rel="noopener"><img class="camera-evidence" loading="lazy" src="${esc(withCameraToken(ev.evidence_url))}" alt="Ảnh bằng chứng sự kiện camera">Xem ảnh bằng chứng</a>` : ev.evidence_expired ? `<small class="evidence-expired">Ảnh minh chứng đã hết hạn${ev.evidence_filename ? ` · ${esc(ev.evidence_filename)}` : ""}</small>` : ev.evidence_status === "failed" ? `<small class="evidence-expired">Không lưu được ảnh bằng chứng${ev.evidence_failure_reason ? ` · ${esc(ev.evidence_failure_reason)}` : ""}</small>` : ev.evidence_status === "pending" ? `<small>Ảnh bằng chứng đang chờ xử lý</small>` : ev.evidence_filename ? `<small>Ảnh minh chứng chưa khả dụng · ${esc(ev.evidence_filename)}</small>` : `<small>Không xác định – dữ liệu Evidence cũ</small>`}</span>
      </li>`).join("") : "<li>Chưa ghi nhận sự kiện camera ngoài.</li>";
  } catch (err) {
    $("#cam-event-list").innerHTML = `<li>Không tải được sự kiện camera: ${esc(err.message)}</li>`;
  }
}

if (outImage) {
  outImage.addEventListener("load", () => {
    outReconnectAttempts = 0;
    outReconnectDelay = 2000;
    if (outReconnectTimer) { clearTimeout(outReconnectTimer); outReconnectTimer = null; }
    drawCameraZone();
  });
  outImage.addEventListener("error", () => {
    // Exponential backoff avoids hammering the server while the USB camera is offline.
    const input = $("#cam-out-url");
    if (heatmapEnabled || !input || input.value !== "/api/camera/stream" || outReconnectTimer || outReconnectAttempts >= maxOutReconnectAttempts) return;
    outReconnectTimer = setTimeout(() => {
      outReconnectTimer = null;
      outReconnectAttempts += 1;
      outImage.src = withCameraToken(`/api/camera/stream?retry=${Date.now()}`);
      outReconnectDelay = Math.min(outReconnectDelay * 2, 30000);
    }, outReconnectDelay);
  });
}
const associationForm = $("#track-association-form");
if (associationForm) associationForm.addEventListener("submit", async event => {
  event.preventDefault();
  const uid = $("#associate-uid").value.trim();
  const trackId = Number($("#associate-track").value);
  const message = $("#associate-message");
  if (!uid || !$("#associate-track").value) { message.textContent = "Nhập UID và chọn Track ID."; return; }
  try {
    const result = await api("/api/access/associate", {method:"POST", headers:{"Content-Type":"application/json"}, body:JSON.stringify({uid, track_id:trackId})});
    message.textContent = `Đã liên kết UID ${result.uid} với Track ID ${result.track_id}.`;
  } catch (err) { message.textContent = `Không liên kết được: ${err.message}`; }
});

loadCameraZone();
refreshUsbCamera();
let cameraRefreshTimer=setInterval(()=>{if(!document.hidden && (!$("#overview").hidden || !$("#outside").hidden)) refreshUsbCamera();},4000);
document.addEventListener("visibilitychange",()=>{if(!document.hidden && (!$("#overview").hidden || !$("#outside").hidden)) refreshUsbCamera();});

function cameraCard(camera) {
  const connected = camera.connected === true ? "Đang kết nối" : camera.connected === false ? "Ngoại tuyến" : "Chưa xác minh";
  const fps = camera.fps != null && Number.isFinite(Number(camera.fps)) ? `${Number(camera.fps).toFixed(1)} FPS` : "Chưa có số đo";
  return `<b>${esc(camera.name)}</b><span class="status-chip ${camera.connected===true?"good":camera.connected===false?"bad":"unknown"}">${connected}</span><p>AI: ${camera.ai_enabled ? "Có" : "Không"} · FPS: ${fps}</p><small>${esc(camera.error || "Không có lỗi được báo cáo")}</small>`;
}
const historyManager = createHistoryManager({ api, post, esc, formatDate });
const { loadAdvancedHistory, loadAdminUsers } = historyManager;

async function refresh() {
  const isAdmin = currentUserRole === "admin";
  const [s, alerts, scans, cards, incidents] = await Promise.all(
    [api("/api/status"), api("/api/alerts"), api("/api/scans"), isAdmin ? api("/api/cards") : Promise.resolve([]), api("/api/incidents")]).catch(() => []);
  if (!s) return;
  updateGlobalStatus(s, incidents);
  // Device heartbeat is rendered by the dashboard independently of the optional 3D module.
  const espStatus=document.getElementById("twin-esp-status");
  const espDot=document.getElementById("twin-esp-dot");
  if(espStatus) espStatus.textContent=s.device_online?"Trực tuyến":"Ngoại tuyến";
  if(espDot) espDot.className=s.device_online?"is-up":"is-down";
  if (window.KhoAIWarehouseTwin?.updateSystem) window.KhoAIWarehouseTwin.updateSystem(s);
  if (!document.querySelector("#alerts").hidden) {
    Promise.all([api("/api/ai/explainability"), api("/api/cameras/center")]).then(([explain, cameras]) => {
      const state = document.querySelector("#ai-explain-state");
      if (state) { state.textContent = ({SAFE:"An toàn",WARNING:"Cảnh báo",ALARM:"Báo động",UNKNOWN:"Chưa xác định",DISABLED:"Đã tắt"})[explain.state] || explain.state || "Chưa xác định"; state.dataset.state=explain.state||"UNKNOWN"; }
      const reason = document.querySelector("#ai-explain-reason");
      if (reason) reason.textContent = explain.reason || "Backend chưa cung cấp lý do.";
      const inputs = document.querySelector("#ai-explain-inputs");
      if (inputs) inputs.innerHTML = (explain.inputs || []).length ? explain.inputs.map(v=>`<li>${esc(typeof v === "string" ? v : JSON.stringify(v))}</li>`).join("") : "<li>Không có dữ liệu giải thích chi tiết từ backend.</li>";
      const out = document.querySelector("#camera-center-out"), inside = document.querySelector("#camera-center-in");
      if (out) out.innerHTML = cameraCard(cameras.external);
      if (inside) inside.innerHTML = cameraCard(cameras.internal);
    }).catch(()=>{});
  }
  if (!document.querySelector("#history").hidden) loadAdvancedHistory();
  if (!document.querySelector("#admin")?.hidden) loadAdminUsers();
  if (!window.__khoaiStatsFetchedAt || Date.now() - window.__khoaiStatsFetchedAt > 15000) {
    window.__khoaiStatsFetchedAt = Date.now();
    api("/api/stats").then(stats => {
      if (typeof window.KhoAIAnalytics?.update === "function") window.KhoAIAnalytics.update(stats);
      else window.__khoaiPendingAnalyticsStats = stats;
    }).catch(() => {
      const updated = $("#analytics-updated"); if (updated) updated.textContent = "KHÔNG LẤY ĐƯỢC DỮ LIỆU";
    });
  }
  const dev = $("#s-dev"); dev.textContent = s.device_online ? "Trực tuyến" : "Ngoại tuyến";
  dev.className = s.device_online ? "on-ok" : "on-bad";
  const alarmLabels = {off:"Tắt", warning:"Cảnh báo", severe:"Nghiêm trọng", unknown:"Không xác định · cần kiểm tra hệ thống"};
  const alarmClasses = {off:"on-ok", warning:"on-warn", severe:"on-bad", unknown:"on-warn"};
  const al = $("#s-alarm");
  al.textContent = alarmLabels[s.alarm] || alarmLabels.unknown;
  al.className = alarmClasses[s.alarm] || alarmClasses.unknown;
  $("#s-cards").textContent = s.cards; $("#s-scans").textContent = s.scans_today; $("#s-open").textContent = s.open_alerts;
  const b = $("#badge"); b.hidden = !s.open_alerts; b.textContent = s.open_alerts;

  $("#o-people").textContent = s.outside.people; $("#o-scanned").textContent = s.outside.scanned;
  $("#o-sec").textContent = s.outside.max_seconds + " giây";
  $("#o-real").textContent = `${s.time_scale_mode === "DEMO" ? "CHẾ ĐỘ DEMO · " : ""}≈ ${s.outside.real_minutes} phút ngoài đời (1 giây = ${s.time_scale} giây)`;

  document.querySelectorAll(".z").forEach(z => {
  const ps = s.inside.filter(p => p.zone === z.dataset.z);
  z.classList.toggle("busy", ps.length > 0 && !ps.some(p => p.wrong));
  z.classList.toggle("wrong", ps.some(p => p.wrong));
  z.querySelector("i").textContent = ps.map(p =>
    (p.name || p.color || "?") +
    (p.wrong ? " (sai vùng)" : "")
  ).join(", ");
});

  const openIncidents = incidents.filter(i => i.status === "OPEN");
  const hasActiveSiren = openIncidents.some(i => i.siren);
  const incidentHtml = (openIncidents.length ? `<li><b>${openIncidents.length} sự cố đang mở</b> <button data-incident-ack-all>Xác nhận tất cả</button> ${hasActiveSiren ? `<button data-siren-off>Tắt còi</button>` : ""}</li>` : "") + openIncidents.map(i => `
    <li class="severe"><span><b>Sự cố ${esc(i.incident_id)}</b>
      <small>Bắt đầu ${esc(String(i.started_at || "").replace("T", " "))} · ${esc(i.event_count)} sự kiện · ${i.acknowledged ? "Đã xác nhận" : "Chưa xác nhận"} · Còi ${i.siren ? "đang bật" : "đã tắt"}</small></span>
      <button data-timeline="${esc(i.incident_id)}">Xem diễn biến</button> ${i.acknowledged ? "Đã xác nhận sự cố" : `<button data-incident-ack="${esc(i.incident_id)}">Xác nhận sự cố</button>`}</li>`).join("");
  const alertHtml = incidentHtml + (alerts.length ? alerts.map(a => `
    <li class="${esc(a.level)} ${a.handled ? "done" : ""}"><span><b>${a.level === "severe" ? "Nghiêm trọng" : "Thường"}</b> · ${esc(KIND[a.kind] || REASON[a.kind] || a.kind)}
      <small>${esc(String(a.ts || "").replace("T"," "))} · vùng ${esc(ZN[a.zone] || a.zone || "–")} · ${esc(a.message)}</small></span>
      ${a.level === "info" ? "Thông tin" : a.handled ? "Đã xử lý" : `<button data-ack="${esc(a.id)}">Đã xử lý</button>`}</li>`).join("") : "<li>Chưa có cảnh báo.</li>");
  setHtmlIfChanged($("#alert-list"), alertHtml);

  const scanHtml = scans.map(r => `<tr><td>${esc(String(r.ts || "").replace("T"," "))}</td><td>${esc(r.uid)}</td><td>${esc(r.name || "Không rõ")}</td>
    <td class="${esc(r.result)}">${r.result === "allow" ? "Cho phép" : "Từ chối"}</td><td>${esc(REASON[r.reason] || "")}</td></tr>`).join("");
  setHtmlIfChanged($("#scan-body"), scanHtml);

  if (!$("#history").hidden) {
    try {
      const audit = await api("/api/system/access-logs?limit=150");
      const labels = {LOGIN:"Đăng nhập", LOGOUT:"Đăng xuất", ADMIN_ACTION:"Thao tác quản trị"};
      $("#system-access-body").innerHTML = audit.length ? audit.map(row => `<tr>
        <td>${esc(String(row.event_at || "").replace("T", " "))}</td>
        <td>${esc(row.operator_name || "Quản trị viên")}</td>
        <td>${esc(labels[row.event_type] || row.event_type)}</td>
        <td>${esc(row.ip_address || "–")}</td>
        <td>${esc([row.method, row.path].filter(Boolean).join(" ") || "–")}</td>
        <td>${esc(row.details || (row.user_agent || "–"))}</td>
      </tr>`).join("") : `<tr><td colspan="6">Chưa có lịch sử truy cập hệ thống.</td></tr>`;
    } catch (err) {
      $("#system-access-body").innerHTML = `<tr><td colspan="6">Không tải được nhật ký: ${esc(err.message)}</td></tr>`;
    }
  }

  const cardHtml = cards.map(c => `<tr><td>${esc(c.uid)}</td><td>${esc(c.name)}</td><td>${esc(c.expires_at || "–")}</td>
    <td>${esc(c.used_today)}/${esc(c.daily_quota)}</td><td>${esc(c.zones.map(z => ZN[z] || z).join(", "))}</td>
    <td>${c.item ? esc(c.item) + " × " + c.boxes : "–"}</td><td>${esc(c.color || "–")}</td>
    <td>${c.active ? "Đang hoạt động" : "Đã khóa"}</td>
    <td><button data-toggle-card="${esc(c.uid)}" data-active="${c.active ? "1" : "0"}">${c.active ? "Khóa" : "Mở khóa"}</button>
    <button data-del="${esc(c.uid)}">Xóa</button></td></tr>`).join("");
  setHtmlIfChanged($("#card-body"), cardHtml);
}

document.body.addEventListener("click", async e => {
  if (e.target.dataset.ack) {
    try {
      await post(`/api/alerts/${e.target.dataset.ack}/ack`, {});
      toast("Đã đánh dấu cảnh báo là đã xử lý.","success");
      await refresh();
    } catch (err) {
      toast("Không thể xác nhận cảnh báo: " + err.message,"error");
    }
  }
  if (e.target.dataset.incidentAckAll !== undefined) {
    try {
      await post("/api/incidents/ack-all", {});
      await refresh();
    } catch (err) { toast("Không thể xác nhận tất cả sự cố: " + err.message,"error"); }
  }
  if (e.target.dataset.timeline) {
    try {
      const data = await api(`/api/incidents/${encodeURIComponent(e.target.dataset.timeline)}/timeline`);
      const target = document.querySelector("#incident-timeline");
      target.innerHTML = `<h3>Diễn biến sự cố · ${esc(data.incident.incident_id)}</h3>` + data.events.map(item=>`<div class="timeline-row"><time>${esc(item.event_at)}</time><b>${esc(CAMERA_EVENT_LABEL[item.type] || item.type)}</b><p>${esc(item.explanation || "Không có diễn giải bổ sung")}</p><small>Mã theo dõi: ${esc(item.track_id ?? "–")}</small></div>`).join("") || "<p>Sự cố chưa có sự kiện chi tiết.</p>";
      target.hidden = false;
    } catch(err) { toast("Không tải được diễn biến: "+err.message,"error"); }
  }
  if (e.target.dataset.incidentAck) {
    try {
      await post(`/api/incidents/${e.target.dataset.incidentAck}/ack`, {});
      await refresh();
    } catch (err) { toast("Không thể xác nhận sự cố: " + err.message,"error"); }
  }
  if (e.target.dataset.sirenOff !== undefined) {
    if (!(await confirmAction("Tắt còi sẽ dừng âm báo vật lý đang hoạt động. Tiếp tục?", "Xác nhận tắt còi"))) return;
    try {
      await post("/api/incidents/siren-off", {});
      await refresh();
    } catch (err) { toast("Không thể tắt còi: " + err.message,"error"); }
  }
  if (e.target.dataset.bindRfid) {
    const uid = e.target.dataset.bindRfid;
    const trackId = Number(e.target.dataset.trackId);
    if (!Number.isInteger(trackId)) return;
    try {
      await post("/api/access/associate", {uid, track_id: trackId});
      await refreshPendingRfidBindings();
      toast(`Đã ghép UID ${uid} với Track ${trackId}.`,"success");
    } catch (err) { toast("Không thể ghép thẻ: " + err.message,"error"); }
  }
  if (e.target.dataset.userToggle) {
    const active=e.target.dataset.active!=="1";
    if (!active && !(await confirmAction("Thu hồi tài khoản sẽ ngăn tài khoản này tiếp tục truy cập. Tiếp tục?", "Thu hồi tài khoản"))) return;
    try {
      await api(`/api/admin/users/${encodeURIComponent(e.target.dataset.userToggle)}`,{method:"PATCH",headers:{"Content-Type":"application/json"},body:JSON.stringify({active})});
      await loadAdminUsers();
    } catch(err) { toast("Không cập nhật được tài khoản: "+err.message,"error"); }
  }
  if (e.target.dataset.toggleCard) {
    const active = e.target.dataset.active !== "1";
    if (!active && !(await confirmAction(`Khóa thẻ ${e.target.dataset.toggleCard}?`, "Xác nhận khóa thẻ"))) return;
    try {
      await api(`/api/cards/${e.target.dataset.toggleCard}`, {method:"PATCH", headers:{"Content-Type":"application/json"}, body:JSON.stringify({active})});
      await refresh();
    } catch (err) { toast("Không thể thay đổi trạng thái thẻ: " + err.message,"error"); }
  }
  if (e.target.dataset.del && await confirmAction(`Xóa thẻ ${e.target.dataset.del}? Thao tác này không thể hoàn tác.`, "Xác nhận xóa thẻ")) {
    try {
      await api(`/api/cards/${e.target.dataset.del}`, {method:"DELETE"});
      await refresh();
    } catch (err) {
      toast("Không thể xóa thẻ: " + err.message,"error");
    }
  }
});

$("#btn-last").onclick = async () => {
  const r = await api("/api/rfid/last-unknown");
  $("#form-msg").textContent = r.uid ? `Đã điền UID quẹt lúc ${String(r.ts || "").replace("T"," ")}.` : "Chưa có thẻ lạ nào được quẹt.";
  if (r.uid) $("#uid").value = r.uid;
};

$("#card-form").onsubmit = async e => {
  e.preventDefault();
  const f = new FormData(e.target), msg = $("#form-msg");
  try {
    await post("/api/cards", {
      uid: f.get("uid"), name: f.get("name"), age: f.get("age") ? +f.get("age") : null,
      expires_at: f.get("expires_at") || null, daily_quota: +f.get("daily_quota") || 3,
      zones: f.getAll("z"), item: f.get("item") || null, boxes: +f.get("boxes") || 0, color: f.get("color") || null });
    msg.textContent = "Đã cấp thẻ."; e.target.reset(); refresh();
  } catch (err) { msg.textContent = "Lỗi: " + err.message; }
};

// Resolve the existing cookie session at page load so role-based UI is correct
// even when no API request returns 401 (the normal case for a valid session).
requestAdminToken().then(user=>{if(user)applyRole(user);refresh();}).catch(()=>{});
let refreshTimer=setInterval(()=>{if(!document.hidden)refresh();},5000);
document.addEventListener("visibilitychange",()=>{if(document.hidden){clearInterval(refreshTimer);}else{refresh();refreshTimer=setInterval(()=>{if(!document.hidden)refresh();},5000);}});


// Live operational indicators: only show ONLINE after a successful health response.
(async function startOperationalIndicators(){
  const clock=document.getElementById("local-clock");
  const system=document.querySelector(".system-indicator");
  const sidebar=document.querySelector(".sidebar-status");
  const updateClock=()=>{if(clock) clock.textContent=new Date().toLocaleString("vi-VN");};
  updateClock(); setInterval(updateClock,1000);
  async function check(){
    try{
      const health=await api("/api/health");
      const online=health.status==="ok";
      const degradedReason=[!health.camera_ok?"camera":null,!health.ai_ok?"AI":null].filter(Boolean).join(" và ");
      const degradedLabel=degradedReason?`CAMERA/AI CHƯA SẴN SÀNG · ${degradedReason}`:"HỆ THỐNG ĐANG SUY GIẢM";
      if(system){const label=system.querySelector("span"); if(label) label.textContent=online?"HỆ THỐNG HOẠT ĐỘNG":degradedLabel; system.dataset.state=online?"online":"degraded";}
      if(sidebar){const label=sidebar.querySelector("small"); if(label) label.textContent=online?"Máy chủ đang phản hồi":(degradedReason?`Máy chủ phản hồi · ${degradedReason} chưa sẵn sàng`:"Máy chủ đang suy giảm"); sidebar.dataset.state=online?"online":"degraded";}
    }catch(_){
      if(system){const label=system.querySelector("span"); if(label) label.textContent="MẤT KẾT NỐI HỆ THỐNG"; system.dataset.state="offline";}
      if(sidebar){const label=sidebar.querySelector("small"); if(label) label.textContent="Không kết nối được máy chủ"; sidebar.dataset.state="offline";}
    }
  }
  await check(); setInterval(check,5000);
})();

// Browser stream selection is isolated from AI/Decision Engine state.
initStreamController({ withCameraToken });
initStreamMetrics();
