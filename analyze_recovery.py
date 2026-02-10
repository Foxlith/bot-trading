"""Analiza cuanto debe subir el mercado para recuperar los $75 (ASCII SAFE)."""
import sys, os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from src.core.state_manager import get_state_manager
from src.core.data_manager import get_data_manager
from src.core.exchange_manager import get_exchange
from config.settings import CAPITAL

sm = get_state_manager()
dm = get_data_manager()
ex = get_exchange()

print("=" * 60)
print("ANALISIS DE RECUPERACION")
print("=" * 60)

initial = float(CAPITAL['initial_usd'])
balance = ex.get_balance()
liquid = float(balance.get("USDT", 0))

positions = sm.get_open_positions()

assets_data = {}
for p in positions:
    symbol = p['symbol']
    if symbol not in assets_data:
        assets_data[symbol] = {'amount': 0, 'cost': 0}
    
    amt = float(p['amount'])
    price = float(p['entry_price'])
    assets_data[symbol]['amount'] += amt
    assets_data[symbol]['cost'] += (amt * price)

total_invested_cost = 0
current_total_value = liquid

print(f"\nEstado Actual:")
print(f"  USDT Liquid: ${liquid:.4f}")

for symbol, data in assets_data.items():
    if data['amount'] <= 0: continue
    avg_entry = data['cost'] / data['amount']
    total_invested_cost += data['cost']
    
    try:
        mkt = dm.get_market_summary(symbol)
        curr_price = float(mkt['price'])
        curr_val = data['amount'] * curr_price
        current_total_value += curr_val
        
        diff_pct = ((curr_price / avg_entry) - 1) * 100
        dist_to_be = ((avg_entry / curr_price) - 1) * 100
        
        print(f"\n  {symbol}:")
        print(f"    - Amount: {data['amount']:.8f}")
        print(f"    - Buy Price (Avg): ${avg_entry:.2f}")
        print(f"    - Market Price: ${curr_price:.2f}")
        print(f"    - P&L: {diff_pct:+.2f}%")
        print(f"    - Reach Break-even: {max(0, dist_to_be):.2f}%")
        
    except Exception as e:
        print(f"  Error symbol {symbol}: {e}")

real_pnl = current_total_value - initial
print(f"\nResumen Final:")
print(f"  Initial Capital: ${initial:.2f}")
print(f"  Current Capital: ${current_total_value:.2f}")
print(f"  Total P&L:       ${real_pnl:+.2f} ({ (real_pnl/initial)*100 :.2f}%)")

if initial - current_total_value > 0:
    if total_invested_cost > 0:
        # subida = (initial - liquid) / total_invested_cost
        subida_needed = ((initial - liquid) / total_invested_cost) - 1
        print(f"\nOBJETIVO:")
        print(f"  El mercado debe subir un promedio de {subida_needed*100:.2f}% para volver a $75.00")
    else:
        print("\nNo open positions.")
else:
    print("\nCapital recovered.")
