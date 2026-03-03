#!/usr/bin/env python3
"""
Phase 3 entrypoint: run the email-triggered agent.

  Run once (process latest unread email):
    python run_email_agent.py --once

  Poll inbox every 30s (or UARB_POLL_INTERVAL_SEC):
    python run_email_agent.py --poll

Environment (optional): UARB_IMAP_*, UARB_SMTP_*, UARB_POLL_INTERVAL_SEC.
See email_agent/config.py for variable names.
"""
import argparse
import sys

from email_agent.config import IMAP_USER, IMAP_PASSWORD, SMTP_USER, SMTP_PASSWORD
from email_agent.loop import run_once, run_polling
from email_agent.config import POLL_INTERVAL_SEC


def main():
    ap = argparse.ArgumentParser(description="UARB email agent: poll inbox, fetch docs, reply with ZIP")
    ap.add_argument("--once", action="store_true", help="Process latest unread email once and exit")
    ap.add_argument("--poll", action="store_true", help="Poll IMAP every N seconds (default 30)")
    ap.add_argument("--interval", type=int, default=POLL_INTERVAL_SEC, help="Poll interval in seconds (default: %(default)s)")
    args = ap.parse_args()

    if not args.once and not args.poll:
        ap.error("Specify --once or --poll")

    if not IMAP_USER or not IMAP_PASSWORD:
        print("Error: Set UARB_IMAP_USER and UARB_IMAP_PASSWORD to poll inbox.", file=sys.stderr)
        sys.exit(1)
    if not SMTP_USER or not SMTP_PASSWORD:
        print("Error: Set UARB_SMTP_USER and UARB_SMTP_PASSWORD to send replies.", file=sys.stderr)
        sys.exit(1)

    if args.once:
        processed = run_once()
        print("Processed 1 email." if processed else "No unread email to process.")
        if processed:
            print("If you don't see a reply, check the sender inbox and Spam/All Mail.")
        sys.exit(0)

    print(f"Polling inbox every {args.interval}s. Ctrl+C to stop.")
    run_polling(interval_sec=args.interval)


if __name__ == "__main__":
    main()
