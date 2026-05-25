import sqlite3
import pandas as pd

conn = sqlite3.connect('signals.db')
c    = conn.cursor()

# Add score columns if they don't exist
for col in [
    ("buy_value_score",   "REAL"),
    ("position_score",    "REAL"),
    ("multi_buy_score",   "REAL"),
    ("cap_score",         "REAL"),
    ("total_score",       "REAL"),
    ("signal_rank",       "INTEGER"),
]:
    try:
        c.execute(f"ALTER TABLE insider_trades ADD COLUMN {col[0]} {col[1]}")
        conn.commit()
    except sqlite3.OperationalError:
        pass

# ── Scoring functions ───────────────────────────────────────────────

def score_buy_value(total_value):
    """
    How much did the insider spend of their own money?
    More money = stronger conviction signal
    Max 30 points
    """
    if total_value >= 1_000_000:  return 30   # £1M+     — very strong
    if total_value >= 500_000:    return 25   # £500k+
    if total_value >= 250_000:    return 20   # £250k+
    if total_value >= 100_000:    return 15   # £100k+
    if total_value >= 50_000:     return 10   # £50k+
    if total_value >= 10_000:     return 5    # £10k+
    return 2                                  # under £10k — weak signal

def score_position(position_pct):
    """
    Where is the stock in its 52 week range when they bought?
    Buying near the low = strong signal (they think it's cheap)
    Buying near the high = weaker signal
    Max 30 points
    """
    if position_pct is None:     return 10
    if position_pct <= 10:       return 30   # bottom 10% of 52wk range
    if position_pct <= 20:       return 26
    if position_pct <= 35:       return 20
    if position_pct <= 50:       return 14
    if position_pct <= 65:       return 8
    return 4                                  # top 35% of range

def score_multi_buy(ticker, filed_date):
    """
    Are multiple insiders at the same company buying within 30 days?
    Multiple insiders buying = very strong conviction signal
    Max 20 points
    """
    c.execute("""
        SELECT COUNT(DISTINCT exec_name) FROM insider_trades
        WHERE ticker = ?
        AND trade_type = 'BUY'
        AND ABS(julianday(date) - julianday(?)) <= 30
    """, (ticker, filed_date))
    count = c.fetchone()[0]

    if count >= 4:  return 20
    if count >= 3:  return 15
    if count >= 2:  return 10
    return 0

def score_market_cap(market_cap):
    """
    Small/mid cap insider buys are more significant than mega cap
    A CEO buying £100k of Apple is nothing
    A CEO buying £100k of a £50M company is massive
    Max 20 points
    """
    if market_cap <= 0:              return 5   # unknown
    if market_cap < 50_000_000:      return 20  # micro cap  < £50M
    if market_cap < 300_000_000:     return 17  # small cap  < £300M
    if market_cap < 2_000_000_000:   return 12  # mid cap    < £2B
    if market_cap < 10_000_000_000:  return 6   # large cap  < £10B
    return 2                                     # mega cap   £10B+

# ── Run scoring on all enriched rows ───────────────────────────────
def run_scoring():
    c.execute("""
        SELECT rowid, ticker, total_value, position_pct, market_cap, date
        FROM insider_trades
        WHERE enriched = 1 AND trade_type = 'BUY'
    """)
    rows = c.fetchall()

    if not rows:
        print("No enriched trades found. Run enrich.py first.")
        return

    print(f"Scoring {len(rows)} trades...\n")

    for row in rows:
        rowid, ticker, total_value, position_pct, market_cap, filed_date = row

        s_value    = score_buy_value(total_value    or 0)
        s_position = score_position(position_pct)
        s_multi    = score_multi_buy(ticker, filed_date)
        s_cap      = score_market_cap(market_cap    or 0)
        s_total    = s_value + s_position + s_multi + s_cap

        c.execute("""
            UPDATE insider_trades SET
                buy_value_score = ?,
                position_score  = ?,
                multi_buy_score = ?,
                cap_score       = ?,
                total_score     = ?
            WHERE rowid = ?
        """, (s_value, s_position, s_multi, s_cap, s_total, rowid))

    conn.commit()

    # Assign rank by total score
    c.execute("""
        SELECT rowid, total_score FROM insider_trades
        WHERE enriched = 1 AND trade_type = 'BUY'
        ORDER BY total_score DESC
    """)
    ranked = c.fetchall()
    for rank, (rowid, _) in enumerate(ranked, 1):
        c.execute("UPDATE insider_trades SET signal_rank = ? WHERE rowid = ?", (rank, rowid))
    conn.commit()

    # Print leaderboard
    c.execute("""
        SELECT ticker, company, exec_name, title, shares_bought, price,
               total_value, position_pct, market_cap, sector,
               buy_value_score, position_score, multi_buy_score, cap_score,
               total_score, signal_rank, date
        FROM insider_trades
        WHERE enriched = 1 AND trade_type = 'BUY'
        ORDER BY total_score DESC
        LIMIT 20
    """)
    top = c.fetchall()

    print("=" * 80)
    print(f"{'RANK':<5} {'TICKER':<7} {'SCORE':<7} {'EXEC':<25} {'SHARES':>9} {'£ VALUE':>12} {'52WK POS':>9} {'SECTOR'}")
    print("=" * 80)

    for row in top:
        (ticker, company, exec_name, title, shares, price,
         total_val, pos_pct, mkt_cap, sector,
         s_val, s_pos, s_multi, s_cap,
         total_score, rank, date) = row

        val_str = f"£{total_val:,.0f}"  if total_val else "N/A"
        pos_str = f"{pos_pct:.0f}%"     if pos_pct is not None else "N/A"

        print(f"#{rank:<4} {ticker:<7} {total_score:<7.0f} {exec_name[:24]:<25} "
              f"{shares:>9,} {val_str:>12} {pos_str:>9} {sector or 'Unknown'}")

    print("=" * 80)
    print(f"\nTop signal: #{top[0][15]} {top[0][0]} — score {top[0][14]:.0f}/100")
    print("\nRun dashboard.py to view in browser.")

if __name__ == "__main__":
    run_scoring()