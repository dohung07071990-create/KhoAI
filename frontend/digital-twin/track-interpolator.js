/**
 * Smooths timestamped, calibrated floor positions for Digital Twin rendering.
 * It never invents positions: only valid backend mappings enter the state.
 */
export class TrackInterpolator {
  constructor({ smoothingMs = 220, fadeAfterMs = 8000, staleAfterMs = 15000 } = {}) {
    this.smoothingMs = Math.max(1, Number(smoothingMs) || 220);
    this.fadeAfterMs = Math.max(this.smoothingMs, Number(fadeAfterMs) || 8000);
    this.staleAfterMs = Math.max(this.fadeAfterMs, Number(staleAfterMs) || 15000);
    this.tracks = new Map();
    this.lastStepAt = null;
    this.activeContextKey = null;
  }

  update(items, { mappingValid, cameraId, calibrationId } = {}, receivedAt = Date.now()) {
    if (!mappingValid || !cameraId || !calibrationId) {
      this.clear();
      return 0;
    }
    const contextKey = `${cameraId}:${calibrationId}`;
    if (this.activeContextKey !== contextKey) {
      this.clear();
      this.activeContextKey = contextKey;
    }
    const values = Array.isArray(items) ? items : Object.values(items || {});
    let accepted = 0;
    for (const item of values) {
      if (!item || item.mapping_valid !== true || item.camera_id !== cameraId ||
          item.calibration_id !== calibrationId || !Number.isInteger(Number(item.track_id)) ||
          Number(item.track_id) < 0 || !Array.isArray(item.floor_xy) ||
          item.floor_xy.length !== 2) continue;
      const x = Number(item.floor_xy[0]);
      const y = Number(item.floor_xy[1]);
      const observedAt = Date.parse(item.observed_at || '');
      if (!Number.isFinite(x) || !Number.isFinite(y) || !Number.isFinite(observedAt)) continue;
      const key = `${cameraId}:${String(item.track_id)}`;
      const previous = this.tracks.get(key);
      if (previous && observedAt < previous.observedAt) continue;
      const current = previous || { x, y, targetX: x, targetY: y, lastStepAt: receivedAt };
      current.targetX = x;
      current.targetY = y;
      current.observedAt = observedAt;
      current.receivedAt = receivedAt;
      current.state = String(item.decision_state || 'UNKNOWN');
      current.trackId = item.track_id;
      current.cameraId = cameraId;
      current.calibrationId = calibrationId;
      this.tracks.set(key, current);
      accepted += 1;
    }
    return accepted;
  }

  step(now = Date.now()) {
    const output = [];
    for (const [key, track] of this.tracks) {
      const age = Math.max(0, now - track.observedAt);
      if (age > this.staleAfterMs) {
        this.tracks.delete(key);
        continue;
      }
      const dt = Math.max(0, Math.min(1000, now - (track.lastStepAt ?? now)));
      const alpha = 1 - Math.exp(-dt / this.smoothingMs);
      track.x += (track.targetX - track.x) * alpha;
      track.y += (track.targetY - track.y) * alpha;
      track.lastStepAt = now;
      output.push({
        key, trackId: track.trackId, cameraId: track.cameraId,
        x: track.x, y: track.y, state: track.state,
        ageMs: age, stale: age > this.fadeAfterMs,
        opacity: Math.max(0.18, 1 - Math.max(0, age - this.fadeAfterMs) /
          Math.max(1, this.staleAfterMs - this.fadeAfterMs))
      });
    }
    return output;
  }

  clear() {
    this.tracks.clear();
    this.lastStepAt = null;
    this.activeContextKey = null;
  }
}
