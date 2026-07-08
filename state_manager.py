"""State management for IPO tracking.

Manages a JSON state file that tracks IPO lifecycle, subscription history,
and notification status to prevent duplicate alerts.
"""

import json
import logging
import os
from datetime import datetime, date
from typing import Any, Optional

from config import STATE_FILE, IPOState, SUBSCRIPTION_MILESTONES

logger = logging.getLogger(__name__)


def _default_ipo_entry() -> dict:
    """Return a default IPO tracking entry."""
    return {
        "state": IPOState.OPEN,
        "company_name": "Unknown",
        "issue_price_band": {"min": None, "max": None},
        "lot_size": None,
        "open_date": None,
        "close_date": None,
        "series": "EQ",
        "last_subscription": {
            "total": None,
            "retail": None,
            "qib": None,
            "nii": None,
            "employee": None,
        },
        "subscription_history": [],
        "notifications_sent": {
            "open_alert": False,
            "close_alert": False,
            "listing_alert": False,
            "upcoming_alert": False,
            "daily": [],
            "milestones_notified": [],
        },
        "listing_price": None,
        "listing_close_price": None,
        "listing_date": None,
        "listing_gain_pct": None,
    }


class StateManager:
    """Manages persistent state for tracked IPOs.
    
    State is stored as a JSON file with the following structure:
    {
        "tracked_ipos": { "SYMBOL": { ...ipo_data... } },
        "last_run": "ISO timestamp"
    }
    """

    def __init__(self, state_file: str = STATE_FILE):
        self.state_file = state_file
        self.state: dict = {"tracked_ipos": {}, "last_run": None}
        self.load()

    def load(self) -> None:
        """Load state from the JSON file. Creates empty state if file doesn't exist."""
        if os.path.exists(self.state_file):
            try:
                with open(self.state_file, 'r', encoding='utf-8') as f:
                    self.state = json.load(f)
                logger.info(f"Loaded state with {len(self.state.get('tracked_ipos', {}))} tracked IPOs")
            except (json.JSONDecodeError, IOError) as e:
                logger.error(f"Error loading state file: {e}. Starting with empty state.")
                self.state = {"tracked_ipos": {}, "last_run": None}
        else:
            logger.info("No state file found. Starting fresh.")
            self.state = {"tracked_ipos": {}, "last_run": None}

    def save(self) -> None:
        """Save current state to the JSON file."""
        self.state["last_run"] = datetime.now().isoformat()
        try:
            with open(self.state_file, 'w', encoding='utf-8') as f:
                json.dump(self.state, f, indent=2, ensure_ascii=False)
            logger.info("State saved successfully")
        except IOError as e:
            logger.error(f"Error saving state file: {e}")

    @property
    def tracked_ipos(self) -> dict:
        """Get the tracked IPOs dictionary."""
        return self.state.setdefault("tracked_ipos", {})

    def get_ipo(self, symbol: str) -> Optional[dict]:
        """Get tracking data for a specific IPO symbol."""
        return self.tracked_ipos.get(symbol)

    def upsert_ipo(self, symbol: str, **kwargs) -> dict:
        """Create or update an IPO tracking entry.
        
        Args:
            symbol: The IPO symbol.
            **kwargs: Fields to set/update in the IPO entry.
            
        Returns:
            The updated IPO entry.
        """
        if symbol not in self.tracked_ipos:
            self.tracked_ipos[symbol] = _default_ipo_entry()
            logger.info(f"New IPO tracked: {symbol}")
        
        entry = self.tracked_ipos[symbol]
        
        for key, value in kwargs.items():
            if key in entry:
                if isinstance(entry[key], dict) and isinstance(value, dict):
                    entry[key].update(value)
                else:
                    entry[key] = value
            else:
                entry[key] = value
        
        return entry

    def update_subscription(
        self, symbol: str, subscription_data: dict[str, Optional[float]]
    ) -> bool:
        """Update subscription data and record in history.
        
        Args:
            symbol: The IPO symbol.
            subscription_data: Dict with 'total', 'retail', 'qib', 'nii', 'employee' values.
            
        Returns:
            True if subscription data changed significantly, False otherwise.
        """
        entry = self.get_ipo(symbol)
        if not entry:
            logger.warning(f"Cannot update subscription for untracked IPO: {symbol}")
            return False
        
        old_total = entry["last_subscription"].get("total")
        new_total = subscription_data.get("total")
        
        # Update current subscription
        entry["last_subscription"].update(subscription_data)
        
        # Record in history
        today_str = date.today().isoformat()
        history = entry["subscription_history"]
        
        # Replace today's entry if exists, otherwise append
        history_entry = {
            "date": today_str,
            **{k: v for k, v in subscription_data.items() if v is not None}
        }
        
        updated = False
        for i, h in enumerate(history):
            if h.get("date") == today_str:
                history[i] = history_entry
                updated = True
                break
        
        if not updated:
            history.append(history_entry)
        
        # Check if change is significant (for notification purposes)
        if old_total is None and new_total is not None:
            return True
        if old_total is not None and new_total is not None:
            # Consider significant if changed by more than 0.5x or crossed a milestone
            diff = abs(new_total - old_total)
            milestones = [1, 3, 5, 10, 20, 50, 100]
            for m in milestones:
                if old_total < m <= new_total:
                    return True
            return diff >= 0.5
        
        return False

    def is_daily_notified(self, symbol: str) -> bool:
        """Check if daily notification was already sent today for this IPO."""
        entry = self.get_ipo(symbol)
        if not entry:
            return False
        
        today_str = date.today().isoformat()
        return today_str in entry["notifications_sent"].get("daily", [])

    def mark_daily_notified(self, symbol: str) -> None:
        """Mark that daily notification was sent today for this IPO."""
        entry = self.get_ipo(symbol)
        if entry:
            daily = entry["notifications_sent"].setdefault("daily", [])
            today_str = date.today().isoformat()
            if today_str not in daily:
                daily.append(today_str)

    def is_notified(self, symbol: str, notification_type: str) -> bool:
        """Check if a specific notification type was already sent.
        
        Args:
            symbol: The IPO symbol.
            notification_type: One of 'open_alert', 'close_alert', 'listing_alert'.
        """
        entry = self.get_ipo(symbol)
        if not entry:
            return False
        return entry["notifications_sent"].get(notification_type, False)

    def mark_notified(self, symbol: str, notification_type: str) -> None:
        """Mark a specific notification type as sent."""
        entry = self.get_ipo(symbol)
        if entry:
            entry["notifications_sent"][notification_type] = True

    def check_milestone_crossed(
        self, symbol: str, new_total: Optional[float]
    ) -> list[int]:
        """Check if subscription total crossed any milestones.
        
        Args:
            symbol: The IPO symbol.
            new_total: The current total subscription multiplier.
            
        Returns:
            List of newly crossed milestones (e.g., [1, 3, 5]).
        """
        if new_total is None:
            return []
        
        entry = self.get_ipo(symbol)
        if not entry:
            return []
        
        already_notified = entry["notifications_sent"].setdefault("milestones_notified", [])
        newly_crossed = []
        
        for milestone in SUBSCRIPTION_MILESTONES:
            if new_total >= milestone and milestone not in already_notified:
                newly_crossed.append(milestone)
                already_notified.append(milestone)
        
        return newly_crossed

    def transition_state(self, symbol: str, new_state: str) -> Optional[str]:
        """Transition an IPO to a new lifecycle state.
        
        Args:
            symbol: The IPO symbol.
            new_state: The new state (from IPOState constants).
            
        Returns:
            The previous state, or None if IPO not found.
        """
        entry = self.get_ipo(symbol)
        if not entry:
            logger.warning(f"Cannot transition untracked IPO: {symbol}")
            return None
        
        old_state = entry["state"]
        entry["state"] = new_state
        logger.info(f"{symbol}: State transition {old_state} → {new_state}")
        return old_state

    def get_ipos_by_state(self, state: str) -> dict[str, dict]:
        """Get all IPOs in a specific lifecycle state."""
        return {
            sym: data for sym, data in self.tracked_ipos.items()
            if data.get("state") == state
        }

    def get_active_ipos(self) -> dict[str, dict]:
        """Get all IPOs that are not archived (OPEN, CLOSED, or LISTED)."""
        active_states = {IPOState.UPCOMING, IPOState.OPEN, IPOState.CLOSED, IPOState.LISTED}
        return {
            sym: data for sym, data in self.tracked_ipos.items()
            if data.get("state") in active_states
        }

    def archive_old_ipos(self, days_after_listing: int = 7) -> list[str]:
        """Archive IPOs that listed more than N days ago.
        
        Args:
            days_after_listing: Days after listing before archiving.
            
        Returns:
            List of archived symbols.
        """
        archived = []
        today = date.today()
        
        for symbol, data in list(self.tracked_ipos.items()):
            if data.get("state") == IPOState.LISTED and data.get("listing_date"):
                try:
                    # Try multiple date formats
                    listing_date_str = data["listing_date"]
                    listing_date = None
                    for fmt in ('%Y-%m-%d', '%d-%b-%Y', '%d-%B-%Y', '%d/%m/%Y'):
                        try:
                            listing_date = datetime.strptime(listing_date_str, fmt).date()
                            break
                        except ValueError:
                            continue
                    
                    if listing_date and (today - listing_date).days > days_after_listing:
                        data["state"] = IPOState.ARCHIVED
                        archived.append(symbol)
                        logger.info(f"{symbol}: Archived (listed {(today - listing_date).days} days ago)")
                        
                except Exception as e:
                    logger.warning(f"Error checking listing date for {symbol}: {e}")
        
        return archived

    def cleanup_archived(self) -> int:
        """Remove archived IPOs that are older than 30 days.
        
        Returns:
            Number of entries removed.
        """
        removed = 0
        for symbol in list(self.tracked_ipos.keys()):
            if self.tracked_ipos[symbol].get("state") == IPOState.ARCHIVED:
                del self.tracked_ipos[symbol]
                removed += 1
        
        if removed:
            logger.info(f"Cleaned up {removed} archived IPO entries")
        return removed
