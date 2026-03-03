"""Compose reply email body (success and error)."""
import re
from datetime import datetime
from typing import Dict, TYPE_CHECKING, Optional

from .config import ALLOWED_DOC_TYPES

if TYPE_CHECKING:
    from uarb_automation.models import MatterResult


def _format_date_best_effort(s: str) -> str:
    """
    Convert common UARB date formats to "Month D, YYYY" (e.g. 04/07/2025 -> April 7, 2025).
    If parsing fails, return original.
    """
    raw = (s or "").strip()
    if not raw:
        return ""
    # Try numeric month/day/year
    for fmt in ("%m/%d/%Y", "%m/%d/%y", "%m-%d-%Y", "%m-%d-%y"):
        try:
            dt = datetime.strptime(raw, fmt)
            return dt.strftime("%B %-d, %Y")  # macOS supports %-d
        except Exception:
            continue
    return raw


def _format_metadata(metadata: Dict[str, str]) -> str:
    """Turn metadata dict into a short, professional summary (best-effort)."""
    if not metadata:
        return "I couldn't extract detailed metadata for this matter."
    parts: list[str] = []

    title = (metadata.get("title") or "").strip()
    amount = (metadata.get("amount") or "").strip()
    if title and amount:
        parts.append(f"{title} - {amount}.")
    elif title:
        parts.append(f"{title}.")

    status = (metadata.get("status") or "").strip()
    type_ = (metadata.get("type") or "").strip()
    category = (metadata.get("category") or "").strip()
    if status:
        parts.append(f"Status: {status}.")

    if type_ and category:
        parts.append(f"It relates to {type_} within the {category} category.")
    elif category:
        parts.append(f"Category: {category}.")
    elif type_:
        parts.append(f"Type: {type_}.")

    dr = (metadata.get("date_received") or "").strip()
    dfs = (metadata.get("date_final_submission") or "").strip()
    if dr and dfs:
        dr_f = _format_date_best_effort(dr)
        dfs_f = _format_date_best_effort(dfs)
        parts.append(f"The matter had an initial filing on {dr_f} and a final filing on {dfs_f}.")
    elif dr:
        parts.append(f"Date received: {_format_date_best_effort(dr)}.")
    elif dfs:
        parts.append(f"Final submission: {_format_date_best_effort(dfs)}.")

    outcome = (metadata.get("outcome") or "").strip()
    if outcome:
        parts.append(f"Outcome: {outcome}.")

    description = (metadata.get("description") or "").strip()
    if description:
        parts.append(f"Description: {description}.")

    # Fallback: if nothing structured, use a trimmed header blob.
    if not parts:
        blob = (metadata.get("header_text") or "").strip()
        blob = re.sub(r"\s+", " ", blob)
        if len(blob) > 220:
            blob = blob[:217] + "..."
        return blob or "No structured metadata available."

    return " ".join(parts)


def _plural(n: int, singular: str, plural: Optional[str] = None) -> str:
    if n == 1:
        return singular
    return plural or (singular + "s")


def _format_counts_sentence(counts: Dict[str, int]) -> str:
    """
    Format counts sentence like:
    "I found 13 Exhibits, 5 Key Documents, 21 Other Documents, and no Transcripts or Recordings."
    """
    order = ["Exhibits", "Key Documents", "Other Documents", "Transcripts", "Recordings"]
    normalized: Dict[str, int] = {k: int(v) for k, v in (counts or {}).items()}
    for k in order:
        normalized.setdefault(k, 0)

    nonzero = [(k, normalized[k]) for k in order if normalized[k] > 0]
    zero = [k for k in order if normalized[k] == 0]

    parts: list[str] = []
    for k, n in nonzero:
        parts.append(f"{n} {k}")

    if zero:
        # "no Transcripts or Recordings" / "no Exhibits" etc.
        if len(zero) == 1:
            zero_phrase = f"no {zero[0]}"
        elif len(zero) == 2:
            zero_phrase = f"no {zero[0]} or {zero[1]}"
        else:
            zero_phrase = "no " + ", ".join(zero[:-1]) + f", or {zero[-1]}"
        parts.append(zero_phrase)

    if not parts:
        return "I couldn't determine file counts for this matter."

    if len(parts) == 1:
        return f"I found {parts[0]}."
    if len(parts) == 2:
        return f"I found {parts[0]} and {parts[1]}."
    return f"I found {', '.join(parts[:-1])}, and {parts[-1]}."


def compose_success_body(
    matter: str,
    doc_type: str,
    result: "MatterResult",
) -> str:
    """
    Compose the reply body for a successful run.
    Includes: matter summary, total file count, counts per tab, downloaded X of Y, zip attached.
    """
    counts = result.counts_per_tab
    downloaded = len(result.downloaded_files)
    # Available for the requested tab (display name might be same as doc_type)
    available_for_tab = int(counts.get(doc_type, 0)) if counts else 0

    md = result.metadata or {}

    # Prefer full body text for robust parsing; fallback to header_text.
    body_text = (md.get("raw_body") or md.get("header_text") or "").strip()
    lines = [ln.strip() for ln in body_text.splitlines() if ln.strip()]

    # Title and amount: line containing a dollar value.
    title = ""
    amount = ""
    for ln in lines:
        if "$" in ln:
            m = re.search(r"(.+?)\\s*-\\s*(\\$\\d[\\d,]*(?:\\.\\d{2})?)", ln)
            if m:
                title = m.group(1).strip()
                amount = m.group(2).strip()
            else:
                title = ln.strip()
            break

    # Dates: first two MM/DD/YYYY occurrences anywhere in the body.
    date_matches = re.findall(r"\\b\\d{2}/\\d{2}/\\d{4}\\b", body_text)
    dr = _format_date_best_effort(date_matches[0]) if len(date_matches) >= 1 else ""
    dfs = _format_date_best_effort(date_matches[1]) if len(date_matches) >= 2 else ""

    # Category: first short line without digits after the last date, before "Back to Search Results".
    category = ""
    if date_matches:
        last_date = date_matches[-1]
        # Find index of line containing the last date.
        last_idx = 0
        for i, ln in enumerate(lines):
            if last_date in ln:
                last_idx = i
        for ln in lines[last_idx + 1 :]:
            if "Back to Search Results" in ln:
                break
            if any(ch.isdigit() for ch in ln):
                continue
            if len(ln) > 40:
                continue
            category = ln.strip()
            break

    # Type: first non-empty, non-status line after the matter number that isn't the title.
    type_ = ""
    matter_idx = None
    for i, ln in enumerate(lines):
        if matter in ln:
            matter_idx = i
            break
    if matter_idx is not None:
        for ln in lines[matter_idx + 1 :]:
            if "Awaiting" in ln or "Back to Search" in ln or "$" in ln:
                continue
            if re.search(r"\\b\\d{2}/\\d{2}/\\d{4}\\b", ln):
                continue
            if not ln.strip():
                continue
            type_ = ln.strip()
            # Trim trailing "Approvals" if present (e.g., "Capital Expenditure Approvals")
            type_ = re.sub(r"\bApprovals\b", "", type_).strip(" -—,\t")
            break

    pieces: list[str] = ["Hi User,"]

    # Sentence 1: "<matter> is about <title> - <amount>."
    if title and amount:
        pieces.append(f"{matter} is about the {title} - {amount}.")
    elif title:
        pieces.append(f"{matter} is about the {title}.")
    else:
        pieces.append(f"{matter} is about this matter.")

    # Sentence 2: "It relates to <type> within the <category> category."
    if type_ and category:
        pieces.append(f"It relates to {type_} within the {category} category.")

    # Sentence 3: initial/final filing sentence
    if dr and dfs:
        pieces.append(f"The matter had an initial filing on {dr} and a final filing on {dfs}.")

    # Sentence 4: counts sentence
    pieces.append(_format_counts_sentence(counts or {}))

    # Sentence 5: download sentence (avoid "out of 0")
    if available_for_tab > 0:
        pieces.append(
            f"I downloaded {downloaded} out of the {available_for_tab} {doc_type} and am attaching them as a ZIP here."
        )
    elif downloaded > 0:
        pieces.append(
            f"I downloaded {downloaded} {_plural(downloaded, 'file')} from {doc_type} and am attaching them as a ZIP here."
        )
    else:
        pieces.append("I am attaching a ZIP here.")

    return " ".join(pieces)


def compose_error_body(parse_error_message: str) -> str:
    """Compose reply body for parse failure; include allowed doc types."""
    lines = [
        "Hi,",
        "",
        parse_error_message,
        "",
        f"Allowed document types: {', '.join(ALLOWED_DOC_TYPES)}.",
        "",
        "Best regards,",
        "UARB Document Agent",
    ]
    return "\n".join(lines)


def compose_automation_error_body(matter: str, doc_type: str, error_message: str) -> str:
    """Compose reply when automation (fetch/zip) failed."""
    lines = [
        "Hi,",
        "",
        f"I received your request for {doc_type} from matter {matter}, but something went wrong while fetching or zipping the documents:",
        "",
        error_message,
        "",
        "Please try again later or contact support if the issue persists.",
        "",
        "Best regards,",
        "UARB Document Agent",
    ]
    return "\n".join(lines)


def compose_success_body_v2(
    matter: str,
    doc_type: str,
    result: "MatterResult",
) -> str:
    """
    Alternative success body that relies directly on structured metadata from the scraper,
    instead of re-parsing the raw page text.
    """
    counts = result.counts_per_tab
    downloaded = len(result.downloaded_files)
    available_for_tab = int((counts or {}).get(doc_type, 0))

    md = result.metadata or {}

    lines: list[str] = []
    lines.append("Hi User,")
    lines.append("")

    # Matter summary paragraph
    summary = _format_metadata(md)
    if summary and matter not in summary:
        lines.append(f"{matter}: {summary}")
    else:
        lines.append(summary or f"{matter} is about this matter.")

    lines.append("")

    # Documents paragraph
    lines.append(_format_counts_sentence(counts or {}))

    if available_for_tab > 0:
        lines.append(
            f"I downloaded {downloaded} out of the {available_for_tab} {doc_type} and am attaching them as a ZIP here."
        )
    elif downloaded > 0:
        lines.append(
            f"I downloaded {downloaded} {_plural(downloaded, 'file')} from {doc_type} and am attaching them as a ZIP here."
        )
    else:
        lines.append("I am attaching a ZIP here.")

    lines.append("")
    lines.append("Best regards,")
    lines.append("UARB Document Agent")

    return "\n".join(lines)
