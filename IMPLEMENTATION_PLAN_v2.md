# IPO Discord Monitor — Implementation Plan v2

**Created:** 2026-07-07  
**Status:** Draft — Orchestrated

---

## 1. Goal
Implement a highly robust, redundant request/fetching mechanism for the NSE IPO Monitor to reliably bypass NSE's 403 Forbidden errors (anti-bot protections) on GitHub Actions runners, within free tier resource limits.

---

## 2. Anti-Bot Bypass & Redundancy Design

NSE India uses advanced anti-bot mitigation (such as Akamai/Cloudflare) that inspects both the IP address and the client's TLS/JA3 fingerprint. Since standard GitHub Actions runner IPs belong to cloud ranges (Microsoft Azure), they are frequently flagged. Additionally, the standard Python `requests` TLS signature is easily blocked.

To achieve maximum reliability, we implement a **dual-strategy (Primary + Fallback)** fetching mechanism.

### Strategy A: Primary Fetcher — `curl_cffi` (TLS/JA3 Impersonation)
- **Concept**: `curl_cffi` is a Python binding for `curl-impersonate`. It compiles curl with custom TLS engines to mimic the TLS/JA3 fingerprint of real browsers (like Chrome, Firefox, Safari).
- **Why**: It is lightweight, fast, has zero browser binary overhead, and completely bypasses TLS-fingerprint-based blocks.
- **Integration**: We will replace or wrap the standard `requests.Session` in `nse_client.py` using `curl_cffi.requests.Session(impersonate="chrome")`.

### Strategy B: Fallback Fetcher — `playwright` (Headless Browser)
- **Concept**: If `curl_cffi` gets blocked or fails, we fallback to a headless Chromium browser managed by `playwright`.
- **Why**: It uses a real browser engine (Chromium), which runs Javascript, passes browser integrity checks, and obtains authentic cookies/headers.
- **Optimization**: To keep GitHub Actions runner execution times and storage within free tier limits, we will install only the Chromium browser binary and cache it using `actions/cache`.
- **Method**: The Playwright fallback will launch a headless browser, navigate to the NSE India main page to acquire cookies and headers, and then either fetch the API directly within the page context (`page.evaluate`) or transfer cookies back to execute the API call, ensuring it succeeds.

---

## 3. Implementation Details

### A. Dependency Updates (`requirements.txt`)
We will add:
```
curl_cffi>=0.7.0
playwright>=1.40.0
```

### B. NSEClient Refactoring (`nse_client.py`)
1. **Redundant Client Modes**:
   - `mode = "curl_cffi"` (Primary)
   - `mode = "playwright"` (Fallback)
2. **Session Lifecycle**:
   - Create `_initialize_curl_cffi_session() -> bool`
   - Create `_initialize_playwright_session() -> bool`
3. **Robust Fetching Wrapper**:
   - Refactor `_request_with_retry(self, url, params)`:
     - Attempt request using `curl_cffi` session.
     - If blocked (403/401) or request errors out, catch exception, log the issue, and switch mode to `"playwright"`.
     - Initialize Playwright session and fetch the requested resource.
     - Fallback mode persists for the rest of the execution to prevent repeatedly booting browsers.
4. **Playwright Fetching Mechanism**:
   - Launch headless Chromium.
   - Navigate to `https://www.nseindia.com`.
   - Execute the API request inside the page using `page.evaluate(...)` or page API request context, which guarantees headers and cookies match the browser session.
   - Close browser on cleanup.

### C. GitHub Actions Workflow Updates (`.github/workflows/ipo_monitor.yml`)
Modify the steps to:
1. Cache Playwright browser binaries to speed up workflow execution and save storage.
2. Install Playwright system dependencies and Chromium:
   ```bash
   pip install -r requirements.txt
   playwright install chromium --with-deps
   ```

---

## 4. Integration & Backward Compatibility

- **No Breaking Changes**: The public API of `NSEClient` will remain identical. All extraction helpers (`extract_symbol`, `extract_price_band`, etc.) and public fetch methods (`get_current_issues`, `get_ipo_detail`, `get_past_issues`) will behave exactly the same.
- **State Integrity**: State management in `state_manager.py` and state representation in `state.json` will not be altered.
- **Discord Alerts**: Error alerts are preserved. If both primary and fallback fetchers fail, the script will raise an error and notify Discord as before.

---

## 5. Verification Plan

The Worker and Reviewers must verify:
1. **Dry-run Execution**: Running `python ipo_monitor.py --dry-run --verbose` works without returning 403.
2. **Consecutive Runs**: Run the script 3 times consecutively to verify cookie freshness and session renewal.
3. **Primary-to-Fallback Transition**: Force a failure in the primary fetcher (e.g. by setting an invalid User-Agent or simulating a 403 response) and verify the client seamlessly falls back to Playwright and successfully retrieves data.
4. **GitHub Actions execution**: Verify that the updated workflow file installs dependencies properly and runs successfully.
