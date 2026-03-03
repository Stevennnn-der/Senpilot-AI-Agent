import re
from typing import Dict, Tuple, Union
from playwright.sync_api import Page, Frame
from .config import TAB_MAP
from . import selectors as S
from .overlay import wait_for_no_modal_curtain


def _parse_tab_count(label_text: str) -> Tuple[str, int]:
    txt = " ".join(label_text.split())
    m = re.match(r"^(.*?)\s*-\s*(\d+)\s*$", txt)
    if m:
        return m.group(1).strip(), int(m.group(2))
    return txt.strip(), 0


class MatterScraper:
    def __init__(self, scope: Union[Page, Frame]):
        """Scope is the page or frame where matter content lives (e.g. from navigator.content_scope())."""
        self.scope = scope

    def scrape_metadata(self) -> Dict[str, str]:
        md: Dict[str, str] = {}

        # Ensure any Vaadin/WebDirect modal curtain is gone so content is stable.
        try:
            wait_for_no_modal_curtain(self.scope, timeout_ms=6_000)
        except Exception:
            pass

        # Robust approach: grab visible page text and parse between known headings.
        # FileMaker WebDirect markup can reorder newlines, so "line after heading" is brittle.
        try:
            blob_raw = self.scope.locator("body").inner_text(timeout=3_000) or ""
        except Exception:
            blob_raw = ""

        md["raw_body"] = blob_raw
        md["header_text"] = " ".join(blob_raw.split())[:2000]

        def _between(start_pat: str, end_pat: str) -> str:
            m = re.search(
                rf"{start_pat}\s*(.*?)\s*{end_pat}",
                blob_raw,
                flags=re.I | re.S,
            )
            return (m.group(1) or "").strip() if m else ""

        def _clean(s: str) -> str:
            return " ".join((s or "").split()).strip()

        # Title + amount appear between "Title - Description" and "Type Category"
        title_block = _clean(_between(r"Title\s*-\s*Description", r"Type\s*Category"))
        if title_block:
            amt = re.search(r"\$\s?\d[\d,]*(?:\.\d{2})?", title_block)
            if amt:
                md["amount"] = amt.group(0).replace(" ", "")
                before = title_block[: amt.start()].strip(" -—–:\t")
                md["title"] = before[:240] if before else title_block[:240]
            else:
                md["title"] = title_block[:240]

        # Category + Type appear between "Type Category" and "Date Received"
        type_block_raw = _between(r"Type\s*Category", r"Date\s*Received")
        type_block = type_block_raw.strip()
        if type_block:
            # Prefer newline split (often in a 2-row layout), else split by 2+ spaces.
            parts = [p.strip() for p in re.split(r"[\r\n]+", type_block) if p.strip()]
            if len(parts) < 2:
                parts = [p.strip() for p in re.split(r"\s{2,}", _clean(type_block)) if p.strip()]
            if len(parts) >= 2:
                md["category"] = parts[0][:120]
                md["type"] = " ".join(parts[1:])[:120]

        # Dates: between headings
        date_received = _clean(_between(r"Date\s*Received", r"Decision\s*Date"))
        if date_received:
            md["date_received"] = date_received[:60]

        decision_date = _clean(_between(r"Decision\s*Date", r"Outcome"))
        if decision_date:
            md["date_final_submission"] = decision_date[:60]
        else:
            final_sub = _clean(_between(r"Date\s*Final\s*Submission", r"Outcome"))
            if final_sub:
                md["date_final_submission"] = final_sub[:60]

        # Outcome: between "Outcome" and the first tab anchor (or end)
        m_out = re.search(r"Outcome\s*(.*)$", blob_raw, flags=re.I | re.S)
        if m_out:
            tail = m_out.group(1) or ""
            m_end = re.search(S.ANY_TAB_ANCHOR, tail)
            outcome_txt = tail[: m_end.start()] if m_end else tail
            outcome_txt = _clean(outcome_txt)
            if outcome_txt:
                md["outcome"] = outcome_txt[:120]

        # Fallback parsing for search-results style layout where headings like
        # "Title - Description" / "Type Category" aren't present in the blob.
        if not any(md.get(k) for k in ("title", "category", "type", "date_received", "date_final_submission")):
            lines = [ln.strip() for ln in (blob_raw or "").splitlines() if ln.strip()]

            # Find the matter line (e.g., M01234) to anchor the layout.
            matter_match = re.search(r"M\d{5}", blob_raw or "")
            matter_idx = None
            if matter_match:
                matter_id = matter_match.group(0)
                for i, ln in enumerate(lines):
                    if matter_id in ln:
                        matter_idx = i
                        break

            if matter_idx is not None:
                # Expected layout after the "M01234" line (based on observed page):
                #   [matter]
                #   [category]        -> e.g. "Memo"
                #   [status]          -> e.g. "Closed"
                #   [title]
                #   [description]
                #   [date_received]
                #   [decision_date]
                #   [outcome]         -> e.g. "Dismissed/Denied"
                #   [type]            -> e.g. "Liquor"
                #   [...]

                # Category (e.g., "Memo").
                if matter_idx + 1 < len(lines) and not md.get("category"):
                    md["category"] = lines[matter_idx + 1][:120]

                # Status (e.g., "Closed").
                if matter_idx + 2 < len(lines) and not md.get("status"):
                    md["status"] = lines[matter_idx + 2][:120]

                # Title and description.
                title_start = matter_idx + 3
                if title_start < len(lines) and not md.get("title"):
                    title_line = lines[title_start]
                    desc_line = ""
                    if title_start + 1 < len(lines):
                        next_line = lines[title_start + 1]
                        # Treat the next line as description if it is not a date.
                        if not re.search(r"\d{2}/\d{2}/\d{4}", next_line):
                            desc_line = next_line
                    full_title = title_line
                    if desc_line:
                        full_title = f"{title_line} {desc_line}"
                        md.setdefault("description", desc_line[:240])
                    md["title"] = full_title[:240]

                # Dates after the title/description block.
                tail_lines = lines[title_start + 1 :]
                date_lines = [ln for ln in tail_lines if re.search(r"\d{2}/\d{2}/\d{4}", ln)]
                if date_lines and not md.get("date_received"):
                    md["date_received"] = date_lines[0][:60]
                if len(date_lines) > 1 and not md.get("date_final_submission"):
                    md["date_final_submission"] = date_lines[1][:60]

                # Outcome: first non-date, non-navigation line after the last date.
                if date_lines:
                    last_date = date_lines[-1]
                    start_idx = 0
                    for i, ln in enumerate(tail_lines):
                        if last_date in ln:
                            start_idx = i + 1
                            break
                    for ln in tail_lines[start_idx:]:
                        if "Back to Search" in ln:
                            break
                        if re.search(r"\d{2}/\d{2}/\d{4}", ln):
                            continue
                        if ln.strip():
                            md["outcome"] = ln.strip()[:120]
                            break

                # Type: take the first non-empty, non-date, non-navigation line
                # that appears after the outcome.
                if not md.get("type"):
                    after_outcome_seen = False
                    for ln in tail_lines:
                        if md.get("outcome") and md["outcome"] in ln:
                            after_outcome_seen = True
                            continue
                        if not after_outcome_seen:
                            continue
                        if "Back to Search" in ln:
                            break
                        if re.search(r"\d{2}/\d{2}/\d{4}", ln):
                            continue
                        if ln.strip():
                            md["type"] = ln.strip()[:120]
                            break

        return md

    def scrape_tab_counts(self) -> Dict[str, int]:
        counts: Dict[str, int] = {}

        try:
            wait_for_no_modal_curtain(self.scope, timeout_ms=6_000)
        except Exception:
            pass

        # 1) Try locator-based (ideal when text nodes are stable)
        found_any = False
        for tab_name in TAB_MAP.values():
            loc = self.scope.get_by_text(S.TAB_LABEL(tab_name))
            if loc.count() > 0:
                txt = loc.first.inner_text().strip()
                name, n = _parse_tab_count(txt)
                counts[name] = n
                found_any = found_any or (n > 0)
            else:
                counts[tab_name] = 0

        # 2) Fallback: parse from visible body text (more robust if frame/DOM differs)
        if not found_any:
            try:
                blob_raw = self.scope.locator("body").inner_text(timeout=3_000) or ""
            except Exception:
                blob_raw = ""
            matches = re.findall(
                r"(Exhibits|Key Documents|Other Documents|Transcripts|Recordings)\s*[-–—]\s*(\d+)",
                blob_raw,
                flags=re.I,
            )
            parsed = {k.title(): int(v) for k, v in matches}
            # Preserve canonical keys
            for k in TAB_MAP.values():
                if k in parsed:
                    counts[k] = parsed[k]

        return counts