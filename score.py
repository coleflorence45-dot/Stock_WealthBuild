import sqlite3

conn = sqlite3.connect('signals.db')
c    = conn.cursor()

# Add score columns if they don't exist
for col in [
    ("buy_value_score", "REAL"),
    ("position_score",  "REAL"),
    ("multi_buy_score", "REAL"),
    ("cap_score",       "REAL"),
    ("total_score",     "REAL"),
    ("signal_rank",     "INTEGER"),
    ("reddit_score",    "REAL"),
    ("trends_score",    "REAL"),
]:
    try:
        c.execute(f"ALTER TABLE insider_trades ADD COLUMN {col[0]} {col[1]}")
        conn.commit()
    except sqlite3.OperationalError:
        pass

# ── Scoring functions ───────────────────────────────────────────────

def score_buy_value(total_value):
    """How much did the insider spend? More = stronger conviction. Max 30pts"""
    if total_value >= 1_000_000: return 30
    if total_value >= 500_000:   return 25
    if total_value >= 250_000:   return 20
    if total_value >= 100_000:   return 15
    if total_value >= 50_000:    return 10
    if total_value >= 10_000:    return 5
    return 2

def score_position(position_pct):
    """Where in the 52wk range did they buy? Near low = strong signal. Max 30pts"""
    if position_pct is None:   return 10
    if position_pct <= 10:     return 30
    if position_pct <= 20:     return 26
    if position_pct <= 35:     return 20
    if position_pct <= 50:     return 14
    if position_pct <= 65:     return 8
    return 4

def score_multi_buy(ticker, filed_date):
    """Multiple insiders buying same company within 30 days = high conviction. Max 20pts"""
    c.execute("""
        SELECT COUNT(DISTINCT exec_name) FROM insider_trades
        WHERE ticker = ?
        AND trade_type = 'BUY'
        AND ABS(julianday(date) - julianday(?)) <= 30
    """, (ticker, filed_date))
    count = c.fetchone()[0]
    if count >= 4: return 20
    if count >= 3: return 15
    if count >= 2: return 10
    return 0

def score_market_cap(market_cap):
    """Small cap insider buys are more significant than mega cap. Max 20pts"""
    if market_cap <= 0:             return 5
    if market_cap < 50_000_000:     return 20
    if market_cap < 300_000_000:    return 17
    if market_cap < 2_000_000_000:  return 12
    if market_cap < 10_000_000_000: return 6
    return 2

# ── Main scoring run ────────────────────────────────────────────────

def run_scoring():
    c.execute("""
        SELECT rowid, ticker, total_value, position_pct,
               market_cap, date, reddit_score, trends_score
        FROM insider_trades
        WHERE enriched = 1 AND trade_type = 'BUY'
    """)
    rows = c.fetchall()

    if not rows:
        print("No enriched trades found. Run enrich.py first.")
        return

    print(f"Scoring {len(rows)} trades...\n")

    for row in rows:
        rowid, ticker, total_value, position_pct, \
        market_cap, filed_date, reddit_score, trends_score = row

        s_value    = score_buy_value(total_value  or 0)
        s_position = score_position(position_pct)
        s_multi    = score_multi_buy(ticker, filed_date)
        s_cap      = score_market_cap(market_cap  or 0)
        s_reddit   = reddit_score if reddit_score is not None else 0
        s_trends   = trends_score if trends_score is not None else 0
        s_total    = s_value + s_position + s_multi + s_cap + s_reddit + s_trends

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

    # Assign ranks
    c.execute("""
        SELECT rowid, total_score FROM insider_trades
        WHERE enriched = 1 AND trade_type = 'BUY'
        ORDER BY total_score DESC
    """)
    for rank, (rowid, _) in enumerate(c.fetchall(), 1):
        c.execute("UPDATE insider_trades SET signal_rank = ? WHERE rowid = ?", (rank, rowid))
    conn.commit()

    # Print leaderboard
    c.execute("""
        SELECT ticker, company, exec_name, shares_bought,
               total_value, position_pct, sector,
               buy_value_score, position_score, multi_buy_score,
               cap_score, reddit_score, trends_score,
               total_score, signal_rank, date
        FROM insider_trades
        WHERE enriched = 1 AND trade_type = 'BUY'
        ORDER BY total_score DESC
        LIMIT 20
    """)
    top = c.fetchall()

    print("=" * 90)
    print(f"{'RNK':<4} {'TICKER':<7} {'SCORE':<6} {'EXEC':<26} "
          f"{'SHARES':>9} {'£VALUE':>11} {'52WK':>6} {'R':>4} {'T':>4}  SECTOR")
    print("=" * 90)

    for row in top:
        (ticker, company, exec_name, shares, total_val, pos_pct, sector,
         s_val, s_pos, s_multi, s_cap, s_reddit, s_trends,
         total_score, rank, date) = row

        val_str    = f"£{total_val:,.0f}"  if total_val  else "N/A"
        pos_str    = f"{pos_pct:.0f}%"     if pos_pct is not None else "N/A"
        reddit_str = f"{int(s_reddit)}"    if s_reddit   else "-"
        trends_str = f"{int(s_trends)}"    if s_trends   else "-"

        print(f"#{rank:<3} {ticker:<7} {total_score:<6.0f} {exec_name[:25]:<26} "
              f"{shares:>9,} {val_str:>11} {pos_str:>6} "
              f"{reddit_str:>4} {trends_str:>4}  {sector or 'Unknown'}")

    print("=" * 90)
    print("R = Reddit score (max 20)  |  T = Trends score (max 15)")

    top_row = top[0]
    print(f"\n★  Top signal: #{top_row[14]} {top_row[0]} — score {top_row[13]:.0f}/100+")
    print(f"   {top_row[2]} bought {int(top_row[3]):,} shares of {top_row[1]}")
    print(f"   Filed: {top_row[15]}")

    print("\n── Triple confirmed signals (insider + reddit + trends) ──")
    triple = [r for r in top if
              (r[11] or 0) >= 5 and
              (r[12] or 0) >= 4 and
              (r[7]  or 0) >= 10]

    if triple:
        for r in triple:
            print(f"  ★★★ {r[0]} — score {r[13]:.0f} | insider buy + reddit + rising trends")
    else:
        print("  None yet — keep running daily, these emerge over time")

    print("\nRun dashboard.py to view in browser.")

if __name__ == "__main__":
    run_scoring()