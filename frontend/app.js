const $ = s => document.querySelector(s);
const ZN = {entry:"Nhập", exit:"Xuất", important:"Quan trọng", critical:"Cực kỳ quan trọng", A:"A", door:"Cửa"};
const REASON = {unknown_card:"Thẻ lạ", expired:"Hết hạn", quota_exhausted:"Hết lượt"};
const KIND = {tailgating:"Người đi lọt", loitering:"Đứng lâu", wrong_zone:"Sai vùng", headcount:"Lệch số người", boxes_over:"Thừa thùng"};
const CAMERA_EVENT_LABEL = {unauthorized_entry:"Xâm nhập vùng bảo vệ", zone_entry:"Đi vào vùng bảo vệ", zone_exit:"Rời vùng bảo vệ", long_dwell:"Đứng lâu trong vùng"};
const esc = s => String(s ?? "").replace(/[&<>"]/g, c => ({"&":"&amp;","<":"&lt;",">":"&gt;",'"':"&quot;"}[c]));
const api = async (u, o) => { const r = await fetch(u, o); if (!r.ok) throw new Error((await r.json()).detail || r.status); return r.json(); };
const post = (u, b) => api(u, {method:"POST", headers:{"Content-Type":"application/json"}, body:JSON.stringify(b)});

// Tab
document.querySelectorAll("#tabs button").forEach(b => b.onclick = () => {
  document.querySelectorAll("#tabs button").forEach(x => x.classList.toggle("on", x === b));
  document.querySelectorAll("main > section").forEach(s => s.hidden = s.id !== b.dataset.t);
  refresh();
});

// Địa chỉ camera: nhớ trong trình duyệt
let heatmapEnabled = false;
const heatmapButton = $("#cam-heatmap-toggle");
[["out","cam-out"],["in","cam-in"]].forEach(([k,id]) => {
  const inp = $("#cam-"+k+"-url"), img = $("#"+id+" img");
  // Camera ngoài mặc định lấy trực tiếp luồng USB đã được YOLO xử lý từ backend KhoAI.
  // Người dùng vẫn có thể thay bằng URL MJPEG của một camera IP nếu cần.
  const defaultUrl = k === "out" ? "/api/camera/stream" : "http://192.168.2.35:81/stream";
  inp.value = localStorage.getItem("cam-"+k) || defaultUrl;
  const apply = () => {
    localStorage.setItem("cam-"+k, inp.value);
    if (k === "out") {
      heatmapEnabled = false;
      if (heatmapButton) { heatmapButton.setAttribute("aria-pressed", "false"); heatmapButton.textContent = "Heatmap chuyển động"; }
    }
    img.src = inp.value;
  };
  inp.onchange = apply;
  if (k === "out" && !localStorage.getItem("cam-out")) img.src = defaultUrl;
  else if (inp.value) img.src = inp.value;
});

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
      outImage.src = `/api/camera/heatmap?t=${Date.now()}`;
    } else {
      const saved = localStorage.getItem("cam-out") || "/api/camera/stream";
      outImage.src = saved;
    }
  };
  setInterval(() => {
    if (heatmapEnabled && !document.querySelector("#outside").hidden) {
      outImage.src = `/api/camera/heatmap?t=${Date.now()}`;
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
  const pts = zoneEditing ? zoneDraft : cameraZone;
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

async function refreshUsbCamera() {
  try {
    const s = await api("/api/camera/status");
    if (Array.isArray(s.frame_size)) cameraFrameSize = s.frame_size;
    $("#cam-read-fps").textContent = s.capture_fps == null ? "–" : s.capture_fps;
    $("#cam-ai-fps").textContent = s.process_fps == null ? (s.fps ?? "–") : s.process_fps;
    $("#cam-latency").textContent = s.process_latency_ms == null ? "–" : `${s.process_latency_ms} ms`;
    $("#cam-age").textContent = s.frame_age_ms == null ? "–" : `${s.frame_age_ms} ms`;
    $("#cam-detections").textContent = s.detections ?? 0;
    const aiStatus = !s.camera_available ? (s.camera_error || "Camera chưa sẵn sàng")
      : s.model_error ? "Lỗi model" : s.model_loading ? "Đang tải model"
      : s.model_loaded ? (s.tracking ? "YOLO + ByteTrack" : "YOLO (không tracking)") : "Đang khởi tạo";
    $("#cam-ai-status").textContent = aiStatus;
    $("#cam-ai-status").className = s.camera_available && s.model_loaded && !s.model_error ? "on-ok" : "on-warn";
    if (s.zone_warning) setZoneMessage(s.zone_warning, true);
  } catch (err) {
    $("#cam-ai-status").textContent = "Backend camera lỗi";
    $("#cam-ai-status").className = "on-bad";
  }
  try {
    const events = await api("/api/camera/events?limit=12");
    $("#cam-event-list").innerHTML = events.length ? events.map(ev => `
      <li class="${["high", "critical", "severe"].includes(String(ev.severity || "").toLowerCase()) ? "severe" : ""}">
        <span><b>${esc(CAMERA_EVENT_LABEL[ev.type] || ev.type || "Sự kiện camera")}</b>
        <small>${esc(String(ev.event_at || "").replace("T", " "))} · ID ${esc(ev.track_id ?? "chưa có ID")} · ${esc(ev.message || "")}</small>
        ${ev.dwell_seconds != null ? `<small>Thời gian trong vùng: ${esc(ev.dwell_seconds)} giây</small>` : ""}
        ${ev.evidence_url ? `<a class="camera-evidence-link" href="${esc(ev.evidence_url)}" target="_blank" rel="noopener"><img class="camera-evidence" loading="lazy" src="${esc(ev.evidence_url)}" alt="Ảnh bằng chứng sự kiện camera">Xem ảnh bằng chứng</a>` : ""}</span>
      </li>`).join("") : "<li>Chưa ghi nhận sự kiện camera ngoài.</li>";
  } catch (err) {
    $("#cam-event-list").innerHTML = `<li>Không tải được sự kiện camera: ${esc(err.message)}</li>`;
  }
}

if (outImage) {
  outImage.addEventListener("load", drawCameraZone);
  outImage.addEventListener("error", () => {
    // Tự thử kết nối lại với luồng backend mặc định nếu trình duyệt mất MJPEG.
    const input = $("#cam-out-url");
    if (heatmapEnabled || !input || input.value !== "/api/camera/stream") return;
    setTimeout(() => { outImage.src = `/api/camera/stream?retry=${Date.now()}`; }, 2000);
  });
}
loadCameraZone();
refreshUsbCamera();
setInterval(refreshUsbCamera, 2000);

async function refresh() {
  const [s, alerts, scans, cards] = await Promise.all(
    [api("/api/status"), api("/api/alerts"), api("/api/scans"), api("/api/cards")]).catch(() => []);
  if (!s) return;
  const dev = $("#s-dev"); dev.textContent = s.device_online ? "Trực tuyến" : "Ngoại tuyến";
  dev.className = s.device_online ? "on-ok" : "on-bad";
  const al = $("#s-alarm"); al.textContent = {off:"Tắt", warning:"Cảnh báo", severe:"Nghiêm trọng"}[s.alarm];
  al.className = {off:"on-ok", warning:"on-warn", severe:"on-bad"}[s.alarm];
  $("#s-cards").textContent = s.cards; $("#s-scans").textContent = s.scans_today; $("#s-open").textContent = s.open_alerts;
  const b = $("#badge"); b.hidden = !s.open_alerts; b.textContent = s.open_alerts;

  $("#o-people").textContent = s.outside.people; $("#o-scanned").textContent = s.outside.scanned;
  $("#o-sec").textContent = s.outside.max_seconds + " giây";
  $("#o-real").textContent = `≈ ${s.outside.real_minutes} phút ngoài đời (1 giây = ${s.time_scale} giây)`;

  document.querySelectorAll(".z").forEach(z => {
  const ps = s.inside.filter(p => p.zone === z.dataset.z);
  z.classList.toggle("busy", ps.length > 0 && !ps.some(p => p.wrong));
  z.classList.toggle("wrong", ps.some(p => p.wrong));
  z.querySelector("i").textContent = ps.map(p =>
    (p.name || p.color || "?") +
    (p.wrong ? " (sai vùng)" : "")
  ).join(", ");
});

  $("#alert-list").innerHTML = alerts.length ? alerts.map(a => `
    <li class="${a.level} ${a.handled ? "done" : ""}"><span><b>${a.level === "severe" ? "Nghiêm trọng" : "Thường"}</b> · ${KIND[a.kind] || REASON[a.kind] || a.kind}
      <small>${a.ts.replace("T"," ")} · vùng ${ZN[a.zone] || "–"} · ${esc(a.message)}</small></span>
      ${a.handled ? "Đã xử lý" : `<button data-ack="${a.id}">Đã xử lý</button>`}</li>`).join("") : "<li>Chưa có cảnh báo.</li>";

  $("#scan-body").innerHTML = scans.map(r => `<tr><td>${r.ts.replace("T"," ")}</td><td>${esc(r.uid)}</td><td>${esc(r.name || "Không rõ")}</td>
    <td class="${r.result}">${r.result === "allow" ? "Cho phép" : "Từ chối"}</td><td>${REASON[r.reason] || ""}</td></tr>`).join("");

  $("#card-body").innerHTML = cards.map(c => `<tr><td>${esc(c.uid)}</td><td>${esc(c.name)}</td><td>${c.expires_at || "–"}</td>
    <td>${c.used_today}/${c.daily_quota}</td><td>${c.zones.map(z => ZN[z]).join(", ")}</td>
    <td>${c.item ? esc(c.item) + " × " + c.boxes : "–"}</td><td>${c.color || "–"}</td>
    <td><button data-del="${esc(c.uid)}">Xóa</button></td></tr>`).join("");
}

document.body.addEventListener("click", async e => {
  if (e.target.dataset.ack) { await post(`/api/alerts/${e.target.dataset.ack}/ack`, {}); refresh(); }
  if (e.target.dataset.del && confirm("Xóa thẻ này?")) { await api(`/api/cards/${e.target.dataset.del}`, {method:"DELETE"}); refresh(); }
});

$("#btn-last").onclick = async () => {
  const r = await api("/api/rfid/last-unknown");
  $("#form-msg").textContent = r.uid ? `Đã điền UID quẹt lúc ${r.ts.replace("T"," ")}.` : "Chưa có thẻ lạ nào được quẹt.";
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

refresh(); setInterval(refresh, 2000);
