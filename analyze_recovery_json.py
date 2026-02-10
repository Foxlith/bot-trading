"""Analiza cuanto debe subir el mercado (JSON output)."""
import sys, os, json
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from src.core.state_manager import get_state_manager
from src.core.data_manager import get_data_manager
from src.core.exchange_manager import get_exchange
from config.settings import CAPITAL

sm = get_state_manager()
dm = get_data_manager()
ex = get_exchange()

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

report = {
    "initial_capital": initial,
    "current_usdt": liquid,
    "assets": [],
    "total_invested_cost": 0,
    "current_total_value": liquid
}

for symbol, data in assets_data.items():
    if data['amount'] <= 0: continue
    avg_entry = data['cost'] / data['amount']
    report["total_invested_cost"] += data['cost']
    
    asset_info = {
        "symbol": symbol,
        "amount": data['amount'],
        "avg_entry": avg_entry,
        "market_price": 0,
        "pnl_pct": 0,
        "dist_to_be": 0
    }
    
    try:
        mkt = dm.get_market_summary(symbol)
        curr_price = float(mkt['price'])
        curr_val = data['amount'] * curr_price
        report["current_total_value"] += curr_val
        
        asset_info["market_price"] = curr_price
        asset_info["pnl_pct"] = ((curr_price / avg_entry) - 1) * 100
        asset_info["dist_to_be"] = max(0, ((avg_entry / curr_price) - 1) * 100)
    except:
        pass
    
    report["assets"].append(asset_info)

report["total_pnl"] = report["current_total_value"] - initial
report["total_pnl_pct"] = (report["total_pnl"] / initial) * 100

if initial - report["current_total_value"] > 0 and report["total_invested_cost"] > 0:
    report["recovery_needed_pct"] = ((initial - liquid) / report["total_invested_cost"] - 1) * 100
else:
    report["recovery_needed_pct"] = 0

with open("recovery_status.json", "w") as f:
    json.dump(report, f, indent=4)
print("JSON report generated.")
