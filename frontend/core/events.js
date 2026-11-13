// Namespaced event bus shared by independent frontend modules.
const target = new EventTarget();
export const Events = Object.freeze({
  AUTH_ROLE_CHANGED: "khoai:auth-role-changed",
  CAMERA_STATUS_CHANGED: "khoai:camera-status-changed",
  TWIN_READY: "khoai:twin-ready"
});
export function emit(type, detail = {}) {
  target.dispatchEvent(new CustomEvent(type, { detail }));
  window.dispatchEvent(new CustomEvent(type, { detail }));
}
export function on(type, listener, options) {
  target.addEventListener(type, listener, options);
  return () => target.removeEventListener(type, listener, options);
}
