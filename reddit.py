"""
reddit.py — tracks mention velocity of your top insider buy tickers
across r/stocks, r/investing, r/wallstreetbets, r/SecurityAnalysis

Setup:
1. Go to https://www.reddit.com/prefs/apps
2. Click "create another app" at the bottom
3. Choose "script"
4. Name it anything, redirect uri = http://localhost:8080
5. Copy the client_id (under the app name) and client_secret
6. Paste them below
"""

import praw
import sqlite3
import time
from datetime import datetime

# ── Your Reddit API credentials ─────────────────────────────────────
CLIENT_ID     = "paste_your_client_id_here"
CLIENT_SECRET = "paste_your_client_secret_here"
USER_AGENT    = "InsiderScanner/1.0 by YourRedditUsername"

# ── Database setup ──────────────────────────────────────────────────
conn = sqlite3.connect('signals.db')
c    = conn.cursor()

c.execute('''CREATE TABLE IF NOT EXISTS reddit_mentions (
    ticker      TEXT,
    subreddit   TEXT,
    mentions    INTEGER,
    date        TEXT,
    sample_post TEXT
)''')
conn.commit()

# Add reddit_score column to insider_trades if not exists
try:
    c.execute("ALTER TABLE insider_trades ADD COLUMN reddit_score REAL")
    conn.commit()
except sqlite3.OperationalError:
    pass

# ── Subreddits to monitor ───────────────────────────────────────────
SUBREDDITS = [
    "stocks",
    "investing",
    "wallstreetbets",
    "SecurityAnalysis",
    "StockMarket"
]

def get_top_tickers():
    """Get all tickers from insider_trades that scored above 40"""
    c.execute("""
        SELECT DISTINCT ticker FROM insider_trades
        WHERE total_score >= 40
        AND ticker != 'UNKNOWN'
    """)
    return [row[0] for row in c.fetchall()]

def search_reddit(ticker, reddit):
    """Count mentions of a ticker across target subreddits in last 7 days"""
    total_mentions = 0
    sample_post    = ""

    for sub_name in SUBREDDITS:
        try:
            subreddit = reddit.subreddit(sub_name)

            # Search for ticker mentions
            results = subreddit.search(
                f"${ticker} OR \"{ticker}\"",
                time_filter="week",
                limit=25
            )

            count = 0
            for post in results:
                count += 1
                if not sample_post:
                    sample_post = post.title[:100]

            total_mentions += count
            time.sleep(0.5)  # rate limit

        except Exception as e:
            continue

    return total_mentions, sample_post

def score_reddit_mentions(mentions):
    """Convert mention count to a score component"""
    if mentions >= 50:  return 20
    if mentions >= 20:  return 15
    if mentions >= 10:  return 10
    if mentions >= 5:   return 5
    if mentions >= 1:   return 2
    return 0

def run_reddit_scan():
    reddit  = praw.Reddit(
        client_id     = CLIENT_ID,
        client_secret = CLIENT_SECRET,
        user_agent    = USER_AGENT
    )

    tickers = get_top_tickers()
    today   = datetime.today().strftime("%Y-%m-%d")

    if not tickers:
        print("No tickers found. Run main.py and score.py first.")
        return

    print(f"Scanning Reddit for {len(tickers)} tickers...\n")

    for i, ticker in enumerate(tickers):
        print(f"  [{i+1}/{len(tickers)}] ${ticker}...", end=" ")
        mentions, sample = search_reddit(ticker, reddit)

        # Save to reddit_mentions table
        c.execute("""
            INSERT INTO reddit_mentions (ticker, subreddit, mentions, date, sample_post)
            VALUES (?, ?, ?, ?, ?)
        """, (ticker, "combined", mentions, today, sample))

        # Update reddit_score on insider_trades
        score = score_reddit_mentions(mentions)
        c.execute("""
            UPDATE insider_trades SET reddit_score = ?
            WHERE ticker = ?
        """, (score, ticker))

        conn.commit()

        if mentions > 0:
            print(f"{mentions} mentions | sample: {sample[:50]}...")
        else:
            print("no mentions found")

        time.sleep(1)

    print(f"\nReddit scan complete.")
    print("Re-run score.py to include reddit scores in rankings.")

if __name__ == "__main__":
    run_reddit_scan()