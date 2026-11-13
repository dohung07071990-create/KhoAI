import test from 'node:test';
import assert from 'node:assert/strict';
import { TrackInterpolator } from '../frontend/digital-twin/track-interpolator.js';

const context = { mappingValid: true, cameraId: 'usb_external', calibrationId: 'cal-1' };
const item = (overrides = {}) => ({
  track_id: 7, camera_id: 'usb_external', calibration_id: 'cal-1',
  mapping_valid: true, floor_xy: [2, 3], observed_at: '2026-11-10T00:00:00.000+07:00',
  decision_state: 'WARNING', ...overrides
});

test('accepts only valid camera- and calibration-specific mapped tracks', () => {
  const tracker = new TrackInterpolator();
  assert.equal(tracker.update([item()], context, Date.parse('2026-11-09T17:00:00Z')), 1);
  assert.equal(tracker.update([item({ camera_id: 'other' })], context), 0);
  assert.equal(tracker.update([item({ calibration_id: 'old' })], context), 0);
  assert.equal(tracker.update([item({ mapping_valid: false })], context), 0);
  assert.equal(tracker.tracks.size, 1);
});

test('interpolates toward new calibrated position without jumping immediately', () => {
  const tracker = new TrackInterpolator({ smoothingMs: 100 });
  const t0 = Date.parse('2026-11-09T17:00:00Z');
  tracker.update([item({ observed_at: new Date(t0).toISOString() })], context, t0);
  tracker.step(t0 + 100);
  tracker.update([item({ floor_xy: [10, 3], observed_at: new Date(t0 + 200).toISOString() })], context, t0 + 200);
  const moved = tracker.step(t0 + 250)[0];
  assert.ok(moved.x > 2 && moved.x < 10);
});

test('rejects out-of-order observations and removes stale tracks', () => {
  const tracker = new TrackInterpolator({ staleAfterMs: 1000, fadeAfterMs: 500 });
  const t0 = Date.parse('2026-11-09T17:00:00Z');
  tracker.update([item({ observed_at: new Date(t0).toISOString() })], context, t0);
  tracker.update([item({ floor_xy: [99, 99], observed_at: new Date(t0 - 100).toISOString() })], context, t0 + 100);
  assert.equal(tracker.step(t0 + 200)[0].x, 2);
  assert.equal(tracker.step(t0 + 1100).length, 0);
  assert.equal(tracker.tracks.size, 0);
});

test('clears positions immediately when calibration is invalid', () => {
  const tracker = new TrackInterpolator();
  tracker.update([item()], context);
  tracker.update([item()], { ...context, mappingValid: false });
  assert.equal(tracker.step().length, 0);
});

test('does not interpolate across calibration changes', () => {
  const tracker = new TrackInterpolator({ smoothingMs: 100 });
  const t0 = Date.parse('2026-11-09T17:00:00Z');
  tracker.update([item({ observed_at: new Date(t0).toISOString() })], context, t0);
  tracker.update([item({ floor_xy: [20, 30], calibration_id: 'cal-2', observed_at: new Date(t0 + 100).toISOString() })],
    { ...context, calibrationId: 'cal-2' }, t0 + 100);
  const result = tracker.step(t0 + 100)[0];
  assert.equal(result.x, 20);
  assert.equal(result.y, 30);
  assert.equal(tracker.tracks.size, 1);
});
