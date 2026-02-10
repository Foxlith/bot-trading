import sqlite3

conn = sqlite3.connect('data/trading_bot.db')
cur = conn.cursor()

# All trades
cur.execute('SELECT symbol, profit, closed_at, strategy FROM trade_history WHERE side="sell" ORDER BY closed_at')
trades = cur.fetchall()

print('TRADES:')
for t in trades:
    print(f'{t[0]}|{t[1]}|{t[2]}|{t[3]}')

# Portfolio
cur.execute('SELECT current_capital, total_profit, trades_count, winning_trades, losing_trades FROM portfolio_state ORDER BY id DESC LIMIT 1')
p = cur.fetchone()
print(f'\nPORTFOLIO: capital={p[0]}, profit={p[1]}, trades={p[2]}, wins={p[3]}, losses={p[4]}')

# Calculate metrics
profits = [t[1] for t in trades if t[1] is not None]
wins = len([p for p in profits if p > 0])
losses = len([p for p in profits if p < 0])

print(f'\nMETRICS:')
print(f'Total Trades: {len(trades)}')
print(f'Wins: {wins}, Losses: {losses}')
print(f'Win Rate: {(wins/len(trades))*100:.1f}%')
print(f'Total Profit: {sum(profits):.6f}')
print(f'Best Trade: {max(profits):.6f}')
print(f'Worst Trade: {min(profits):.6f}')
print(f'Avg Trade: {sum(profits)/len(profits):.6f}')

# By symbol
print('\nBY SYMBOL:')
by_sym = {}
for t in trades:
    sym = t[0]
    if sym not in by_sym:
        by_sym[sym] = {'count': 0, 'profit': 0, 'wins': 0}
    by_sym[sym]['count'] += 1
    by_sym[sym]['profit'] += t[1] if t[1] else 0
    if t[1] and t[1] > 0:
        by_sym[sym]['wins'] += 1

for sym, data in by_sym.items():
    wr = (data['wins']/data['count'])*100 if data['count'] > 0 else 0
    print(f'{sym}: {data["count"]} trades, profit=${data["profit"]:.6f}, WR={wr:.0f}%')
