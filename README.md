# IPO Discord Monitor 📈

Automated monitoring of NSE India IPO data with rich Discord notifications.

## Features

- 🔄 **Live IPO Tracking** — Monitors currently open IPOs on NSE
- 📊 **Subscription Updates** — Category-wise subscription data (QIB, NII, Retail)
- 🔔 **Listing Alerts** — Issue price vs listing price with P&L breakdown
- 💰 **Selling Charges** — Estimated DP charges, STT, taxes in P&L calculation
- 🔄 **Lifecycle Management** — Tracks IPOs from OPEN → CLOSED → LISTED → ARCHIVED
- 🛡️ **Anti-Bot Handling** — NSE session/cookie management with retry logic
- ⚠️ **Error Alerts** — Discord notifications when data fetching fails

## Quick Start

### 1. Clone & Install

```bash
git clone <your-repo-url>
cd ipo
pip install -r requirements.txt
```

### 2. Configure Discord Webhook

```bash
cp .env.example .env
# Edit .env with your Discord webhook URL
```

To create a Discord webhook:
1. Open Discord → Server Settings → Integrations → Webhooks
2. Click "New Webhook" → Copy webhook URL
3. Paste into `.env` file

### 3. Run

```bash
# Dry run (no Discord notifications, preview only)
python ipo_monitor.py --dry-run --verbose

# Live run
python ipo_monitor.py --verbose
```

## GitHub Actions (Automated)

The included workflow runs automatically on weekdays:

| Schedule (UTC) | IST | Purpose |
|---------------|-----|--------|
| 04:30 Mon-Fri | 10:00 AM | Morning check |
| 08:30 Mon-Fri | 2:00 PM | Afternoon update |
| 12:30 Mon-Fri | 6:00 PM | Evening update |

### Setup

1. Push this repo to GitHub
2. Go to **Settings → Secrets and variables → Actions**
3. Add secret: `DISCORD_WEBHOOK_URL` = your webhook URL
4. The workflow will run automatically on schedule

You can also trigger manually: **Actions → IPO Discord Monitor → Run workflow**

## Project Structure

```
├── ipo_monitor.py          # Main orchestration script
├── nse_client.py           # NSE API client with session handling
├── discord_notifier.py     # Discord webhook with rich embeds
├── state_manager.py        # State file lifecycle management
├── config.py               # Configuration & constants
├── requirements.txt        # Python dependencies
├── .env.example            # Environment variable template
├── .gitignore              # Git ignore rules
├── state.json              # Runtime state (auto-created)
├── README.md               # This file
└── .github/
    └── workflows/
        └── ipo_monitor.yml # GitHub Actions workflow
```

## Discord Notifications

### New IPO Alert
Sent when a new IPO opens for bidding. Includes price band, lot size, and min investment.

### Subscription Update
Daily update during bidding window with category-wise breakdown (QIB, NII, Retail).

### Close Alert
Sent when bidding closes with final subscription numbers.

### Listing Alert
Sent when listing price is available. Includes full P&L breakdown:
- Gross gain/loss per share and per lot
- Estimated selling charges (DP, STT, transaction charges, SEBI, stamp duty, GST)
- **Final Net P&L** after all deductions

## IPO Lifecycle

```
OPEN → CLOSED → LISTED → ARCHIVED
```

- **OPEN**: Bidding is active. Daily subscription updates sent.
- **CLOSED**: Bidding ended. Awaiting listing.
- **LISTED**: Listed on exchange. P&L notification sent.
- **ARCHIVED**: 7+ days after listing. Auto-cleaned.

## Configuration

| Environment Variable | Required | Description |
|---------------------|----------|-------------|
| `DISCORD_WEBHOOK_URL` | Yes | Discord webhook URL for notifications |

Additional settings in `config.py`:
- NSE request delays and retry counts
- P&L charge rates (DP, STT, etc.)
- State file location

## Known Limitations

- **NSE Anti-Bot**: NSE may block automated requests. The script handles this with session management and retries, but sustained blocking may occur.
- **API Schema**: NSE APIs are undocumented. Field names are inferred and may change without notice.
- **GitHub Actions IPs**: NSE may block GitHub Actions IP ranges. Consider self-hosted runners or a VPS as fallback.

## License

MIT
