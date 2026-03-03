"""SMTP client to send reply with optional ZIP attachment."""
import os
import smtplib
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from email.mime.base import MIMEBase
from email import encoders
from pathlib import Path
from typing import Optional

from .config import SMTP_HOST, SMTP_PORT, SMTP_USER, SMTP_PASSWORD, SMTP_USE_TLS

REPLY_SUBJECT_PREFIX = "Re: "


def send_email_with_attachment(
    to_addr: str,
    subject: str,
    body: str,
    attachment_path: Optional[str] = None,
) -> None:
    """
    Send an email (no "Re:" prefix). Use for local-prompt flow: prompt → fetch & zip → send ZIP.
    """
    if not SMTP_USER or not SMTP_PASSWORD:
        raise RuntimeError("UARB_SMTP_USER and UARB_SMTP_PASSWORD must be set.")

    msg = MIMEMultipart()
    msg["From"] = SMTP_USER
    msg["To"] = to_addr
    msg["Subject"] = subject
    msg.attach(MIMEText(body, "plain", "utf-8"))

    if attachment_path and os.path.isfile(attachment_path):
        path = Path(attachment_path)
        with open(attachment_path, "rb") as f:
            part = MIMEBase("application", "zip")
            part.set_payload(f.read())
        encoders.encode_base64(part)
        part.add_header(
            "Content-Disposition",
            "attachment",
            filename=path.name,
        )
        msg.attach(part)

    with smtplib.SMTP(SMTP_HOST, SMTP_PORT) as server:
        if SMTP_USE_TLS:
            server.starttls()
        server.login(SMTP_USER, SMTP_PASSWORD)
        server.sendmail(SMTP_USER, [to_addr], msg.as_string())


def send_reply(
    to_addr: str,
    subject: str,
    body: str,
    attachment_path: Optional[str] = None,
    in_reply_to: Optional[str] = None,
    references: Optional[str] = None,
) -> None:
    """
    Send an email reply. If attachment_path is set, attach that file (e.g. ZIP).
    to_addr: recipient (e.g. from_addr or reply_to of incoming email).
    """
    if not SMTP_USER or not SMTP_PASSWORD:
        raise RuntimeError("UARB_SMTP_USER and UARB_SMTP_PASSWORD must be set to send replies.")

    msg = MIMEMultipart()
    msg["From"] = SMTP_USER
    msg["To"] = to_addr
    if not subject.strip().startswith(REPLY_SUBJECT_PREFIX):
        subject = REPLY_SUBJECT_PREFIX + subject
    msg["Subject"] = subject
    if in_reply_to:
        msg["In-Reply-To"] = in_reply_to
    if references:
        msg["References"] = references

    msg.attach(MIMEText(body, "plain", "utf-8"))

    if attachment_path and os.path.isfile(attachment_path):
        path = Path(attachment_path)
        with open(attachment_path, "rb") as f:
            part = MIMEBase("application", "zip")
            part.set_payload(f.read())
        encoders.encode_base64(part)
        part.add_header(
            "Content-Disposition",
            "attachment",
            filename=path.name,
        )
        msg.attach(part)

    with smtplib.SMTP(SMTP_HOST, SMTP_PORT) as server:
        if SMTP_USE_TLS:
            server.starttls()
        server.login(SMTP_USER, SMTP_PASSWORD)
        server.sendmail(SMTP_USER, [to_addr], msg.as_string())
