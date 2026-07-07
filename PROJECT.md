# Project: NSE IPO Monitor - Redundant Request Fetching

## Architecture
The NSE IPO Monitor consists of the following components:
- `nse_client.py`: Handles HTTP/API requests to NSE India website.
- `ipo_monitor.py`: Orchestrates the retrieval of data, state updates, and triggers alerts.
- `discord_notifier.py`: Prepares and sends rich embeds to Discord webhooks.
- `state_manager.py`: Manages the state in `state.json`.
- `config.py`: Contains configurations like endpoints, headers, and rates.
- `.github/workflows/ipo_monitor.yml`: Runs the monitor periodically via GitHub Actions.

Data flow:
1. `ipo_monitor.py` starts and instantiates `StateManager` and `NSEClient`.
2. `NSEClient` initializes session (obtains cookies from NSE main page).
3. `NSEClient` requests current IPO list.
4. For each IPO, `NSEClient` requests detail (prices, dates, subscription info).
5. `NSEClient` requests past IPO list.
6. `StateManager` updates state based on fetched details, and transitions states.
7. `discord_notifier.py` sends notifications to Discord.
8. State is saved back to `state.json`.

## Code Layout
- `D:\kaniamutan\Desktop\antigravity folder\ipo\nse_client.py` (main client logic)
- `D:\kaniamutan\Desktop\antigravity folder\ipo\ipo_monitor.py` (orchestrator logic)
- `D:\kaniamutan\Desktop\antigravity folder\ipo\.github\workflows\ipo_monitor.yml` (GitHub Actions workflow)
- `D:\kaniamutan\Desktop\antigravity folder\ipo\requirements.txt` (dependencies)

## Milestones
| # | Name | Scope | Dependencies | Status |
|---|------|-------|-------------|--------|
| 1 | Robust Redundant Fetching | Implement dual-strategy (primary + fallback) request mechanism in `nse_client.py` and run inside GHA | None | IN_PROGRESS |

## Interface Contracts
### `NSEClient` ↔ `ipo_monitor.py`
- `NSEClient` must expose the same public methods:
  - `initialize_session() -> bool`
  - `get_current_issues() -> list[dict]`
  - `get_ipo_detail(symbol: str, series: str = "EQ") -> Optional[dict]`
  - `get_past_issues() -> list[dict]`
  - `get_listing_day_price(symbol: str, listing_date_str: str) -> Optional[dict]`
  - `close()`
- Signature and return type of these public methods must remain backward-compatible to avoid breaking existing logic in `ipo_monitor.py`.
- Internal implementation details of `_request_with_retry` and session management can be modified to add the primary and fallback fetching mechanisms.
