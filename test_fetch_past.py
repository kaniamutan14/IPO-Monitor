"""Quick test: fetch past listed IPOs from NSE and search for Meesho."""
from nse_client import NSEClient
import json

nse = NSEClient()
nse.initialize_session()

# Fetch past issues list
past = nse.get_past_issues()
print(f"Total past issues found: {len(past)}")

if past:
    # Show first 10 entries
    print("\n--- Recent Listed IPOs ---")
    for p in past[:10]:
        sym = nse.extract_symbol(p)
        name = nse.extract_company_name(p)
        info = nse.extract_listing_info(p)
        ip = info.get("issue_price", "?")
        lp = info.get("listing_price", "?")
        ld = info.get("listing_date", "?")
        print(f"  {sym}: {name} | Issue: {ip} | Listed: {lp} on {ld}")

    # Search for Meesho
    print("\n--- Searching for Meesho ---")
    meesho = [p for p in past if "meesho" in nse.extract_company_name(p).lower() or (nse.extract_symbol(p) or "").lower() == "meesho"]
    if meesho:
        print("Meesho found!")
        print(json.dumps(meesho[0], indent=2, ensure_ascii=False))
    else:
        print("Meesho not found in past issues list")

    # Print ALL available keys from first entry to understand the schema
    print("\n--- Raw schema (first entry keys) ---")
    print(json.dumps(past[0], indent=2, ensure_ascii=False))

nse.close()
