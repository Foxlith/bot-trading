"""
Unrealized P&L and Liquidity Analysis - FIXED
==============================================
"""
import sqlite3
import json
from datetime import datetime

DB_PATH = "data/trading_bot.db"

# Current market prices (Jan 26, 2026)
CURRENT_PRICES = {
    "BTC/USDT": 90000,
    "ETH/USDT": 2950,
    "SOL/USDT": 128
}

def get_positions():
    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()
    
    # Get strategy states
    cur.execute("SELECT strategy_name, state_data FROM strategy_state")
    strategies = {}
    for row in cur.fetchall():
        try:
            strategies[row[0]] = json.loads(row[1])
        except:
            strategies[row[0]] = {}
    
    # Get portfolio
    cur.execute("SELECT current_capital, total_profit FROM portfolio_state ORDER BY id DESC LIMIT 1")
    portfolio = cur.fetchone()
    
    conn.close()
    
    return strategies, portfolio

def analyze():
    strategies, portfolio = get_positions()
    capital = portfolio[0] if portfolio else 75
    profit = portfolio[1] if portfolio else 0
    
    print("=" * 70)
    print("UNREALIZED P&L AND LIQUIDITY ANALYSIS")
    print(f"Date: {datetime.now().strftime('%Y-%m-%d %H:%M')}")
    print("=" * 70)
    
    print(f"\nPortfolio Capital: ${capital:.2f}")
    print(f"Realized Profit: ${profit:.4f}")
    
    total_invested = 0
    total_current = 0
    
    # DCA Positions
    dca = strategies.get("dca_intelligent", {})
    dca_positions = dca.get("positions", {})
    
    print("\n=== DCA POSITIONS ===")
    for symbol, pos in dca_positions.items():
        amount = pos.get("amount", 0)
        avg_price = pos.get("avg_price", 0)
        current = CURRENT_PRICES.get(symbol, 0)
        
        invested = amount * avg_price
        value_now = amount * current
        pnl = value_now - invested
        pnl_pct = (pnl / invested * 100) if invested > 0 else 0
        
        total_invested += invested
        total_current += value_now
        
        emoji = "+" if pnl >= 0 else ""
        print(f"{symbol}:")
        print(f"  Amount: {amount:.8f}")
        print(f"  Avg Buy: ${avg_price:,.2f} | Current: ${current:,.2f}")
        print(f"  Invested: ${invested:.4f} | Now: ${value_now:.4f}")
        print(f"  Unrealized: ${emoji}{pnl:.4f} ({emoji}{pnl_pct:.2f}%)")
    
    # Grid Positions
    grid = strategies.get("grid_trading", {})
    grids = grid.get("grids", {})
    
    print("\n=== GRID POSITIONS ===")
    for symbol, g in grids.items():
        levels = g.get("levels", [])
        bought = [l for l in levels if l.get("status") == "bought"]
        
        if bought:
            total_amt = sum(l.get("amount", 0) for l in bought)
            total_cost = sum(l.get("amount", 0) * l.get("buy_executed_price", l.get("buy_price", 0)) for l in bought)
            current = CURRENT_PRICES.get(symbol, 0)
            value_now = total_amt * current
            pnl = value_now - total_cost
            pnl_pct = (pnl / total_cost * 100) if total_cost > 0 else 0
            
            total_invested += total_cost
            total_current += value_now
            
            emoji = "+" if pnl >= 0 else ""
            print(f"{symbol}: {len(bought)} levels bought")
            print(f"  Total Amount: {total_amt:.8f}")
            print(f"  Invested: ${total_cost:.4f} | Now: ${value_now:.4f}")
            print(f"  Unrealized: ${emoji}{pnl:.4f} ({emoji}{pnl_pct:.2f}%)")
        else:
            print(f"{symbol}: No bought levels")
    
    # Summary
    total_unrealized = total_current - total_invested
    emoji = "+" if total_unrealized >= 0 else ""
    
    print("\n" + "=" * 70)
    print("SUMMARY")
    print("=" * 70)
    print(f"Total Invested in Positions: ${total_invested:.4f}")
    print(f"Current Value: ${total_current:.4f}")
    print(f"UNREALIZED P&L: ${emoji}{total_unrealized:.4f}")
    
    available = capital - total_invested
    print(f"\nAvailable Liquidity: ${available:.4f}")
    
    # Stress test -5%
    print("\n=== STRESS TEST: Market -5% ===")
    stressed = total_current * 0.95
    stressed_pnl = stressed - total_invested
    print(f"If market drops 5%:")
    print(f"  Position Value: ${stressed:.4f}")
    print(f"  Unrealized P&L: ${stressed_pnl:.4f}")
    
    # Can continue?
    print("\n=== SUSTAINABILITY CHECK ===")
    if available > 1:
        print(f"Available for new buys: ${available:.2f}")
        print("STATUS: Bot CAN continue buying dips")
    else:
        print("WARNING: LOW LIQUIDITY - Bot may run out of capital!")
    
    # Final verdict
    print("\n=== VERDICT ===")
    if total_unrealized < 0:
        print(f"If you CLOSE ALL now: LOSS of ${abs(total_unrealized):.4f}")
    else:
        print(f"If you CLOSE ALL now: GAIN of ${total_unrealized:.4f}")

if __name__ == "__main__":
    analyze()
