# IPO Discord Monitor — Implementation Plan v4 (Phase 2)

**Created:** 2026-07-08  
**Status:** Draft — Awaiting Approval

---

## 1. Goals

Implement the three Phase 2 features deferred from Plan v1:

1. **Weekly Summary Digest** — A Sunday morning recap of all tracked IPOs
2. **Upcoming IPO Alerts** — Notify when a new IPO is announced but hasn't opened yet
3. **Subscription Milestone Alerts** — Real-time alerts when subscription crosses key thresholds

---

## 2. Feature Details

### A. Weekly Summary Digest

**Trigger:** Sunday 10:00 AM IST via GitHub Actions cron (`30 4 * * 0`)

**Content:** A single Discord embed summarizing:
- Currently open IPOs with latest subscription numbers
- IPOs awaiting listing (CLOSED state) with final subscription
- IPOs that listed in the past 7 days with P&L results
- Count of archived IPOs

**Changes:**
| File | Change |
|------|--------|
| `ipo_monitor.py` | Add `--weekly-digest` CLI flag; add `generate_weekly_digest()` function |
| `discord_notifier.py` | Add `send_weekly_digest()` function with multi-section embed |
| `ipo_monitor.yml` | Add Sunday cron + pass `--weekly-digest` flag on Sundays |

### B. Upcoming IPO Alerts

**Logic:** When an IPO appears in the current-issues data but its `open_date` is in the future (i.e., bidding hasn't started yet), treat it as `UPCOMING` instead of `OPEN`.

**Notification:** "New IPO Announced — {company_name}, opens on {open_date}"

**Changes:**
| File | Change |
|------|--------|
| `ipo_monitor.py` | In `process_current_issues()`, compare `open_date` to today — if future, set state to `UPCOMING` and send upcoming alert instead of open alert |
| `discord_notifier.py` | Add `send_upcoming_ipo_alert()` function |
| `state_manager.py` | Add `upcoming_alert` to `notifications_sent` schema |

### C. Subscription Milestone Alerts

**Milestones:** `[1, 3, 5, 10, 20, 50, 100]` x subscribed

**Logic:** After updating subscription data, check if the **total** subscription crossed any milestone since the last check. Only alert once per milestone.

**Changes:**
| File | Change |
|------|--------|
| `config.py` | Add `SUBSCRIPTION_MILESTONES` list |
| `state_manager.py` | Add `milestones_notified` list to IPO entry schema; add `check_milestones()` method |
| `discord_notifier.py` | Add `send_milestone_alert()` function |
| `ipo_monitor.py` | After `update_subscription()`, call milestone check and send alerts |

---

## 3. State Schema Additions

New fields in the `notifications_sent` object:
```json
{
  "notifications_sent": {
    "upcoming_alert": false,
    "milestones_notified": [1, 3, 5]
  }
}
```

---

## 4. Verification Plan

1. Syntax check: `python -m py_compile ipo_monitor.py discord_notifier.py state_manager.py config.py`
2. Dry-run test: `python ipo_monitor.py --dry-run --verbose`
3. Weekly digest dry-run: `python ipo_monitor.py --weekly-digest --dry-run --verbose`
4. Unit tests: Ensure existing tests still pass
5. Backward compatibility: Existing state.json files load without errors (new fields get defaults)
