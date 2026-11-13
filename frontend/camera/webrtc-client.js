let peer = null;
let activeStream = null;

function waitForIceGathering(pc, timeoutMs = 5000) {
  if (pc.iceGatheringState === "complete") return Promise.resolve();
  return new Promise(resolve => {
    const timer = setTimeout(done, timeoutMs);
    function done() {
      clearTimeout(timer);
      pc.removeEventListener("icegatheringstatechange", check);
      resolve();
    }
    function check() {
      if (pc.iceGatheringState === "complete") done();
    }
    pc.addEventListener("icegatheringstatechange", check);
  });
}

export async function startWebRTC(videoElement, endpoint = "/api/camera/webrtc/offer") {
  await stopWebRTC();
  if (!videoElement) throw new Error("Không tìm thấy phần tử video WebRTC.");
  const pc = new RTCPeerConnection({ iceServers: [] });
  peer = pc;
  activeStream = new MediaStream();
  videoElement.srcObject = activeStream;
  pc.addTransceiver("video", { direction: "recvonly" });
  pc.addEventListener("track", event => {
    for (const track of event.streams[0]?.getTracks?.() || [event.track]) {
      if (!activeStream.getTracks().some(item => item.id === track.id)) activeStream.addTrack(track);
    }
    videoElement.play().catch(() => {});
  });
  try {
    const offer = await pc.createOffer();
    await pc.setLocalDescription(offer);
    await waitForIceGathering(pc);
    const response = await fetch(endpoint, {
      method: "POST",
      credentials: "same-origin",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ type: pc.localDescription.type, sdp: pc.localDescription.sdp })
    });
    const answer = await response.json().catch(() => ({}));
    if (!response.ok) throw new Error(answer.detail || `WebRTC HTTP ${response.status}`);
    await pc.setRemoteDescription(answer);
    return pc;
  } catch (error) {
    await stopWebRTC();
    throw error;
  }
}

export async function stopWebRTC() {
  if (peer) {
    const old = peer;
    peer = null;
    old.getSenders().forEach(sender => sender.track?.stop());
    old.getReceivers().forEach(receiver => receiver.track?.stop());
    await old.close();
  }
  if (activeStream) activeStream.getTracks().forEach(track => track.stop());
  activeStream = null;
}
