import base64
from types import SimpleNamespace
import pytest
from app.services import gigachat_client as module


def client(monkeypatch, *, client_id="test-id", secret="test-secret", key=""):
    monkeypatch.setattr(module, "settings", SimpleNamespace(GIGACHAT_CLIENT_ID=client_id,
        GIGACHAT_CLIENT_SECRET=secret, GIGACHAT_AUTH_KEY=key))
    return module.GigaChatAutoToken()


def test_classic_credentials_and_long_id_are_encoded(monkeypatch):
    value = "x" * 80
    header = client(monkeypatch, client_id=value)._build_auth_header()
    assert base64.b64decode(header[6:]).decode() == value + ":test-secret"


@pytest.mark.parametrize("prefix", ["", "Basic "])
def test_explicit_ready_key_supported(monkeypatch, prefix):
    key = base64.b64encode(b"ready-id:ready-secret").decode()
    assert client(monkeypatch, key=prefix+key)._build_auth_header() == "Basic " + key


def test_ready_key_in_id_supported_without_secret(monkeypatch):
    key = base64.b64encode(b"ready-id:ready-secret").decode()
    assert client(monkeypatch, client_id=key, secret="")._build_auth_header() == "Basic " + key


@pytest.mark.parametrize("key", ["private-invalid-key", base64.b64encode(b"missing-separator").decode()])
def test_invalid_ready_key_error_never_discloses_credentials(monkeypatch, key):
    with pytest.raises(RuntimeError) as caught:
        client(monkeypatch, key=key)._build_auth_header()
    assert key not in str(caught.value)
    assert "test-secret" not in str(caught.value)


@pytest.mark.asyncio
async def test_ready_key_oauth_preserves_expiry_and_single_refresh(monkeypatch):
    import asyncio
    import httpx
    key = base64.b64encode(b"ready-id:ready-secret").decode()
    value = client(monkeypatch, key=key)
    module.settings.GIGACHAT_SCOPE = "test-scope"
    requests = []
    original = httpx.AsyncClient
    def response(request):
        requests.append(request)
        return httpx.Response(200, json={"access_token":"synthetic-token", "expires_at":2000000300000})
    monkeypatch.setattr(module, "build_gigachat_ssl_context", lambda: True)
    monkeypatch.setattr(module.httpx, "AsyncClient", lambda **kwargs: original(transport=httpx.MockTransport(response)))
    monkeypatch.setattr(module.time, "time", lambda: 2000000000)
    tokens = await asyncio.gather(value.get_valid_token(), value.get_valid_token())
    assert tokens == ["synthetic-token", "synthetic-token"]
    assert len(requests) == 1
    assert requests[0].headers["Authorization"] == "Basic " + key
    assert value.expires_at == 2000000240
