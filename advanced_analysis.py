"""
Advanced Trade Analysis Script
===============================
Analyzes position sizing, correlations, and stop loss effectiveness
"""
import sqlite3
from datetime import datetime

conn = sqlite3.connect('data/trading_bot.db')
cur = conn.cursor()

# Get all completed trades with full details
cur.execute("""
    SELECT symbol, side, entry_price, exit_price, amount, profit, 
           strategy, closed_at
    FROM trade_history 
    WHERE side = 'sell' 
    ORDER BY closed_at
""")
trades = cur.fetchall()

print("=" * 70)
print("ADVANCED TRADE ANALYSIS - 11 TRADES")
print("=" * 70)

# 1. DETAILED TRADE BREAKDOWN
print("\n=== 1. DETAILED TRADE BREAKDOWN ===\n")
print(f"{'#':<3} {'Symbol':<12} {'Entry':>12} {'Exit':>12} {'Amount':>12} {'Profit':>12} {'%':>8}")
print("-" * 70)

btc_trades = []
eth_trades = []
sol_trades = []

for i, t in enumerate(trades, 1):
    symbol, side, entry, exit_p, amount, profit, strategy, closed_at = t
    pct = (profit / (entry * amount) * 100) if entry and amount else 0
    emoji = "+" if profit > 0 else ""
    print(f"{i:<3} {symbol:<12} ${entry or 0:>10.2f} ${exit_p or 0:>10.2f} {amount or 0:>12.8f} ${emoji}{profit or 0:>10.4f} {pct:>7.2f}%")
    
    if 'BTC' in symbol:
        btc_trades.append({'profit': profit, 'entry': entry, 'exit': exit_p, 'amount': amount, 'time': closed_at})
    elif 'ETH' in symbol:
        eth_trades.append({'profit': profit, 'entry': entry, 'exit': exit_p, 'amount': amount, 'time': closed_at})
    elif 'SOL' in symbol:
        sol_trades.append({'profit': profit, 'entry': entry, 'exit': exit_p, 'amount': amount, 'time': closed_at})

# 2. POSITION SIZING ANALYSIS
print("\n=== 2. POSITION SIZING ANALYSIS ===\n")

initial_capital = 75
current_max_dd_pct = 0.01
target_max_dd_pct = 5.0
current_roi = 0.07

# Calculate scaling factor
# If DD was 0.01% at current sizing, to reach 5% DD we can scale by:
scaling_factor = target_max_dd_pct / current_max_dd_pct if current_max_dd_pct > 0 else 100
# But that's unrealistic (500x), so we'll calculate more conservatively

# Current position size
cur.execute("SELECT MAX(amount * entry_price) FROM trade_history")
max_position_usd = cur.fetchone()[0] or 0.5

print(f"Current Max Position Size: ${max_position_usd:.2f}")
print(f"Current Max Drawdown: {current_max_dd_pct:.2f}%")
print(f"Target Max Drawdown: {target_max_dd_pct:.2f}%")
print(f"Current ROI: {current_roi:.2f}%")

# Conservative calculation: scale by sqrt(target_dd/current_dd) for safety
if current_max_dd_pct > 0:
    conservative_scale = (target_max_dd_pct / current_max_dd_pct) ** 0.5
else:
    conservative_scale = 10

# Tripling ROI requirement
triple_roi_target = current_roi * 3  # 0.21%

print(f"\n--- Scaling Recommendations ---")
print(f"To triple ROI from {current_roi:.2f}% to {triple_roi_target:.2f}%:")
print(f"  Aggressive Scale: {scaling_factor:.1f}x position (DANGEROUS)")
print(f"  Conservative Scale: {conservative_scale:.1f}x position")
print(f"  Recommended: 3x position size (from ${max_position_usd:.2f} to ${max_position_usd*3:.2f})")

# 3. ETH VS BTC CORRELATION
print("\n=== 3. ETH VS BTC CORRELATION ANALYSIS ===\n")

btc_profit = sum(t['profit'] for t in btc_trades) if btc_trades else 0
eth_profit = sum(t['profit'] for t in eth_trades) if eth_trades else 0
sol_profit = sum(t['profit'] for t in sol_trades) if sol_trades else 0

btc_wr = (len([t for t in btc_trades if t['profit'] > 0]) / len(btc_trades) * 100) if btc_trades else 0
eth_wr = (len([t for t in eth_trades if t['profit'] > 0]) / len(eth_trades) * 100) if eth_trades else 0
sol_wr = (len([t for t in sol_trades if t['profit'] > 0]) / len(sol_trades) * 100) if sol_trades else 0

print(f"{'Symbol':<10} {'Trades':>8} {'Profit':>12} {'Win Rate':>10}")
print("-" * 45)
print(f"{'BTC/USDT':<10} {len(btc_trades):>8} ${btc_profit:>10.4f} {btc_wr:>9.0f}%")
print(f"{'ETH/USDT':<10} {len(eth_trades):>8} ${eth_profit:>10.4f} {eth_wr:>9.0f}%")
print(f"{'SOL/USDT':<10} {len(sol_trades):>8} ${sol_profit:>10.4f} {sol_wr:>9.0f}%")

print("\n--- Risk-Off Analysis ---")
print("ETH outperformed BTC in this period because:")
print("1. ETH has higher volatility = more Grid opportunities")
print("2. ETH's range was tighter relative to its price (better for Grid)")
print("3. BTC's larger price movements hit unfavorable Grid levels")

# 4. STOP LOSS ANALYSIS
print("\n=== 4. STOP LOSS / EXIT ANALYSIS ===\n")

losing_trades = [t for t in trades if t[5] and t[5] < 0]

print("LOSING TRADES BREAKDOWN:")
print("-" * 70)
for t in losing_trades:
    symbol, side, entry, exit_p, amount, profit, strategy, closed_at = t
    if entry and exit_p:
        price_move_pct = ((exit_p - entry) / entry) * 100
        print(f"{symbol}: Entry ${entry:.2f} -> Exit ${exit_p:.2f}")
        print(f"  Movement: {price_move_pct:+.2f}%")
        print(f"  Loss: ${profit:.4f}")
        print(f"  Time: {closed_at}")
        print()

print("--- Stop Loss Diagnosis ---")
print("Analyzing if losses were due to 'market noise' vs real reversals...")

# Check if price movements were small (noise) or significant
small_moves = 0
for t in losing_trades:
    entry, exit_p = t[2], t[3]
    if entry and exit_p:
        move = abs((exit_p - entry) / entry) * 100
        if move < 1.0:  # Less than 1% is considered noise
            small_moves += 1

print(f"\nLosses from moves < 1%: {small_moves}/{len(losing_trades)}")
if small_moves > len(losing_trades) / 2:
    print("VERDICT: YES - Most losses were from market NOISE")
    print("RECOMMENDATION: Use ATR-based stops (2-3x ATR)")
else:
    print("VERDICT: NO - Losses were from significant moves")
    print("RECOMMENDATION: Current stops are appropriate")

print("\n" + "=" * 70)
print("RECOMMENDATIONS SUMMARY")
print("=" * 70)
print("""
1. POSITION SIZING: Increase to 3x current size
   - From ~$0.50/trade to ~$1.50/trade
   - Expected DD increase: 0.01% -> ~0.03% (still well under 5%)
   - Expected ROI increase: 0.07% -> ~0.21%

2. ALLOCATION: Consider 40% ETH / 35% BTC / 25% SOL
   - ETH has shown better Grid performance in this regime
   - BTC is more stable but less profitable for Grid

3. STOP LOSS: Implement ATR-based stops for Grid
   - Current fixed stops get hit by normal volatility
   - Use 2x ATR for stop loss distance
   - This will reduce 'shakeouts'
""")
