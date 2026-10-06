"""The real SMTP and web push adapters against local stub servers."""

import base64
import json
import os
import socket
import threading
from collections.abc import Iterator
from http.server import BaseHTTPRequestHandler, HTTPServer
from typing import Any, ClassVar

import pytest
from aiosmtpd.controller import Controller
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import ec

from mahlzeit.mail import SmtpMailer
from mahlzeit.push import Delivery, WebPushSender


def _free_port() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return int(s.getsockname()[1])


class _Inbox:
    def __init__(self) -> None:
        self.messages: list[Any] = []

    async def handle_DATA(self, server: Any, session: Any, envelope: Any) -> str:  # noqa: N802
        self.messages.append(envelope)
        return "250 OK"


def test_smtp_mailer_sends(settings) -> None:
    inbox = _Inbox()
    port = _free_port()
    controller = Controller(inbox, hostname="127.0.0.1", port=port)
    controller.start()
    try:
        settings(
            smtp_host="127.0.0.1",
            smtp_port=port,
            smtp_security="none",
            smtp_from="mahlzeit@example.org",
        )
        SmtpMailer().send(to="jonas@example.org", subject="Hallo", body="Grüße")
    finally:
        controller.stop()
    (envelope,) = inbox.messages
    assert envelope.rcpt_tos == ["jonas@example.org"]
    assert b"Subject: Hallo" in envelope.content


class _PushService(BaseHTTPRequestHandler):
    status = 201
    requests: ClassVar[list[dict[str, Any]]] = []

    def do_POST(self) -> None:
        body = self.rfile.read(int(self.headers["Content-Length"]))
        type(self).requests.append({"headers": dict(self.headers), "body": body})
        self.send_response(type(self).status)
        self.end_headers()

    def log_message(self, *args: Any) -> None:
        pass


@pytest.fixture
def push_service() -> Iterator[tuple[str, type[_PushService]]]:
    _PushService.requests = []
    _PushService.status = 201
    server = HTTPServer(("127.0.0.1", 0), _PushService)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    yield f"http://127.0.0.1:{server.server_port}/push/abc", _PushService
    server.shutdown()


def _browser_subscription(endpoint: str) -> dict[str, Any]:
    key = ec.generate_private_key(ec.SECP256R1())
    public = key.public_key().public_bytes(
        serialization.Encoding.X962, serialization.PublicFormat.UncompressedPoint
    )
    b64 = lambda raw: base64.urlsafe_b64encode(raw).decode().rstrip("=")  # noqa: E731
    return {"endpoint": endpoint, "keys": {"p256dh": b64(public), "auth": b64(os.urandom(16))}}


def test_web_push_sends_encrypted_with_vapid(push_service) -> None:
    endpoint, service = push_service
    assert WebPushSender().send(_browser_subscription(endpoint), {"title": "Hi"}) is Delivery.SENT
    (request,) = service.requests
    headers = {k.lower(): v for k, v in request["headers"].items()}
    assert headers["content-encoding"] == "aes128gcm"
    assert headers["authorization"].startswith("vapid t=")
    assert b"Hi" not in request["body"]
    json.dumps(headers)


@pytest.mark.parametrize("status", [404, 410])
def test_web_push_reports_gone(push_service, status: int) -> None:
    endpoint, service = push_service
    service.status = status
    assert WebPushSender().send(_browser_subscription(endpoint), {"title": "Hi"}) is Delivery.GONE


def test_web_push_raises_on_server_error(push_service) -> None:
    endpoint, service = push_service
    service.status = 500
    with pytest.raises(RuntimeError):
        WebPushSender().send(_browser_subscription(endpoint), {"title": "Hi"})
