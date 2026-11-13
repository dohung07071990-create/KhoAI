// History and administrator-account views; data access is injected from the app shell.
export function createHistoryManager({ api, post, esc, formatDate }) {
  let advancedHistoryBusy = false;
  async function loadAdvancedHistory() {
    if (advancedHistoryBusy) return;
    advancedHistoryBusy = true;
    try {
      const kind = document.querySelector("#history-kind")?.value || "access";
      const q = document.querySelector("#history-query")?.value || "";
      const start = document.querySelector("#history-start")?.value || "";
      const end = document.querySelector("#history-end")?.value || "";
      const rows = await api(`/api/history/advanced?kind=${encodeURIComponent(kind)}&q=${encodeURIComponent(q)}&start=${encodeURIComponent(start)}&end=${encodeURIComponent(end)}&limit=500`);
      const body = document.querySelector("#advanced-history-body");
      if (body) body.innerHTML = rows.map(row => `<tr><td>${esc(formatDate(row.event_at))}</td><td>${esc(({LOGIN:"Đăng nhập",LOGOUT:"Đăng xuất",ADMIN_ACTION:"Thao tác quản trị",allow:"Cho phép",deny:"Từ chối",zone_warning:"Cảnh báo vùng",anonymous_zone_alarm:"Báo động vùng không xác thực",intrusion_attempt_aborted:"Đã hủy phiên xâm nhập",camera_offline:"Camera mất kết nối",camera_unstable:"Camera không ổn định",camera_recovered:"Camera kết nối lại"})[row.event_type || row.result] || row.event_type || row.result || "–")}</td><td>${esc(row.operator_name || row.card_name || row.uid || "–")}</td><td>${esc(row.path || row.message || row.details || "–")}</td></tr>`).join("") || `<tr><td colspan="4">Không có dữ liệu phù hợp.</td></tr>`;
      window.__khoaiAdvancedRows = rows;
    } catch (err) {
      const body = document.querySelector("#advanced-history-body");
      if (body) body.innerHTML = `<tr><td colspan="4">${esc(err.message)}</td></tr>`;
    } finally { advancedHistoryBusy = false; }
  }
  async function loadAdminUsers() {
    const body = document.querySelector("#admin-user-body");
    if (!body) return;
    try {
      const users = await api("/api/admin/users");
      body.innerHTML = users.map(user => `<tr><td>${esc(user.username)}</td><td>${esc(user.display_name)}</td><td>${user.role === "admin" ? "Quản trị" : "Người xem"}</td><td>${user.active ? "Hoạt động" : "Đã khóa"} <button type="button" data-user-toggle="${esc(user.user_id)}" data-active="${user.active ? "1" : "0"}">${user.active ? "Thu hồi" : "Kích hoạt"}</button></td></tr>`).join("") || `<tr><td colspan="4">Chưa có tài khoản.</td></tr>`;
    } catch (err) { body.innerHTML = `<tr><td colspan="4">${esc(err.message)}</td></tr>`; }
  }
  const adminUserForm = document.querySelector("#admin-user-form");
  if (adminUserForm) adminUserForm.addEventListener("submit", async event => {
    event.preventDefault();
    const form = new FormData(adminUserForm), message = document.querySelector("#admin-user-message");
    try {
      await post("/api/admin/users", { username: form.get("username"), display_name: form.get("display_name"), password: form.get("password"), role: form.get("role") });
      message.textContent = "Đã tạo tài khoản."; adminUserForm.reset(); await loadAdminUsers();
    } catch (err) { message.textContent = "Không tạo được tài khoản: " + err.message; }
  });
  const applyButton = document.querySelector("#history-apply");
  if (applyButton) applyButton.addEventListener("click", loadAdvancedHistory);
  const exportButton = document.querySelector("#history-export");
  if (exportButton) exportButton.addEventListener("click", () => {
    const rows = window.__khoaiAdvancedRows || [];
    const keys = [...new Set(rows.flatMap(row => Object.keys(row)))];
    const csv = [keys.join(","), ...rows.map(row => keys.map(key => '"' + String(typeof row[key] === "object" ? JSON.stringify(row[key]) : row[key] ?? "").replace(/"/g, '""') + '"').join(","))].join("\r\n");
    const blob = new Blob(["\ufeff" + csv], { type: "text/csv;charset=utf-8" });
    const url = URL.createObjectURL(blob), link = document.createElement("a");
    link.href = url; link.download = "khoai-history.csv"; link.click(); URL.revokeObjectURL(url);
  });
  return { loadAdvancedHistory, loadAdminUsers };
}
