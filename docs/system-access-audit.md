# System Access Audit

KhoAI now stores two independent history streams:

- `access_logs`: RFID card scans at the warehouse access point (`allow` / `deny`).
- `system_access_logs`: administrator session events (`LOGIN`, `LOGOUT`) and state-changing admin API requests (`ADMIN_ACTION`).

The system currently authenticates administrators with one shared `KHOAI_ADMIN_TOKEN`. The operator label entered at the browser prompt is self-declared metadata, not a verified identity. The audit screen explicitly states this. IP address and user-agent are recorded as supporting context, not proof of identity.

To identify individual people reliably, replace the shared-token model with individual user accounts, password hashing, per-user sessions, roles, and account disable/revocation. Do not present self-declared names as authenticated identities.

System audit rows use the same `KHOAI_LOG_RETENTION_DAYS` retention setting as RFID/security logs. The default is 365 days.
