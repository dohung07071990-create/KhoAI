const $ = s => document.querySelector(s);
const ZN = {entry:"Nhập", exit:"Xuất", important:"Quan trọng", critical:"Cực kỳ quan trọng", A:"A", door:"Cửa"};
const REASON = {unknown_card:"Thẻ lạ", expired:"Hết hạn", quota_exhausted:"Hết lượt"};
const KIND = {tailgating:"Người đi lọt", loitering:"Đứng lâu", wrong_zone:"Sai vùng", headcount:"Lệch số người", boxes_over:"Thừa thùng"};
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
[["out","cam-out"],["in","cam-in"]].forEach(([k,id]) => {
  const inp = $("#cam-"+k+"-url"), img = $("#"+id+" img");
  inp.value = localStorage.getItem("cam-"+k) || (k === "in" ? "http://192.168.2.35:81/stream" : "");
  const apply = () => { localStorage.setItem("cam-"+k, inp.value); img.src = inp.value; };
  inp.onchange = apply; if (inp.value) img.src = inp.value;
});

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
    z.querySelector("i").textContent = ps.map(p => (p.name || p.color || "?") + (p.wrong ? " (sai vùng)" : "")).join(", ");
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
