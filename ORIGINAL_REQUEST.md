# Original User Request

## Initial Request — 2026-07-07T06:53:49Z

Implement a highly robust, redundant anti-bot request mechanism for the existing NSE IPO Monitor project to reliably bypass NSE's 403 Forbidden errors and achieve a "set and forget" level of reliability.

Working directory: D:\kaniamutan\Desktop\antigravity folder\ipo
Integrity mode: development

## Requirements

### R1. Reliable NSE Data Fetching
The system must successfully fetch data from the NSE IPO endpoints (`ipo-current-issue`, `ipo-detail`, `public-past-issues`) without being blocked by 403 Forbidden or similar anti-bot errors.

### R2. Anti-Bot Redundancy
The mechanism must include automatic fallbacks or redundancy. If the primary fetching method fails or gets blocked, an alternative method must seamlessly take over to ensure data retrieval. The agent team is free to decide the best architecture and libraries for this.

### R3. Seamless Integration
The solution must be fully integrated into the existing `nse_client.py` and `ipo_monitor.py` architecture without breaking the current state management or Discord notification logic.

### R4. GitHub Actions Compatibility
The anti-bot solution must be executable within a standard `ubuntu-latest` GitHub Actions runner. Any necessary system dependencies (e.g., browser binaries for Playwright) must be added to the `.github/workflows/ipo_monitor.yml` workflow file.

## Acceptance Criteria

### Execution Reliability
- [ ] Running `python ipo_monitor.py --dry-run` successfully fetches current IPOs and past issues without returning 403 Forbidden errors.
- [ ] The script can be run 3 times consecutively without being blocked.
- [ ] The script executes entirely unattended (no manual captcha solving or browser interaction required by the user).

### Code Completeness
- [ ] The code in `nse_client.py` explicitly implements at least two different request methods/strategies (a primary and a fallback) for handling NSE sessions or requests.
- [ ] The GitHub Actions workflow file (`ipo_monitor.yml`) is updated to install any new dependencies required by the anti-bot mechanism.

## Follow-up — 2026-07-07T06:54:16Z

The user has added an additional constraint: The implementation must be able to run within the limits of the GitHub Actions free tier. Keep resource usage (memory, execution time, and storage for dependencies like browsers) within what the standard free tier provides.

