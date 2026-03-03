#!/usr/bin/env python3
"""
Local prompt flow: you provide a prompt (hardcoded or in terminal) → parse matter + doc type
→ fetch & zip → send the ZIP to your email. No inbox polling.

Usage:
  # Use hardcoded prompt (default)
  python3 run_local_prompt.py

  # Ask any question: different M number and/or document type
  python3 run_local_prompt.py --prompt "I need Exhibits from M12383"
  python3 run_local_prompt.py --prompt "Key Documents for M12205 please"

  # Interactive: keep asking different questions in one session
  python3 run_local_prompt.py --interactive

  # Optional: override recipient
  python3 run_local_prompt.py --to someone@example.com
"""
import argparse
import sys

from email_agent.config import SEND_ZIP_TO, ALLOWED_DOC_TYPES
from email_agent.parser import parse_email
from email_agent.smtp_client import send_email_with_attachment
from email_agent.compose import compose_success_body_v2 as compose_success_body

# Hardcoded prompt for "AI agent" style input (required for take-home; no real AI yet)
DEFAULT_PROMPT = "Hi Agent, Can you give me Other Documents files from M12205? Thanks!"

EXTRACTION_PROMPT_TEMPLATE = """You are an information extraction assistant.

Task: Extract the UARB matter number and requested document type from the user's message.

Rules:
- Matter number format: M followed by exactly 5 digits (example: M12205). Return it in uppercase.
- Document type must be exactly one of:
  - Exhibits
  - Key Documents
  - Other Documents
  - Transcripts
  - Recordings
- The user may write the doc type in any casing (camelCase, lowercase, etc.). You MUST output the canonical spelling above.
- If either field is missing, output null for that field.

Output:
Return ONLY a single JSON object with this shape:
{"matter": "M12345" | null, "doc_type": "<one of the 5 types>" | null}

User message:
{user_message}
"""


def _run_one(prompt: str, to_addr: str, headed: bool) -> bool:
    """Parse prompt, fetch & zip, send email. Returns True on success, False on parse error."""
    parsed, err = parse_email("", prompt)
    if err is not None:
        print(f"Parse error: {err.message}", file=sys.stderr)
        return False

    matter, doc_type = parsed.matter, parsed.doc_type
    print(f"Parsed: matter={matter}, doc_type={doc_type}")
    print("Running fetch & zip...")

    from fetch_and_zip import run as run_automation

    try:
        result = run_automation(matter, doc_type, headed=headed)
    except Exception as e:
        print(f"Automation failed: {e}", file=sys.stderr)
        return False

    subject = f"UARB documents {matter} – {doc_type}"
    body = compose_success_body(matter, doc_type, result)
    try:
        send_email_with_attachment(
            to_addr=to_addr,
            subject=subject,
            body=body,
            attachment_path=result.zip_path,
        )
    except Exception as e:
        print(f"Send email failed: {e}", file=sys.stderr)
        return False

    print(f"ZIP sent to {to_addr}: {result.zip_path}\n")
    return True


def _print_interactive_help():
    print("Ask for documents by including:")
    print("  - A matter number: M plus 5 digits (e.g. M12205, M12383)")
    print("  - A document type: one of", ", ".join(ALLOWED_DOC_TYPES))
    print("Examples: 'Exhibits from M12383'  or  'Key Documents for M12205'")
    print("Type a request and press Enter. Empty line or 'quit' to exit.\n")


def main():
    ap = argparse.ArgumentParser(description="Local prompt → fetch & zip → email ZIP")
    ap.add_argument(
        "--prompt",
        default=DEFAULT_PROMPT,
        help="Request text containing matter number (M12345) and doc type (default: hardcoded)",
    )
    ap.add_argument(
        "--to",
        default=SEND_ZIP_TO,
        help="Email address to send the ZIP to (default: UARB_SEND_ZIP_TO or your Gmail)",
    )
    ap.add_argument("--headed", action="store_true", help="Show browser window")
    ap.add_argument(
        "--interactive",
        action="store_true",
        help="Interactive mode: keep asking for requests (different M numbers / doc types) until you type quit or empty line",
    )
    ap.add_argument(
        "--show-extraction-prompt",
        action="store_true",
        help="Print the LLM extraction prompt you can use for an AI agent (for the demo).",
    )
    args = ap.parse_args()

    to_addr = args.to.strip()

    if args.show_extraction_prompt:
        prompt = (args.prompt or DEFAULT_PROMPT).strip()
        print(EXTRACTION_PROMPT_TEMPLATE.format(user_message=prompt))
        return

    if args.interactive:
        _print_interactive_help()
        while True:
            try:
                line = input("Your request> ").strip()
            except EOFError:
                break
            if not line or line.lower() in ("quit", "exit", "q"):
                print("Bye.")
                break
            _run_one(line, to_addr, args.headed)
        return

    prompt = (args.prompt or DEFAULT_PROMPT).strip()
    if not prompt:
        print("Error: prompt is empty.", file=sys.stderr)
        sys.exit(1)

    ok = _run_one(prompt, to_addr, args.headed)
    sys.exit(0 if ok else 1)


if __name__ == "__main__":
    main()
