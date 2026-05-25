import sqlite3

conn = sqlite3.connect('signals.db')
c = conn.cursor()

c.execute('''CREATE TABLE IF NOT EXISTS signals (
    ticker TEXT,
    date TEXT,
    insider_score REAL,
    sentiment_score REAL,
    momentum_score REAL,
    total_score REAL,
    notes TEXT
)''')

c.execute('''CREATE TABLE IF NOT EXISTS insider_trades (
    ticker TEXT,
    exec_name TEXT,
    title TEXT,
    shares_bought INTEGER,
    price REAL,
    date TEXT
)''')

conn.commit()