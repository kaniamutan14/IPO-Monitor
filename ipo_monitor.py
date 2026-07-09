"""IPO Discord Monitor — Main Orchestrator.

Fetches IPO data from NSE India, tracks lifecycle states,
and sends Discord notifications for subscription updates and listing results.

Usage:
    python ipo_monitor.py              # Normal daily run
    python ipo_monitor.py --dry-run    # Preview without sending Discord notifications
    python ipo_monitor.py --verbose    # Verbose logging
"""

import argparse
import logging
import sys
from datetime import datetime, date
from typing import Optional

from config import IPOState, DISCORD_WEBHOOK_URL
from nse_client import NSEClient, NSEClientError
from state_manager import StateManager
import discord_notifier as notifier

# Configure logging
def setup_logging(verbose: bool = False) -> None:
    """Configure logging with appropriate level and format."""
    level = logging.DEBUG if verbose else logging.INFO
    logging.basicConfig(
        level=level,
        format="%(asctime)s | %(levelname)-7s | %(name)s | %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )


logger = logging.getLogger(__name__)


def compute_day_number(
    open_date_str: Optional[str], close_date_str: Optional[str]
) -> tuple[Optional[int], Optional[int]]:
    """Compute current day number and total days of the bidding window.
    
    Args:
        open_date_str: The IPO open date string.
        close_date_str: The IPO close date string.
        
    Returns:
        Tuple of (current_day_number, total_days) or (None, None).
    """
    if not open_date_str or not close_date_str:
        return None, None
    
    today = date.today()
    
    # Try multiple date formats
    open_date = None
    close_date = None
    for fmt in ('%d-%b-%Y', '%d-%B-%Y', '%Y-%m-%d', '%d/%m/%Y'):
        try:
            open_date = datetime.strptime(open_date_str, fmt).date()
            break
        except ValueError:
            continue
    
    for fmt in ('%d-%b-%Y', '%d-%B-%Y', '%Y-%m-%d', '%d/%m/%Y'):
        try:
            close_date = datetime.strptime(close_date_str, fmt).date()
            break
        except ValueError:
            continue
    
    if not open_date or not close_date:
        return None, None
    
    total_days = (close_date - open_date).days + 1
    current_day = (today - open_date).days + 1
    
    if current_day < 1:
        current_day = 1
    elif current_day > total_days:
        current_day = total_days
    
    return current_day, total_days


def process_current_issues(
    nse: NSEClient, state: StateManager, dry_run: bool = False
) -> int:
    """Process currently open IPO issues.
    
    Fetches current issues from NSE, updates state, and sends notifications.
    
    Args:
        nse: Initialized NSE client.
        state: State manager instance.
        dry_run: If True, log actions but don't send Discord notifications.
        
    Returns:
        Number of notifications sent.
    """
    notifications_sent = 0
    current_issues = nse.get_current_issues()
    
    if not current_issues:
        logger.info("No current IPO issues found on NSE")
        return 0
    
    current_symbols = set()
    
    for issue in current_issues:
        symbol = nse.extract_symbol(issue)
        if not symbol:
            logger.warning(f"Skipping issue with no symbol: {issue}")
            continue
        
        current_symbols.add(symbol)
        company_name = nse.extract_company_name(issue)
        series = nse.extract_series(issue)
        open_date, close_date = nse.extract_dates(issue)
        
        logger.info(f"Processing current issue: {symbol} ({company_name})")
        
        # Determine if this IPO is upcoming (not yet open for bidding)
        is_upcoming = False
        if open_date:
            for fmt in ('%d-%b-%Y', '%d-%B-%Y', '%Y-%m-%d', '%d/%m/%Y'):
                try:
                    open_dt = datetime.strptime(open_date, fmt).date()
                    if open_dt > date.today():
                        is_upcoming = True
                    break
                except ValueError:
                    continue
        
        # Check if this is a new IPO we haven't seen before
        existing = state.get_ipo(symbol)
        is_new = existing is None
        
        # Fetch detailed IPO data
        detail = nse.get_ipo_detail(symbol, series)
        
        if detail:
            price_band = nse.extract_price_band(detail)
            lot_size = nse.extract_lot_size(detail)
            subscription = nse.extract_subscription_data(detail)
        else:
            price_band = (None, None)
            lot_size = None
            subscription = {'total': None, 'retail': None, 'qib': None, 'nii': None, 'employee': None}
            logger.warning(f"Could not fetch detail for {symbol}, using basic info")
        
        # Set appropriate state
        ipo_state = IPOState.UPCOMING if is_upcoming else IPOState.OPEN
        
        # Update state
        state.upsert_ipo(
            symbol,
            state=ipo_state,
            company_name=company_name,
            series=series,
            open_date=open_date,
            close_date=close_date,
            issue_price_band={"min": price_band[0], "max": price_band[1]},
            lot_size=lot_size,
        )
        
        # Handle UPCOMING IPOs
        if is_upcoming:
            if is_new and not state.is_notified(symbol, 'upcoming_alert'):
                logger.info(f"Sending UPCOMING IPO alert for {symbol}")
                if not dry_run:
                    success = notifier.send_upcoming_ipo_alert(
                        symbol=symbol,
                        company_name=company_name,
                        price_band=price_band,
                        lot_size=lot_size,
                        open_date=open_date,
                        close_date=close_date,
                    )
                    if success:
                        state.mark_notified(symbol, 'upcoming_alert')
                        notifications_sent += 1
                else:
                    logger.info(f"[DRY RUN] Would send upcoming alert for {symbol}")
                    notifications_sent += 1
            continue  # Skip subscription updates for upcoming IPOs
        
        # Update subscription data
        sub_changed = state.update_subscription(symbol, subscription)
        
        # Send notifications
        if is_new and not state.is_notified(symbol, 'open_alert'):
            # New IPO — send open alert
            logger.info(f"Sending NEW IPO alert for {symbol}")
            if not dry_run:
                success = notifier.send_open_ipo_alert(
                    symbol=symbol,
                    company_name=company_name,
                    price_band=price_band,
                    lot_size=lot_size,
                    open_date=open_date,
                    close_date=close_date,
                )
                if success:
                    state.mark_notified(symbol, 'open_alert')
                    notifications_sent += 1
            else:
                logger.info(f"[DRY RUN] Would send open alert for {symbol}")
                notifications_sent += 1
        
        # Subscription milestone alerts
        total_sub = subscription.get('total')
        if total_sub is not None:
            milestones_crossed = state.check_milestone_crossed(symbol, total_sub)
            for milestone in milestones_crossed:
                logger.info(f"Subscription milestone {milestone}x crossed for {symbol}")
                if not dry_run:
                    success = notifier.send_milestone_alert(
                        symbol=symbol,
                        company_name=company_name,
                        milestone=milestone,
                        subscription=subscription,
                        close_date=close_date,
                    )
                    if success:
                        notifications_sent += 1
                else:
                    logger.info(f"[DRY RUN] Would send milestone {milestone}x alert for {symbol}")
                    notifications_sent += 1
        
        # Daily subscription update (if not already sent today)
        if not state.is_daily_notified(symbol):
            day_num, total_days = compute_day_number(open_date, close_date)
            
            logger.info(f"Sending subscription update for {symbol}")
            if not dry_run:
                success = notifier.send_subscription_update(
                    symbol=symbol,
                    company_name=company_name,
                    price_band=price_band,
                    lot_size=lot_size,
                    subscription=subscription,
                    open_date=open_date,
                    close_date=close_date,
                    day_number=day_num,
                    total_days=total_days,
                )
                if success:
                    state.mark_daily_notified(symbol)
                    notifications_sent += 1
            else:
                logger.info(f"[DRY RUN] Would send subscription update for {symbol}")
                notifications_sent += 1
    
    # Check for IPOs that were OPEN but are no longer in current issues
    # They may have closed
    for symbol, data in state.get_ipos_by_state(IPOState.OPEN).items():
        if symbol not in current_symbols:
            logger.info(f"{symbol} no longer in current issues — marking as CLOSED")
            state.transition_state(symbol, IPOState.CLOSED)
            
            if not state.is_notified(symbol, 'close_alert'):
                logger.info(f"Sending close alert for {symbol}")
                if not dry_run:
                    success = notifier.send_close_alert(
                        symbol=symbol,
                        company_name=data.get('company_name', 'Unknown'),
                        final_subscription=data.get('last_subscription', {}),
                        price_band=(
                            data.get('issue_price_band', {}).get('min'),
                            data.get('issue_price_band', {}).get('max'),
                        ),
                        lot_size=data.get('lot_size'),
                    )
                    if success:
                        state.mark_notified(symbol, 'close_alert')
                        notifications_sent += 1
                else:
                    logger.info(f"[DRY RUN] Would send close alert for {symbol}")
                    notifications_sent += 1
    
    return notifications_sent


def process_listing_data(
    nse: NSEClient, state: StateManager, dry_run: bool = False
) -> int:
    """Check past issues for listing data of tracked IPOs.
    
    Looks for IPOs that have closed and are awaiting listing,
    then checks if listing data is now available.
    
    Args:
        nse: Initialized NSE client.
        state: State manager instance.
        dry_run: If True, log actions but don't send Discord notifications.
        
    Returns:
        Number of listing notifications sent.
    """
    notifications_sent = 0
    
    # Get IPOs awaiting listing (CLOSED state)
    awaiting_listing = state.get_ipos_by_state(IPOState.CLOSED)
    
    if not awaiting_listing:
        logger.info("No IPOs awaiting listing")
        return 0
    
    logger.info(f"{len(awaiting_listing)} IPO(s) awaiting listing: {list(awaiting_listing.keys())}")
    
    # Fetch past issues from NSE
    past_issues = nse.get_past_issues()
    
    if not past_issues:
        logger.info("No past issues data available from NSE")
        return 0
    
    # Build a lookup by symbol
    past_by_symbol = {}
    for pi in past_issues:
        sym = nse.extract_symbol(pi)
        if sym:
            past_by_symbol[sym] = pi
    
    # Check each awaiting IPO
    for symbol, data in awaiting_listing.items():
        if state.is_notified(symbol, 'listing_alert'):
            continue
        
        if symbol in past_by_symbol:
            listing_info = nse.extract_listing_info(past_by_symbol[symbol])
            
            # Fallback: if past-issues has listing date but no price,
            # try historical equity endpoint for OHLC data
            if not listing_info['listing_price'] and listing_info.get('listing_date'):
                logger.info(f"{symbol}: No listing price in past-issues, trying yfinance...")
                historical = nse.get_listing_day_price(symbol, listing_info['listing_date'])
                if historical and historical.get('open'):
                    listing_info['listing_price'] = historical['open']
                    listing_info['listing_close_price'] = historical.get('close')
                    logger.info(f"{symbol}: Got listing price from historical: {historical['open']}")
            
            if listing_info['listing_price'] and listing_info['listing_price'] > 0:
                logger.info(f"{symbol} has listing data: {listing_info}")
                
                # Update state with listing info
                issue_price = listing_info['issue_price'] or data.get('issue_price_band', {}).get('max')
                listing_price = listing_info['listing_price']
                
                if issue_price and listing_price:
                    gain_pct = ((listing_price - issue_price) / issue_price) * 100
                else:
                    gain_pct = None
                
                state.upsert_ipo(
                    symbol,
                    listing_price=listing_price,
                    listing_close_price=listing_info.get('listing_close_price'),
                    listing_date=listing_info.get('listing_date'),
                    listing_gain_pct=gain_pct,
                )
                state.transition_state(symbol, IPOState.LISTED)
                
                # Send listing notification
                if issue_price and listing_price:
                    logger.info(f"Sending listing alert for {symbol}")
                    if not dry_run:
                        success = notifier.send_listing_alert(
                            symbol=symbol,
                            company_name=data.get('company_name', 'Unknown'),
                            issue_price=issue_price,
                            listing_price=listing_price,
                            lot_size=data.get('lot_size'),
                            final_subscription_total=data.get('last_subscription', {}).get('total'),
                            listing_close_price=listing_info.get('listing_close_price'),
                        )
                        if success:
                            state.mark_notified(symbol, 'listing_alert')
                            notifications_sent += 1
                    else:
                        logger.info(f"[DRY RUN] Would send listing alert for {symbol}")
                        notifications_sent += 1
                else:
                    logger.warning(f"Missing price data for {symbol} listing notification")
    
    return notifications_sent


def generate_weekly_digest(
    state: StateManager, dry_run: bool = False
) -> int:
    """Generate and send a weekly summary digest.
    
    Args:
        state: State manager instance.
        dry_run: If True, log but don't send.
        
    Returns:
        Number of notifications sent (0 or 1).
    """
    logger.info("Generating weekly digest...")
    
    open_ipos = []
    for sym, data in state.get_ipos_by_state(IPOState.OPEN).items():
        open_ipos.append({
            'symbol': sym,
            'company_name': data.get('company_name', 'Unknown'),
            'subscription_total': data.get('last_subscription', {}).get('total'),
            'close_date': data.get('close_date'),
        })
    
    upcoming_ipos = []
    for sym, data in state.get_ipos_by_state(IPOState.UPCOMING).items():
        upcoming_ipos.append({
            'symbol': sym,
            'company_name': data.get('company_name', 'Unknown'),
            'open_date': data.get('open_date'),
        })
    
    closed_ipos = []
    for sym, data in state.get_ipos_by_state(IPOState.CLOSED).items():
        closed_ipos.append({
            'symbol': sym,
            'company_name': data.get('company_name', 'Unknown'),
            'subscription_total': data.get('last_subscription', {}).get('total'),
        })
    
    listed_ipos = []
    for sym, data in state.get_ipos_by_state(IPOState.LISTED).items():
        issue_price = data.get('issue_price_band', {}).get('max')
        listing_price = data.get('listing_price')
        lot_size = data.get('lot_size')
        gain_pct = data.get('listing_gain_pct')
        
        net_pnl = None
        if issue_price and listing_price and lot_size:
            from discord_notifier import calculate_selling_charges
            gross = (listing_price - issue_price) * lot_size
            charges = calculate_selling_charges(listing_price, lot_size)
            net_pnl = gross - charges['total']
        
        listed_ipos.append({
            'symbol': sym,
            'company_name': data.get('company_name', 'Unknown'),
            'issue_price': issue_price,
            'listing_price': listing_price,
            'gain_pct': gain_pct,
            'net_pnl': net_pnl,
        })
    
    logger.info(f"Digest: {len(open_ipos)} open, {len(upcoming_ipos)} upcoming, "
                f"{len(closed_ipos)} closed, {len(listed_ipos)} listed")
    
    if not dry_run:
        success = notifier.send_weekly_digest(
            open_ipos=open_ipos,
            closed_ipos=closed_ipos,
            listed_ipos=listed_ipos,
            upcoming_ipos=upcoming_ipos,
        )
        return 1 if success else 0
    else:
        logger.info("[DRY RUN] Would send weekly digest")
        return 1


def main() -> int:
    """Main entry point for the IPO monitor.
    
    Returns:
        Exit code (0 for success, 1 for error).
    """
    parser = argparse.ArgumentParser(
        description="IPO Discord Monitor — Tracks NSE IPOs and sends Discord notifications"
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Preview actions without sending Discord notifications",
    )
    parser.add_argument(
        "--verbose", "-v",
        action="store_true",
        help="Enable verbose/debug logging",
    )
    parser.add_argument(
        "--weekly-digest",
        action="store_true",
        help="Generate and send a weekly summary digest",
    )
    args = parser.parse_args()
    
    setup_logging(verbose=args.verbose)
    
    logger.info("=" * 60)
    logger.info("IPO Discord Monitor — Starting")
    logger.info(f"Time: {datetime.now().isoformat()}")
    mode_parts = []
    if args.dry_run:
        mode_parts.append("DRY RUN")
    if args.weekly_digest:
        mode_parts.append("WEEKLY DIGEST")
    if not mode_parts:
        mode_parts.append("LIVE")
    logger.info(f"Mode: {' | '.join(mode_parts)}")
    logger.info("=" * 60)
    
    # Validate Discord webhook
    if not args.dry_run and not DISCORD_WEBHOOK_URL:
        logger.error("DISCORD_WEBHOOK_URL not set! Set it in .env or environment.")
        logger.error("Use --dry-run to test without Discord.")
        return 1
    
    # Initialize components
    nse = NSEClient()
    state = StateManager()
    total_notifications = 0
    
    try:
        # Initialize NSE session
        if not nse.initialize_session():
            error_msg = "Failed to initialize NSE session. NSE may be blocking requests."
            logger.error(error_msg)
            if not args.dry_run:
                notifier.send_error_alert(
                    "NSE Session Failed",
                    error_msg + "\nThe script could not establish a session with NSE India. "
                    "This may be due to anti-bot protection or network issues.",
                )
            return 1
        
        # Process current (open) IPOs
        logger.info("--- Processing Current IPOs ---")
        n = process_current_issues(nse, state, dry_run=args.dry_run)
        total_notifications += n
        logger.info(f"Current issues: {n} notification(s) sent")
        
        # Process listing data for closed IPOs
        logger.info("--- Checking Listing Data ---")
        n = process_listing_data(nse, state, dry_run=args.dry_run)
        total_notifications += n
        logger.info(f"Listing checks: {n} notification(s) sent")
        
        # Weekly digest (if requested)
        if args.weekly_digest:
            logger.info("--- Generating Weekly Digest ---")
            n = generate_weekly_digest(state, dry_run=args.dry_run)
            total_notifications += n
            logger.info(f"Weekly digest: {n} notification(s) sent")
        
        # Archive old IPOs
        archived = state.archive_old_ipos(days_after_listing=7)
        if archived:
            logger.info(f"Archived {len(archived)} old IPO(s): {archived}")
        
        # Cleanup very old archived entries
        cleaned = state.cleanup_archived()
        
        # If no IPOs active and no notifications sent, optionally notify
        active_count = len(state.get_active_ipos())
        if active_count == 0 and total_notifications == 0:
            logger.info("No active IPOs and no notifications to send")
            # Uncomment below if you want a daily 'no IPOs' notification:
            # if not args.dry_run:
            #     notifier.send_no_active_ipos()
        
        logger.info(f"Active IPOs tracked: {active_count}")
        logger.info(f"Total notifications sent: {total_notifications}")
        
    except Exception as e:
        logger.exception(f"Unexpected error: {e}")
        if not args.dry_run:
            notifier.send_error_alert(
                "IPO Monitor Error",
                f"Unexpected error during execution:\n{str(e)}",
            )
        return 1
    
    finally:
        # Persist only real runs. Dry-run mutates state in memory for preview, but
        # saving it would suppress future first-seen notifications in live mode.
        if args.dry_run:
            logger.info("Dry-run mode: state changes were not saved")
        else:
            state.save()
        nse.close()
    
    logger.info("IPO Monitor completed successfully")
    return 0


if __name__ == "__main__":
    sys.exit(main())
