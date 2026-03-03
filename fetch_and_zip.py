#!/usr/bin/env python3
import argparse
from pathlib import Path

from uarb_automation.browser import BrowserFactory
from uarb_automation.navigator import MatterNavigator
from uarb_automation.scraper import MatterScraper
from uarb_automation.downloader import TabDownloader
from uarb_automation.zipper import Zipper
from uarb_automation.models import MatterResult
from uarb_automation.config import TAB_MAP


def run(matter: str, doc_type: str, headed: bool) -> MatterResult:
    if doc_type not in TAB_MAP:
        raise ValueError(f'--type must be one of: {", ".join(TAB_MAP.keys())}')

    session = BrowserFactory.launch(headless=not headed, accept_downloads=True)
    page = session.page

    try:
        nav = MatterNavigator(page)
        nav.goto_matter(matter)
        scope = nav.content_scope()

        scraper = MatterScraper(scope)
        metadata = scraper.scrape_metadata()
        counts = scraper.scrape_tab_counts()
        total = sum(counts.values())

        dl = TabDownloader(page, scope)
        tab_name = dl.click_tab(doc_type)

        download_root = Path("downloads").absolute()
        download_root.mkdir(parents=True, exist_ok=True)

        downloaded = dl.download_first_n(matter, tab_name, download_root)
        zip_path = Zipper.zip_tab(download_root, matter, tab_name)

        return MatterResult(
            zip_path=zip_path,
            downloaded_files=downloaded,
            counts_per_tab=counts,
            total_count=total,
            metadata=metadata,
        )
    finally:
        session.close()


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--matter", required=True, help="e.g., M12205")
    ap.add_argument("--type", required=True, choices=list(TAB_MAP.keys()))
    ap.add_argument("--headed", action="store_true", help="Show the browser for debugging")
    args = ap.parse_args()

    result = run(args.matter.strip(), args.type, headed=args.headed)

    print("\n=== Matter Metadata (best-effort) ===")
    for k, v in result.metadata.items():
        print(f"- {k}: {v}")

    print("\n=== Tab Counts ===")
    for tab, n in result.counts_per_tab.items():
        print(f"- {tab}: {n}")
    print(f"TOTAL: {result.total_count}")

    print("\n=== Downloaded Files ===")
    for fp in result.downloaded_files:
        print(fp)

    print(f"\nZIP: {result.zip_path}\n")


if __name__ == "__main__":
    main()