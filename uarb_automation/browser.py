from dataclasses import dataclass
from playwright.sync_api import Browser, BrowserContext, Page, sync_playwright


@dataclass
class BrowserSession:
    playwright: object
    browser: Browser
    context: BrowserContext
    page: Page

    def close(self):
        try:
            self.context.close()
        finally:
            self.browser.close()
            self.playwright.stop()


class BrowserFactory:
    @staticmethod
    def launch(headless: bool, accept_downloads: bool = True) -> BrowserSession:
        p = sync_playwright().start()
        browser = p.chromium.launch(headless=headless)
        context = browser.new_context(accept_downloads=accept_downloads)
        page = context.new_page()
        return BrowserSession(playwright=p, browser=browser, context=context, page=page)