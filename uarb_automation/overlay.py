# uarb_automation/overlay.py
from typing import Union
from playwright.sync_api import Page, Frame, TimeoutError as PWTimeoutError

def wait_for_no_modal_curtain(
    page_or_frame: Union[Page, Frame], timeout_ms: int = 3_000
) -> None:
    """
    FileMaker WebDirect (Vaadin) uses a modality curtain that intercepts clicks:
      <div class="v-window-modalitycurtain"></div>

    We wait until it's gone/hidden. Pass the content frame when content is in an iframe.
    """
    curtain = page_or_frame.locator("div.v-window-modalitycurtain")
    try:
        # If it doesn't exist, this returns quickly.
        curtain.wait_for(state="hidden", timeout=timeout_ms)
    except PWTimeoutError:
        # Sometimes it stays attached but becomes non-blocking; try waiting for it to detach.
        curtain.wait_for(state="detached", timeout=timeout_ms)