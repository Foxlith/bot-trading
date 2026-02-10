import sqlite3
conn = sqlite3.connect('data/trading_bot.db')
cur = conn.cursor()
cur.execute("PRAGMA table_info(positions)")
print("POSITIONS SCHEMA:")
for r in cur.fetchall():
    print(f"  {r}")
cur.execute("SELECT * FROM positions WHERE status='open' LIMIT 2")
print("\nSAMPLE OPEN POSITIONS:")
cols = [d[0] for d in cur.description]
print(f"  Columns: {cols}")
for r in cur.fetchall():
    print(f"  {dict(zip(cols, r))}")
conn.close()
