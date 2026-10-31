import importlib.util
from pathlib import Path
import socket
import threading
from unittest.mock import Mock


def _load_tunnel():
    path = Path(__file__).resolve().parents[2] / "tools" / "gigachat_tunnel.py"
    spec = importlib.util.spec_from_file_location("gigachat_tunnel_test", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _request_through_tunnel(module, request: bytes) -> bytes:
    with module.Server(("127.0.0.1", 0), module.Tunnel) as server:
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        try:
            with socket.socket() as client:
                client.settimeout(3)
                client.connect(server.server_address)
                client.sendall(request)
                return client.recv(1024)
        finally:
            server.shutdown()
            thread.join(timeout=3)


def test_local_tunnel_refuses_arbitrary_destinations(monkeypatch):
    module = _load_tunnel()
    upstream = Mock(side_effect=AssertionError("Forbidden destination must not be connected"))
    monkeypatch.setattr(module.socket, "create_connection", upstream)
    response = _request_through_tunnel(module, b"CONNECT example.com:443 HTTP/1.1\r\nHost: example.com:443\r\n\r\n")
    assert response.startswith(b"HTTP/1.1 403")
    upstream.assert_not_called()


def test_local_tunnel_allows_only_fixed_gigachat_oauth_and_cbr_tls_targets(monkeypatch):
    module = _load_tunnel()
    calls: list[tuple[str, int]] = []

    def fake_connect(target, timeout):
        calls.append(target)
        upstream, peer = socket.socketpair()
        # The request client closes after reading the CONNECT response.  Keeping
        # the peer alive until then lets the handler enter its normal relay loop.
        peer.close()
        return upstream

    monkeypatch.setattr(module.socket, "create_connection", fake_connect)
    for request in (
        b"CONNECT gigachat.devices.sberbank.ru:443 HTTP/1.1\r\nHost: gigachat.devices.sberbank.ru:443\r\n\r\n",
        b"CONNECT ngw.devices.sberbank.ru:9443 HTTP/1.1\r\nHost: ngw.devices.sberbank.ru:9443\r\n\r\n",
        b"CONNECT WWW.CBR.RU:443 HTTP/1.0\r\nHost: www.cbr.ru:443\r\n\r\n",
    ):
        assert _request_through_tunnel(module, request).startswith(b"HTTP/1.1 200")
    assert calls == [
        ("gigachat.devices.sberbank.ru", 443),
        ("ngw.devices.sberbank.ru", 9443),
        ("www.cbr.ru", 443),
    ]


def test_local_tunnel_rejects_malformed_or_nearby_authorities():
    module = _load_tunnel()
    for first_line in (
        b"GET www.cbr.ru:443 HTTP/1.1",
        b"CONNECT www.cbr.ru:444 HTTP/1.1",
        b"CONNECT ngw.devices.sberbank.ru:443 HTTP/1.1",
        b"CONNECT www.cbr.ru:443@evil.example HTTP/1.1",
        b"CONNECT www.cbr.ru:443 HTTP/2",
        b"CONNECT www.cbr.ru:443 HTTP/1.1 extra",
    ):
        assert module._target_from_connect_request(first_line) is None
