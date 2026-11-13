# KhoAI dev.24.1 – Security & Deployment Hardening

## Docker
- Image now includes `config/profiles/` required by `ai.config_profiles`.
- Default zone file is initialized from `ai/zone.json.example`; runtime data remains in `/app/data`.

## Device API key
- `KHOAI_API_KEY` must be a private value of at least 32 characters and must not be a sample value.
- Failed RFID API-key attempts are rate-limited per client IP in each application process.
- Replace the example value before deployment.

## Authentication
- Password hashes use PBKDF2-HMAC-SHA256 with 600,000 iterations for new hashes. Existing supported PBKDF2 hashes are verified and upgraded after successful login.
- Login performs a dummy PBKDF2 verification when the username is absent.
- An account cannot demote/deactivate itself; the final active admin cannot be demoted/deactivated.
- Bootstrap admin password must be at least 12 characters.

## Privacy and streams
- Viewer responses mask RFID UIDs to their final four hexadecimal characters in access history, scan history, alerts and last-unknown-card output.
- Camera metadata WebSocket checks same-host Origin when supplied and revalidates its session while connected.
- Camera MJPEG streams revalidate the session while streaming. ESP32-CAM upstream uses finite connect/read/write/pool timeouts.

## Remaining deployment requirements
- Configure trusted proxy forwarding only for known proxy addresses; do not trust arbitrary `X-Forwarded--For` headers.
- API-key rate limiting is process-local; multi-worker deployments should add a shared limiter.
- RFID UID remains a weak identifier; this software change does not make UID-only cards clone-resistant.
- ESP32 firmware transport/signature security is outside this software-only patch.
