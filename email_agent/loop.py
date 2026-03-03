"""
Agent loop: poll inbox (or run once), parse email, run automation, compose and send reply.
"""
import time
from typing import Optional

from .config import IMAP_USER, POLL_INTERVAL_SEC
from .imap_client import get_latest_unread, IncomingEmail
from .parser import parse_email, ParsedRequest, ParseError
from .compose import compose_success_body_v2 as compose_success_body, compose_error_body, compose_automation_error_body
from .smtp_client import send_email_with_attachment


def _extract_reply_to(incoming: IncomingEmail) -> str:
    """Prefer Reply-To, else From (strip name part if needed)."""
    addr = incoming.reply_to or incoming.from_addr
    if "<" in addr and ">" in addr:
        start = addr.index("<") + 1
        end = addr.index(">")
        return addr[start:end].strip()
    return addr.strip()


def process_one_email() -> bool:
    """
    Process at most one unread email: parse, run automation, send reply.
    Returns True if an email was processed, False if none or error.
    """
    incoming = get_latest_unread()
    if not incoming:
        return False

    reply_to_addr = _extract_reply_to(incoming)
    subject = incoming.subject or ""
    body = incoming.body or ""

    parsed, err = parse_email(subject, body)
    if err is not None:
        send_email_with_attachment(
            to_addr=reply_to_addr,
            subject=subject or "UARB request error",
            body=compose_error_body(err.message),
            attachment_path=None,
        )
        return True

    assert parsed is not None
    matter, doc_type = parsed.matter, parsed.doc_type

    # Run automation (fetch + zip)
    try:
        from fetch_and_zip import run as run_automation
        result = run_automation(matter, doc_type, headed=False)
    except Exception as e:
        send_email_with_attachment(
            to_addr=reply_to_addr,
            subject=subject or f"UARB documents {matter} – {doc_type}",
            body=compose_automation_error_body(matter, doc_type, str(e)),
            attachment_path=None,
        )
        return True

    reply_body = compose_success_body(matter, doc_type, result)
    # Use the same SMTP sending path as the local-prompt flow to avoid
    # mail-client threading quirks and keep behavior consistent.
    send_email_with_attachment(
        to_addr=reply_to_addr,
        subject=subject or f"UARB documents {matter} – {doc_type}",
        body=reply_body,
        attachment_path=result.zip_path,
    )
    return True


def run_once() -> bool:
    """Run one cycle: process latest unread email if any. Returns True if processed."""
    return process_one_email()


def run_polling(interval_sec: Optional[int] = None) -> None:
    """Poll inbox every interval_sec; run until interrupted."""
    interval = interval_sec if interval_sec is not None else POLL_INTERVAL_SEC
    while True:
        process_one_email()
        time.sleep(interval)
