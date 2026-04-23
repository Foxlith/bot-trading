"""
Legacy Positions Break-Even Analysis
====================================
Calculates the exit price needed to break even on legacy positions
accounting for fees that were not tracked originally.
"""
import sqlite3
import json
from datetime import datetime

DB_PATH = "data/trading_bot.db"
FEE_RATE = 0.001  # 0.1%

# Current prices (approximate for display)
CURRENT_PRICES = {
    "BTC/USDT": 90000,
    "ETH/USDT": 2950,
    "SOL/USDT": 128
}

def get_positions():
    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()
    cur.execute("SELECT strategy_name, state_data FROM strategy_state")
    strategies = {}
    for row in cur.fetchall():
        try:
            strategies[row[0]] = json.loads(row[1])
        except:
            pass
    conn.close()
    return strategies

def calculate_break_even(entry_price):
    """
    Calculate exit price to cover 0.1% entry fee + 0.1% exit fee.
    Formula: Exit = Entry * (1 + fee) / (1 - fee)
    """
    if entry_price == 0: return 0
    return entry_price * (1 + FEE_RATE) / (1 - FEE_RATE)

def analyze_legacy():
    strategies = get_positions()
    
    print("=" * 80)
    print("LEGACY POSITIONS BREAK-EVEN ANALYSIS (Including Hidden Fees)")
    print("=" * 80)
    print(f"Fee Rate Assumed: {FEE_RATE*100:.1f}% per trade (0.2% roundtrip)")
    print("-" * 80)
    print(f"{'STRATEGY':<15} {'SYMBOL':<10} {'AMOUNT':>10} {'ENTRY':>10} {'BREAK-EVEN':>12} {'GAP %':>8}")
    print("-" * 80)
    
    # 1. GRID POSITIONS
    grid_strat = strategies.get("grid_trading", {})
    grids = grid_strat.get("grids", {})
    
    for symbol, grid_data in grids.items():
        levels = grid_data.get("levels", [])
        bought = [l for l in levels if l.get("status") == "bought"]
        
        for lvl in bought:
            # Legacy positions usually lack explicit fee tracking
            # Use stored buy price or executed price
            entry = lvl.get("buy_executed_price", lvl.get("buy_price", 0))
            amount = lvl.get("amount", 0)
            
            be_price = calculate_break_even(entry)
            gap = ((be_price - entry) / entry) * 100
            
            print(f"{'Grid':<15} {symbol:<10} {amount:>10.5f} ${entry:>9.2f} ${be_price:>11.2f} {gap:>7.2f}%")

    # 2. DCA POSITIONS
    dca_strat = strategies.get("dca_intelligent", {})
    dca_pos = dca_strat.get("positions", {})
    
    for symbol, pos in dca_pos.items():
        entry = pos.get("avg_price", 0)
        amount = pos.get("amount", 0)
        
        if amount > 0:
            be_price = calculate_break_even(entry)
            gap = ((be_price - entry) / entry) * 100
            
            print(f"{'DCA':<15} {symbol:<10} {amount:>10.5f} ${entry:>9.2f} ${be_price:>11.2f} {gap:>7.2f}%")

    # 3. TECHNICAL POSITIONS
    tech_strat = strategies.get("technical_rsi_macd", {})
    tech_pos = tech_strat.get("positions", {})
    
    # Check if positions is a dict or list (depends on implementation version)
    # Based on earlier reads, it seemed to be a dict by symbol
    if isinstance(tech_pos, dict):
        for symbol, pos in tech_pos.items():
            entry = pos.get("entry_price", 0)
            amount = pos.get("amount", 0)
            
            be_price = calculate_break_even(entry)
            gap = ((be_price - entry) / entry) * 100
            
            print(f"{'Technical':<15} {symbol:<10} {amount:>10.5f} ${entry:>9.2f} ${be_price:>11.2f} {gap:>7.2f}%")

    print("-" * 80)
    print("NOTE: Any sell below 'BREAK-EVEN' price results in a NET LOSS after fees.")

if __name__ == "__main__":
    analyze_legacy()
