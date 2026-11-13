// Metadata-only status channel; video remains on MJPEG/WebRTC endpoints.
export function initStreamMetrics() {
  const target = document.getElementById('stream-distribution-status');
  if (!target || typeof WebSocket === 'undefined') return () => {};
  let socket = null;
  let retryTimer = null;
  let stopped = false;
  let retryDelay = 1000;
  let watchdogTimer = null;
  let lastMessageAt = 0;

  const render = payload => {
    const streams = payload?.streams || {};
    const usb = streams.usb || {};
    const inside = streams.inside || {};
    const usbCount = Number(usb.viewers || 0);
    const insideCount = Number(inside.viewers || 0);
    target.textContent = `PHÂN PHỐI VIDEO · USB ${usbCount} · ESP32-CAM ${insideCount}`;
    target.dataset.state = 'online';
    target.title = `USB: ${usbCount} người xem; ESP32-CAM: ${insideCount} người xem. Capture và AI hoạt động độc lập.`;
  };

  const connect = () => {
    if (stopped) return;
    const scheme = location.protocol === 'https:' ? 'wss:' : 'ws:';
    socket = new WebSocket(`${scheme}//${location.host}/ws/camera/streams`);
    socket.addEventListener('open', () => {
      retryDelay = 1000;
      lastMessageAt = Date.now();
      target.dataset.state = 'connecting';
      if (watchdogTimer !== null) window.clearInterval(watchdogTimer);
      watchdogTimer = window.setInterval(() => {
        if (socket && socket.readyState === WebSocket.OPEN && Date.now() - lastMessageAt > 5000) socket.close();
      }, 1500);
    });
    socket.addEventListener('message', event => {
      lastMessageAt = Date.now();
      try { render(JSON.parse(event.data)); } catch (_) { /* ignore malformed metadata */ }
    });
    socket.addEventListener('close', event => {
      if (watchdogTimer !== null) window.clearInterval(watchdogTimer);
      watchdogTimer = null;
      if (stopped) return;
      target.dataset.state = event.code === 4401 ? 'auth-expired' : 'offline';
      target.textContent = event.code === 4401 ? 'PHÂN PHỐI VIDEO · PHIÊN ĐĂNG NHẬP HẾT HẠN' : 'PHÂN PHỐI VIDEO · ĐANG KẾT NỐI LẠI';
      if (event.code === 4401) return;
      retryTimer = window.setTimeout(connect, retryDelay);
      retryDelay = Math.min(15000, retryDelay * 2);
    });
    socket.addEventListener('error', () => socket?.close());
  };

  connect();
  return () => {
    stopped = true;
    if (retryTimer !== null) window.clearTimeout(retryTimer);
    if (watchdogTimer !== null) window.clearInterval(watchdogTimer);
    socket?.close();
  };
}
