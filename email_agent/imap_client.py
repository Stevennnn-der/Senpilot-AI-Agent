"""IMAP client to fetch the latest unread email."""
import imaplib
from email import message_from_bytes
from email.message import Message
from email.header import decode_header
from dataclasses import dataclass
from typing import Optional

from .config import IMAP_HOST, IMAP_PORT, IMAP_USER, IMAP_PASSWORD, IMAP_USE_SSL


@dataclass
class IncomingEmail:
    """A single incoming email (subject + plain body)."""
    message_id: str
    subject: str
    body: str
    from_addr: str
    reply_to: Optional[str] = None


def _decode_payload(part: Message) -> str:
    """Decode text payload; handle charset."""
    payload = part.get_payload(decode=True)
    if payload is None:
        return ""
    charset = part.get_content_charset() or "utf-8"
    try:
        return payload.decode(charset, errors="replace")
    except Exception:
        return payload.decode("utf-8", errors="replace")


def _get_text_body(msg: Message) -> str:
    """Extract plain text body from message."""
    if msg.is_multipart():
        for part in msg.walk():
            if part.get_content_type() == "text/plain":
                return _decode_payload(part)
        for part in msg.walk():
            if part.get_content_type() == "text/html":
                return _decode_payload(part)  # fallback
        return ""
    return _decode_payload(msg)


def get_latest_unread() -> Optional[IncomingEmail]:
    """
    Connect via IMAP, fetch the latest unread email from INBOX.
    Returns None if no unread or connection/config error.
    """
    if not IMAP_USER or not IMAP_PASSWORD:
        return None

    try:
        if IMAP_USE_SSL:
            conn = imaplib.IMAP4_SSL(IMAP_HOST, IMAP_PORT)
        else:
            conn = imaplib.IMAP4(IMAP_HOST, IMAP_PORT)
        conn.login(IMAP_USER, IMAP_PASSWORD)
        conn.select("INBOX", readonly=False)

        _, numbers = conn.search(None, "UNSEEN")
        num_list = numbers[0].split()
        if not num_list:
            conn.close()
            conn.logout()
            return None

        # Latest is last in list
        latest_id = num_list[-1]
        _, data = conn.fetch(latest_id, "(RFC822)")
        if not data or not data[0]:
            conn.close()
            conn.logout()
            return None

        raw = data[0][1]
        msg = message_from_bytes(raw)
        subject = msg.get("Subject", "")
        if isinstance(subject, bytes):
            subject = subject.decode("utf-8", errors="replace")
        elif isinstance(subject, str) and subject.startswith("=?"):
            # Decode MIME encoded-word
            decoded = decode_header(subject)
            parts = []
            for s, enc in decoded:
                if isinstance(s, bytes):
                    parts.append(s.decode(enc or "utf-8", errors="replace"))
                else:
                    parts.append(s)
            subject = " ".join(parts)

        body = _get_text_body(msg)
        from_addr = msg.get("From", "")
        reply_to = msg.get("Reply-To") or from_addr
        message_id = msg.get("Message-ID", "")

        conn.close()
        conn.logout()
        return IncomingEmail(
            message_id=message_id,
            subject=subject,
            body=body,
            from_addr=from_addr,
            reply_to=reply_to,
        )
    except Exception as e:
        # Fail quietly for the agent, but leave a breadcrumb in stdout/stderr for debugging.
        try:
            print(f"IMAP error while fetching unread mail: {e}")
        except Exception:
            pass
        return None


def mark_as_read(message_id: Optional[str]) -> None:
    """Optional: mark the email as read so we don't process again. Not used if we run once."""
    # Could be implemented with IMAP STORE FLAGS \Seen
    pass
