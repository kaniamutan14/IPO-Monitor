# Implementation Plan v5: Yahoo Finance (yfinance) Integration for Listing Prices

## 1. Objective
Replace the heavily firewalled NSE Historical Equity API with the reliable, unrestricted `yfinance` (Yahoo Finance) library for fetching IPO listing prices. This will permanently solve the HTTP 503 / `net::ERR_HTTP2_PROTOCOL_ERROR` issues and allow the script to operate flawlessly in a "set-and-forget" automated environment like GitHub Actions.

## 2. Dependencies
*   Add `yfinance` to `requirements.txt`.
*   Ensure `pandas` is installed (as it is a dependency of `yfinance`).

## 3. Symbol Translation Logic
Yahoo Finance uses specific suffixes to identify exchanges:
*   National Stock Exchange of India (NSE) symbols require the `.NS` suffix.
*   Example: `MEESHO` becomes `MEESHO.NS`.
*   Example SME IPO: `KNACK` becomes `KNACK.NS`.

## 4. Code Modifications

### 4.1 Update `nse_client.py`
The method `get_listing_day_price(self, symbol: str, listing_date_str: str)` currently attempts to use the `NSE_HISTORICAL_EQUITY` endpoint. This will be completely refactored to use `yfinance`.

**Proposed Logic:**
1. Format the date strings. `yfinance` expects dates in `YYYY-MM-DD` format.
2. Append `.NS` to the provided `symbol`.
3. Use `yf.Ticker(f"{symbol}.NS").history(start=start_date, end=end_date)`. Note: The `end` date in `yfinance` is exclusive, so the end date must be `listing_date + 1 day`.
4. Extract the `Open`, `High`, `Low`, and `Close` prices from the resulting Pandas DataFrame.
5. Return the dictionary in the exact same format the rest of the application expects:
   ```json
   {
       "open": 204.0,
       "high": 214.2,
       "low": 193.8,
       "close": 193.8
   }
   ```

### 4.2 Error Handling & Fallbacks
*   **Missing Tickers:** Yahoo Finance can occasionally be a few hours late in adding a brand new ticker symbol on the morning of its listing. 
*   **Handling Empty DataFrames:** If `yfinance` returns an empty DataFrame, the method should gracefully return `None`. The `ipo_monitor.py` script's state machine handles this perfectly—it will simply leave the IPO in the `CLOSED` state and try again on the next cron job run until the data becomes available.

## 5. Testing Strategy
1.  **Unit/Integration Test:** Create a script (`test_yfinance_listing.py`) to query known historical listings (e.g., `SHADOWFAX.NS` and `KNACK.NS`) to verify that `yfinance` correctly returns the OHLC data.
2.  **Format Verification:** Ensure the returned data types are standard Python floats (converting from `numpy.float64` if necessary) so they serialize perfectly into the `state.json` file.

## 6. Execution Steps
1. [ ] Update `requirements.txt` and install `yfinance`.
2. [ ] Refactor `nse_client.py` -> `get_listing_day_price`.
3. [ ] Run `test_yfinance_listing.py` to validate.
4. [ ] Push changes to GitHub.
