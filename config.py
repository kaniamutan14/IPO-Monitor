"""Configuration for IPO Discord Monitor."""
import os

try:
    from dotenv import load_dotenv
except ImportError:
    load_dotenv = None

if load_dotenv:
    load_dotenv()

# Discord
DISCORD_WEBHOOK_URL = os.getenv("DISCORD_WEBHOOK_URL", "")
ETF_DISCORD_WEBHOOK_URL = os.getenv("ETF_DISCORD_WEBHOOK_URL", "")

# NSE API Endpoints
NSE_BASE_URL = "https://www.nseindia.com"
NSE_CURRENT_ISSUES = f"{NSE_BASE_URL}/api/ipo-current-issue"
NSE_IPO_DETAIL = f"{NSE_BASE_URL}/api/ipo-detail"  # ?symbol=X&series=EQ
NSE_PAST_ISSUES = f"{NSE_BASE_URL}/api/public-past-issues"
NSE_MAIN_PAGE = NSE_BASE_URL

# NSE Request Config
NSE_HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/137.0.0.0 Safari/537.36",
    "Accept": "application/json, text/plain, */*",
    "Accept-Language": "en-US,en;q=0.9",
    "Accept-Encoding": "gzip, deflate, br",
    "Referer": "https://www.nseindia.com/market-data/all-upcoming-issues-ipo",
    "X-Requested-With": "XMLHttpRequest",
    "Connection": "keep-alive",
}
NSE_REQUEST_DELAY = (1.5, 3.0)  # Random delay range in seconds between API calls
NSE_MAX_RETRIES = 2

# Playwright Settings
PLAYWRIGHT_TIMEOUT = 30000
PLAYWRIGHT_HEADLESS = True

# State
STATE_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "state.json")

# IPO Lifecycle States
class IPOState:
    UPCOMING = "UPCOMING"
    OPEN = "OPEN"
    CLOSED = "CLOSED"
    LISTED = "LISTED"
    ARCHIVED = "ARCHIVED"

# P&L Charges
DP_CHARGES = 15.93  # DP charges per script for equity
STT_SELL_RATE = 0.00025  # STT on sell side (0.025%)
TRANSACTION_CHARGES_RATE = 0.0000345  # NSE transaction charges
SEBI_CHARGES_RATE = 0.000001  # SEBI turnover charges
STAMP_DUTY_RATE = 0.00015  # Stamp duty on sell
GST_RATE = 0.18  # GST on transaction charges + SEBI charges

# Subscription Milestones for alerts
SUBSCRIPTION_MILESTONES = [1, 3, 5, 10, 20, 50, 100]
