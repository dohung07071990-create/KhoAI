import { startWebRTC, stopWebRTC } from './webrtc-client.js';

// Browser-side protocol switch. MJPEG remains the default and recovery path.
export function initStreamController({ withCameraToken = url => url } = {}) {
  const button = document.getElementById("cam-webrtc-toggle");
  const video = document.getElementById("cam-out-webrtc");
  const image = document.querySelector("#cam-out img");
  const status = document.getElementById("vision-feed-health");
  if (!button || !video || !image) return () => {};
  let enabled = false;
  const onClick = async () => {
    button.disabled = true;
    try {
      if (!enabled) {
        if (status) status.textContent = "ĐANG THIẾT LẬP WEBRTC…";
        await startWebRTC(video);
        enabled = true; video.hidden = false; image.hidden = true;
        button.textContent = "Dùng MJPEG";
        if (status) status.textContent = "WEBRTC ĐANG KẾT NỐI";
      } else {
        await stopWebRTC(); enabled = false;
        video.hidden = true; image.hidden = false;
        const saved = localStorage.getItem("cam-out") || "/api/camera/stream";
        image.src = saved.startsWith("/api/camera/") ? withCameraToken(saved) : saved;
        button.textContent = "Thử WebRTC";
        if (status) status.textContent = "MJPEG ĐANG HOẠT ĐỘNG";
      }
    } catch (error) {
      enabled = false; video.hidden = true; image.hidden = false;
      button.textContent = "Thử WebRTC";
      if (status) status.textContent = `WEBRTC KHÔNG KHẢ DỤNG · ${error.message}`;
      await stopWebRTC();
    } finally { button.disabled = false; }
  };
  button.addEventListener("click", onClick);
  const onUnload = () => { stopWebRTC(); };
  window.addEventListener("beforeunload", onUnload);
  return () => { button.removeEventListener("click", onClick); window.removeEventListener("beforeunload", onUnload); stopWebRTC(); };
}
