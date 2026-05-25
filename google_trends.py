"""
google_trends.py — checks if search interest is rising for your top tickers
Rising search interest BEFORE price movement = early signal
"""

from pytrends.request import TrendReq
import sqlite3
import time
from datetime import datetime

conn = sqlite3.connect('signals.db')
c    = conn.cursor()

try:
    c.execute("ALTER TABLE insider_trades ADD COLUMN trends_score REAL")
    conn.commit()
except sqlite3.OperationalError:
    pass

def get_top_tickers():
    c.execute("""
        SELECT DISTINCT ticker FROM insider_trades
        WHERE total_score >= 40
        AND ticker != 'UNKNOWN'
    """)
    return [row[0] for row in c.fetchall()]

def get_trend_score(ticker):
    """
    Returns a score based on whether search interest is rising.
    Compares last 4 weeks vs previous 4 weeks.
    """
    try:
        pytrends = TrendReq(hl='en-US', tz=0)
        pytrends.build_payload([ticker], timeframe='today 3-m')
        data = pytrends.interest_over_time()

        if data.empty or ticker not in data.columns:
            return 0, "no data"

        values    = data[ticker].tolist()
        half      = len(values) // 2
        old_avg   = sum(values[:half]) / half if half > 0 else 0
        new_avg   = sum(values[half:]) / len(values[half:]) if values[half:] else 0

        if old_avg == 0:
            return 0, "no baseline"

        change_pct = ((new_avg - old_avg) / old_avg) * 100

        # Score based on how much interest is rising
        if change_pct >= 100:  score = 15   # doubled in interest
        elif change_pct >= 50: score = 12
        elif change_pct >= 25: score = 8
        elif change_pct >= 10: score = 4
        elif change_pct >= 0:  score = 1
        else:                  score = 0    # interest falling

        return score, f"{change_pct:+.0f}% trend change"

    except Exception as e:
        return 0, f"error: {e}"

def run_trends_scan():
    tickers = get_top_tickers()

    if not tickers:
        print("No tickers found. Run main.py and score.py first.")
        return

    print(f"Checking Google Trends for {len(tickers)} tickers...\n")

    for i, ticker in enumerate(tickers):
        print(f"  [{i+1}/{len(tickers)}] {ticker}...", end=" ")
        score, note = get_trend_score(ticker)

        c.execute("""
            UPDATE insider_trades SET trends_score = ?
            WHERE ticker = ?
        """, (score, ticker))
        conn.commit()

        print(f"score {score}/15 | {note}")
        time.sleep(1)  # Google Trends rate limits aggressively

    print("\nTrends scan complete.")
    print("Re-run score.py to include trend scores in rankings.")

if __name__ == "__main__":
    run_trends_scan()