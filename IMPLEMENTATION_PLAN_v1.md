# IPO Discord Monitor — Implementation Plan v1

**Created:** 2026-07-07  
**Status:** Approved — Building

---

## Goal

Daily automated monitoring of NSE IPO data with Discord notifications covering:
- Issue price & price band
- Minimum subscription amount (lot size × issue price)
- Category-wise subscription status (QIB, NII, Retail, Total)
- Listing day price vs issue price with full P&L breakdown (including estimated selling charges)

---

## Data Sources (NSE Only)

| Endpoint | Purpose |
|----------|---------|
| `GET /api/ipo-current-issue` | List of symbols currently open for bidding |
| `GET /api/ipo-detail?symbol=SYMBOL&series=EQ` | Price band, bid lot, subscription categories |
| `GET /api/public-past-issues` | Listing date and listing price for closed IPOs |

Base URL: `https://www.nseindia.com`

---

## Architecture

```
ipo/
├── ipo_monitor.py          # Main orchestration script
├── nse_client.py           # NSE API client with session/cookie handling
├── discord_notifier.py     # Discord webhook with rich embeds
├── state_manager.py        # State file (JSON) lifecycle management
├── config.py               # Configuration & constants
├── requirements.txt        # Python dependencies
├── .env.example            # Example environment variables
├── .gitignore              # Git ignore rules
├── state.json              # Runtime state (auto-created, gitignored)
├── README.md               # Project documentation
└── .github/
    └── workflows/
        └── ipo_monitor.yml # GitHub Actions cron workflow
```

---

## IPO Lifecycle State Machine

```
UPCOMING → OPEN → CLOSED → LISTED → ARCHIVED
```

| State | Trigger | Notification |
|-------|---------|-------------|
| `UPCOMING` | Appears in upcoming data | "New IPO announced, opens on DATE" |
| `OPEN` | Bidding window active | Daily subscription update (category-wise) |
| `CLOSED` | Bidding window ended | Final subscription numbers |
| `LISTED` | Listing price available | Issue price vs listing price, P&L with charges |
| `ARCHIVED` | 7 days after listing | No notification, cleanup |

---

## State File Schema (`state.json`)

```json
{
  "tracked_ipos": {
    "SYMBOL": {
      "state": "OPEN",
      "company_name": "XYZ Industries Ltd",
      "issue_price_band": { "min": 185, "max": 195 },
      "lot_size": 76,
      "open_date": "2026-07-07",
      "close_date": "2026-07-09",
      "series": "EQ",
      "last_subscription": {
        "total": 3.5,
        "retail": 5.2,
        "qib": 1.1,
        "nii": 2.8
      },
      "subscription_history": [
        { "date": "2026-07-07", "total": 0.8, "retail": 1.2, "qib": 0.3, "nii": 0.5 }
      ],
      "notifications_sent": {
        "open_alert": true,
        "close_alert": false,
        "listing_alert": false,
        "daily": ["2026-07-07", "2026-07-08"]
      },
      "listing_price": null,
      "listing_date": null,
      "listing_gain_pct": null
    }
  },
  "last_run": "2026-07-07T10:00:00+05:30"
}
```

---

## Discord Notification Formats

### Open IPO — Daily Subscription Update
```
🟢 IPO SUBSCRIPTION UPDATE — Day 2/3

📌 XYZ Industries Ltd
━━━━━━━━━━━━━━━━━━━
💰 Price Band: ₹185 - ₹195
📦 Lot Size: 76 shares
💵 Min Investment: ₹14,820

📊 Subscription Status:
   Retail:    8.42x  📈
   NII:      3.15x  📈
   QIB:     12.67x  📈
   Total:    6.89x  📈

📅 Closes: 09-Jul-2026
📅 Listing (Expected): 14-Jul-2026
```

### Listing Day Result
```
🔔 IPO LISTING — XYZ Industries Ltd

💰 Issue Price: ₹195
📈 Listing Price: ₹312
🎯 Gain: +60.0% (₹117/share)
💰 Per Lot Gain (Gross): ₹8,892 (76 shares)

📊 Estimated Selling Charges:
   DP Charges:           ₹15.93
   STT (0.025%):         ₹5.93
   Other Taxes (est):    ₹25.00
   Total Charges:        ₹46.86

💵 Final Net P&L/Lot:   ₹8,845.14

📊 Final Subscription was: 6.89x
```

---

## NSE Anti-Bot Mitigation Strategy

1. **Session bootstrap**: `GET https://www.nseindia.com` → capture cookies
2. **Random delay**: 1-2 seconds between requests
3. **Required headers**:
   - `User-Agent`: Real browser UA
   - `Referer`: `https://www.nseindia.com/market-data/all-upcoming-issues-ipo`
   - `Accept`: `application/json`
   - `X-Requested-With`: `XMLHttpRequest`
4. **Cookie reuse**: Same session across all API calls in a run
5. **Retry on 403**: Fresh session + retry once
6. **Failure alert**: Discord notification if data fetch fails

---

## Scheduling

### GitHub Actions Cron (IST = UTC+5:30)

| Cron (UTC) | IST Equivalent | Purpose |
|-----------|----------------|---------|
| `30 4 * * 1-5` | 10:00 AM IST | Morning check (market open) |
| `30 8 * * 1-5` | 2:00 PM IST | Afternoon update |
| `30 12 * * 1-5` | 6:00 PM IST | Evening update (post-market) |
| `30 4 * * 0` | Sunday 10:00 AM | Weekly summary digest |

Weekdays only (Mon–Fri) for daily checks. Sunday for weekly digest.

---

## Risk Register

| Risk | Impact | Mitigation |
|------|--------|------------|
| NSE API schema changes | Script breaks silently | Validate response schema, alert on unexpected structure |
| NSE rate limiting / IP ban | No data | Rotate User-Agent, add delays, failure alerts |
| GitHub Actions IP blocked by NSE | Persistent 403s | Fallback to OCI VPS or self-hosted runner |
| Discord webhook rate limits | Missed notifications | Batch embeds (multiple IPOs in one message) |
| IPO with no `series=EQ` | Data fetch fails | Handle bonds, InvITs, REITs gracefully |
| Weekend/holiday runs | Wasted execution | Skip weekends in cron |

---

## Tech Stack

| Component | Choice | Reason |
|-----------|--------|--------|
| Language | Python 3.10+ | Best HTTP/JSON ecosystem |
| HTTP | `requests` (Session) | Cookie persistence |
| Scheduling | GitHub Actions cron | Free, reliable |
| State | JSON file (local) | Simple, sufficient |
| Notifications | Discord Webhook | Rich embeds, free |
| Env Config | `python-dotenv` | Clean secret management |

---

## Features Checklist

- [x] NSE session/cookie management
- [x] Current IPO fetching
- [x] Per-IPO detail fetching (price, lot, subscription)
- [x] Category-wise subscription (QIB, NII, Retail)
- [x] Past/listed IPO fetching
- [x] Listing price vs issue price P&L
- [x] Estimated selling charges in P&L
- [x] IPO lifecycle state machine
- [x] Duplicate notification prevention
- [x] Subscription history tracking
- [x] Rich Discord embeds
- [x] Failure/error Discord alerts
- [x] GitHub Actions workflow
- [ ] Weekly summary digest (Phase 2)
- [ ] Upcoming IPO alerts (Phase 2)
- [ ] Subscription milestone alerts (Phase 2)
