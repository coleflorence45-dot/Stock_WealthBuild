import requests
import sqlite3
import xml.etree.ElementTree as ET
from datetime import datetime, timedelta
import time

conn = sqlite3.connect('signals.db')
c = conn.cursor()

c.execute('''CREATE TABLE IF NOT EXISTS insider_trades (
    ticker        TEXT,
    company       TEXT,
    exec_name     TEXT,
    title         TEXT,
    shares_bought INTEGER,
    price         REAL,
    date          TEXT,
    trade_type    TEXT,
    total_value   REAL
)''')
conn.commit()

HEADERS = {"User-Agent": "YourName your@email.com"}

def get_insider_filings(days_back=90, page_from=0):
    today = datetime.today()
    start = today - timedelta(days=days_back)
    url = (
        "https://efts.sec.gov/LATEST/search-index?"
        "forms=4"
        "&dateRange=custom"
        f"&startdt={start.strftime('%Y-%m-%d')}"
        f"&enddt={today.strftime('%Y-%m-%d')}"
        f"&from={page_from}"
    )
    r = requests.get(url, headers=HEADERS)
    return r.json()

def get_ticker_from_cik(cik):
    url = f"https://data.sec.gov/submissions/CIK{cik.zfill(10)}.json"
    try:
        r = requests.get(url, headers=HEADERS, timeout=10)
        if r.status_code != 200:
            return "UNKNOWN"
        tickers = r.json().get("tickers", [])
        return tickers[0] if tickers else "UNKNOWN"
    except:
        return "UNKNOWN"

def get_trade_details(filing_id, company_cik):
    try:
        parts     = filing_id.split(":")
        acc_raw   = parts[0]
        filename  = parts[1] if len(parts) > 1 else "primary_doc.xml"
        acc_clean = acc_raw.replace("-", "")
        cik_int   = str(int(company_cik))

        urls_to_try = [
            f"https://www.sec.gov/Archives/edgar/data/{cik_int}/{acc_clean}/{filename}",
            f"https://www.sec.gov/Archives/edgar/data/{cik_int}/{acc_clean}/{acc_raw}.xml",
            f"https://www.sec.gov/Archives/edgar/data/{cik_int}/{acc_clean}/form4.xml",
        ]

        content = None
        for url in urls_to_try:
            try:
                r = requests.get(url, headers=HEADERS, timeout=10)
                if r.status_code == 200 and len(r.content) > 200:
                    content = r.content
                    break
            except:
                continue
            time.sleep(0.1)

        if not content:
            return None

        root    = ET.fromstring(content)
        results = []

        for txn in root.findall(".//nonDerivativeTransaction"):
            code = txn.findtext(".//transactionCode", "")
            if code != "P":
                continue

            shares_raw = txn.findtext(".//transactionShares/value", "0")
            price_raw  = txn.findtext(".//transactionPricePerShare/value", "0")
            title      = root.findtext(".//officerTitle", "Unknown")

            shares = int(float(shares_raw)) if shares_raw else 0
            price  = float(price_raw)        if price_raw  else 0.0

            if shares < 100:
                continue

            results.append({
                "trade_type":  "BUY",
                "shares":      shares,
                "price":       price,
                "title":       title,
                "total_value": round(shares * price, 2)
            })

        return results if results else None

    except:
        return None

def process_page(hits, page_num, buys_found_total):
    buys_found = 0
    skipped    = 0

    for i, hit in enumerate(hits):
        source        = hit.get("_source", {})
        filing_id     = hit.get("_id", "")
        display_names = source.get("display_names", [])
        ciks          = source.get("ciks", [])
        filed_date    = source.get("file_date", "")

        exec_name    = display_names[0].split("(CIK")[0].strip() if display_names else "Unknown"
        company_name = display_names[1].split("(CIK")[0].strip() if len(display_names) > 1 else "Unknown"
        company_cik  = ciks[1] if len(ciks) > 1 else (ciks[0] if ciks else "")

        if not company_cik:
            skipped += 1
            continue

        ticker  = get_ticker_from_cik(company_cik)
        details = get_trade_details(filing_id, company_cik)

        if not details:
            skipped += 1
            continue

        for trade in details:
            # Deduplicate — skip if this exact trade already saved
            c.execute('''SELECT COUNT(*) FROM insider_trades
                         WHERE ticker=? AND exec_name=? AND shares_bought=? AND date=?''',
                      (ticker, exec_name, trade["shares"], filed_date))

            if c.fetchone()[0] > 0:
                continue  # already have it

            value_str    = f"£{trade['total_value']:,.0f}" if trade['total_value'] > 0 else "price TBC"
            total_so_far = buys_found_total + buys_found + 1
            print(f"  #{total_so_far:<4} BUY  {ticker:<6} | {exec_name:<28} | "
                  f"{trade['shares']:>8,} shares @ ${trade['price']:.2f} | {value_str}")

            c.execute('''INSERT INTO insider_trades
                         (ticker, company, exec_name, title,
                          shares_bought, price, date, trade_type, total_value)
                         VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)''',
                      (ticker, company_name, exec_name, trade["title"],
                       trade["shares"], trade["price"], filed_date,
                       trade["trade_type"], trade["total_value"]))
            buys_found += 1

    conn.commit()
    return buys_found, skipped

if __name__ == "__main__":

    # ── Controls ────────────────────────────────────────────────────
    PAGES     = 10   # 10 pages = 1,000 filings scanned
    DAYS_BACK = 90   # 90 days of history
    # ────────────────────────────────────────────────────────────────

    total_buys = 0
    total_skip = 0

    print(f"Scanning {PAGES * 100} filings over last {DAYS_BACK} days...\n")

    for page in range(PAGES):
        page_from = page * 100  # FIXED — jump 100 per page not 10
        print(f"--- Page {page + 1}/{PAGES} (filings {page_from+1}-{page_from+100}) ---")

        data = get_insider_filings(days_back=DAYS_BACK, page_from=page_from)
        hits = data.get("hits", {}).get("hits", [])

        if not hits:
            print("  No more results")
            break

        buys, skipped = process_page(hits, page + 1, total_buys)
        total_buys   += buys
        total_skip   += skipped
        print(f"  Page {page + 1} done — {buys} new unique buys found\n")
        time.sleep(1)

    print(f"{'='*60}")
    print(f"TOTAL: {total_buys} unique BUY transactions saved")
    print(f"       {total_skip} filings were sales/options/skipped")
    print(f"{'='*60}")
    print("Done.")