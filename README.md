## UARB Document Agent

This project implements an agent that:

- Navigates the Nova Scotia Utility and Review Board (UARB) public documents site  
- Fetches up to 10 documents of a requested type for a given matter number  
- Zips the documents  
- Sends them back over email with a concise, structured summary of the matter  

The core logic is all plain Python; no external LLM is required at runtime.

---

## High‑level flow

### 1. User request

There are two entrypoints:

- **Email agent (primary / for reviewers)**  
  - User sends a natural‑language email to the agent inbox (e.g. `UARB_IMAP_USER` from `.env`) that contains:
    - A matter number like `M01234`
    - A document type: `Exhibits`, `Key Documents`, `Other Documents`, `Transcripts`, or `Recordings`
  - You run:

    ```bash
    python run_email_agent.py --once      # process latest unread email and reply
    # or
    python run_email_agent.py --poll      # keep polling every N seconds
    ```

- **Local prompt helper (dev/demo)**  
  - You invoke:

    ```bash
    python run_local_prompt.py \
      --prompt "Hi Agent, can you send me Other Documents from M01234?" \
      --to you@example.com
    ```

  - The script parses the prompt, runs the automation, and emails you directly (no IMAP).

Both flows ultimately go through the same **fetch + zip** pipeline and the same **summary** generator, so behavior is consistent.

---

## Project structure

- `fetch_and_zip.py` – orchestrates browser, navigation, scraping, downloading, and zipping
- `uarb_automation/`
  - `browser.py` – Playwright browser launcher (`BrowserFactory`)
  - `navigator.py` – open UARB site and navigate to a matter (`MatterNavigator`)
  - `scraper.py` – extract metadata and tab counts from the matter page (`MatterScraper`)
  - `downloader.py` – click “Go Get It” and download files (`TabDownloader`)
  - `zipper.py` – zip downloaded files (`Zipper`)
  - `config.py` – base URL, tab names, timeouts
  - `selectors.py` – robust regex/literals for page elements and tabs
  - `models.py` – `MatterResult` dataclass
- `email_agent/`
  - `config.py` – IMAP/SMTP config + allowed doc types
  - `imap_client.py` – fetch latest unread email
  - `smtp_client.py` – send emails (local and agent flows)
  - `parser.py` – parse natural language into `(matter, doc_type)`
  - `compose.py` – build professional email bodies and summaries
  - `loop.py` – glue: IMAP → parse → fetch & zip → SMTP
- `run_email_agent.py` – email entrypoint (phase 3)
- `run_local_prompt.py` – local prompt entrypoint (test harness)

---

## Configuration

### Python environment

Create and activate a virtualenv (or use your preferred environment manager), then install dependencies:

```bash
pip install -r requirements.txt
```

### .env

Create `.env` in the project root. An example is already present; it looks like:

```env
# IMAP (read inbox) — agent’s Gmail + app password
UARB_IMAP_HOST=imap.gmail.com
UARB_IMAP_PORT=993
UARB_IMAP_USER=your.agent@gmail.com
UARB_IMAP_PASSWORD=your-app-password
UARB_IMAP_SSL=true

# SMTP (send reply with ZIP) — same Gmail + app password
UARB_SMTP_HOST=smtp.gmail.com
UARB_SMTP_PORT=587
UARB_SMTP_USER=your.agent@gmail.com
UARB_SMTP_PASSWORD=your-app-password
UARB_SMTP_TLS=true

# Optional: poll interval in seconds (default 30)
# UARB_POLL_INTERVAL_SEC=30

# Local prompt flow (run_local_prompt.py): send ZIP to this address
# UARB_SEND_ZIP_TO=you@example.com
```

The email agent loads this file automatically via `dotenv` in `email_agent/config.py`.

---

## Running the agent

### Email‑triggered agent (`run_email_agent.py`)

This is the main entrypoint that matches the challenge spec (“a user emails your agent a matter number and document type”).

1. Ensure `.env` is configured and Playwright/browser dependencies are installed.
2. From any email account (including the agent account itself), send an email **to** `UARB_IMAP_USER` such as:

   > Hi Agent, can you send me Other Documents from M01234?

3. Process the latest unread email:

   ```bash
   python run_email_agent.py --once
   ```

   - If an unread email was processed, you’ll see:

     ```text
     Processed 1 email.
     ```

   - The reply (with ZIP + summary) is sent to the **sender** of that email (using `Reply-To` if present, otherwise `From`).

4. To keep the agent running and polling for new requests:

   ```bash
   python run_email_agent.py --poll
   # or specify a custom interval:
   python run_email_agent.py --poll --interval 60
   ```

### Local prompt flow (`run_local_prompt.py`)

This is a convenient way to test the full pipeline from your terminal without involving IMAP.

```bash
python run_local_prompt.py \
  --prompt "Hello, I want to download Other Documents for M01234 please" \
  --to you@example.com \
  --headed        # optional: show browser window for debugging
```

Flow:

1. `run_local_prompt.py` uses `email_agent.parser.parse_email` to extract `matter` and `doc_type`.
2. It calls `fetch_and_zip.run(matter, doc_type, headed)`.
3. It builds a summary email body via `email_agent.compose.compose_success_body_v2`.
4. It sends the email and ZIP attachment via `send_email_with_attachment`.

---

## Core automation flow

The heart of the system is `fetch_and_zip.run(matter: str, doc_type: str, headed: bool) -> MatterResult`.

At a high level:

```python
session = BrowserFactory.launch(headless=not headed, accept_downloads=True)
page = session.page

nav = MatterNavigator(page)
nav.goto_matter(matter)          # open site, find “Go Directly to Matter”, search, wait for content
scope = nav.content_scope()      # page or iframe containing the matter view

scraper = MatterScraper(scope)
metadata = scraper.scrape_metadata()
counts = scraper.scrape_tab_counts()

dl = TabDownloader(page, scope)
tab_name = dl.click_tab(doc_type)

download_root = Path("downloads").absolute()
download_root.mkdir(parents=True, exist_ok=True)

downloaded = dl.download_first_n(matter, tab_name, download_root)
zip_path = Zipper.zip_tab(download_root, matter, tab_name)
```

It returns a `MatterResult` with:

- `zip_path` – path to the ZIP file
- `downloaded_files` – list of downloaded paths
- `counts_per_tab` – dict of tab → document count
- `total_count` – total documents across all tabs
- `metadata` – structured metadata for the summary

This object is used identically by both the email agent and the local prompt flow.

---

## Navigation and robustness

### Browser session

`uarb_automation/browser.py`:

- Uses Playwright’s synchronous API.
- `BrowserFactory.launch(headless, accept_downloads)`:
  - Starts Playwright.
  - Launches Chromium.
  - Creates a context with `accept_downloads=True`.
  - Opens a new page and returns a `BrowserSession` dataclass with a `close()` method.

This centralizes browser lifecycle and avoids leaks.

### Matter navigation (`MatterNavigator`)

Defined in `uarb_automation/navigator.py`.

- **`open_home()`**
  - `page.goto(BASE_URL, wait_until="load")` where `BASE_URL` is `https://uarb.novascotia.ca/fmi/webd/UARB15`.
  - Waits for iframes, since FileMaker often loads the form inside an iframe.

- **`_find_matter_input_and_search(matter)`**
  - Iterates over main page and all frames, trying multiple strategies to find the “Go Directly to Matter” input:
    - Inputs with placeholder exactly `"eg M01234"` or matching `M01234` via regex.
    - Inputs whose placeholder partially matches `M0`.
    - A FileMaker widget pattern: `div.placeholder` with “eg M01234” near an `fm-textarea` containing `div.text`.
  - Once the input is found, it:
    - Brings it into view and focuses it.
    - Clears existing text via keyboard (`Control+A` + `Backspace`).
    - Types the matter number with a small delay.
    - Locates the adjacent **Search** button and clicks it.
  - Retries this process for up to 15 seconds before failing with a detailed `RuntimeError`.

- **`wait_for_matter_page(matter)`**
  - Polls all frames for the presence of either:
    - Any of the tab labels like “Exhibits - 3”, or
    - A “Download Files” modal that is only present on the matter page.
  - Uses a small JS helper to inspect the frame’s `document.body.innerText`.
  - Sets `self.content_frame` to the frame containing the matter view.
  - On timeout, captures `debug_after_search.png` and `debug_after_search.html` for debugging.

- **`content_scope()`**
  - Returns the correct Playwright `Page` or `Frame` that contains the matter content.
  - All scraper and downloader locators use this “scope” to avoid worrying about iframe details.

- **`_dismiss_download_modal_if_open()`**
  - If the “Download Files” modal is open when navigation completes, it:
    - Locates the modal by its title text.
    - Clicks the **Close** button.
    - Waits for the Vaadin modality curtain to disappear (via `wait_for_no_modal_curtain`).

---

## Scraping logic

Implemented in `uarb_automation/scraper.py` (`MatterScraper`).

### `scrape_metadata(scope) -> Dict[str, str]`

1. Ensures any Vaadin/WebDirect overlay is gone using `wait_for_no_modal_curtain`.
2. Retrieves visible text from `body`:

   ```python
   blob_raw = self.scope.locator("body").inner_text(timeout=3_000) or ""
   md["raw_body"] = blob_raw
   md["header_text"] = " ".join(blob_raw.split())[:2000]
   ```

3. **Heading‑based extraction** (for the full detail layout):

   - Between `"Title - Description"` and `"Type Category"` → `title` (+ optional `amount`).
   - Between `"Type Category"` and `"Date Received"` → `category` and `type`.
   - Between `"Date Received"` and `"Decision Date"` → `date_received`.
   - Between `"Decision Date"` / `"Date Final Submission"` and `"Outcome"` → `date_final_submission`.
   - After `"Outcome"` and up to the first tab anchor → `outcome`.

4. **Search‑results fallback** (for the “Public Documents Database” row layout):

   Using the lines around the matter number, for example:

   ```text
   M01234
   Memo
   Closed
   LM-08-057(1):  Kal Can Ltd. o/a Bogey’s Bar & Grill Lounge, Bridgewater
   Request by Bogey’s Bar & Grill Lounge to Reinstate ...
   07/18/2008
   07/18/2008
   Dismissed/Denied
   Liquor
   Back to Search Result
   ```

   the fallback logic fills:

   - `category` (`Memo`)
   - `status` (`Closed`)
   - `title` and `description`
   - `date_received` and `date_final_submission`
   - `outcome` (`Dismissed/Denied`)
   - `type` (`Liquor`)

This two‑tiered strategy makes scraping robust to both the detail view and the summary table view without relying on brittle CSS selectors.

### `scrape_tab_counts(scope) -> Dict[str, int]`

1. For each tab name in `TAB_MAP` (`Exhibits`, `Key Documents`, etc.), tries to locate a label like `"Other Documents - 1"` using a regex from `selectors.py`.
2. If that fails for all tabs, falls back to scanning the entire `body` text for:

   ```regex
   (Exhibits|Key Documents|Other Documents|Transcripts|Recordings)\s*[-–—]\s*(\d+)
   ```

3. Returns a dict mapping tab names to counts, e.g.:

   ```python
   {
       "Exhibits": 0,
       "Key Documents": 1,
       "Other Documents": 1,
       "Transcripts": 0,
       "Recordings": 0,
   }
   ```

---

## Downloading and zipping

Although the detailed implementation lives in `uarb_automation/downloader.py` and `uarb_automation/zipper.py`, the main points are:

- **`TabDownloader`**
  - Uses the same `scope` as the scraper to click on the requested tab.
  - Clicks the “Go Get It” button (or equivalent) to trigger a download.
  - Leverages Playwright’s download events to intercept files and save them to disk.
  - Enforces `MAX_DOWNLOADS` from `uarb_automation/config.py` so the agent won’t pull more than 10 files.

- **`Zipper`**
  - Gathers the downloaded files from a `downloads/<matter>/<tab>` folder.
  - Creates a ZIP named `<matter>_<TabName>.zip`.

The `MatterResult` dataclass in `uarb_automation/models.py` wraps these results for use by the email layer.

---

## Email parsing and composition

### Parsing (`email_agent/parser.py`)

Both the email agent and the local prompt flow share the same parsing logic:

- Looks for a matter number in the form `M` followed by exactly 5 digits (e.g. `M01234`, `M12205`).
- Normalizes the document type to exactly one of:
  - `Exhibits`
  - `Key Documents`
  - `Other Documents`
  - `Transcripts`
  - `Recordings`
- Returns either a `ParsedRequest(matter, doc_type)` or a `ParseError` with a human‑readable message.

### Composition (`email_agent/compose.py`)

- **`_format_metadata(metadata)`**  
  Takes the metadata dict from `MatterScraper` and constructs a concise, professional summary using:

  - `title`
  - `status`
  - `type` and `category` (“It relates to Liquor within the Memo category.”)
  - `date_received` and `date_final_submission` (formatted, e.g., “July 18, 2008”)
  - `outcome`
  - `description` (short explanation of the matter)

- **`_format_counts_sentence(counts)`**  
  Converts per‑tab counts into a natural sentence:

  > I found 1 Key Documents, 1 Other Documents, and no Exhibits, Transcripts, or Recordings.

- **`compose_success_body_v2(matter, doc_type, result)`**  
  Generates the final email body:

  ```text
  Hi User,

  M01234: LM-08-057(1):  Kal Can Ltd. o/a Bogey’s Bar & Grill Lounge, Bridgewater Request by Bogey’s Bar & Grill Lounge to Reinstate Eating Establishment Liquor License No. 001725 and Lounge License No. 004172. Status: Closed. It relates to Liquor within the Memo category. The matter had an initial filing on July 18, 2008 and a final filing on July 18, 2008. Outcome: Dismissed/Denied. Description: Request by Bogey’s Bar & Grill Lounge to Reinstate Eating Establishment Liquor License No. 001725 and Lounge License No. 004172.

  I found 1 Key Documents, 1 Other Documents, and no Exhibits, Transcripts, or Recordings. I downloaded 1 out of the 1 Other Documents and am attaching them as a ZIP here.

  Best regards,
  UARB Document Agent
  ```

- **Error bodies**
  - `compose_error_body(parse_error_message)` – for parse failures, explains what went wrong and lists allowed doc types.
  - `compose_automation_error_body(matter, doc_type, error_message)` – for automation failures (navigation/scraping/downloading), explains the error but keeps the tone user‑friendly.

---

## Email transport

`email_agent/smtp_client.py`:

- **`send_email_with_attachment(to_addr, subject, body, attachment_path=None)`**
  - Used by both:
    - `run_local_prompt.py`
    - `email_agent/loop.py` (for success + error replies)
  - Sends a plain‑text email via SMTP using the host/user/password from `.env`.
  - Optionally attaches a ZIP file.

`email_agent/imap_client.py`:

- **`get_latest_unread()`**
  - Connects to IMAP using `.env` config.
  - Selects the `INBOX`.
  - Finds the last `UNSEEN` message.
  - Extracts:
    - `subject`
    - plain‑text `body`
    - `from_addr`
    - `reply_to`
    - `message_id`
  - Returns an `IncomingEmail` dataclass or `None` if there is no unread mail.

---

## Email agent loop

`email_agent/loop.py` ties IMAP, parsing, automation, and SMTP together.

### `process_one_email() -> bool`

1. **Fetch latest unread:**  
   `incoming = get_latest_unread()`
2. **Determine reply‑to address:**  
   Prefer `Reply-To`, else `From`, stripping any display name.
3. **Parse matter + doc type:**  
   `parsed, err = parse_email(subject, body)`
   - On error, calls `send_email_with_attachment` with `compose_error_body`.
4. **Run automation:**  
   Calls `fetch_and_zip.run(matter, doc_type, headed=False)`.  
   On failure, sends `compose_automation_error_body`.
5. **Compose success reply:**  
   Uses `compose_success_body_v2` to build the email body, and sends:

   - Subject: original subject, or `UARB documents <matter> – <doc_type>`
   - Body: summary of the matter and counts
   - Attachment: generated ZIP

### `run_once()` and `run_polling()`

- `run_once()` just calls `process_one_email()` and returns whether anything was processed.
- `run_polling(interval_sec)` runs in a simple loop:

  ```python
  while True:
      process_one_email()
      time.sleep(interval)
  ```

`run_email_agent.py` wraps these with CLI flags (`--once`, `--poll`, `--interval`) and checks that IMAP/SMTP credentials are present.

---

## Notes and potential improvements

- The scraper is purposely conservative: if headings are missing, it falls back to layout‑based heuristics, but always preserves the full header text for safety.
- If UARB changes their HTML significantly, the fallback strategies provide a reasonable first line of defense before more targeted updates are needed.
- The agent currently focuses on one matter/doc‑type request per email; it could be extended to support multiple requests in one message.

This README should give you everything you need to understand how the agent works, how to run it, and where to look to adjust navigation, scraping, or email behavior.

