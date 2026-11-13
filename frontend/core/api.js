// Same-origin API client. Authentication policy is injected by auth-manager.
export function createApiClient({ getToken, clearTokenIf, requestAdminToken }) {
  const api = async (url, options = {}) => {
    const send = token => {
      const headers = new Headers(options.headers || {});
      if (token) headers.set("X-Admin-Token", token);
      return fetch(url, { ...options, headers, credentials: options.credentials || "same-origin" });
    };
    const used = getToken();
    let response = await send(used);
    if (response.status === 401 && !url.startsWith("/api/rfid/") && !url.startsWith("/api/device/")) {
      clearTokenIf(used);
      await requestAdminToken();
      response = await send(""); // authenticated HttpOnly session cookie
    }
    let payload = {};
    try { payload = await response.json(); } catch (_) { /* endpoint may return a stream */ }
    if (!response.ok) throw new Error(payload.detail || response.status);
    return payload;
  };
  const post = (url, body) => api(url, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body)
  });
  return { api, post };
}
