import os
import re
from pathlib import Path
from typing import List, Tuple, Union
from playwright.sync_api import Page, Frame, TimeoutError as PWTimeoutError

from .config import DEFAULT_TIMEOUT_MS, DOWNLOAD_TIMEOUT_MS, MAX_DOWNLOADS, TAB_MAP
from . import selectors as S
from .overlay import wait_for_no_modal_curtain


def sanitize_filename(name: str) -> str:
    name = re.sub(r"[\\/:*?\"<>|]+", "_", name)
    name = re.sub(r"\s+", " ", name).strip()
    return name[:180] if len(name) > 180 else name


class TabDownloader:
    def __init__(self, page: Page, scope: Union[Page, Frame]):
        """
        page: used for expect_download (must be Page).
        scope: page or frame where matter content lives; use for all locators.
        """
        self.page = page
        self.scope = scope

    def click_tab(self, doc_type: str) -> str:
        tab_name = TAB_MAP.get(doc_type)
        if not tab_name:
            raise ValueError(f"Unknown doc type: {doc_type}. Valid: {list(TAB_MAP.keys())}")

        wait_for_no_modal_curtain(self.scope, timeout_ms=6_000)
        self.scope.get_by_text(S.TAB_LABEL(tab_name)).first.click()
        wait_for_no_modal_curtain(self.scope, timeout_ms=6_000)

        self.scope.get_by_text(S.GO_GET_IT).first.wait_for(timeout=DEFAULT_TIMEOUT_MS)
        return tab_name

    def _row_signature(self, btn_index: int) -> Tuple[str, str]:
        buttons = self._go_get_it_buttons()
        btn = buttons.nth(btn_index)
        row = btn.locator("xpath=ancestor::*[self::tr or self::div][1]")

        try:
            txt = row.inner_text(timeout=200)
        except Exception:
            txt = ""

        m = re.search(r"\b(\d{4,7})\b", txt)
        doc_id = m.group(1) if m else f"row{btn_index+1:02d}"
        titleish = " ".join(txt.split())[:120] if txt else doc_id
        return doc_id, titleish

    def _go_get_it_buttons(self):
        """
        IMPORTANT: avoid clicking the inner <span>. Click the actual button/container.
        """
        return self.scope.get_by_text(S.GO_GET_IT).locator(
            "xpath=ancestor-or-self::*[self::button or @role='button' or contains(@class,'fm-button') or contains(@class,'v-button')][1]"
        )

    def _wait_for_download_modal(self):
        """
        Wait for the 'Download Files' modal to appear.
        We anchor on either the title text or the hint text.
        """
        # The modal is usually a Vaadin window (v-window). We'll search broadly but reliably.
        self.scope.get_by_text(S.DOWNLOAD_MODAL_TITLE).first.wait_for(timeout=3_000)
        self.scope.get_by_text(S.DOWNLOAD_MODAL_HINT).first.wait_for(timeout=3_000)

        # Return a container-ish locator for scoping clicks
        modal = self.scope.get_by_text(S.DOWNLOAD_MODAL_TITLE).first.locator(
            "xpath=ancestor::*[contains(@class,'v-window') or contains(@class,'v-overlay')][1]"
        )
        return modal

    def _click_middle_filename_and_download(self, modal, out_dir: Path, doc_id: str) -> str:
        """
        In the modal, click the middle filename button (e.g., '67691.pdf'),
        wait for a download event, save it, return saved path.
        """
        # (1) Try clickables inside modal that contain a dot
        file_buttons = modal.locator(
            "xpath=.//*[self::button or self::a or @role='button'][contains(., '.')]"
        )
        n = file_buttons.count()
        if n > 0:
            idx = (n - 1) // 2
            file_btn = file_buttons.nth(idx)
        else:
            # (2) Looser: any element in modal containing ".pdf"
            in_modal = modal.get_by_text(".pdf")
            if in_modal.count() > 0:
                file_btn = in_modal.first
            else:
                # (3) Modal body may be in iframe: search scope for "12345.pdf"
                file_btn = self.scope.get_by_text(re.compile(r"\d+\.pdf", re.I)).first

        file_btn.wait_for(state="visible", timeout=5_000)
        file_btn.scroll_into_view_if_needed()

        # Read visible label for naming
        try:
            label = file_btn.inner_text(timeout=500).strip()
        except Exception:
            label = "download"

        with self.page.expect_download(timeout=DOWNLOAD_TIMEOUT_MS) as dl_info:
            file_btn.click(timeout=10_000, force=True)
        download = dl_info.value

        suggested = sanitize_filename(download.suggested_filename)
        stem, ext = os.path.splitext(suggested)
        if not ext:
            # if suggested filename lacks extension, try from label
            ext = ".pdf" if ".pdf" in label.lower() else ".bin"

        filename = sanitize_filename(f"{doc_id}__{stem or label}{ext}")
        dest = out_dir / filename
        download.save_as(str(dest))
        return str(dest)

    def _close_download_modal(self, modal) -> None:
        # After download the modal DOM may change; find Close at scope level (the visible one is the modal's)
        by_role = self.scope.get_by_role("button", name=S.CLOSE_BTN)
        close_btn = by_role.first if by_role.count() > 0 else self.scope.get_by_text("Close").first
        close_btn.wait_for(state="visible", timeout=5_000)
        close_btn.scroll_into_view_if_needed()
        close_btn.click(timeout=10_000, force=True)

        # Wait for modal + curtain to be gone
        try:
            modal.wait_for(state="hidden", timeout=5_000)
        except Exception:
            pass
        wait_for_no_modal_curtain(self.scope, timeout_ms=6_000)

    def download_first_n(self, matter: str, tab_name: str, download_root: Path) -> List[str]:
        out_dir = download_root / matter / tab_name
        out_dir.mkdir(parents=True, exist_ok=True)

        files: List[str] = []
        buttons = self._go_get_it_buttons()
        n = min(buttons.count(), MAX_DOWNLOADS)

        for i in range(n):
            doc_id, _ = self._row_signature(i)
            btn = buttons.nth(i)

            wait_for_no_modal_curtain(self.scope, timeout_ms=6_000)
            btn.scroll_into_view_if_needed()
            wait_for_no_modal_curtain(self.scope, timeout_ms=6_000)

            # 1) Click GO GET IT (opens modal)
            btn.click(timeout=1_000)

            # 2) Wait for modal
            modal = self._wait_for_download_modal()

            # 3) Click middle filename button to trigger real download
            saved_path = self._click_middle_filename_and_download(modal, out_dir, doc_id)
            files.append(saved_path)

            # 4) Close modal
            self._close_download_modal(modal)

        return files