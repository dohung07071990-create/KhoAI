// Authentication UI and session bootstrap. Network requests stay same-origin.
export function createAuthManager({ onUser, onLegacyToken }) {
  let authFlight = null;
  let token = "";
  let previewMode = false;

  function showAccountLogin() {
    return new Promise(resolve => {
      let overlay = document.querySelector("#khoai-login-overlay");
      if (!overlay) {
        overlay = document.createElement("div"); overlay.id = "khoai-login-overlay"; overlay.className = "login-overlay";
        overlay.innerHTML = `<form class="login-card" id="khoai-login-form"><div class="login-brand">KHO<span>AI</span></div><h2>Đăng nhập quản trị</h2><p>Phiên đăng nhập được xác thực bằng tài khoản riêng.</p><label>Tên đăng nhập<input name="username" autocomplete="username" required maxlength="80"></label><label>Mật khẩu<input name="password" type="password" autocomplete="current-password" required maxlength="256"></label><p class="login-error" role="alert" aria-live="polite"></p><div class="login-actions"><button type="submit" class="primary">Đăng nhập</button><button type="button" class="login-cancel">Đóng</button></div><div class="legacy-token-row" hidden><label>Token quản trị cũ<input name="legacy_token" type="password" autocomplete="off"></label><button type="button" class="legacy-token-submit">Xác thực token</button></div><button type="button" class="legacy-login">Dùng token quản trị cũ</button><small>Nếu chưa có tài khoản quản trị, vui lòng liên hệ người quản lý hệ thống.</small></form>`;
        document.body.appendChild(overlay);
      }
      const form = overlay.querySelector("form"), error = overlay.querySelector(".login-error");
      overlay.hidden = false; error.textContent = ""; form.reset();
      form.classList.remove("is-error");
      form.querySelectorAll("input").forEach(input => input.addEventListener("input", () => form.classList.remove("is-error"), { once: true }));
      overlay.querySelector(".login-cancel").onclick = () => {
        previewMode = true;
        overlay.hidden = true;
        onUser?.({ display_name: "Xem giao diện", role: "preview" });
        resolve(null);
      };
      const legacyRow = overlay.querySelector(".legacy-token-row");
      overlay.querySelector(".legacy-login").onclick = () => { legacyRow.hidden = !legacyRow.hidden; if (!legacyRow.hidden) legacyRow.querySelector("input").focus(); };
      overlay.querySelector(".legacy-token-submit").onclick = async () => {
        const value = legacyRow.querySelector("input").value.trim();
        if (!value) { error.textContent = "Nhập token quản trị."; return; }
        try {
          const response = await fetch("/api/status", { headers: { "X-Admin-Token": value, "X-Operator-Name": "Quản trị viên (token tương thích)" }, credentials: "same-origin" });
          if (!response.ok) { const payload = await response.json().catch(() => ({})); throw new Error(payload.detail || `HTTP ${response.status}`); }
          token = value; onLegacyToken?.(value); overlay.hidden = true;
          const user = { display_name: "Quản trị viên (token tương thích)", role: "admin" };
          onUser?.(user); resolve(user);
        } catch (err) { error.textContent = err.message; form.classList.remove("is-error"); void form.offsetWidth; form.classList.add("is-error"); }
      };
      form.onsubmit = async event => {
        event.preventDefault(); const data = new FormData(form);
        const submit = form.querySelector('[type="submit"]');
        const idleLabel = submit.textContent;
        submit.disabled = true; submit.setAttribute("aria-busy", "true"); submit.innerHTML = '<span class="login-spinner" aria-hidden="true"></span> Đang xác thực…';
        form.classList.remove("is-error");
        try {
          const response = await fetch("/api/auth/login", { method: "POST", credentials: "same-origin", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ username: data.get("username"), password: data.get("password") }) });
          const payload = await response.json().catch(() => ({}));
          if (!response.ok) throw new Error(payload.detail || `HTTP ${response.status}`);
          overlay.hidden = true;
          const label = document.querySelector(".operator b");
          if (label) label.textContent = String(payload.display_name || payload.username).toLocaleUpperCase("vi-VN");
          onUser?.(payload); resolve(payload);
        } catch (err) { error.textContent = err.message; void form.offsetWidth; form.classList.add("is-error"); form.querySelector('[name="password"]').focus(); }
        finally { submit.disabled = false; submit.removeAttribute("aria-busy"); submit.textContent = idleLabel; }
      };
      form.querySelector('[name="username"]').focus();
    });
  }

  async function requestAdminToken() {
    if (previewMode) return null;
    if (authFlight) return authFlight;
    authFlight = (async () => {
      const response = await fetch("/api/auth/me", { credentials: "same-origin" });
      if (response.ok) { const user = await response.json(); onUser?.(user); return user; }
      return showAccountLogin();
    })().finally(() => { authFlight = null; });
    return authFlight;
  }

  function beginLogin() {
    previewMode = false;
    return requestAdminToken();
  }

  return {
    requestAdminToken,
    beginLogin,
    getToken: () => token,
    setToken(value) { token = String(value || ""); },
    clearTokenIf(value) { if (token === value) token = ""; }
  };
}
