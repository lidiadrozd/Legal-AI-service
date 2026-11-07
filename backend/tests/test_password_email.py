from unittest.mock import AsyncMock

import pytest

from app.services import email_service


@pytest.mark.asyncio
@pytest.mark.parametrize('port,override,tls', [(465, None, True), (587, None, False), (2465, True, True)])
async def test_smtp_transport_and_sender(monkeypatch, port, override, tls):
    for name, value in dict(SMTP_HOST='smtp.example.com', SMTP_PORT=port,
                            SMTP_USER='sender@example.com', SMTP_PASSWORD='test-secret',
                            SMTP_FROM='', SMTP_USE_TLS=override).items():
        monkeypatch.setattr(email_service.settings, name, value)
    send = AsyncMock()
    monkeypatch.setattr(email_service.aiosmtplib, 'send', send)
    await email_service.send_reset_password_email('recipient@example.com', 'https://example.com/reset-password?token=test')
    message = send.call_args.args[0]
    assert message['From'] == 'sender@example.com'
    assert message['To'] == 'recipient@example.com'
    assert send.call_args.kwargs['use_tls'] is tls
    assert send.call_args.kwargs['start_tls'] is not tls
    assert send.call_args.kwargs['timeout'] == 15
    assert len(message.get_payload()) == 2


@pytest.mark.asyncio
async def test_missing_credentials_does_not_connect(monkeypatch):
    monkeypatch.setattr(email_service.settings, 'SMTP_PASSWORD', '')
    send = AsyncMock()
    monkeypatch.setattr(email_service.aiosmtplib, 'send', send)
    with pytest.raises(RuntimeError, match='must be configured'):
        await email_service.send_reset_password_email('recipient@example.com', 'https://example.com')
    send.assert_not_called()
