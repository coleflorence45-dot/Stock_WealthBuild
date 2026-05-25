import sqlite3
import yfinance as yf
import time

conn = sqlite3.connect('signals.db')
c    = conn.cursor()

# Add enrichment columns if they don't exist yet
columns_to_add = [
    ("current_price",   "REAL"),
    ("week52_high",     "REAL"),
    ("week52_low",      "REAL"),
    ("position_pct",    "REAL"),  # 0% = at 52wk low, 100% = at 52wk high
    ("market_cap",      "REAL"),
    ("sector",          "TEXT"),
    ("industry",        "TEXT"),
    ("enriched",        "INTEGER DEFAULT 0"),
]

for col, col_type in columns_to_add:
    try:
        c.execute(f"ALTER TABLE insider_trades ADD COLUMN {col} {col_type}")
        conn.commit()
    except sqlite3.OperationalError:
        pass  # column already exists

# ── Fetch enrichment data for a ticker ─────────────────────────────
def enrich_ticker(ticker):
    try:
        stock = yf.Ticker(ticker)
        info  = stock.info

        current_price = info.get("currentPrice") or info.get("regularMarketPrice") or 0
        week52_high   = info.get("fiftyTwoWeekHigh", 0)
        week52_low    = info.get("fiftyTwoWeekLow",  0)
        market_cap    = info.get("marketCap",        0)
        sector        = info.get("sector",           "Unknown")
        industry      = info.get("industry",         "Unknown")

        # Position within 52wk range — key signal
        # 0% = trading at 52wk low (cheap), 100% = at 52wk high (expensive)
        if week52_high > week52_low:
            position_pct = round(
                (current_price - week52_low) / (week52_high - week52_low) * 100, 1
            )
        else:
            position_pct = 50.0

        return {
            "current_price": current_price,
            "week52_high":   week52_high,
            "week52_low":    week52_low,
            "position_pct":  position_pct,
            "market_cap":    market_cap,
            "sector":        sector,
            "industry":      industry,
        }

    except Exception as e:
        print(f"    yfinance error for {ticker}: {e}")
        return None

# ── Main enrichment loop ────────────────────────────────────────────
def run_enrichment():
    # Get all unique tickers that haven't been enriched yet
    c.execute("""
        SELECT DISTINCT ticker FROM insider_trades
        WHERE (enriched IS NULL OR enriched = 0)
        AND ticker != 'UNKNOWN'
    """)
    tickers = [row[0] for row in c.fetchall()]

    if not tickers:
        print("All tickers already enriched. Nothing to do.")
        return

    print(f"Enriching {len(tickers)} unique tickers...\n")
    success = 0
    failed  = 0

    for i, ticker in enumerate(tickers):
        print(f"  [{i+1}/{len(tickers)}] {ticker}...", end=" ")
        data = enrich_ticker(ticker)

        if not data:
            print("FAILED")
            failed += 1
            continue

        # Update all rows for this ticker
        c.execute("""
            UPDATE insider_trades SET
                current_price = ?,
                week52_high   = ?,
                week52_low    = ?,
                position_pct  = ?,
                market_cap    = ?,
                sector        = ?,
                industry      = ?,
                enriched      = 1
            WHERE ticker = ?
        """, (
            data["current_price"],
            data["week52_high"],
            data["week52_low"],
            data["position_pct"],
            data["market_cap"],
            data["sector"],
            data["industry"],
            ticker
        ))
        conn.commit()

        pos   = data["position_pct"]
        cap   = data["market_cap"]
        cap_str = f"£{cap/1e9:.1f}B" if cap >= 1e9 else f"£{cap/1e6:.0f}M" if cap > 0 else "N/A"

        print(f"{data['sector']:<20} | 52wk position: {pos:>5.1f}% | Cap: {cap_str}")
        success += 1
        time.sleep(0.3)  # be polite to yfinance

    print(f"\n{'='*60}")
    print(f"Enrichment complete: {success} succeeded, {failed} failed")
    print(f"{'='*60}")

if __name__ == "__main__":
    run_enrichment()
    print("Done. Run score.py next.")