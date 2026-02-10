import sqlite3

conn = sqlite3.connect("data/trading_bot.db")
cur = conn.cursor()

# Get tables
cur.execute("SELECT name FROM sqlite_master WHERE type='table'")
tables = [r[0] for r in cur.fetchall()]
print("TABLES:", tables)

# Get schema for each table
for table in tables:
    print(f"\n=== {table} ===")
    cur.execute(f"PRAGMA table_info({table})")
    for col in cur.fetchall():
        print(f"  {col[1]} ({col[2]})")

# Sample data from strategy_state if exists
if "strategy_state" in tables:
    print("\n=== STRATEGY_STATE SAMPLE ===")
    cur.execute("SELECT * FROM strategy_state LIMIT 3")
    for row in cur.fetchall():
        print(row[:2], "...")  # First 2 columns

conn.close()
