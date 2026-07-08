"""Discord webhook notifier for IPO events.

Sends rich embed notifications for IPO subscription updates,
listing results, and error alerts via Discord webhooks.
"""

import logging
import time
from datetime import datetime, timezone
from typing import Any, Optional

try:
    import requests
except ImportError:
    requests = None

from config import (
    DISCORD_WEBHOOK_URL,
    DP_CHARGES,
    STT_SELL_RATE,
    TRANSACTION_CHARGES_RATE,
    SEBI_CHARGES_RATE,
    STAMP_DUTY_RATE,
    GST_RATE,
)

logger = logging.getLogger(__name__)

# Discord embed color constants
COLOR_GREEN = 0x00C853   # Positive / open
COLOR_RED = 0xFF1744     # Negative / loss
COLOR_BLUE = 0x2979FF    # Info / update
COLOR_GOLD = 0xFFD600    # Highlight / milestone
COLOR_ORANGE = 0xFF6D00  # Warning
COLOR_PURPLE = 0xAA00FF  # Listing


def _fmt_price(value: Optional[float]) -> str:
    """Format a price value as ₹X,XXX.XX"""
    if value is None:
        return "N/A"
    if value == int(value):
        return f"₹{int(value):,}"
    return f"₹{value:,.2f}"


def _fmt_sub(value: Optional[float]) -> str:
    """Format a subscription multiplier with trend indicator."""
    if value is None:
        return "N/A"
    if value >= 10:
        emoji = "🔥"
    elif value >= 1:
        emoji = "📈"
    elif value > 0:
        emoji = "📊"
    else:
        emoji = "⚪"
    return f"{value:.2f}x {emoji}"


def _fmt_pct(value: Optional[float]) -> str:
    """Format a percentage with sign and emoji."""
    if value is None:
        return "N/A"
    emoji = "📈" if value >= 0 else "📉"
    sign = "+" if value >= 0 else ""
    return f"{sign}{value:.1f}% {emoji}"


def calculate_selling_charges(
    listing_price: float, quantity: int
) -> dict[str, float]:
    """Calculate estimated selling charges for IPO shares.
    
    Args:
        listing_price: The listing/selling price per share.
        quantity: Number of shares (lot size).
        
    Returns:
        Dict with individual charge components and total.
    """
    turnover = listing_price * quantity
    
    stt = turnover * STT_SELL_RATE
    transaction_charges = turnover * TRANSACTION_CHARGES_RATE
    sebi_charges = turnover * SEBI_CHARGES_RATE
    stamp_duty = turnover * STAMP_DUTY_RATE
    gst = (transaction_charges + sebi_charges) * GST_RATE
    dp_charges = DP_CHARGES  # Flat per scrip
    
    total = stt + transaction_charges + sebi_charges + stamp_duty + gst + dp_charges
    
    return {
        "dp_charges": round(dp_charges, 2),
        "stt": round(stt, 2),
        "transaction_charges": round(transaction_charges, 2),
        "sebi_charges": round(sebi_charges, 2),
        "stamp_duty": round(stamp_duty, 2),
        "gst": round(gst, 2),
        "total": round(total, 2),
    }


def _send_webhook(payload: dict) -> bool:
    """Send a payload to the Discord webhook.
    
    Args:
        payload: The Discord webhook JSON payload.
        
    Returns:
        True if sent successfully, False otherwise.
    """
    if not DISCORD_WEBHOOK_URL:
        logger.error("DISCORD_WEBHOOK_URL not configured!")
        return False

    if requests is None:
        logger.error("requests is not installed; cannot send Discord webhook.")
        return False
    
    try:
        response = requests.post(
            DISCORD_WEBHOOK_URL,
            json=payload,
            timeout=10,
        )
        
        if response.status_code == 204:
            logger.info("Discord notification sent successfully")
            return True
        elif response.status_code == 429:
            # Rate limited
            retry_after = response.json().get("retry_after", 5)
            logger.warning(f"Discord rate limited. Retry after {retry_after}s")
            time.sleep(retry_after)
            # Retry once
            response = requests.post(DISCORD_WEBHOOK_URL, json=payload, timeout=10)
            return response.status_code == 204
        else:
            logger.error(f"Discord webhook failed: {response.status_code} - {response.text}")
            return False
            
    except requests.RequestException as e:
        logger.error(f"Discord webhook error: {e}")
        return False


def send_open_ipo_alert(
    symbol: str,
    company_name: str,
    price_band: tuple[Optional[float], Optional[float]],
    lot_size: Optional[int],
    open_date: Optional[str],
    close_date: Optional[str],
) -> bool:
    """Send notification for a newly opened IPO."""
    min_price, max_price = price_band
    min_investment = "N/A"
    if lot_size and max_price:
        min_investment = _fmt_price(lot_size * max_price)
    
    embed = {
        "title": f"🆕 NEW IPO OPEN — {company_name}",
        "description": f"**{symbol}** is now open for bidding!",
        "color": COLOR_GREEN,
        "fields": [
            {
                "name": "💰 Price Band",
                "value": f"{_fmt_price(min_price)} - {_fmt_price(max_price)}",
                "inline": True,
            },
            {
                "name": "📦 Lot Size",
                "value": f"{lot_size or 'N/A'} shares",
                "inline": True,
            },
            {
                "name": "💵 Min Investment",
                "value": min_investment,
                "inline": True,
            },
            {
                "name": "📅 Bidding Window",
                "value": f"{open_date or 'N/A'} → {close_date or 'N/A'}",
                "inline": False,
            },
        ],
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "footer": {"text": "IPO Monitor • NSE Data"},
    }
    
    return _send_webhook({"embeds": [embed]})


def send_subscription_update(
    symbol: str,
    company_name: str,
    price_band: tuple[Optional[float], Optional[float]],
    lot_size: Optional[int],
    subscription: dict[str, Optional[float]],
    open_date: Optional[str],
    close_date: Optional[str],
    day_number: Optional[int] = None,
    total_days: Optional[int] = None,
) -> bool:
    """Send daily subscription update for an open IPO."""
    min_price, max_price = price_band
    min_investment = "N/A"
    if lot_size and max_price:
        min_investment = _fmt_price(lot_size * max_price)
    
    day_str = ""
    if day_number and total_days:
        day_str = f" — Day {day_number}/{total_days}"
    
    sub_lines = []
    for cat, label in [('retail', 'Retail'), ('nii', 'NII'), ('qib', 'QIB'), ('employee', 'Employee')]:
        val = subscription.get(cat)
        if val is not None:
            sub_lines.append(f"**{label}:** {_fmt_sub(val)}")
    
    total_sub = subscription.get('total')
    if total_sub is not None:
        sub_lines.append(f"\n**Overall Total:** {_fmt_sub(total_sub)}")
    
    subscription_text = "\n".join(sub_lines) if sub_lines else "No subscription data available"
    
    embed = {
        "title": f"📊 IPO SUBSCRIPTION UPDATE{day_str}",
        "description": f"**{company_name}** ({symbol})",
        "color": COLOR_BLUE,
        "fields": [
            {
                "name": "💰 Price Band",
                "value": f"{_fmt_price(min_price)} - {_fmt_price(max_price)}",
                "inline": True,
            },
            {
                "name": "📦 Lot Size",
                "value": f"{lot_size or 'N/A'} shares",
                "inline": True,
            },
            {
                "name": "💵 Min Investment",
                "value": min_investment,
                "inline": True,
            },
            {
                "name": "📊 Subscription Status",
                "value": subscription_text,
                "inline": False,
            },
            {
                "name": "📅 Closes",
                "value": close_date or "N/A",
                "inline": True,
            },
        ],
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "footer": {"text": "IPO Monitor • NSE Data"},
    }
    
    return _send_webhook({"embeds": [embed]})


def send_close_alert(
    symbol: str,
    company_name: str,
    final_subscription: dict[str, Optional[float]],
    price_band: tuple[Optional[float], Optional[float]],
    lot_size: Optional[int],
) -> bool:
    """Send notification when IPO bidding closes with final subscription numbers."""
    sub_lines = []
    for cat, label in [('retail', 'Retail'), ('nii', 'NII'), ('qib', 'QIB'), ('employee', 'Employee')]:
        val = final_subscription.get(cat)
        if val is not None:
            sub_lines.append(f"**{label}:** {_fmt_sub(val)}")
    
    total_sub = final_subscription.get('total')
    if total_sub is not None:
        sub_lines.append(f"\n**Overall Total:** {_fmt_sub(total_sub)}")
    
    subscription_text = "\n".join(sub_lines) if sub_lines else "No data"
    
    embed = {
        "title": f"🔒 IPO BIDDING CLOSED — {company_name}",
        "description": f"**{symbol}** bidding has closed. Awaiting allotment & listing.",
        "color": COLOR_GOLD,
        "fields": [
            {
                "name": "📊 Final Subscription",
                "value": subscription_text,
                "inline": False,
            },
            {
                "name": "💰 Price Band",
                "value": f"{_fmt_price(price_band[0])} - {_fmt_price(price_band[1])}",
                "inline": True,
            },
            {
                "name": "📦 Lot Size",
                "value": f"{lot_size or 'N/A'} shares",
                "inline": True,
            },
        ],
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "footer": {"text": "IPO Monitor • NSE Data"},
    }
    
    return _send_webhook({"embeds": [embed]})


def send_listing_alert(
    symbol: str,
    company_name: str,
    issue_price: float,
    listing_price: float,
    lot_size: Optional[int],
    final_subscription_total: Optional[float] = None,
    listing_close_price: Optional[float] = None,
) -> bool:
    """Send listing day result with P&L breakdown including selling charges."""
    gain_per_share = listing_price - issue_price
    gain_pct = ((listing_price - issue_price) / issue_price) * 100
    
    # Determine color based on gain/loss
    if gain_pct >= 20:
        color = COLOR_GREEN
        result_emoji = "🚀"
    elif gain_pct >= 0:
        color = COLOR_BLUE
        result_emoji = "📈"
    elif gain_pct >= -10:
        color = COLOR_ORANGE
        result_emoji = "📉"
    else:
        color = COLOR_RED
        result_emoji = "💔"
    
    # P&L fields
    fields = [
        {"name": "💰 Issue Price", "value": _fmt_price(issue_price), "inline": True},
        {"name": f"{result_emoji} Listing Price", "value": _fmt_price(listing_price), "inline": True},
        {"name": "📊 Change", "value": _fmt_pct(gain_pct), "inline": True},
    ]
    
    if listing_close_price:
        close_gain_pct = ((listing_close_price - issue_price) / issue_price) * 100
        fields.append({
            "name": "🔚 Listing Day Close",
            "value": f"{_fmt_price(listing_close_price)} ({_fmt_pct(close_gain_pct)})",
            "inline": True,
        })
    
    if lot_size:
        gross_gain_lot = gain_per_share * lot_size
        
        # Calculate selling charges
        charges = calculate_selling_charges(listing_price, lot_size)
        net_gain_lot = gross_gain_lot - charges["total"]
        
        fields.append({
            "name": "📦 Per Lot P&L (Gross)",
            "value": f"{_fmt_price(gross_gain_lot)} ({lot_size} shares)",
            "inline": False,
        })
        
        # Selling charges breakdown
        charges_text = (
            f"DP Charges: {_fmt_price(charges['dp_charges'])}\n"
            f"STT (0.025%): {_fmt_price(charges['stt'])}\n"
            f"Txn Charges: {_fmt_price(charges['transaction_charges'])}\n"
            f"SEBI: {_fmt_price(charges['sebi_charges'])}\n"
            f"Stamp Duty: {_fmt_price(charges['stamp_duty'])}\n"
            f"GST: {_fmt_price(charges['gst'])}\n"
            f"**Total: {_fmt_price(charges['total'])}**"
        )
        
        fields.append({
            "name": "🧾 Estimated Selling Charges",
            "value": charges_text,
            "inline": True,
        })
        
        fields.append({
            "name": "💵 Final Net P&L / Lot",
            "value": f"**{_fmt_price(net_gain_lot)}**",
            "inline": True,
        })
    
    if final_subscription_total is not None:
        fields.append({
            "name": "📊 Final Subscription Was",
            "value": _fmt_sub(final_subscription_total),
            "inline": True,
        })
    
    embed = {
        "title": f"🔔 IPO LISTED — {company_name}",
        "description": f"**{symbol}** has listed on the exchange!",
        "color": color,
        "fields": fields,
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "footer": {"text": "IPO Monitor • NSE Data"},
    }
    
    return _send_webhook({"embeds": [embed]})


def send_upcoming_ipo_alert(
    symbol: str,
    company_name: str,
    price_band: tuple[Optional[float], Optional[float]],
    lot_size: Optional[int],
    open_date: Optional[str],
    close_date: Optional[str],
) -> bool:
    """Send notification for a newly announced upcoming IPO."""
    min_price, max_price = price_band
    min_investment = "N/A"
    if lot_size and max_price:
        min_investment = _fmt_price(lot_size * max_price)
    
    embed = {
        "title": f"📢 NEW IPO ANNOUNCED — {company_name}",
        "description": f"**{symbol}** has been announced! Bidding opens on **{open_date or 'TBA'}**.",
        "color": COLOR_GOLD,
        "fields": [
            {
                "name": "💰 Price Band",
                "value": f"{_fmt_price(min_price)} - {_fmt_price(max_price)}",
                "inline": True,
            },
            {
                "name": "📦 Lot Size",
                "value": f"{lot_size or 'N/A'} shares",
                "inline": True,
            },
            {
                "name": "💵 Min Investment",
                "value": min_investment,
                "inline": True,
            },
            {
                "name": "📅 Bidding Window",
                "value": f"{open_date or 'TBA'} → {close_date or 'TBA'}",
                "inline": False,
            },
        ],
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "footer": {"text": "IPO Monitor • NSE Data"},
    }
    
    return _send_webhook({"embeds": [embed]})


def send_milestone_alert(
    symbol: str,
    company_name: str,
    milestone: int,
    subscription: dict[str, Optional[float]],
    close_date: Optional[str],
) -> bool:
    """Send alert when subscription crosses a milestone threshold."""
    total_sub = subscription.get('total')
    
    # Build subscription breakdown
    sub_lines = []
    for cat, label in [('retail', 'Retail'), ('nii', 'NII'), ('qib', 'QIB'), ('employee', 'Employee')]:
        val = subscription.get(cat)
        if val is not None:
            sub_lines.append(f"**{label}:** {_fmt_sub(val)}")
    
    if total_sub is not None:
        sub_lines.append(f"\n**Overall Total:** {_fmt_sub(total_sub)}")
    
    subscription_text = "\n".join(sub_lines) if sub_lines else "No data"
    
    # Milestone emoji escalation
    if milestone >= 50:
        emoji = "🚀"
    elif milestone >= 10:
        emoji = "🔥"
    elif milestone >= 5:
        emoji = "⚡"
    else:
        emoji = "🎯"
    
    embed = {
        "title": f"{emoji} SUBSCRIPTION MILESTONE — {company_name}",
        "description": f"**{symbol}** total subscription just crossed **{milestone}x**!",
        "color": COLOR_GOLD if milestone >= 10 else COLOR_BLUE,
        "fields": [
            {
                "name": "📊 Subscription Breakdown",
                "value": subscription_text,
                "inline": False,
            },
            {
                "name": "📅 Closes",
                "value": close_date or "N/A",
                "inline": True,
            },
        ],
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "footer": {"text": "IPO Monitor • NSE Data"},
    }
    
    return _send_webhook({"embeds": [embed]})


def send_weekly_digest(
    open_ipos: list[dict],
    closed_ipos: list[dict],
    listed_ipos: list[dict],
    upcoming_ipos: list[dict],
) -> bool:
    """Send a weekly summary digest of all tracked IPOs.
    
    Args:
        open_ipos: List of dicts with keys: symbol, company_name, subscription_total, close_date
        closed_ipos: List of dicts with keys: symbol, company_name, subscription_total
        listed_ipos: List of dicts with keys: symbol, company_name, issue_price, listing_price, gain_pct, net_pnl
        upcoming_ipos: List of dicts with keys: symbol, company_name, open_date
    """
    total_active = len(open_ipos) + len(closed_ipos) + len(listed_ipos) + len(upcoming_ipos)
    
    description_parts = [
        f"📊 Open IPOs: **{len(open_ipos)}**",
        f"📢 Upcoming: **{len(upcoming_ipos)}**",
        f"🔒 Awaiting Listing: **{len(closed_ipos)}**",
        f"🔔 Listed This Week: **{len(listed_ipos)}**",
    ]
    
    fields = []
    
    # Upcoming IPOs section
    if upcoming_ipos:
        lines = []
        for ipo in upcoming_ipos:
            lines.append(f"📢 **{ipo['company_name']}** ({ipo['symbol']})\n    Opens: {ipo.get('open_date', 'TBA')}")
        fields.append({
            "name": "📢 Upcoming IPOs",
            "value": "\n".join(lines)[:1024],
            "inline": False,
        })
    
    # Open IPOs section
    if open_ipos:
        lines = []
        for ipo in open_ipos:
            sub = ipo.get('subscription_total')
            sub_str = f"{sub:.2f}x" if sub else "N/A"
            lines.append(f"🟢 **{ipo['company_name']}** ({ipo['symbol']})\n    Sub: {sub_str} | Closes: {ipo.get('close_date', 'N/A')}")
        fields.append({
            "name": "🟢 Open for Bidding",
            "value": "\n".join(lines)[:1024],
            "inline": False,
        })
    
    # Closed IPOs section
    if closed_ipos:
        lines = []
        for ipo in closed_ipos:
            sub = ipo.get('subscription_total')
            sub_str = f"{sub:.2f}x" if sub else "N/A"
            lines.append(f"🔒 **{ipo['company_name']}** ({ipo['symbol']})\n    Final Sub: {sub_str} | Listing Expected")
        fields.append({
            "name": "🔒 Awaiting Listing",
            "value": "\n".join(lines)[:1024],
            "inline": False,
        })
    
    # Listed IPOs section
    if listed_ipos:
        lines = []
        for ipo in listed_ipos:
            gain_str = _fmt_pct(ipo.get('gain_pct'))
            pnl = ipo.get('net_pnl')
            pnl_str = _fmt_price(pnl) if pnl else "N/A"
            lines.append(
                f"🔔 **{ipo['company_name']}** ({ipo['symbol']})\n"
                f"    {_fmt_price(ipo.get('issue_price'))} → {_fmt_price(ipo.get('listing_price'))} ({gain_str})\n"
                f"    Net P&L/Lot: {pnl_str}"
            )
        fields.append({
            "name": "🔔 Recently Listed",
            "value": "\n".join(lines)[:1024],
            "inline": False,
        })
    
    if not fields:
        fields.append({
            "name": "ℹ️ Status",
            "value": "No IPO activity this week.",
            "inline": False,
        })
    
    from datetime import date as _date
    embed = {
        "title": f"📋 WEEKLY IPO DIGEST — {_date.today().strftime('%d-%b-%Y')}",
        "description": "\n".join(description_parts),
        "color": COLOR_PURPLE,
        "fields": fields,
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "footer": {"text": "IPO Monitor • Weekly Digest"},
    }
    
    return _send_webhook({"embeds": [embed]})


def send_error_alert(error_message: str, details: str = "") -> bool:
    """Send an error/warning notification."""
    embed = {
        "title": "⚠️ IPO Monitor — Error",
        "description": error_message,
        "color": COLOR_ORANGE,
        "fields": [],
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "footer": {"text": "IPO Monitor"},
    }
    
    if details:
        embed["fields"].append({
            "name": "Details",
            "value": f"```\n{details[:1000]}\n```",
            "inline": False,
        })
    
    return _send_webhook({"embeds": [embed]})


def send_no_active_ipos() -> bool:
    """Send a notification indicating no active IPOs were found."""
    embed = {
        "title": "ℹ️ IPO Monitor — Daily Check",
        "description": "No active IPOs found on NSE today.",
        "color": COLOR_BLUE,
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "footer": {"text": "IPO Monitor • NSE Data"},
    }
    
    return _send_webhook({"embeds": [embed]})
