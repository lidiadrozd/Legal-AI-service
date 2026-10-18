import ssl
from pathlib import Path
from types import SimpleNamespace

import pytest

from app.services import gigachat_client


def test_gigachat_ca_added_without_disabling_verification(monkeypatch):
    path = Path(__file__).resolve().parents[1] / "certs/russian_trusted_root_ca.pem"
    monkeypatch.setattr(gigachat_client, "settings", SimpleNamespace(GIGACHAT_CA_BUNDLE_FILE=str(path)))
    context = gigachat_client.build_gigachat_ssl_context()
    assert context.verify_mode == ssl.CERT_REQUIRED
    assert context.check_hostname is True
    assert any(
        value == "Russian Trusted Root CA"
        for certificate in context.get_ca_certs()
        for rdn in certificate["subject"]
        for key, value in rdn if key == "commonName"
    )


def test_missing_configured_ca_fails_instead_of_disabling_tls(monkeypatch, tmp_path):
    monkeypatch.setattr(gigachat_client, "settings", SimpleNamespace(
        GIGACHAT_CA_BUNDLE_FILE=str(tmp_path / "missing.pem")))
    with pytest.raises(FileNotFoundError):
        gigachat_client.build_gigachat_ssl_context()
