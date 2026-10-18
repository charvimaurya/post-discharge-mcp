"""Local CA setup and real signature math; no Amazon or patient network calls."""

import base64
import json
import os
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace

import certifi
import pytest
from cryptography import x509
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.asymmetric import padding, rsa
from cryptography.x509.oid import NameOID

from app.alexa.skill import RequestVerifier
from scripts import run_web_bridge
from tests.test_alexa import alexa, _envelope


@pytest.mark.parametrize("trusted_roots", [0, 12])
def test_local_ca_fallback_only_when_default_store_is_empty(monkeypatch, trusted_roots):
    monkeypatch.delenv("SSL_CERT_FILE", raising=False)
    monkeypatch.delenv("SSL_CERT_DIR", raising=False)
    monkeypatch.setattr(run_web_bridge.ssl, "create_default_context", lambda: SimpleNamespace(
        cert_store_stats=lambda: {"x509_ca": trusted_roots}))
    run_web_bridge.configure_local_tls_trust()
    assert os.environ.get("SSL_CERT_FILE") == (certifi.where() if not trusted_roots else None)


@pytest.mark.parametrize("setting", ["SSL_CERT_FILE", "SSL_CERT_DIR"])
def test_local_ca_fallback_preserves_explicit_trust(monkeypatch, setting):
    monkeypatch.delenv("SSL_CERT_FILE", raising=False)
    monkeypatch.delenv("SSL_CERT_DIR", raising=False)
    monkeypatch.setenv(setting, "/custom/trust")
    monkeypatch.setattr(run_web_bridge.ssl, "create_default_context",
                        lambda: pytest.fail("Must preserve custom trust configuration"))
    run_web_bridge.configure_local_tls_trust()
    assert os.environ[setting] == "/custom/trust"
    if setting == "SSL_CERT_DIR":
        assert "SSL_CERT_FILE" not in os.environ


@pytest.mark.parametrize("tampered", [False, True])
def test_signed_launch_checks_signature_without_bridge_key(alexa, monkeypatch, tampered):
    # Only the trust anchor is injected: the SDK's signature verification is real.
    # This does not establish trust in an actual Amazon certificate chain.
    key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    name = x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, "synthetic-test")])
    now = datetime.now(timezone.utc)
    cert = (x509.CertificateBuilder().subject_name(name).issuer_name(name)
            .public_key(key.public_key()).serial_number(x509.random_serial_number())
            .not_valid_before(now - timedelta(minutes=1))
            .not_valid_after(now + timedelta(minutes=1)).sign(key, hashes.SHA256()))
    monkeypatch.setattr(RequestVerifier, "_retrieve_and_validate_certificate_chain", lambda *args: cert)
    monkeypatch.setenv("ALEXA_VERIFY_SIGNATURE", "true")
    monkeypatch.setenv("ALEXA_VERIFY_TIMESTAMP", "true")
    monkeypatch.delenv("BRIDGE_KEY", raising=False)
    envelope = _envelope({"type": "LaunchRequest"})
    envelope["request"]["timestamp"] = now.strftime("%Y-%m-%dT%H:%M:%SZ")
    body = json.dumps(envelope)
    signature = key.sign(body.encode(), padding.PKCS1v15(), hashes.SHA256())
    if tampered:
        body += " "
    from starlette.testclient import TestClient
    from app.web_bridge import app
    response = TestClient(app).post("/alexa", content=body, headers={
        "Signature-256": base64.b64encode(signature).decode(),
        "SignatureCertChainUrl": "https://s3.amazonaws.com/echo.api/synthetic-test.pem",
    })
    if tampered:
        assert response.status_code == 400
        assert response.json() == {"error": "Request refused."}
        assert not alexa.turns
    else:
        assert response.status_code == 200
        assert response.json()["version"] == "1.0"
        assert response.json()["response"]["outputSpeech"]["type"] == "PlainText"
        assert alexa.turns == [("What is next?", "amzn1.echo-api.session.s-1")]
