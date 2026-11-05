"""Sending email (password reset links).

Configure an SMTP account in backend/.env (see .env.example), e.g. Gmail with an App Password:

    SMTP_HOST=smtp.gmail.com
    SMTP_PORT=587
    SMTP_USER=you@gmail.com
    SMTP_PASSWORD=abcd efgh ijkl mnop      # a Google "App password", not your normal password
    MAIL_FROM=FindYourMate <you@gmail.com>

Without SMTP settings, emails aren't sent: the message (including the link) is printed in the backend terminal
instead, so you can still test the flow on your own computer.
"""
from __future__ import annotations

import os
import smtplib
import ssl
from email.message import EmailMessage


class MailError(Exception):
    pass


def configured() -> bool:
    return bool(os.environ.get("SMTP_HOST"))


def send(to: str, subject: str, text: str, html: str | None = None) -> bool:
    """Send an email. Returns True if sent by SMTP, False if only printed (SMTP not configured)."""
    sender = os.environ.get("MAIL_FROM") or os.environ.get("SMTP_USER") or "FindYourMate <no-reply@localhost>"
    msg = EmailMessage()
    msg["Subject"] = subject
    msg["From"] = sender
    msg["To"] = to
    msg.set_content(text)
    if html:
        msg.add_alternative(html, subtype="html")

    if not configured():
        print("\n" + "=" * 70 + "\n[email not sent — SMTP isn't set up in backend/.env; printing instead]\n"
              f"To: {to}\nSubject: {subject}\n\n{text}\n" + "=" * 70 + "\n", flush=True)
        return False

    host = os.environ["SMTP_HOST"]
    port = int(os.environ.get("SMTP_PORT") or 587)
    user = os.environ.get("SMTP_USER")
    password = os.environ.get("SMTP_PASSWORD")
    try:
        if port == 465:
            with smtplib.SMTP_SSL(host, port, context=ssl.create_default_context(), timeout=20) as s:
                if user:
                    s.login(user, password or "")
                s.send_message(msg)
        else:
            with smtplib.SMTP(host, port, timeout=20) as s:
                s.starttls(context=ssl.create_default_context())
                if user:
                    s.login(user, password or "")
                s.send_message(msg)
    except Exception as e:  # noqa: BLE001
        raise MailError(f"Couldn't send email: {e}") from e
    return True
