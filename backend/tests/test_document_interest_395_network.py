from app.services import document_interest_395 as interest_395


class _Response:
    status = 200

    def __enter__(self):
        return self

    def __exit__(self, *_args):
        return False

    def read(self, _limit):
        return b"<html>official rate history</html>"


def test_cbr_history_uses_the_fixed_configured_proxy(monkeypatch):
    captured = {}

    class _Opener:
        def open(self, request, *, timeout):
            captured["url"] = request.full_url
            captured["timeout"] = timeout
            return _Response()

    def build(handler):
        captured["proxies"] = handler.proxies
        return _Opener()

    monkeypatch.setattr(interest_395, "_cbr_proxy_url", lambda: "http://host.docker.internal:8766")
    monkeypatch.setattr(interest_395, "build_opener", build)

    body = interest_395._fetch_cbr_page("https://www.cbr.ru/hd_base/KeyRate/")

    assert body == "<html>official rate history</html>"
    assert captured["proxies"] == {"https": "http://host.docker.internal:8766"}
    assert captured["url"] == "https://www.cbr.ru/hd_base/KeyRate/"
    assert captured["timeout"] == 15
