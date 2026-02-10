import os, sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from src.core.state_manager import get_state_manager
from src.core.exchange_manager import get_exchange
from src.core.data_manager import get_data_manager
from config.settings import CAPITAL

sm = get_state_manager()
ex = get_exchange()
dm = get_data_manager()

balance = ex.get_balance()
liquid_usdt = balance.get("USDT", 0)
assets_value = 0
for asset, amount in balance.items():
    if asset != "USDT" and amount > 0:
        try:
            data = dm.get_market_summary(f"{asset}/USDT")
            assets_value += float(amount) * float(data.get("price", 0))
        except:
            pass

total_capital = float(liquid_usdt) + float(assets_value)
initial = float(CAPITAL['initial_usd'])
stats = sm.get_trade_stats()
realized = float(stats.get("total_profit", 0))
real_pnl = total_capital - initial
latent = real_pnl - realized
roi = (real_pnl / initial) * 100

print(f"Capital Inicial: ${initial:.2f}")
print(f"Capital Actual: ${total_capital:.2f}")
print(f"  Liquidez: ${liquid_usdt:.4f}")
print(f"  Activos: ${assets_value:.2f}")
print(f"P&L Total: ${real_pnl:+.2f} ({roi:+.2f}%)")
print(f"  Realizado: ${realized:+.2f}")
print(f"  Latente: ${latent:+.2f}")
print(f"Trades: {stats['total_trades']} total, {stats['winning_trades']} won, {stats['losing_trades']} lost")
print(f"Win Rate: {stats['win_rate']:.1f}%")
print(f"CHECK: {initial} + {real_pnl:.2f} = {initial + real_pnl:.2f}")
print(f"CHECK: {realized:.2f} + {latent:.2f} = {realized + latent:.2f}")
