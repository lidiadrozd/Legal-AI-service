"""Local allow-listed CONNECT tunnel for Docker Desktop outbound TLS issues.

Listens on Windows loopback only. It neither terminates TLS nor sees message
contents.  It can reach only the fixed TLS destinations used by the local
service: GigaChat chat, GigaChat OAuth, and the Bank of Russia's key-rate
history page.
"""
import select
import socket
import socketserver
import argparse

ALLOWED_TARGETS = {
    "gigachat.devices.sberbank.ru:443": ("gigachat.devices.sberbank.ru", 443),
    "ngw.devices.sberbank.ru:9443": ("ngw.devices.sberbank.ru", 9443),
    "www.cbr.ru:443": ("www.cbr.ru", 443),
}


def _target_from_connect_request(first_line: bytes) -> tuple[str, int] | None:
    """Return an allow-listed TLS target for a syntactically valid CONNECT line.

    A CONNECT proxy must not turn this loopback helper into an unrestricted
    network relay.  Therefore the authority is not parsed into an arbitrary
    destination: after strict ASCII request-line parsing it is looked up in a
    fixed allow-list.  Host names are case-insensitive; the port remains fixed
    at 443.
    """
    try:
        method, authority, version = first_line.decode("ascii", "strict").split(" ")
    except (UnicodeDecodeError, ValueError):
        return None
    if method != "CONNECT" or version not in {"HTTP/1.0", "HTTP/1.1"}:
        return None
    return ALLOWED_TARGETS.get(authority.lower())


class Tunnel(socketserver.BaseRequestHandler):
    def handle(self):
        peer = self.request
        peer.settimeout(10)
        header = bytearray()
        while b"\r\n\r\n" not in header:
            chunk = peer.recv(1)
            if not chunk: return
            header.extend(chunk)
            if len(header) > 8192: return
        first = bytes(header).split(b"\r\n", 1)[0]
        target = _target_from_connect_request(first)
        if target is None:
            peer.sendall(b"HTTP/1.1 403 Forbidden\r\nContent-Length: 0\r\n\r\n")
            return
        try:
            upstream = socket.create_connection(target, timeout=10)
        except OSError:
            peer.sendall(b"HTTP/1.1 502 Bad Gateway\r\nContent-Length: 0\r\n\r\n")
            return
        with upstream:
            peer.sendall(b"HTTP/1.1 200 Connection Established\r\n\r\n")
            peer.settimeout(180)
            upstream.settimeout(180)
            try:
                while True:
                    readable, _, _ = select.select([peer, upstream], [], [], 180)
                    if not readable: return
                    for source in readable:
                        data = source.recv(65536)
                        if not data: return
                        destination = upstream if source is peer else peer
                        destination.sendall(data)
            except OSError:
                return


class Server(socketserver.ThreadingTCPServer):
    allow_reuse_address = True
    daemon_threads = True


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Run the fixed local TLS CONNECT tunnel.")
    parser.add_argument("--port", type=int, default=8766)
    args = parser.parse_args()
    if not 1 <= args.port <= 65535:
        parser.error("--port must be between 1 and 65535")
    with Server(("127.0.0.1", args.port), Tunnel) as server:
        server.serve_forever()
