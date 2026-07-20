"""NSE India API client with session management for IPO data.

Handles anti-bot cookie/session requirements by bootstrapping a session
from the NSE main page before making API calls.
"""

import re
import time
import random
import logging
from typing import Any, Optional

try:
    from curl_cffi import requests as curl_requests
except ImportError:
    curl_requests = None

try:
    from playwright.sync_api import sync_playwright
except ImportError:
    sync_playwright = None

from config import (
    NSE_BASE_URL,
    NSE_CURRENT_ISSUES,
    NSE_IPO_DETAIL,
    NSE_PAST_ISSUES,
    NSE_MAIN_PAGE,
    NSE_HEADERS,
    NSE_REQUEST_DELAY,
    NSE_MAX_RETRIES,
)

logger = logging.getLogger(__name__)


class NSEClientError(Exception):
    """Raised when NSE API requests fail."""
    pass


class _TransitionToPlaywright(Exception):
    """Internal exception used to trigger playwright fallback transition."""
    pass


class NSEClient:
    """Client for NSE India IPO API endpoints.
    
    Manages session cookies required by NSE's anti-bot protection.
    Must call initialize_session() before making API requests.
    """

    def __init__(self):
        self.session: Optional[Any] = None
        self._session_initialized = False
        self.mode = "curl_cffi"  # "curl_cffi" (primary) or "playwright" (fallback)
        self._playwright = None
        self._browser = None
        self._context = None
        self._page = None

    def initialize_session(self) -> bool:
        """Bootstrap a session by visiting NSE main page to get cookies.
        
        Returns:
            True if session was successfully initialized, False otherwise.
        """
        if self.mode == "curl_cffi":
            if self._initialize_curl_cffi_session():
                return True

            logger.warning("curl_cffi session initialization failed; trying Playwright fallback.")
            self.mode = "playwright"
            self._session_initialized = False

        return self._initialize_playwright_session()

    def _initialize_curl_cffi_session(self) -> bool:
        if curl_requests is None:
            logger.error("curl_cffi is not installed on the system.")
            return False
        try:
            self.session = curl_requests.Session(impersonate="chrome110")
            self.session.headers.update(NSE_HEADERS)
            
            logger.info("Initializing NSE curl_cffi session...")
            response = self.session.get(
                NSE_MAIN_PAGE,
                timeout=15,
                allow_redirects=True
            )
            
            if response.status_code == 200:
                self._session_initialized = True
                cookie_names = [
                    getattr(cookie, "name", str(cookie))
                    for cookie in self.session.cookies
                ]
                logger.info(f"NSE curl_cffi session initialized. Cookies: {cookie_names}")
                return True
            else:
                logger.error(f"Failed to initialize NSE curl_cffi session. Status: {response.status_code}")
                return False
                
        except Exception as e:
            logger.error(f"Error initializing NSE curl_cffi session: {e}")
            return False

    def _initialize_playwright_session(self) -> bool:
        if sync_playwright is None:
            logger.error("playwright is not installed on the system.")
            return False
        try:
            logger.info("Initializing NSE playwright session...")
            if self._page and not self._page.is_closed():
                self._session_initialized = True
                return True
            
            self._close_playwright()
            
            from config import PLAYWRIGHT_TIMEOUT, PLAYWRIGHT_HEADLESS
            
            self._playwright = sync_playwright().start()
            self._browser = self._playwright.chromium.launch(
                headless=PLAYWRIGHT_HEADLESS,
                args=[
                    # Firefox doesn't use blink features flag
                ]
            )
            
            self._context = self._browser.new_context(
                user_agent=NSE_HEADERS.get("User-Agent"),
                viewport={"width": 1280, "height": 720},
                extra_http_headers={
                    "Accept-Language": NSE_HEADERS.get("Accept-Language", "en-US,en;q=0.9"),
                }
            )
            
            self._context.add_init_script("Object.defineProperty(navigator, 'webdriver', {get: () => undefined})")
            
            self._page = self._context.new_page()
            self._page.set_default_timeout(PLAYWRIGHT_TIMEOUT)
            
            response = self._page.goto(NSE_MAIN_PAGE, wait_until="load", timeout=PLAYWRIGHT_TIMEOUT)
            status = response.status if response else 0
            if status == 200:
                self._session_initialized = True
                logger.info("NSE playwright session initialized successfully.")
                return True
            else:
                logger.error(f"Failed to initialize NSE playwright session. Status: {status}")
                self._close_playwright()
                self._session_initialized = False
                return False
                
        except Exception as e:
            logger.error(f"Error initializing NSE playwright session: {e}")
            self._close_playwright()
            return False

    def _close_playwright(self):
        try:
            if self._page:
                self._page.close()
        except Exception:
            pass
        self._page = None
        
        try:
            if self._context:
                self._context.close()
        except Exception:
            pass
        self._context = None
        
        try:
            if self._browser:
                self._browser.close()
        except Exception:
            pass
        self._browser = None
        
        try:
            if self._playwright:
                self._playwright.stop()
        except Exception:
            pass
        self._playwright = None

    def _fetch_with_playwright(self, url: str, params: Optional[dict] = None) -> Optional[dict]:
        if sync_playwright is None:
            logger.error("Attempted to fetch using Playwright, but playwright is not installed.")
            raise NSEClientError("Playwright is not installed.")
        try:
            from config import PLAYWRIGHT_TIMEOUT
            if not self._session_initialized or not self._page or self._page.is_closed():
                if not self._initialize_playwright_session():
                    logger.error("Failed to initialize Playwright session during fetch")
                    return None
            
            if "nseindia.com" not in self._page.url:
                logger.info("Playwright page not on NSE domain, navigating to main page...")
                self._page.goto(NSE_MAIN_PAGE, wait_until="load", timeout=PLAYWRIGHT_TIMEOUT)

            from urllib.parse import urlencode
            full_url = url
            if params:
                query_string = urlencode(params)
                full_url = f"{url}?{query_string}" if "?" not in url else f"{url}&{query_string}"
                
            delay = random.uniform(*NSE_REQUEST_DELAY)
            logger.debug(f"Playwright: waiting {delay:.1f}s before request...")
            time.sleep(delay)
            
            logger.info(f"Playwright: fetching {full_url} inside page context...")
            
            js_code = """
            async (fetchUrl) => {
                const response = await fetch(fetchUrl, {
                    headers: {
                        'Accept': 'application/json, text/plain, */*',
                        'X-Requested-With': 'XMLHttpRequest'
                    }
                });
                if (!response.ok) {
                    throw new Error(`HTTP error! status: ${response.status}`);
                }
                return await response.json();
            }
            """
            data = self._page.evaluate(js_code, full_url)
            return data
        except Exception as e:
            logger.error(f"Playwright fetch error for {url}: {e}")
            self._session_initialized = False
            return None

    def _request_with_retry(self, url: str, params: Optional[dict] = None) -> Optional[dict]:
        """Make a GET request with retry logic and session refresh/fallback.
        
        Args:
            url: The API endpoint URL.
            params: Optional query parameters.
            
        Returns:
            Parsed JSON response or None if all retries fail.
        """
        for attempt in range(NSE_MAX_RETRIES + 1):
            if self.mode == "curl_cffi":
                try:
                    if not self._session_initialized:
                        if not self._initialize_curl_cffi_session():
                            logger.error("Cannot make request - curl_cffi session initialization failed")
                            logger.info("Transitioning to playwright mode due to curl_cffi initialization failure...")
                            self.mode = "playwright"
                            self._session_initialized = False
                            raise _TransitionToPlaywright()
                    
                    delay = random.uniform(*NSE_REQUEST_DELAY)
                    logger.debug(f"Waiting {delay:.1f}s before curl_cffi request...")
                    time.sleep(delay)
                    
                    response = self.session.get(url, params=params, timeout=15)
                    
                    if response.status_code == 200:
                        content_type = response.headers.get('Content-Type', '')
                        if 'application/json' in content_type or 'text/json' in content_type:
                            return response.json()
                        else:
                            try:
                                return response.json()
                            except ValueError:
                                logger.warning(f"Non-JSON response from {url}: {content_type}")
                                if attempt < NSE_MAX_RETRIES:
                                    logger.info(f"Refreshing curl_cffi session (attempt {attempt + 1})...")
                                    self._session_initialized = False
                                    continue
                                else:
                                    logger.info("Transitioning to playwright mode due to non-JSON response from curl_cffi...")
                                    self.mode = "playwright"
                                    self._session_initialized = False
                    
                    elif response.status_code in (401, 403):
                        logger.warning(f"Auth error {response.status_code} from {url} in curl_cffi. Switching to playwright fallback...")
                        self.mode = "playwright"
                        self._session_initialized = False
                        
                    elif response.status_code == 404:
                        logger.debug(f"HTTP 404 from {url} in curl_cffi. Resource not found.")
                        return None
                        
                    else:
                        logger.error(f"HTTP {response.status_code} from {url} in curl_cffi")
                        if attempt < NSE_MAX_RETRIES:
                            time.sleep(2)
                            self._session_initialized = False
                            continue
                        else:
                            logger.info("Transitioning to playwright mode after HTTP error retries exhausted...")
                            self.mode = "playwright"
                            self._session_initialized = False
                        
                except _TransitionToPlaywright:
                    pass
                except Exception as e:
                    logger.error(f"curl_cffi request error for {url}: {e}")
                    if attempt < NSE_MAX_RETRIES:
                        self._session_initialized = False
                        continue
                    else:
                        logger.info("Transitioning to playwright mode after request exception...")
                        self.mode = "playwright"
                        self._session_initialized = False
            
            if self.mode == "playwright":
                try:
                    data = self._fetch_with_playwright(url, params)
                    if data is not None:
                        return data
                    
                    if attempt < NSE_MAX_RETRIES:
                        logger.info(f"Retrying playwright fetch (attempt {attempt + 1})...")
                        time.sleep(2)
                        continue
                except NSEClientError:
                    raise
                except Exception as e:
                    logger.error(f"Playwright fetch error in retry loop: {e}")
                    if attempt < NSE_MAX_RETRIES:
                        time.sleep(2)
                        continue
                        
            # If we exhausted retries in playwright mode and it failed,
            # revert to curl_cffi for the next symbol instead of staying trapped in Playwright.
            if self.mode == "playwright":
                logger.info("Playwright fetch failed completely. Reverting mode back to curl_cffi for future requests.")
                self.mode = "curl_cffi"
        
        return None


    def get_current_issues(self) -> list[dict]:
        """Fetch currently open IPO issues.
        
        Returns:
            List of IPO issue dicts with symbol, companyName, dates, etc.
            Empty list if request fails.
        """
        logger.info("Fetching current IPO issues...")
        data = self._request_with_retry(NSE_CURRENT_ISSUES)
        
        if data is None:
            logger.error("Failed to fetch current issues")
            return []
        
        # Response could be a list directly or wrapped in a key
        if isinstance(data, list):
            logger.info(f"Found {len(data)} current IPO issues")
            return data
        elif isinstance(data, dict):
            # Try common wrapper keys
            for key in ('data', 'issues', 'currentIssues'):
                if key in data and isinstance(data[key], list):
                    logger.info(f"Found {len(data[key])} current IPO issues (in '{key}')")
                    return data[key]
            logger.warning(f"Unexpected current issues response structure: {list(data.keys())}")
            return []
        
        return []

    def get_ipo_detail(self, symbol: str, series: str = "EQ") -> Optional[dict]:
        """Fetch detailed IPO information for a specific symbol.
        
        Args:
            symbol: The IPO symbol (e.g., 'AFCONS').
            series: The series code (default 'EQ').
            
        Returns:
            Dict with IPO details or None if request fails.
        """
        logger.info(f"Fetching IPO detail for {symbol} ({series})...")
        data = self._request_with_retry(
            NSE_IPO_DETAIL,
            params={"symbol": symbol, "series": series}
        )
        
        if data is None:
            logger.error(f"Failed to fetch detail for {symbol}")
        
        return data

    def get_past_issues(self) -> list[dict]:
        """Fetch past/listed IPO issues.
        
        Returns:
            List of past IPO issue dicts with listing prices, dates, etc.
            Empty list if request fails.
        """
        logger.info("Fetching past IPO issues...")
        data = self._request_with_retry(NSE_PAST_ISSUES)
        
        if data is None:
            logger.error("Failed to fetch past issues")
            return []
        
        if isinstance(data, list):
            logger.info(f"Found {len(data)} past IPO issues")
            return data
        elif isinstance(data, dict):
            for key in ('data', 'issues', 'pastIssues'):
                if key in data and isinstance(data[key], list):
                    logger.info(f"Found {len(data[key])} past IPO issues (in '{key}')")
                    return data[key]
            logger.warning(f"Unexpected past issues response structure: {list(data.keys())}")
            return []
        
        return []

    def get_listing_day_price(self, symbol: str, listing_date_str: str) -> Optional[dict]:
        """Fetch listing day OHLC prices using yfinance.
        
        Replaces the restricted NSE historical endpoint.
        
        Args:
            symbol: The equity symbol.
            listing_date_str: Listing date string.
            
        Returns:
            Dict with 'open', 'high', 'low', 'close' prices, or None.
        """
        from datetime import datetime, timedelta
        try:
            import yfinance as yf
        except ImportError:
            logger.error("yfinance is not installed. Run: pip install yfinance pandas")
            return None
        
        # Parse listing date
        listing_date = None
        for fmt in ('%d-%b-%Y', '%d-%B-%Y', '%Y-%m-%d', '%d/%m/%Y'):
            try:
                listing_date = datetime.strptime(listing_date_str, fmt)
                break
            except ValueError:
                continue
        
        if not listing_date:
            logger.warning(f"Could not parse listing date: {listing_date_str}")
            return None
            
        start_date = listing_date.strftime('%Y-%m-%d')
        end_date = (listing_date + timedelta(days=1)).strftime('%Y-%m-%d')
        
        logger.info(f"Fetching listing day price for {symbol} using yfinance ({start_date} to {end_date})")
        
        # Try NSE (.NS) first, then fallback to BSE (.BO) for SME IPOs
        df = None
        for suffix in ('.NS', '.BO'):
            ticker = f"{symbol}{suffix}"
            logger.info(f"Trying ticker {ticker}...")
            try:
                # yfinance returns a pandas DataFrame
                df = yf.Ticker(ticker).history(start=start_date, end=end_date)
                if df is not None and not df.empty:
                    logger.info(f"Successfully fetched data for {ticker}")
                    break
            except Exception as e:
                logger.debug(f"yfinance error for {ticker}: {e}")
                
        if df is None or df.empty:
            logger.warning(f"No historical data found for {symbol} on {start_date} via yfinance")
            
            # --- Fallback: Try NSE NextApi (getSymbolData) ---
            logger.info(f"Fallback: Attempting to fetch listing price for {symbol} via NSE NextApi")
            for series in ('EQ', 'ST', 'SM'):
                url = f"https://www.nseindia.com/api/NextApi/apiClient/GetQuoteApi?functionName=getSymbolData&marketType=N&series={series}&symbol={symbol}"
                data = self._request_with_retry(url)
                if data and "equityResponse" in data and len(data["equityResponse"]) > 0:
                    meta = data["equityResponse"][0].get("metaData", {})
                    if "open" in meta and meta["open"] > 0:
                        logger.info(f"Fallback successful for {symbol} (Series: {series})")
                        result = {
                            'open': float(meta.get("open", 0)),
                            'high': float(meta.get("dayHigh", 0)),
                            'low': float(meta.get("dayLow", 0)),
                            'close': float(meta.get("lastPrice", meta.get("previousClose", 0)))
                        }
                        # Last price could be in orderBook
                        order_book = data["equityResponse"][0].get("orderBook", {})
                        if "lastPrice" in order_book and order_book["lastPrice"] > 0:
                            result['close'] = float(order_book["lastPrice"])
                            
                        logger.info(f"Listing day prices for {symbol} (from NextApi): {result}")
                        return result
                        
            return None
            
        try:
            # yfinance returns np.float64, we must cast to Python float for JSON serialization
            result = {
                'open': float(df['Open'].iloc[0]),
                'high': float(df['High'].iloc[0]),
                'low': float(df['Low'].iloc[0]),
                'close': float(df['Close'].iloc[0]),
            }
            logger.info(f"Listing day prices for {symbol}: {result}")
            return result
        except Exception as e:
            logger.error(f"Error parsing yfinance DataFrame for {symbol}: {e}")
            return None

    # --- Data Extraction Helpers (flexible field access) ---

    @staticmethod
    def extract_symbol(issue: dict) -> Optional[str]:
        """Extract symbol from an issue dict, trying multiple field names."""
        for key in ('symbol', 'Symbol', 'SYMBOL', 'sym', 'htmSym'):
            if key in issue and issue[key]:
                return str(issue[key]).strip()
        return None

    @staticmethod
    def extract_company_name(issue: dict) -> str:
        """Extract company name from an issue dict."""
        for key in ('companyName', 'company', 'company_name', 'name', 'issuerCompany', 'Company Name'):
            if key in issue and issue[key]:
                return str(issue[key]).strip()
        return "Unknown Company"

    @staticmethod
    def extract_series(issue: dict) -> str:
        """Extract series from an issue dict."""
        for key in ('series', 'Series', 'SERIES'):
            if key in issue and issue[key]:
                return str(issue[key]).strip()
        return "EQ"

    @staticmethod
    def extract_dates(issue: dict) -> tuple[Optional[str], Optional[str]]:
        """Extract open and close dates from an issue dict.
        
        Returns:
            Tuple of (open_date, close_date) as strings or None.
        """
        open_date = None
        close_date = None
        
        for key in ('issueStartDate', 'ipoStartDate', 'openDate', 'startDate', 'issue_start_date'):
            if key in issue and issue[key]:
                open_date = str(issue[key]).strip()
                break
        
        for key in ('issueEndDate', 'ipoEndDate', 'closeDate', 'endDate', 'issue_end_date'):
            if key in issue and issue[key]:
                close_date = str(issue[key]).strip()
                break
        
        return open_date, close_date

    @staticmethod
    def parse_price_value(value: Any) -> Optional[float]:
        """Parse a price value that may be a number, string with ₹/commas, etc.
        
        Examples:
            463 → 463.0
            '₹463' → 463.0
            '1,234.56' → 1234.56
            '₹1,234.56' → 1234.56
        """
        if value is None:
            return None
        if isinstance(value, (int, float)):
            return float(value)
        
        # Remove ₹, commas, spaces
        cleaned = re.sub(r'[₹,\s]', '', str(value))
        try:
            return float(cleaned)
        except (ValueError, TypeError):
            return None

    @staticmethod
    def extract_price_band(detail: dict) -> tuple[Optional[float], Optional[float]]:
        """Extract price band (min, max) from IPO detail response.
        
        Handles both structured fields and string formats like '₹440 - ₹463'.
        
        Returns:
            Tuple of (min_price, max_price) or (None, None).
        """
        # Try structured fields first
        min_price = None
        max_price = None
        
        for key in ('minPrice', 'priceRangeMin', 'min_price', 'floorPrice'):
            if key in detail:
                min_price = NSEClient.parse_price_value(detail[key])
                if min_price:
                    break
        
        for key in ('maxPrice', 'priceRangeMax', 'max_price', 'capPrice', 'cutOffPrice'):
            if key in detail:
                max_price = NSEClient.parse_price_value(detail[key])
                if max_price:
                    break
        
        if min_price and max_price:
            return min_price, max_price
        
        # Try nested priceBand object (e.g., priceBand: { minPrice: 100, maxPrice: 105 })
        price_band_obj = detail.get('priceBand', {})
        if isinstance(price_band_obj, dict):
            for key in ('minPrice', 'min', 'lower'):
                if key in price_band_obj and not min_price:
                    min_price = NSEClient.parse_price_value(price_band_obj[key])
            for key in ('maxPrice', 'max', 'upper'):
                if key in price_band_obj and not max_price:
                    max_price = NSEClient.parse_price_value(price_band_obj[key])
            if min_price and max_price:
                return min_price, max_price
        
        # Try parsing a combined price band string
        for key in ('priceBand', 'priceRange', 'price_band', 'issuePrice'):
            if key in detail and isinstance(detail[key], str):
                band_str = detail[key]
                # Match patterns like '₹440 - ₹463' or '440-463' or '440 to 463'
                numbers = re.findall(r'[\d,]+\.?\d*', band_str.replace(',', ''))
                if len(numbers) >= 2:
                    try:
                        return float(numbers[0]), float(numbers[-1])
                    except ValueError:
                        pass
                elif len(numbers) == 1:
                    # Fixed price IPO
                    try:
                        price = float(numbers[0])
                        return price, price
                    except ValueError:
                        pass
                        
        # Check issueInfo dataList for Price Range
        issue_info = detail.get('issueInfo', {})
        if isinstance(issue_info, dict):
            data_list = issue_info.get('dataList', [])
            if isinstance(data_list, list):
                for item in data_list:
                    if isinstance(item, dict) and item.get('title') in ('Price Range', 'Issue Price'):
                        val = item.get('value', '')
                        if val:
                            numbers = re.findall(r'[\d,]+\.?\d*', val.replace(',', ''))
                            if len(numbers) >= 2:
                                try:
                                    return float(numbers[0]), float(numbers[1])
                                except ValueError:
                                    pass
                            elif len(numbers) == 1:
                                try:
                                    price = float(numbers[0])
                                    return price, price
                                except ValueError:
                                    pass
        
        return min_price, max_price

    @staticmethod
    def extract_lot_size(detail: dict) -> Optional[int]:
        """Extract lot/bid size from IPO detail response."""
        for key in ('lotSize', 'bidLot', 'minBidQuantity', 'lot_size',
                     'minimumOrderQuantity', 'marketLot'):
            if key in detail:
                try:
                    val = str(detail[key]).replace(',', '').strip()
                    return int(float(val))
                except (ValueError, TypeError):
                    continue
                    
        # Check issueInfo dataList for Bid Lot, Minimum Order Quantity, or Lot Size
        issue_info = detail.get('issueInfo', {})
        if isinstance(issue_info, dict):
            data_list = issue_info.get('dataList', [])
            if isinstance(data_list, list):
                for item in data_list:
                    if isinstance(item, dict) and item.get('title') in ('Bid Lot', 'Minimum Order Quantity', 'Lot Size', 'Market Lot'):
                        val = item.get('value', '')
                        if val:
                            numbers = re.findall(r'[\d,]+\.?\d*', val.replace(',', ''))
                            if numbers:
                                try:
                                    return int(float(numbers[0]))
                                except ValueError:
                                    pass
                                    
        return None

    @staticmethod
    def extract_subscription_data(detail: dict) -> dict[str, Optional[float]]:
        """Extract category-wise subscription data from IPO detail.
        
        Returns:
            Dict with keys: 'total', 'retail', 'qib', 'nii', 'employee'
            Values are subscription multipliers (e.g., 3.5 means 3.5x subscribed)
            or None if not available.
        """
        result = {
            'total': None,
            'retail': None,
            'qib': None,
            'nii': None,
            'employee': None,
        }
        
        # Try to find activeCat.dataList
        active_cat = detail.get('activeCat', {})
        data_list = None
        
        if isinstance(active_cat, dict):
            data_list = active_cat.get('dataList', active_cat.get('data', []))
        elif isinstance(active_cat, list):
            data_list = active_cat
        
        # Also try top-level subscription data
        if not data_list:
            for key in ('subscriptionDetails', 'subscription', 'categoryWise'):
                if key in detail:
                    data_list = detail[key]
                    if isinstance(data_list, list):
                        break
        
        if not data_list or not isinstance(data_list, list):
            logger.warning("No subscription data found in IPO detail")
            return result
        
        # Map category substrings to our keys
        category_map = {
            'total': ['total', 'overall'],
            'retail': ['retail', 'rii'],
            'qib': ['qib', 'qualified'],
            'nii': ['nii', 'non institutional', 'non-institutional', 'hni'],
            'employee': ['employee', 'emp'],
        }
        
        # Fields that might contain the subscription multiplier
        sub_fields = ['subscriptionTimes', 'noOfTimesSubscribed', 'timesSubscribed',
                       'times_subscribed', 'subscription', 'ratio', 'noOfTotalMeant']
        
        for item in data_list:
            if not isinstance(item, dict):
                continue
            
            # Get category name
            cat_name = None
            for cat_key in ('category', 'cat', 'categoryName', 'Category', 'investorCategory'):
                if cat_key in item:
                    cat_name = str(item[cat_key]).strip()
                    break
            
            if not cat_name:
                continue
            
            # Get subscription value
            sub_value = None
            for sf in sub_fields:
                if sf in item and item[sf] is not None:
                    try:
                        val_str = str(item[sf]).replace(',', '').replace('x', '').strip()
                        if val_str and val_str != '-' and val_str != 'NA':
                            sub_value = float(val_str)
                    except (ValueError, TypeError):
                        continue
                    if sub_value is not None:
                        break
            
            # Map to our category keys
            # Special handling: NII subtypes (bNII, sNII) aggregate into 'nii'
            cat_name_lower = cat_name.lower()
            for our_key, possible_names in category_map.items():
                if any(p in cat_name_lower for p in possible_names):
                    if our_key == 'nii' and result['nii'] is not None and sub_value is not None:
                        # If we already have NII, this might be a subcategory;
                        # don't overwrite if we got the main NII. Only sum bNII+sNII
                        # Actually, keep the Total NII if it exists, otherwise take the latest
                        pass
                    else:
                        result[our_key] = sub_value
                    break
                    
        # Fallback for total subscription if activeCat was missing or zeroes
        if not result['total'] or result['total'] == 0.0:
            for graph_key in ('demandGraphALL', 'demandGraph'):
                graph_data = detail.get(graph_key, {})
                if isinstance(graph_data, dict):
                    fallback_sub = graph_data.get('noOfTimesIssueSubscribed')
                    if fallback_sub and fallback_sub != '-':
                        try:
                            result['total'] = float(str(fallback_sub).replace(',', '').strip())
                            break
                        except ValueError:
                            pass
        
        return result

    @staticmethod
    def extract_listing_info(past_issue: dict) -> dict:
        """Extract listing information from a past issue record.
        
        Returns:
            Dict with 'listing_price', 'listing_date', 'issue_price',
            'listing_close_price' — values may be None.
        """
        info = {
            'listing_price': None,
            'listing_date': None,
            'issue_price': None,
            'listing_close_price': None,
        }
        
        # Listing price (opening)
        for key in ('listingPrice', 'listingOpenPrice', 'listing_price',
                     'listingDayOpen', 'openPrice'):
            if key in past_issue:
                info['listing_price'] = NSEClient.parse_price_value(past_issue[key])
                if info['listing_price']:
                    break
        
        # Issue price
        for key in ('issuePrice', 'issue_price', 'offerPrice', 'ipoPrice'):
            if key in past_issue:
                info['issue_price'] = NSEClient.parse_price_value(past_issue[key])
                if info['issue_price']:
                    break
        
        # Listing date
        for key in ('listingDate', 'listing_date', 'dateOfListing'):
            if key in past_issue and past_issue[key]:
                info['listing_date'] = str(past_issue[key]).strip()
                break
        
        # Listing close price
        for key in ('listingDayClose', 'listingClosePrice', 'listing_close_price', 'closePrice'):
            if key in past_issue:
                info['listing_close_price'] = NSEClient.parse_price_value(past_issue[key])
                if info['listing_close_price']:
                    break
        
        return info

    def close(self):
        """Close the session."""
        if self.session:
            try:
                self.session.close()
            except Exception:
                pass
            self.session = None
            
        self._close_playwright()
        self._session_initialized = False
        logger.info("NSE session closed")

    def __del__(self):
        try:
            self.close()
        except Exception:
            pass
