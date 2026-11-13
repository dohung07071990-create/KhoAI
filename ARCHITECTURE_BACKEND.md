# KhoAI backend module map

## Application composition

`backend/app/main.py` is the composition root. It creates the FastAPI application, configures lifespan/middleware, wires runtime services, and retains operational API handlers that have not yet been extracted.

## Extracted modules

| Module | Responsibility | Boundary |
|---|---|---|
| `settings.py` | Environment-derived paths and runtime settings | No API routes |
| `schemas.py` | Pydantic request/response validation models | No database access |
| `database.py` | SQLite connection, transaction, schema and migrations | No HTTP routes |
| `auth.py` | Compatibility facade for authentication, session validation, role/device dependencies | Re-exports primitives; no route registration |
| `security_credentials.py` | Credential comparison, password hashing/verification and admin-secret policy | Pure security primitives; no DB access |
| `device_auth.py` | Device API-key validation and per-IP failure throttling | Independent device authentication dependency; no admin-session or route ownership |
| `auth_rate_limit.py` | Reusable admin-auth failure-window pruning and header throttling mechanics | Receives lock, failure state, limits and credential matcher; no global auth policy or DB access |
| `session_tokens.py` | Opaque session-token digest | SHA-256 digest only; raw cookie is not persisted |
| `uid_normalization.py` | RFID UID canonicalization and validation | Uses the shared UID format policy |
| `routes/auth.py` | Compatibility facade composing authentication route modules | Preserves `create_auth_router()`; no import from `main.py` |
| `routes/auth_sessions.py` | Login, current session, logout and session-cookie handling | Injected auth/session dependencies; no import from `main.py` |
| `routes/admin_users.py` | Administrator account list/create/update and last-admin safeguards | Injected DB, credential, session and authorization dependencies; no import from `main.py` |
| `routes/access.py` | Access check, recent RFID-to-track association, admin access audit logs | Injected access services; no import from `main.py` |
| `routes/rfid.py` | Device-authenticated RFID scan, camera-zone permission check, short-lived camera ticket issuance | Injected access-check callback, DB, detector-module provider, status callbacks and logger; no import from `main.py` |
| `routes/cards.py` | Card registry CRUD (list/create/update/compat delete) | Injected DB, auth, detector and clock services; no import from `main.py` |
| `routes/history.py` | Advanced history, access logs, dashboard counters | Injected `HistoryRouteServices`; no import from `main.py` |
| `privacy.py` | UID redaction and known-card UID cache | No API routes |
| `audit.py` | Admin audit middleware | No domain route logic |
| `retention.py` | Retention coordinator and compatibility API | Delegates audit/evidence policies and scheduling; receives DB/time dependencies |
| `services/audit_retention.py` | Expiry of access logs, security events, system logs and closed incidents | Injected DB/time dependencies; preserves pending Telegram outbox work |
| `services/evidence_retention.py` | Evidence file age/size cleanup and expired-reference metadata | Injected DB/time/logger; protects files referenced by OPEN incidents |
| `services/retention_worker.py` | Periodic retention scheduling and error isolation | Injected prune callback/logger; no DB or API dependency |
| `services/incident_lifecycle.py` | Open/reopen Incident and SAFE+ACK intrusion closure | Injected business clock, cooldown, siren duration and detector-state callback; no API dependency |

| `services/incident_read_service.py` | Incident list and event timeline read model | Injected DB session, UID masker and wall clock; no route registration |
| `services/security_alert_query_service.py` | Security alert filtering, response mapping and UID masking | Injected DB session and UID masker; no route registration |
| `services/incident_query_service.py` | Compatibility facade for the two incident/alert read services | Preserves the previous `IncidentQueryService` interface |

| `telegram/formatting.py` | Sanitized Telegram API errors, safe HTML truncation and escaping | Pure formatting/error helpers; no network or DB dependency |
| `telegram/api_client.py` | Telegram HTTP API calls and text/photo send operations | `TelegramAPIMixin`; consumes bot config/client/runtime state |
| `telegram/commands.py` | Compatibility facade for Telegram command responsibilities | `TelegramCommandMixin`; composes focused command/callback/polling mixins |
| `telegram/command_handlers.py` | Allowlist validation and `/start`, `/help`, `/id`, `/status`, `/alerts`, `/ack`, `/ackall`, `/snapshot` handlers | `TelegramCommandHandlersMixin`; delegates business mutations through injected context callbacks |
| `telegram/callbacks.py` | ACK callback authorization, acknowledgement and keyboard cleanup | `TelegramCallbackMixin`; uses injected context and API methods |
| `telegram/polling.py` | Telegram long-polling loop, send rate-limit and auth recovery probe | `TelegramPollingMixin`; maintains bot polling/auth state |
| `telegram/notifier.py` | Per-chat queue coordinator and notifier loop | `TelegramNotifierMixin`; delegates delivery and digest policies to focused mixins |
| `telegram/notifier_delivery.py` | Event formatting and per-event text/photo outbox delivery | `TelegramOutboxDeliveryMixin`; uses injected context, API and rate-limit methods |
| `telegram/notifier_digest.py` | Delayed WARNING digest batching | `TelegramWarningDigestMixin`; uses injected context, API and rate-limit methods |
| `telegram/bot.py` | Public compatibility facade, config/context models and worker supervisor | Composes the Telegram mixins; retains legacy public import paths |
| `telegram/integration.py` | Telegram composition adapter | Receives an explicit service bundle from `main.py`; does not import the composition root |

## Rules for future extraction

1. `main.py` may compose modules; feature modules must not import `main.py`.
2. Route modules register an `APIRouter` and receive dependencies explicitly through a typed service Protocol or FastAPI dependencies.
3. Domain/service modules must not import FastAPI request objects or register routes.
4. Keep SQL in the domain service/repository that owns the data; do not duplicate SQL across routers.
5. Keep compatibility wrappers in `main.py` only when an existing integration/test imports that historic symbol. Add a test for each wrapper before removing it.
6. Extract one route family at a time and run the complete Python suite, JavaScript suite, compile check, and release validator before packaging.
7. Do not split a handler by moving code blindly when it depends on monkeypatch points, app state, detector lifecycle, or shared alarm state. First define and test the dependency boundary.

## Remaining extraction candidates

- Camera API and stream lifecycle (highest coupling to detector, app state, WebRTC peers and stream manager).
- Incident lifecycle facade and event synchronization are now separated; review remaining orchestration and compatibility bridges before further extraction.
- RFID scan and event ingestion routes.
- Camera API and stream lifecycle.
- Incident lifecycle/event synchronization service.
- Alerts and system status APIs.

The access-check, track-association and system access-audit endpoints were extracted in dev.24.14. Remaining items stay in `main.py`; no claim is made that they have been modularized.

### Route modules (dev.24.11–24.51)
- `routes/auth.py`: compatibility facade.
- `routes/auth_sessions.py`: đăng nhập, đọc phiên và đăng xuất.
- `routes/admin_users.py`: quản lý tài khoản quản trị.
- `routes/history.py`: lịch sử truy cập, nhật ký và thống kê dashboard.
- `routes/spatial_mapping.py`: đọc, hiệu chuẩn và vô hiệu hóa Homography cho camera USB.
- Route modules nhận dependency/service provider từ lúc bootstrap; không import `main.py` để tránh vòng lặp phụ thuộc.

### Route modules (dev.24.12)
- `routes/incidents.py`: danh sách incident/alert, ACK incident/alert và điều khiển tắt còi.

### Route modules (dev.24.13)
- `routes/cards.py`: danh sách thẻ và tạo thẻ; router nhận DB session, schema, UID normalizer, đồng hồ nghiệp vụ và quyền admin qua service provider.
- Incident lifecycle, event ingestion và đồng bộ sự kiện camera vẫn nằm trong `main.py`; chưa tách service lõi.


### Route modules (dev.24.14)
- `routes/access.py`: kiểm tra quyền thẻ, liên kết UID với Track ID sau lần xác thực gần nhất và đọc system access audit logs.
- Router nhận DB session, admin dependency, UID normalizer, business clock/timezone, detector provider và logger qua service provider.
- `main.py` giữ `check_access()` làm compatibility entry point cho luồng `/api/rfid/scan`; logic kiểm tra quyền thực tế dùng chung `check_access_impl()`.


### dev.24.15 — Device routes
- `routes/devices.py`: device heartbeat, RFID scan compatibility listing, and last-unknown-card status.
- Router dependencies are injected; it does not import `main.py`.


### `routes/camera_config.py` (dev.24.16)

Owns administrator APIs for USB-camera anti-theft enablement, protection-zone read/update, RFID entry ROI read/update, and pending RFID-to-track bindings. Detector access and zone validation are injected by the composition root; this router does not import `main.py`.

### `routes/cards.py` (dev.24.17)

Owns administrator card registry list/create/update/delete endpoints. Card revocation is delegated to an injected detector provider; historical access and security logs remain untouched by card deletion.


### `routes/camera_status.py` (dev.24.18)

Owns read-only health, USB camera/AI status, camera control-center summary, and AI explainability endpoints. Detector access, session dependency, version, incident augmentation callback, and logger are supplied by the composition root. Camera streaming/WebRTC lifecycle remains in `main.py`.

### `routes/telegram_admin.py` (dev.24.19)

Owns administrator-only Telegram delivery diagnostics and manual retry endpoints. Database session, admin dependency, business clock, and epoch clock are injected by the application composition root. The Telegram delivery worker and retry scheduler remain outside this router.


### `routes/rfid.py` (dev.24.20)

Owns `POST /api/rfid/scan`, including camera-zone permission evaluation and RFID camera-ticket issuance. Device-key authorization, the shared access-check compatibility callback, UID normalization, database session, detector-module provider, business clock, alarm/siren callbacks, and logger are injected by the composition root. The route does not import `main.py`. The shared `check_access()` compatibility entry point remains in `main.py`.

### `routes/camera_events.py` (dev.24.21)

Owns the read-only camera event feed and incident timeline endpoints. It receives the DB session factory, session dependency, and UID masking callback from the composition root. Camera-event synchronization and incident lifecycle remain in `main.py`.


### `services/incident_store.py` (dev.24.22)

Owns incident persistence primitives: create/reopen, append deduplicated incident events, link source security events, close acknowledged resolved intrusion incidents, close health incidents, and classify health incident type. `main.py` retains compatibility wrappers. The higher-level USB event synchronization loop, incident status aggregation, reconciliation worker, and detector lifecycle remain in `main.py`.


### `services/camera_event_sync.py` (dev.24.23)

Owns persistence and incident routing for external USB detector events, including source-event idempotency, late evidence metadata enrichment, incident classification, and explicit-SAFE reconciliation. Database/session, incident-store callbacks, and business clock are injected. The async polling worker and detector lifecycle remain in `main.py`; compatibility entry points are retained.


### System status route (dev.24.24)
`backend/app/routes/system_status.py` owns the authenticated dashboard status endpoint. Database access, detector access, incident status, alarm level, scan count, and external-camera state are injected by the composition root in `main.py`. The legacy `main.integrated_status()` entry point remains as a compatibility bridge.

### External event ingestion (dev.24.25)
- `routes/external_events.py` owns the authenticated `POST /api/events` compatibility endpoint and its alert persistence helper.
- Runtime dependencies (DB session, admin dependency, business clock/timezone, legacy camera state, external time thresholds, and alarm-level provider) are injected by `main.py`.
- The endpoint remains a compatibility ingestion path; it does not replace the native USB camera Decision Engine.

### `services/incident_status.py` (dev.24.26)

Owns read-only aggregation of open incidents and enrichment of detector status with latched/acknowledged/siren state. Database session, detector-state callback, and wall-clock callback are injected. `main.py` retains `_incident_status()` and `_augment_detector_status()` compatibility bridges; incident mutation and reconciliation remain in their respective services.

### `routes/camera_media.py` (dev.24.27)

Owns read-only camera media endpoints: viewer distribution status, Track thumbnails, USB heatmap, UUID-named evidence JPEGs, and raw USB snapshots. The router receives authorization, detector, stream-manager, camera-read guard, evidence-directory provider, and logger through dependency injection. Long-lived MJPEG/WebRTC and ESP32-CAM proxy lifecycles are extracted separately in `routes/camera_streams.py` (dev.24.28).


### `routes/camera_streams.py` (dev.24.28)

Owns authenticated USB MJPEG output, WebRTC offer negotiation and peer cleanup, metadata-only camera WebSocket, and the authenticated ESP32-CAM MJPEG proxy. App state, detector, stream manager, auth/session validators, WebRTC factory, environment lookup, camera-read guard, and logger are injected by the composition root. `main.py` retains compatibility handler names for existing tests/integrations.


## Incident reconciliation (dev.24.29)
- `services/incident_reconciliation.py` owns periodic reconciliation of open incidents against detector state.
- It closes incidents only when the detector explicitly reports `SAFE` and anti-theft is enabled; detector/provider failures fail closed.
- `main.py` remains the composition root and compatibility bridge; `CameraEventSyncService` is limited to event persistence/classification.

### `services/camera_event_worker.py` (dev.24.30)

Owns the asynchronous polling loop for external USB detector events. It obtains the detector from an injected provider, retrieves a bounded event batch, dispatches persistence and incident reconciliation callbacks through worker threads, isolates iteration failures, and propagates cancellation for clean shutdown. It does not own event semantics or incident policy. `main.py` retains `_camera_event_sync_worker()` as a compatibility wrapper and continues to own FastAPI lifespan task startup/shutdown.

### Application lifecycle (dev.24.31)
`services/application_lifecycle.py` điều phối startup/shutdown bằng dependency injection. `main.py` vẫn là composition root: cung cấp DB initializer, admin validator, lazy detector loader, worker callbacks, Telegram factory và logger. Module lifecycle không import `main.py`; AI và Telegram vẫn được nạp trễ qua callback để giữ khả năng chạy API khi thiếu phụ thuộc AI/Telegram.

### `services/detector_state.py` (dev.24.32)

`DetectorStateReader` isolates the conversion of detector status into the shared incident/alarm state string. It receives a detector provider through dependency injection, keeps AI imports lazy at the composition root, and preserves `main._current_detector_state()` as a compatibility bridge. Detector/provider errors continue to resolve to `UNKNOWN`; anti-theft disabled resolves to `DISARMED`.

### `services/alarm_level.py` (dev.24.33)

`AlarmLevelResolver` translates the current detector's `alarm_state` and the persisted incident latch into the API-facing alarm vocabulary (`off`, `warning`, `severe`, `unknown`). Detector access, incident status, and logging are injected. Detector read failures resolve to `unknown`; an active incident latch takes precedence over a non-alarm detector state. `main.current_alarm_level()` remains the compatibility/composition bridge.

### `services/access_statistics.py` (dev.24.34)

`AccessStatisticsService` owns read-only aggregation of recent allowed scans and distinct UIDs allowed during the current business day. Database session and business timezone are injected. `main.py` retains the legacy `_scans_recently_allowed()` and `_scans_today_allowed()` entry points and refreshes the database-session provider before each call.

### `services/external_alert_store.py` (dev.24.34)

`ExternalAlertStore` owns persistence and duplicate suppression for compatibility alerts emitted by external-camera event ingestion. It skips an existing unacknowledged event with the same event type, zone, and UID; acknowledgement allows a subsequent event to be recorded. Database session and business-time provider are injected. The external-events router receives this operation from the composition root, while retaining a fallback for consumers constructing the router without the new dependency. `main._external_alert()` remains a compatibility bridge.

### `services/incident_commands.py` (dev.24.35)

`IncidentCommandService` owns the write-side bulk incident commands: acknowledging all open, unacknowledged incidents and silencing active sirens on open incidents. It receives the DB session factory, business clock, incident-resolution callback, and status provider through dependency injection. The production incident router delegates these commands through callbacks supplied by the composition root; `main.py` retains compatibility entry points and refreshes legacy monkeypatchable dependencies before delegation. ACK and siren silencing remain separate operations. The router's inline fallback exists only for standalone consumers that do not inject command callbacks.

## External Camera State
`services/external_camera_state.py` owns the in-memory status reported by compatibility external-camera clients. It exposes explicit outside/inside update methods and detached snapshots, with an internal lock for service-mediated access. The composition root injects the store into `routes/external_events.py`. `main._external_camera_state` remains a legacy mapping alias for existing status endpoints and integrations; it is not an authorization or alarm-decision source.

### `services/camera_access_policy.py` (dev.24.37)

`CameraAccessPolicy` owns the rule governing whether a camera read may start the detector. An admin request may start it; a non-admin request may only read when the detector is already running, otherwise the service raises HTTP 503. `main._ensure_camera_for_read()` remains a compatibility bridge passed to camera media and stream routers. This policy controls worker startup only; it does not grant access to protected API routes by itself.


### `services/external_event_processor.py` (dev.24.38)

Owns business processing for compatibility events from outside/inside camera clients: external camera state updates, RFID headcount heuristics, zone/loitering checks, pickup box comparison, and generic event persistence. Dependencies and alert-persistence callback are injected. `routes/external_events.py` retains admin authorization, HTTP registration, and the backward-compatible alert persistence fallback.


### `services/device_read_service.py` (dev.24.39)

Owns read-side compatibility queries for RFID scan history and the most recent denied/unknown card. The device router retains HTTP routing and session authentication; UID masking is injected from the composition root. Device heartbeat behavior remains in the router.

### `services/incident_health_policy.py` (dev.24.40)

`IncidentHealthPolicy` owns health-incident classification and recovery closure rules. It receives the business-time provider through dependency injection and operates on the supplied SQLite connection. `main._health_incident_type()` and `main._close_health_incidents()` remain compatibility bridges for `CameraEventSyncService` and existing integrations. `IncidentStore` remains responsible for intrusion incident persistence and event linking.


### `services/evidence_retention.py` (dev.24.41)

`EvidenceRetentionService` owns age/quota cleanup of JPEG evidence and expiration metadata updates in persisted security and incident events. It protects files referenced by open incidents. Database session, business timezone, and logger are injected. `RetentionService` retains compatibility delegate methods and continues to coordinate log cleanup and its periodic worker.


### Audit retention (`services/audit_retention.py`)
`AuditRetentionService` owns expiry policy and database deletion for access logs, security events, system access logs and closed incidents. It preserves events that still have pending Telegram outbox work. `RetentionService` remains the worker/orchestration facade and combines audit cleanup with evidence-file retention.


## Verification dev.24.43
- Retention scheduling moved to `services/retention_worker.py`; `RetentionService.worker()` remains a compatibility delegate.
- Full verification results are recorded in `TEST_REPORT_v0.6.2-dev.24.43.txt`.


## dev.24.44 — Incident Event Store
- `services/incident_event_store.py` chịu trách nhiệm ghi Incident Event có cooldown/idempotency và liên kết `security_events` với Incident.
- `IncidentStore` giữ các phương thức tương thích, ủy quyền thao tác event sang `IncidentEventStore`; vòng đời mở/đóng Incident vẫn ở `IncidentStore`.

### dev.24.46 — Incident query and alert command boundaries
- `services/incident_query_service.py` owns read-side incident/event hydration and alert filtering/mapping; the router retains HTTP auth and query validation.
- `services/incident_alert_commands.py` owns the write transaction for acknowledging one security alert; the router retains admin authorization.
- The existing `IncidentCommandService` remains responsible for bulk incident acknowledgement and siren silencing.

### Camera event read routes (dev.24.49)
- `routes/camera_event_feed.py`: read-only USB camera event feed (`GET /api/camera/events`).
- `routes/incident_timeline.py`: read-only timeline for a single Incident (`GET /api/incidents/{incident_id}/timeline`).
- `routes/camera_events.py`: compatibility composition facade; preserves the previous `create_camera_event_router` entry point.


### Authentication route split (dev.24.51)
- `routes/auth_sessions.py` owns login, `/api/auth/me`, and logout.
- `routes/admin_users.py` owns administrator account listing and mutations, including last-admin and self-demotion protections.
- `routes/auth.py` remains the stable facade; endpoint paths and injected service contract are unchanged.


### Camera streaming route split (dev.24.52)
- `routes/camera_usb_stream.py`: authenticated USB detector MJPEG stream.
- `routes/camera_webrtc.py`: WebRTC offer negotiation, peer registration, timeout and cleanup.
- `routes/camera_stream_metadata.py`: metadata-only WebSocket with Origin and session validation.
- `routes/inside_camera_stream.py`: authenticated ESP32-CAM MJPEG upstream proxy and resource cleanup.
- `routes/camera_streams.py` remains the compatibility facade and preserves `create_camera_stream_router()` plus legacy handler exports.

### Authentication primitive split (dev.24.54)
- `auth.py` remains the compatibility boundary for existing imports.
- Credential/password policy, opaque session digesting and RFID UID normalization now live in separate focused modules.
- The extraction preserves algorithms and validation rules; it does not change the authentication flow or persistence schema.

### Database layer split (dev.24.55)
- `sqlite_connection.py`: SQLite connection setup, WAL/foreign-key/busy-timeout pragmas, commit/rollback/close lifecycle.
- `schema_tables.py`: idempotent creation of tables and indexes.
- `schema_migrations.py`: forward-only compatibility migrations and optional first-admin bootstrap.
- `database.py`: stable initialization facade and re-exports for existing imports.


## Telegram persistence adapter (dev.24.56)

- `telegram/persistence_schema.py`: tạo schema outbox/lease/runtime và migration replay idempotent.
- `telegram/persistence_queries.py`: callback đọc trạng thái, cảnh báo, snapshot/evidence, khám phá sự kiện và hàng đợi đến hạn.
- `telegram/persistence_delivery.py`: callback ghi nhận acknowledge, trạng thái gửi text/photo, lease, retry và thống kê vận hành.
- `telegram/integration.py`: composition adapter dựng `TelegramContext` từ callbacks và nhận service bundle qua `build_telegram_bot(backend_services)`.
- `main.py` chỉ tạo service bundle gồm DB session, business timezone/clock và app version; Telegram không import ngược composition root.


## Telegram command responsibilities (dev.24.59)

- `telegram/command_handlers.py` owns command parsing, private-chat allowlist checks and user-facing command dispatch.
- `telegram/callbacks.py` owns callback-query authorization, ACK execution, callback response and inline-keyboard cleanup.
- `telegram/polling.py` owns `getUpdates` polling, offset advancement, per-chat rate limiting and auth recovery probing.
- `telegram/commands.py` remains the compatibility facade exporting `TelegramCommandMixin`, composed from the three focused mixins.
- The bot's MRO preserves the existing `TelegramBot(TelegramAPIMixin, TelegramCommandMixin, TelegramNotifierMixin)` composition; no router, DB schema or external API contract changed.


### Telegram configuration and lease boundaries (dev.24.60)
- `telegram/config.py` owns immutable bot configuration, environment parsing, and the `TelegramContext` dependency contract.
- `telegram/lease.py` owns the distributed lease heartbeat/retry safety policy.
- `telegram/bot.py` remains the worker supervisor and compatibility facade; historic imports for config helpers and `_lease_heartbeat_loop` remain available.

### Authentication rate-limit split (dev.24.62)
- `auth_rate_limit.py` owns the shared in-memory failure-window pruning and header-throttling mechanics.
- `auth.py` retains the historical `_record_auth_failure()` and `_check_admin_header()` wrappers and supplies its existing lock, failure map, configured thresholds and credential matcher.
- This dependency-injection boundary preserves `main.py` and test reset/monkeypatch points; it does not change rate-limit thresholds or HTTP behavior.

### Backend dependency cleanup (dev.24.63)
- `telegram/integration.py` no longer imports `main.py`; runtime dependencies arrive through `telegram_backend_services()` from the composition root.
- `auth._session_digest_valid_cached()` accepts an optional validator. The `main.py` compatibility wrapper passes its patchable validator explicitly instead of mutating `auth._session_digest_valid`.
- `privacy._mask_uid_payload()` accepts an optional known-UID provider. The `main.py` facade passes its patchable provider explicitly instead of replacing `privacy._known_card_uids_for_redaction`.
- `telegram/callbacks.py` imports `Any` and keeps its callback behavior unchanged. Route source-marker comments were removed; route tests now inspect the live FastAPI route registry.
