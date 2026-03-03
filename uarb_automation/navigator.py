# uarb_automation/navigator.py
from __future__ import annotations

import re
import time
from typing import Union
from playwright.sync_api import Page, Frame
from .config import BASE_URL
from . import selectors as S
from .overlay import wait_for_no_modal_curtain

# JS to check if this document has the matter *detail* page content (tabs visible),
# or the "Download Files" modal (only shown on matter page; avoids timeout when modal is open).
_MATTER_PAGE_CHECK_JS = """(matter) => {
    const body = document.body?.innerText || "";
    const tabRe = /(Exhibits|Key Documents|Other Documents|Transcripts|Recordings)\\s*[-–—]?\\s*\\d+/i;
    const hasTabs = tabRe.test(body);
    const hasDownloadModal = /Download Files/i.test(body) || /files are ready for download/i.test(body);
    return hasTabs || hasDownloadModal;
}"""


class MatterNavigator:
    def __init__(self, page: Page):
        self.page = page
        # After goto_matter: the frame where matter content lives (None = main frame).
        self.content_frame: Frame | None = None

    def content_scope(self) -> Union[Page, Frame]:
        """Return the page or frame where matter content lives; use this for locators."""
        return self.content_frame if self.content_frame is not None else self.page

    def open_home(self) -> None:
        self.page.goto(BASE_URL, wait_until="load")
        # FileMaker often loads the form in an iframe; wait for it then for content
        try:
            self.page.wait_for_selector("iframe", timeout=10_000)
            time.sleep(2)
        except Exception:
            pass

    def _find_matter_input_and_search(self, matter: str) -> None:
        """
        Find the 'Go Directly to Matter' input (main page or iframe), type the matter number,
        then click the Search button next to it. Polls for up to 15s for the form to appear.
        """
        deadline = time.monotonic() + 15
        last_err = None

        while time.monotonic() < deadline:
            scopes_to_try: list = [self.page]
            for frame in self.page.frames:
                if frame != self.page.main_frame:
                    scopes_to_try.append(frame)

            for scope in scopes_to_try:
                try:
                    # (1) Standard input with placeholder (exact or partial)
                    inp_loc = scope.get_by_placeholder("eg M01234")
                    if inp_loc.count() == 0:
                        inp_loc = scope.get_by_placeholder(re.compile(r"M01234", re.I))
                    if inp_loc.count() == 0:
                        # (2) Any input in "Go Directly to Matter" area
                        inp_loc = scope.locator("input[placeholder*='M01234'], input[placeholder*='M0']")
                    if inp_loc.count() == 0:
                        # (3) FileMaker widget: div.placeholder + fm-textarea > div.text
                        placeholder_loc = scope.locator("div.placeholder", has_text=re.compile(r"eg.*M0?1234", re.I))
                        if placeholder_loc.count() == 0:
                            continue
                        widget = placeholder_loc.first.locator(
                            "xpath=ancestor::div[contains(@class,'fm-textarea')][1]"
                        )
                        inp_loc = widget.locator("div.text")
                        if inp_loc.count() == 0:
                            continue

                    inp = inp_loc.first
                    inp.wait_for(state="visible", timeout=3_000)
                    inp.scroll_into_view_if_needed()
                    inp.click(force=True)
                    time.sleep(0.2)
                
                    self.page.keyboard.press("Control+A")
                    self.page.keyboard.press("Backspace")
                    self.page.keyboard.type(matter, delay=50)
                    time.sleep(0.3)

                    search_btn = inp.locator("xpath=following::button[normalize-space()='Search'][1]")
                    search_btn.wait_for(state="visible", timeout=3_000)
                    search_btn.click()
                    return
                except Exception as e:
                    last_err = e
                    continue
            time.sleep(0.5)

        raise RuntimeError(
            "Could not find the Matter Number input in any frame within 15s. "
            "Check that the page and any iframe loaded. Last error: %s" % (last_err,)
        ) from last_err

    def goto_matter(self, matter: str) -> None:
        self.content_frame = None
        matter = matter.strip().upper()
        self.open_home()

        self._find_matter_input_and_search(matter)

        self.wait_for_matter_page(matter)
        self._dismiss_download_modal_if_open()

    def _dismiss_download_modal_if_open(self) -> None:
        """If the 'Download Files' modal is open (e.g. left over), close it so the page is usable."""
        scope = self.content_scope()
        try:
            title = scope.get_by_text(S.DOWNLOAD_MODAL_TITLE).first
            title.wait_for(timeout=300)
            modal = title.locator(
                "xpath=ancestor::*[contains(@class,'v-window') or contains(@class,'v-overlay')][1]"
            )
            close_btn = modal.get_by_role("button", name=S.CLOSE_BTN).first
            close_btn.click(timeout=500)
            wait_for_no_modal_curtain(scope, timeout_ms=1_500)
        except Exception:
            pass  # No modal or already closed

    def wait_for_matter_page(self, matter: str) -> None:
        """
        WebDirect often doesn't do a real navigation and may load content in an iframe.
        Poll all frames (main + children) for tab label or matter id; store the frame
        that has the content so callers can scope locators to it.
        """
        timeout_ms = 6_000
        deadline = time.monotonic() + (timeout_ms / 1000.0)
        last_exc = None

        while time.monotonic() < deadline:
            for frame in self.page.frames:
                try:
                    if frame.evaluate(_MATTER_PAGE_CHECK_JS, matter):
                        # Content is in this frame; use it for subsequent locators
                        self.content_frame = frame if frame != self.page.main_frame else None
                        return
                except Exception as e:
                    last_exc = e
                    continue
            time.sleep(0.5)

        # Debug artifacts before raising
        self.page.screenshot(path="debug_after_search.png", full_page=True)
        with open("debug_after_search.html", "w", encoding="utf-8") as f:
            f.write(self.page.content())
        raise TimeoutError(
            "Matter page did not appear in any frame within 6s. "
            "See debug_after_search.png and debug_after_search.html"
        ) from last_exc