# diag_airtable_quick.py
from dotenv import load_dotenv
load_dotenv() 
import os, requests, urllib.parse, json

BASE = os.getenv("AIRTABLE_BASE_ID")
TABLE = os.getenv("AIRTABLE_TABLE_NAME", "Candidates")
TOKEN = os.getenv("AIRTABLE_TOKEN")

print("ENV CHECK")
print(" AIRTABLE_BASE_ID:", BASE)
print(" AIRTABLE_TABLE_NAME:", repr(TABLE))
print(" AIRTABLE_TOKEN present?:", bool(TOKEN))
print()

if not BASE:
    print("ERROR: AIRTABLE_BASE_ID is not set in environment.")
    raise SystemExit(2)

# try both table name and table id variants
candidates = [TABLE]
# if TABLE looks like a user-friendly name, add a guess for table id from browser URL if you know it:
# candidates.append("tbl1LDllPZUwekvJe")  # uncomment and set if you want to test table id directly

for t in candidates:
    encoded = urllib.parse.quote(t, safe="")
    url = f"https://api.airtable.com/v0/{BASE}/{encoded}"
    print("Requesting URL:", url)
    headers = {"Content-Type": "application/json"}
    if TOKEN:
        headers["Authorization"] = f"Bearer {TOKEN}"
    try:
        r = requests.get(url, headers=headers, params={"maxRecords": 1}, timeout=15)
        print(" Status code:", r.status_code)
        try:
            body = r.json()
            print(" Response JSON keys:", list(body.keys()))
            print(" Response snippet:", json.dumps(body, indent=2)[:1200])
        except Exception:
            print(" Response text:", r.text[:1000])
    except Exception as ex:
        print(" Request failed:", ex)
    print("-" * 60)
