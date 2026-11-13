from backend.app.telegram.bot import TelegramConfig, TelegramBot, load_config


def test_telegram_disabled_by_default():
    assert load_config({}) is None


def test_telegram_requires_allowlist():
    assert load_config({"TELEGRAM_ENABLED":"1", "TELEGRAM_BOT_TOKEN":"token"}) is None


def test_telegram_config_parses_allowlist():
    cfg = load_config({"TELEGRAM_ENABLED":"1", "TELEGRAM_BOT_TOKEN":"token",
                       "TELEGRAM_ALLOWED_CHAT_IDS":"123,-456;789"})
    assert cfg is not None
    assert cfg.allowed_chat_ids == frozenset({123, 789})


def test_telegram_only_allows_private_allowlisted_chat():
    class Context: pass
    bot = TelegramBot(TelegramConfig("x", frozenset({123})), Context())
    assert bot._authorized(123, 123)
    assert not bot._authorized(-100123, 123)
    assert not bot._authorized(123, 456)
    assert not bot._authorized("123", 123)


def test_telegram_empty_env_is_respected(monkeypatch):
    monkeypatch.setenv("TELEGRAM_ENABLED", "1")
    monkeypatch.setenv("TELEGRAM_BOT_TOKEN", "should-not-be-used")
    assert load_config({}) is None


def test_telegram_html_truncation_keeps_entities_and_tags_valid():
    from backend.app.telegram.bot import _truncate_html
    result = _truncate_html("<b>abc &amp; def</b>", 5)
    assert result == "<b>abc &amp;</b>"


def test_telegram_rejects_negative_group_chat_ids():
    cfg = load_config({"TELEGRAM_ENABLED":"1", "TELEGRAM_BOT_TOKEN":"token",
                       "TELEGRAM_ALLOWED_CHAT_IDS":"-456,123"})
    assert cfg is not None and cfg.allowed_chat_ids == frozenset({123})


def test_telegram_ascii_ack_id_validation():
    import re
    assert re.fullmatch(r"[0-9]+", "123")
    assert not re.fullmatch(r"[0-9]+", "１２３")


def test_telegram_api_error_does_not_expose_bot_token():
    import asyncio
    import httpx
    from backend.app.telegram.bot import TelegramAPIError

    async def run():
        async def handler(request):
            return httpx.Response(500, json={"ok": False, "description": "failure"})
        client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
        bot = TelegramBot(TelegramConfig("SECRET_TOKEN", frozenset({123})), object(), client=client)
        try:
            await bot.api("sendMessage", {"chat_id": 123})
        except TelegramAPIError as exc:
            assert "SECRET_TOKEN" not in str(exc)
            assert "sendMessage" in str(exc)
        else:
            raise AssertionError("Expected TelegramAPIError")
        await client.aclose()
    asyncio.run(run())


def _fake_telegram_context(**overrides):
    from backend.app.telegram.bot import TelegramContext
    defaults = {
        "status": lambda: {}, "alerts": lambda limit: [],
        "acknowledge": lambda event_id, actor: True,
        "acknowledge_all": lambda actor: 0, "snapshot": lambda: None,
        "evidence": lambda event_id: {"status": "not_applicable", "photo": None},
        "discover_events": lambda chat_id, limit: 0,
        "due_items": lambda chat_id, limit: [],
        "mark_text": lambda chat_id, event_id, message_id: None,
        "retry_text": lambda chat_id, event_id, error, delay, permanent: None,
        "mark_photo": lambda chat_id, event_id, status, message_id, error, delay: None,
        "lease": lambda action, owner, ttl: True,
        "retry_permanent": lambda chat_id, event_id: False,
        "ops_status": lambda: {}, "runtime_state": lambda key, value: None,
    }
    defaults.update(overrides)
    return TelegramContext(**defaults)


def test_telegram_api_error_preserves_sanitized_description():
    import asyncio
    import httpx
    from backend.app.telegram.bot import TelegramAPIError

    async def run():
        async def handler(request):
            return httpx.Response(401, json={"ok": False, "description": "Unauthorized"})
        client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
        bot = TelegramBot(TelegramConfig("SECRET", frozenset({123})), _fake_telegram_context(), client)
        try:
            await bot.api("getMe")
        except TelegramAPIError as exc:
            assert exc.status_code == 401
            assert exc.description == "Unauthorized"
            assert "SECRET" not in str(exc)
            assert bot._auth_blocked
        else:
            raise AssertionError("Expected TelegramAPIError")
        await client.aclose()
    asyncio.run(run())


def test_telegram_html_entity_error_falls_back_to_plain_text():
    import asyncio
    import httpx

    async def run():
        calls = []
        async def handler(request):
            body = request.read()
            calls.append((request.url.path, request.headers.get("content-type", ""), body))
            if len(calls) == 1:
                return httpx.Response(400, json={"ok": False, "error_code": 400, "description": "Bad Request: can't parse entities"})
            return httpx.Response(200, json={"ok": True, "result": {"message_id": 77}})
        client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
        bot = TelegramBot(TelegramConfig("x", frozenset({123})), _fake_telegram_context(), client)
        try:
            assert await bot.send(123, "<b>KhoAI</b>") == 77
            assert len(calls) == 2
            assert b'"parse_mode"' in calls[0][2]
            assert b'"parse_mode"' not in calls[1][2]
        finally:
            await client.aclose()
    asyncio.run(run())


def test_telegram_sends_text_with_ack_before_evidence_branch():
    import asyncio
    import httpx

    async def run():
        sent = []
        marks = []
        photos = []
        async def handler(request):
            sent.append((request.url.path.rsplit("/", 1)[-1], request.read()))
            return httpx.Response(200, json={"ok": True, "result": {"message_id": 501}})
        event = {"event_id": 9, "severity": "severe", "event_type": "intrusion",
                 "message": "Phát hiện xâm nhập", "event_at": "2026-11-11T10:00:00+07:00",
                 "created_at": "2026-11-11T10:00:00+07:00", "text_status": "pending",
                 "photo_status": "pending", "acknowledged": 0}
        def due(chat_id, limit):
            return [{**event, "text_status": "sent", "text_message_id": 501}]
        def mark_text(chat_id, event_id, message_id): marks.append((chat_id,event_id,message_id))
        def mark_photo(chat_id,event_id,status,message_id,error,delay): photos.append(status)
        ctx = _fake_telegram_context(due_items=due, mark_text=mark_text, mark_photo=mark_photo)
        client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
        bot = TelegramBot(TelegramConfig("x", frozenset({123})), ctx, client)
        try:
            await bot._process_outbox_item(123, event)
            assert marks == [(123, 9, 501)]
            assert sent[0][0] == "sendMessage"
            assert b"ack:9" in sent[0][1]
            assert photos == ["not_applicable"]
            assert all(name != "sendPhoto" for name, _ in sent)
        finally:
            await client.aclose()
    asyncio.run(run())


def test_telegram_transient_failure_schedules_retry_without_marking_sent():
    import asyncio
    import httpx

    async def run():
        retries, marks = [], []
        async def handler(request):
            return httpx.Response(503, json={"ok": False, "description": "temporarily unavailable"})
        event = {"event_id": 12, "severity": "warning", "event_type": "test",
                 "message": "test", "event_at": "2026-11-11T10:00:00+07:00",
                 "created_at": "2026-11-11T10:00:00+07:00", "text_status": "pending",
                 "photo_status": "pending", "text_attempts": 0}
        ctx = _fake_telegram_context(
            retry_text=lambda *args: retries.append(args),
            mark_text=lambda *args: marks.append(args))
        client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
        bot = TelegramBot(TelegramConfig("x", frozenset({123})), ctx, client)
        try:
            await bot._process_outbox_item(123, event)
            assert len(retries) == 1
            assert retries[0][0:2] == (123, 12)
            assert retries[0][3] >= 1
            assert retries[0][4] is False
            assert marks == []
        finally:
            await client.aclose()
    asyncio.run(run())


def test_telegram_uid_masking_does_not_corrupt_vietnamese_free_text():
    from backend.app.telegram.privacy import mask_telegram_event
    event = {"message": "Cảnh báo: nhân viên vừa vào kho, UID ABCD1234", "details": {"uid": "ABCD1234"}}
    result = mask_telegram_event(event, {"ABCD1234"}, set(), False)
    assert "Cảnh báo: nhân viên vừa vào kho" in result["message"]
    assert "ABCD1234" not in result["message"]
    assert result["details"]["uid"] == "****1234"


def test_dev242_cursor_is_replayed_into_outbox_instead_of_trusted(tmp_path, monkeypatch):
    import asyncio
    from backend.app import main as backend
    from backend.app.telegram.integration import build_telegram_bot

    monkeypatch.setattr(backend, "DB_PATH", tmp_path / "telegram-migration.sqlite3")
    monkeypatch.setenv("TELEGRAM_ENABLED", "1")
    monkeypatch.setenv("TELEGRAM_BOT_TOKEN", "test-token")
    monkeypatch.setenv("TELEGRAM_ALLOWED_CHAT_IDS", "123")
    monkeypatch.setenv("TELEGRAM_REPLAY_HOURS", "6")
    backend.init_db()
    with backend.db_session() as db:
        db.execute("INSERT INTO security_events(event_at,event_type,severity,message,details_json) VALUES(?,?,?,?,?)",
                   (backend.now_business(), "intrusion", "warning", "test alert", "{}"))
        event_id = int(db.execute("SELECT last_insert_rowid()").fetchone()[0])
        db.execute("CREATE TABLE telegram_delivery_state(chat_id INTEGER PRIMARY KEY,last_event_id INTEGER NOT NULL)")
        db.execute("INSERT INTO telegram_delivery_state(chat_id,last_event_id) VALUES(123,999999)")
    bot = build_telegram_bot(backend.telegram_backend_services())
    assert bot is not None
    try:
        with backend.db_session() as db:
            row = db.execute("SELECT text_status,photo_status,replay_pending FROM telegram_outbox WHERE chat_id=123 AND event_id=?", (event_id,)).fetchone()
            assert row is not None
            assert row["text_status"] == "pending"
            assert row["photo_status"] == "pending"
            assert row["replay_pending"] == 1
    finally:
        asyncio.run(bot.client.aclose())


def test_dev241_global_sent_watermark_seeds_new_per_chat_cursor(tmp_path, monkeypatch):
    import asyncio
    from backend.app import main as backend
    from backend.app.telegram.integration import build_telegram_bot

    monkeypatch.setattr(backend, "DB_PATH", tmp_path / "telegram-241.sqlite3")
    monkeypatch.setenv("TELEGRAM_ENABLED", "1")
    monkeypatch.setenv("TELEGRAM_BOT_TOKEN", "test-token")
    monkeypatch.setenv("TELEGRAM_ALLOWED_CHAT_IDS", "456")
    backend.init_db()
    with backend.db_session() as db:
        # Exact 24.1 schema: the confirmed-send cursor was stored as a key/value.
        db.execute("CREATE TABLE telegram_state(key TEXT PRIMARY KEY,value TEXT NOT NULL)")
        db.execute("INSERT INTO telegram_state(key,value) VALUES('last_sent_id','42')")
    bot = build_telegram_bot(backend.telegram_backend_services())
    assert bot is not None
    try:
        with backend.db_session() as db:
            row = db.execute("SELECT last_event_id FROM telegram_delivery_state WHERE chat_id=456").fetchone()
            assert row is not None and int(row[0]) == 42
    finally:
        asyncio.run(bot.client.aclose())


def test_telegram_alert_command_masks_uid_and_person_name(tmp_path, monkeypatch):
    import json
    from backend.app import main as backend
    from backend.app.telegram.persistence_queries import build_query_callbacks

    monkeypatch.setattr(backend, "DB_PATH", tmp_path / "telegram-alert-privacy.sqlite3")
    monkeypatch.delenv("TELEGRAM_INCLUDE_PERSON_NAME", raising=False)
    backend.init_db()
    with backend.db_session() as db:
        db.execute("INSERT INTO cards(uid,name,age,created_at) VALUES(?,?,?,?)",
                   ("A1B2C3D4", "Nguyễn Văn An", 35, backend.now_business()))
        db.execute("INSERT INTO security_events(event_at,event_type,severity,message,details_json) VALUES(?,?,?,?,?)",
                   (backend.now_business(), "rfid_denied", "warning",
                    "Nguyễn Văn An bị từ chối, UID A1B2C3D4",
                    json.dumps({"uid": "A1B2C3D4", "person_name": "Nguyễn Văn An"})))
    result = build_query_callbacks(backend)["alerts"](10)
    assert len(result) == 1
    assert "A1B2C3D4" not in result[0]["message"]
    assert "Nguyễn Văn An" not in result[0]["message"]
    assert result[0]["details"]["uid"] == "****C3D4"
    assert "person_name" not in result[0]["details"]
    assert "details_json" not in result[0]


def test_telegram_uid_masking_preserves_non_uid_hex_and_numeric_text():
    from backend.app.telegram.privacy import mask_telegram_event
    message = "Người đứng lâu 3600 giây, Track 1042 từ 2026-11-11; cadence, face, added; UID A1B2C3D4"
    result = mask_telegram_event({"message": message}, {"A1B2C3D4"}, set(), False)
    assert "3600 giây" in result["message"]
    assert "Track 1042" in result["message"]
    assert "2026-11-11" in result["message"]
    assert "cadence, face, added" in result["message"]
    assert "A1B2C3D4" not in result["message"]
    assert "****C3D4" in result["message"]


def test_telegram_uid_fallback_masks_long_hex_but_preserves_short_numbers():
    from backend.app.telegram.privacy import mask_telegram_event
    message = "Track 1234 và Track 12345678 lúc 2026-11-11, cổng 8080; UID A1B2C3D4 và face"
    result = mask_telegram_event({"message": message}, set(), set(), False)
    assert "Track 1234" in result["message"]
    assert "Track 12345678" in result["message"]
    assert "2026-11-11" in result["message"]
    assert "cổng 8080" in result["message"]
    assert "A1B2C3D4" not in result["message"]
    assert "****C3D4" in result["message"]


def test_delayed_warning_replay_is_summarized_immediately():
    import asyncio
    from types import SimpleNamespace
    from backend.app.telegram.notifier_digest import TelegramWarningDigestMixin

    class FakeNotifier(TelegramWarningDigestMixin):
        config = SimpleNamespace(warning_summary_after_seconds=7200)
        def __init__(self):
            self.messages = []
            self.marked = []
            self.ctx = SimpleNamespace(
                mark_text=lambda *args: self.marked.append(("text", args)),
                mark_photo=lambda *args: self.marked.append(("photo", args)),
                retry_text=lambda *args: self.marked.append(("retry", args)),
            )
        async def _rate_limit(self, _chat_id):
            return None
        async def send(self, _chat_id, message, _buttons):
            self.messages.append(message)
            return len(self.messages)

    async def run():
        bot = FakeNotifier()
        events = [{"event_id": n, "severity": "warning", "text_status": "pending",
                   "replay_pending": 1, "created_at": "2026-11-12T10:00:00+07:00",
                   "event_at": "2026-11-12T10:00:00+07:00", "event_type": "intrusion"}
                  for n in range(1, 51)]
        summarized = await bot._summarize_delayed_warnings(123, events)
        assert summarized == set(range(1, 51))
        assert len(bot.messages) == 3
        assert all("phát lại sau nâng cấp" in message for message in bot.messages)
        assert len([item for item in bot.marked if item[0] == "photo"]) == 50
    asyncio.run(run())


def test_telegram_enabled_parser_is_fail_closed_and_consistent():
    from backend.app.telegram.bot import telegram_enabled, load_config
    base = {"TELEGRAM_BOT_TOKEN": "test", "TELEGRAM_ALLOWED_CHAT_IDS": "123"}
    for value in ("", "disabled", "garbage", "0", "false", "no", "off"):
        env = {**base, "TELEGRAM_ENABLED": value}
        assert telegram_enabled(env) is False
        assert load_config(env) is None
    for value in ("1", "true", "yes", "on"):
        env = {**base, "TELEGRAM_ENABLED": value}
        assert telegram_enabled(env) is True
        assert load_config(env) is not None


def test_stream_session_validation_cache_uses_one_background_check(monkeypatch):
    import asyncio
    from backend.app import main as backend
    calls = []
    monkeypatch.setattr(backend, "_session_digest_valid", lambda digest: calls.append(digest) or True)
    backend._session_validation_cache.clear()
    async def run():
        assert await backend._session_digest_valid_cached("digest-test") is True
        assert await backend._session_digest_valid_cached("digest-test") is True
    asyncio.run(run())
    assert calls == ["digest-test"]
    backend._session_validation_cache.clear()


def test_telegram_run_retries_lease_instead_of_exiting():
    import asyncio
    import httpx
    acquired = asyncio.Event()
    calls = []
    async def run():
        def lease(action, owner, ttl):
            calls.append(action)
            if action == "acquire":
                if calls.count("acquire") == 1:
                    return False
                acquired.set()
                return True
            return True
        bot = TelegramBot(TelegramConfig("x", frozenset({123})),
                          _fake_telegram_context(lease=lambda a, o, t: lease(a, o, t)),
                          client=httpx.AsyncClient())
        async def idle():
            await asyncio.Event().wait()
        bot.command_loop = idle
        bot.notifier_loop = idle
        task = asyncio.create_task(bot.run())
        try:
            await asyncio.wait_for(acquired.wait(), timeout=3)
            assert calls.count("acquire") >= 2
        finally:
            task.cancel()
            try:
                await task
            except asyncio.CancelledError:
                pass
            await bot.client.aclose()
    asyncio.run(run())
