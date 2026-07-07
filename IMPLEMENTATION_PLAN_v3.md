# IPO Discord Monitor — Implementation Plan v3

**Created:** 2026-07-07  
**Status:** Draft — Worker 2 Fixes

---

## 1. Goals
This plan targets two specific issues in `nse_client.py`:
1. **Startup Import Crash**: Import `curl_cffi` and `playwright.sync_api` safely within `try-except` blocks. Gracefully handle situations where they are missing by logging appropriate errors and raising `NSEClientError` (or returning `False` during session initialization).
2. **Transition Loop Bug in `_request_with_retry`**: Remove `continue` statements when switching `self.mode = "playwright"` to allow falling through to the playwright fetch block immediately in the same iteration of the retry loop.

---

## 2. Plan Details

### A. Safe Imports at the Top of `nse_client.py`
Replace:
```python
from curl_cffi import requests as curl_requests
from playwright.sync_api import sync_playwright
```
with:
```python
try:
    from curl_cffi import requests as curl_requests
except ImportError:
    curl_requests = None

try:
    from playwright.sync_api import sync_playwright
except ImportError:
    sync_playwright = None
```

### B. Graceful Missing Dependency Handling
1. **In `_initialize_curl_cffi_session(self) -> bool`**:
   - Check if `curl_requests is None`. If so, log an error and return `False`.
2. **In `_initialize_playwright_session(self) -> bool`**:
   - Check if `sync_playwright is None`. If so, log an error and return `False`.
3. **In `_fetch_with_playwright(self, url, params) -> Optional[dict]`**:
   - Check if `sync_playwright is None`. If so, log an error and raise `NSEClientError("Playwright is not installed.")`.
4. **In `_request_with_retry(self, url, params)`**:
   - Catch `NSEClientError` specifically in the playwright try-except block and propagate it (`raise`), ensuring it is not caught and suppressed by the generic `except Exception as e`.

### C. Transition Loop Bug Fix
1. In `_request_with_retry`, wrap the curl_cffi request section in `if self.mode == "curl_cffi":` (after potential session initialization/fallback check) to allow clean fall-through without raising `AttributeError` on a `None` session.
2. Remove the `continue` statement at each transition to `playwright` mode, so execution falls through to the playwright block in the same iteration.
   - Place 1: curl_cffi session initialization failure.
   - Place 2: non-JSON response from curl_cffi on final retry.
   - Place 3: 401/403 block from curl_cffi.
   - Place 4: HTTP error from curl_cffi when retries exhausted.
   - Place 5: curl_cffi request exception when retries exhausted.

---

## 3. Verification Plan
1. **Compilation Check**:
   - Run `python -m py_compile nse_client.py ipo_monitor.py config.py` to ensure syntactical correctness.
2. **Unit Tests**:
   - Run `pytest test_nse_client_mock.py` or `python -m unittest test_nse_client_mock.py` to verify the mock tests.
3. **Behavior Verification**:
   - Validate behavior when dependencies are missing.
