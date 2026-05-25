import requests
import sqlite3
import json
from datetime import datetime, timedelta

# ── 1. Connect to database ──────────────────────────────────────────
conn = sqlite3.connect('signals.db')
c = conn.cursor()

c.execute('''CREATE TABLE IF NOT EXISTS insider_trades (
    ticker TEXT,
    exec_name TEXT,
    title TEXT,
    shares_bought INTEGER,
    price REAL,
    date TEXT
)''')
conn.commit()

# ── 2. Fetch from SEC ───────────────────────────────────────────────
def get_insider_filings():
    today = datetime.today()
    week_ago = today - timedelta(days=7)

    url = (
        "https://efts.sec.gov/LATEST/search-index?"
        "q=%22transaction+code%22+%22P%22"  # P = Purchase (not sale)
        "&forms=4"
        f"&dateRange=custom"
        f"&startdt={week_ago.strftime('%Y-%m-%d')}"
        f"&enddt={today.strftime('%Y-%m-%d')}"
    )

    response = requests.get(
        url,
        headers={"User-Agent": "YourName your@email.com"}  # CHANGE THIS
    )

    print(f"Status code: {response.status_code}")
    print(f"Raw response preview: {response.text[:500]}")  # shows what's coming back

    return response.json()

# ── 3. Parse results ────────────────────────────────────────────────
def get_filing_details(accession_number, cik):
    """Fetch the actual filing to extract ticker and trade details"""
    # Clean up accession number format
    acc = accession_number.replace("-", "")
    
    url = f"https://data.sec.gov/submissions/CIK{cik.zfill(10)}.json"
    
    response = requests.get(
        url,
        headers={"User-Agent": "YourName your@email.com"}
    )
    
    if response.status_code != 200:
        return None
    
    return response.json()


def parse_and_save(data):
    hits = data.get("hits", {}).get("hits", [])

    if not hits:
        print("No filings found")
        return

    saved = 0

    for hit in hits:
        source = hit.get("_source", {})

        # These fields ARE in the search results
        exec_name  = source.get("display_names", ["Unknown"])[0]
        filed_date = source.get("file_date", "")
        entity     = source.get("entity_name", "UNKNOWN")  # company name
        ticker     = source.get("file_num", "")            # sometimes has it

        # Try to get ticker from entity_names field
        entity_names = source.get("entity_name", "")
        
        # Get CIK to look up proper details
        # The display_names field contains "Name (CIK 0001234567)"
        # We can extract the ticker via a separate lookup
        cik = ""
        display = source.get("display_names", [""])[0]
        if "CIK" in display:
            cik = display.split("CIK")[1].strip().replace(")", "").strip()

        c.execute('''INSERT INTO insider_trades 
                     (ticker, exec_name, title, shares_bought, price, date)
                     VALUES (?, ?, ?, ?, ?, ?)''',
                  (entity_names or "UNKNOWN", exec_name, "Unknown", 0, 0.0, filed_date))
        saved += 1
   
    c.execute("DELETE FROM insider_trades")
    conn.commit()
    print("Cleared old data")

# ── 4. Run it ───────────────────────────────────────────────────────
if __name__ == "__main__":
    print("Fetching SEC insider filings...")
    data = get_insider_filings()
    parse_and_save(data)
    print("Done. Open signals.db to see the data.")