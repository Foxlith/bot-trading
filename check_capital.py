"""Verificación final post-limpieza."""
import sqlite3, json

conn = sqlite3.connect('data/trading_bot.db')
cur = conn.cursor()

# Paper wallet
with open('data/paper_wallet.json', 'r') as f:
    wallet = json.load(f)

print("=== PAPER WALLET ===")
total_usd = float(wallet['USDT'])
print(f"  USDT: ${float(wallet['USDT']):.4f}")

# Calcular valor de activos a precios aproximados actuales
prices = {'BTC': 70055, 'ETH': 2108, 'SOL': 86.70}
for asset, price in prices.items():
    amt = float(wallet.get(asset, 0))
    val = amt * price
    total_usd += val
    print(f"  {asset}: {amt:.10f} × ${price:,.2f} = ${val:.2f}")

print(f"  TOTAL WALLET: ${total_usd:.2f}")

# Posiciones en DB
print("\n=== DB POSITIONS (open) ===")
cur.execute("SELECT symbol, COUNT(*), SUM(entry_price * amount) FROM positions WHERE status = 'open' GROUP BY symbol")
for sym, count, val in cur.fetchall():
    print(f"  {sym}: {count} pos = ${val:.4f}")

cur.execute("SELECT COUNT(*) FROM positions WHERE status = 'open'")
print(f"  Total open: {cur.fetchone()[0]}")

cur.execute("SELECT COUNT(*) FROM positions WHERE status = 'closed'")
print(f"  Total closed: {cur.fetchone()[0]}")

# Grid state consistency
print("\n=== GRID STATE ===")
cur.execute("SELECT state_data FROM strategy_state WHERE strategy_name = 'grid_trading'")
row = cur.fetchone()
if row:
    grid = json.loads(row[0])
    for sym, g in grid.get('grids', {}).items():
        bought = sum(1 for l in g['levels'] if l['status'] == 'bought')
        print(f"  {sym}: {bought}/{len(g['levels'])} niveles comprados")

print("\n✅ Verificación completa")
conn.close()
