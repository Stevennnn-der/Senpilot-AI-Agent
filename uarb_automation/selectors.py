import re

# Go Directly to Matter section
GO_DIRECT_HEADING = re.compile(r"Go Directly to Matter", re.I)
GO_DIRECT_PLACEHOLDER = re.compile(r"eg\s*M0?1234", re.I)

# Tabs look like "Other Documents - 21" or "Other Documents – 21" (en-dash)
TAB_LABEL = lambda tab_name: re.compile(
    rf"^{re.escape(tab_name)}\s*[-–—]\s*\d+\s*$", re.I
)

GO_GET_IT = re.compile(r"Go Get It", re.I)
SEARCH_BTN = re.compile(r"^Search$", re.I)

# Used to detect that matter page loaded (any tab label is fine)
ANY_TAB_ANCHOR = re.compile(
    r"(Exhibits|Key Documents|Other Documents|Transcripts|Recordings)\s*[-–]\s*\d+",
    re.I
)

DOWNLOAD_MODAL_TITLE = re.compile(r"Download Files", re.I)
DOWNLOAD_MODAL_HINT = re.compile(r"files are ready for download", re.I)
CLOSE_BTN = re.compile(r"^Close$", re.I)