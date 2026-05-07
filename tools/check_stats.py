import sqlite3

DB = r'd:\USUARIOS\jostin_fuentes\OneDrive - Corporación Unificada Nacional de Educación Superior - CUN\Escritorio\BOT TRADING\data\trading_bot.db'
conn = sqlite3.connect(DB)
cur = conn.cursor()

# Get column names
cur.execute("PRAGMA table_info(trade_history)")
columns = [row[1] for row in cur.fetchall()]
print(f"Columnas en trade_history: {columns}")

date_col = 'timestamp'
if 'executed_at' in columns:
    date_col = 'executed_at'
elif 'created_at' in columns:
    date_col = 'created_at'
elif 'date' in columns:
    date_col = 'date'

print("\n=== ULTIMOS 15 TRADES ===")
try:
    query = f"""
        SELECT id, symbol, strategy, side, amount, profit, {date_col} 
        FROM trade_history 
        ORDER BY {date_col} DESC LIMIT 15
    """
    cur.execute(query)
    for r in cur.fetchall():
        dust_flag = " ⚠️POLVO" if r[4] < 0.00001 and r[3] == 'sell' else ""
        print(f"  ID:{r[0]} | {r[1]} | {r[3]} | amt:{r[4]:.8f} | profit:${r[5]:.4f} | {r[6]}{dust_flag}")
except Exception as e:
    print(f"Error querying history: {e}")

conn.close()
