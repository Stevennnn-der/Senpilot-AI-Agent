"""Email agent configuration (IMAP/SMTP and doc types)."""
import os
from pathlib import Path
from typing import List

# Load .env from project root if present (for local testing)
try:
    from dotenv import load_dotenv
    root = Path(__file__).resolve().parent.parent
    load_dotenv(root / ".env")
except ImportError:
    pass

from uarb_automation.config import TAB_MAP

# Doc types allowed in requests (keys of TAB_MAP)
ALLOWED_DOC_TYPES: List[str] = list(TAB_MAP.keys())

# IMAP (inbox)
IMAP_HOST = os.environ.get("UARB_IMAP_HOST", "imap.gmail.com")
IMAP_PORT = int(os.environ.get("UARB_IMAP_PORT", "993"))
IMAP_USER = os.environ.get("UARB_IMAP_USER", "")
IMAP_PASSWORD = os.environ.get("UARB_IMAP_PASSWORD", "")
IMAP_USE_SSL = os.environ.get("UARB_IMAP_SSL", "true").lower() in ("1", "true", "yes")

# SMTP (send reply)
SMTP_HOST = os.environ.get("UARB_SMTP_HOST", "smtp.gmail.com")
SMTP_PORT = int(os.environ.get("UARB_SMTP_PORT", "587"))
SMTP_USER = os.environ.get("UARB_SMTP_USER", "")
SMTP_PASSWORD = os.environ.get("UARB_SMTP_PASSWORD", "")
SMTP_USE_TLS = os.environ.get("UARB_SMTP_TLS", "true").lower() in ("1", "true", "yes")

# Polling
POLL_INTERVAL_SEC = int(os.environ.get("UARB_POLL_INTERVAL_SEC", "30"))

# Local prompt flow: send ZIP to this address (no inbox polling)
SEND_ZIP_TO = os.environ.get("UARB_SEND_ZIP_TO", "s012820041010@gmail.com")
