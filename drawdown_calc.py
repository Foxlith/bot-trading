import sqlite3

conn = sqlite3.connect('data/trading_bot.db')
cur = conn.cursor()

# Get losing trades with details
cur.execute("SELECT symbol, profit, closed_at FROM trade_history WHERE side='sell' AND profit < 0 ORDER BY closed_at")
losses = cur.fetchall()

print('LOSING TRADES:')
for t in losses:
    print(f'{t[0]}: ${t[1]:.6f} @ {t[2]}')
    
# Calculate Max Drawdown
cur.execute("SELECT profit FROM trade_history WHERE side='sell' ORDER BY closed_at")
profits = [r[0] for r in cur.fetchall()]

running = 75
peak = 75
max_dd = 0
for p in profits:
    running += p
    if running > peak:
        peak = running
    dd = (peak - running) / peak
    if dd > max_dd:
        max_dd = dd

print(f'\nMAX DRAWDOWN: {max_dd*100:.2f}%')
print(f'Final Capital: ${running:.4f}')
