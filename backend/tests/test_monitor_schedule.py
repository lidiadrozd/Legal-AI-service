from contextlib import asynccontextmanager
from unittest.mock import AsyncMock, Mock
import pytest
import importlib
jobs = importlib.import_module("app.celery_app")
from app.models.law_monitor_state import LawMonitorState


@pytest.mark.asyncio
async def test_retry_selects_only_configured_failed_sources(db_session, monkeypatch):
    db = db_session
    connection = await db.connection()
    await connection.run_sync(lambda c: LawMonitorState.__table__.create(c, checkfirst=True))
    db.add_all([
        LawMonitorState(source_url="https://failed.invalid", last_error="ConnectTimeout", progress={}),
        LawMonitorState(source_url="https://ok.invalid", last_error=None, progress={}),
        LawMonitorState(source_url="https://old.invalid", last_error="ReadTimeout", progress={}),
    ])
    await db.commit()
    monkeypatch.setattr(jobs.settings, "LAW_CHANGE_SOURCES", "https://failed.invalid,https://ok.invalid")
    @asynccontextmanager
    async def session():
        yield db
    monkeypatch.setattr(jobs, "AsyncSessionLocal", session)
    monitor = AsyncMock(return_value=[])
    monkeypatch.setattr(jobs, "monitor_sources", monitor)
    assert await jobs.retry_failed_sources() == []
    monitor.assert_awaited_once_with(source_urls=["https://failed.invalid"])
    state = await db.get(LawMonitorState, 1)
    state.last_error = None
    await db.commit()
    monitor.reset_mock()
    assert await jobs.retry_failed_sources() is None
    monitor.assert_not_awaited()


def test_retry_dispatches_even_when_no_new_changes(monkeypatch):
    monkeypatch.setattr(jobs, "retry_failed_sources", AsyncMock(return_value=[]))
    delivery = Mock()
    monkeypatch.setattr(jobs.send_notifications, "delay", delivery)
    jobs.retry_law_monitoring.run()
    delivery.assert_called_once_with()


def test_retry_without_failures_does_not_dispatch(monkeypatch):
    monkeypatch.setattr(jobs, "retry_failed_sources", AsyncMock(return_value=None))
    delivery = Mock()
    monkeypatch.setattr(jobs.send_notifications, "delay", delivery)
    jobs.retry_law_monitoring.run()
    delivery.assert_not_called()


def test_schedule_preserves_daily_check_and_spaces_retries():
    schedule = jobs.celery_app.conf.beat_schedule
    assert jobs.celery_app.conf.timezone == "Europe/Moscow"
    assert schedule["monitor-laws-daily"]["schedule"].hour == {9}
    assert schedule["retry-failed-law-sources"]["schedule"].hour == {10, 12, 15}
    assert schedule["retry-failed-law-sources"]["schedule"].minute == {0}


@pytest.mark.asyncio
async def test_source_request_has_overall_deadline(monkeypatch):
    import asyncio
    from app.services import law_change_monitor as monitor
    monkeypatch.setattr(monitor.settings, "LAW_CHANGE_HTTP_TIMEOUT", 0)
    cancelled = False
    async def stalled_get(url):
        nonlocal cancelled
        try:
            await asyncio.sleep(10)
        finally:
            cancelled = True
    client = Mock(get=stalled_get)
    with pytest.raises(TimeoutError):
        await monitor._get_source_response(client, "https://source.invalid")
    assert cancelled


def test_task_closes_async_connections_on_success_and_failure(monkeypatch):
    dispose = AsyncMock()
    monkeypatch.setattr(jobs, "engine", Mock(dispose=dispose))
    async def successful():
        return 7
    assert jobs.run_async_task(successful()) == 7
    async def failing():
        raise ValueError("test_failure")
    with pytest.raises(ValueError, match="test_failure"):
        jobs.run_async_task(failing())
    assert dispose.await_count == 2
