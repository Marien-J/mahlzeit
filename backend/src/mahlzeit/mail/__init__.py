"""Outgoing email over SMTP, configured by environment variables."""

from __future__ import annotations

import smtplib
import ssl
from email.message import EmailMessage
from typing import Protocol

from mahlzeit.config import get_settings


class Mailer(Protocol):
    def send(self, *, to: str, subject: str, body: str) -> None: ...


class SmtpMailer:
    def send(self, *, to: str, subject: str, body: str) -> None:
        s = get_settings()
        msg = EmailMessage()
        msg["From"] = s.smtp_from
        msg["To"] = to
        msg["Subject"] = subject
        msg.set_content(body)
        context = ssl.create_default_context()
        smtp: smtplib.SMTP
        if s.smtp_security == "ssl":
            smtp = smtplib.SMTP_SSL(s.smtp_host, s.smtp_port, timeout=20, context=context)
        else:
            smtp = smtplib.SMTP(s.smtp_host, s.smtp_port, timeout=20)
        with smtp:
            if s.smtp_security == "starttls":
                smtp.starttls(context=context)
            if s.smtp_user:
                smtp.login(s.smtp_user, s.smtp_password)
            smtp.send_message(msg)
