"""Parse matter number and document type from email subject/body."""
import re
from dataclasses import dataclass
from typing import Optional, Tuple

from .config import ALLOWED_DOC_TYPES

# Phase 3: matter number regex
MATTER_NUMBER_RE = re.compile(r"\bM\d{5}\b", re.IGNORECASE)

_ALNUM_RE = re.compile(r"[^a-z0-9]+", re.IGNORECASE)


@dataclass
class ParsedRequest:
    """Result of successful parsing."""
    matter: str
    doc_type: str


@dataclass
class ParseError:
    """Result when parsing fails."""
    message: str


def _normalize_matter(raw: str) -> str:
    return raw.strip().upper()

def _normalize_doc_type_for_match(s: str) -> str:
    """
    Normalize doc-type-ish strings for matching.
    - lowercases
    - removes non-alphanumerics
    - strips a trailing 's' to allow singular/plural
    """
    compact = _ALNUM_RE.sub("", (s or "").strip().lower())
    return compact[:-1] if compact.endswith("s") else compact


def _match_doc_type(text: str) -> Optional[str]:
    """Match document type case-insensitively against allowed set."""
    text_lower = text.strip().lower()
    for allowed in ALLOWED_DOC_TYPES:
        if allowed.lower() == text_lower:
            return allowed
    # Substring match: e.g. "other documents" in body
    for allowed in ALLOWED_DOC_TYPES:
        if allowed.lower() in text_lower or text_lower in allowed.lower():
            return allowed
    return None


def _find_doc_type_in_text(text: str) -> Optional[str]:
    """Find first mention of an allowed doc type in text."""
    if not text:
        return None
    text_lower = text.lower()

    # (1) Direct substring match on canonical labels
    for allowed in ALLOWED_DOC_TYPES:
        if allowed.lower() in text_lower:
            return allowed

    # (2) Match normalized versions to catch variants like "OtherDocuments", "keydocuments", etc.
    normalized_text = _normalize_doc_type_for_match(text_lower)
    for allowed in ALLOWED_DOC_TYPES:
        if _normalize_doc_type_for_match(allowed) in normalized_text:
            return allowed

    return None


def parse_email(subject: str, body: str) -> Tuple[Optional[ParsedRequest], Optional[ParseError]]:
    """
    Parse subject and body for matter number (M12345) and document type.
    Returns (ParsedRequest, None) on success, (None, ParseError) on failure.
    """
    combined = f"{subject or ''}\n{body or ''}"
    matter_match = MATTER_NUMBER_RE.search(combined)
    if not matter_match:
        return None, ParseError(
            "I couldn't find a matter number in your email. "
            "Please include one in the format M12345 (e.g. M12205)."
        )

    matter = _normalize_matter(matter_match.group(0))
    doc_type = _find_doc_type_in_text(combined)

    if not doc_type:
        return None, ParseError(
            "I couldn't identify which document type you want. "
            f"Allowed types are: {', '.join(ALLOWED_DOC_TYPES)}. "
            "Please mention one of them (e.g. 'Other Documents', 'Exhibits')."
        )

    return ParsedRequest(matter=matter, doc_type=doc_type), None
