"""
Quant Analysis Script - Trading Bot Performance Forensics
=========================================================
"""
import sqlite3
import json
from datetime import datetime, timedelta
import math

DB_PATH = "data/trading_bot.db"

def get_data():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    cur = conn.cursor()
    
    # Get all trades
    cur.execute("SELECT * FROM trade_history ORDER BY closed_at ASC")
    trades = [dict(r) for r in cur.fetchall()]
    
    # Get portfolio state
    cur.execute("SELECT * FROM portfolio_state ORDER BY id DESC LIMIT 1")
    row = cur.fetchone()
    portfolio = dict(row) if row else {"current_capital": 75, "total_profit": 0}
    
    # Get trade stats
    cur.execute("""
        SELECT 
            COUNT(*) as total,
            SUM(CASE WHEN profit > 0 THEN 1 ELSE 0 END) as wins,
            SUM(CASE WHEN profit < 0 THEN 1 ELSE 0 END) as losses,
            SUM(profit) as total_profit,
            MAX(profit) as best_trade,
            MIN(profit) as worst_trade,
            AVG(profit) as avg_profit
        FROM trade_history WHERE side = 'sell'
    """)
    stats = dict(cur.fetchone())
    
    conn.close()
    return trades, portfolio, stats

def calculate_metrics(trades, initial_capital=75):
    if not trades:
        return None
    
    # Filter only completed trades (sells)
    completed = [t for t in trades if t.get("side") == "sell" and t.get("profit") is not None]
    
    if not completed:
        return {"error": "No completed trades found"}
    
    profits = [t["profit"] for t in completed]
    total_profit = sum(profits)
    
    # Calculate returns
    returns = []
    running_capital = initial_capital
    equity_curve = [initial_capital]
    
    for p in profits:
        ret = p / running_capital if running_capital > 0 else 0
        returns.append(ret)
        running_capital += p
        equity_curve.append(running_capital)
    
    # Max Drawdown
    peak = initial_capital
    max_dd = 0
    for eq in equity_curve:
        if eq > peak:
            peak = eq
        dd = (peak - eq) / peak if peak > 0 else 0
        if dd > max_dd:
            max_dd = dd
    
    # Sharpe Ratio (simplified, assuming risk-free = 0)
    if len(returns) > 1:
        avg_return = sum(returns) / len(returns)
        std_return = (sum((r - avg_return)**2 for r in returns) / len(returns)) ** 0.5
        sharpe = (avg_return / std_return) * (252 ** 0.5) if std_return > 0 else 0
    else:
        sharpe = 0
        avg_return = returns[0] if returns else 0
    
    # Sortino Ratio (downside deviation only)
    negative_returns = [r for r in returns if r < 0]
    if negative_returns:
        downside_std = (sum(r**2 for r in negative_returns) / len(negative_returns)) ** 0.5
        sortino = (avg_return / downside_std) * (252 ** 0.5) if downside_std > 0 else 0
    else:
        sortino = float('inf')  # No negative returns
    
    # Time-based analysis
    first_trade = completed[0].get("closed_at", "")
    last_trade = completed[-1].get("closed_at", "")
    
    try:
        start = datetime.fromisoformat(first_trade.replace("Z", ""))
        end = datetime.fromisoformat(last_trade.replace("Z", ""))
        days_active = (end - start).days + 1
    except:
        days_active = 1
    
    # APY calculation
    if days_active > 0 and initial_capital > 0:
        total_return = total_profit / initial_capital
        daily_return = (1 + total_return) ** (1/days_active) - 1
        apy = ((1 + daily_return) ** 365 - 1) * 100
        
        # CAGR
        cagr = (((initial_capital + total_profit) / initial_capital) ** (365/days_active) - 1) * 100
    else:
        apy = 0
        cagr = 0
    
    # Win rate
    wins = len([p for p in profits if p > 0])
    losses = len([p for p in profits if p < 0])
    win_rate = (wins / len(profits)) * 100 if profits else 0
    
    # Projections
    monthly_return = total_profit / max(days_active/30, 1)
    
    current_capital = initial_capital + total_profit
    projections = {}
    for months in [12, 24, 36]:
        # Optimistic (compound growth)
        if monthly_return > 0:
            monthly_pct = monthly_return / current_capital
            optimistic = current_capital * ((1 + monthly_pct) ** months)
        else:
            optimistic = current_capital
        
        # Stress scenario (-20% market crash)
        stress = optimistic * 0.80
        
        projections[f"{months}m"] = {
            "optimistic": round(optimistic, 2),
            "stress": round(stress, 2)
        }
    
    return {
        "trades_analyzed": len(completed),
        "days_active": days_active,
        "initial_capital": initial_capital,
        "current_capital": round(current_capital, 2),
        "total_profit": round(total_profit, 4),
        "total_return_pct": round((total_profit / initial_capital) * 100, 2),
        "win_rate": round(win_rate, 2),
        "wins": wins,
        "losses": losses,
        "best_trade": round(max(profits), 4),
        "worst_trade": round(min(profits), 4),
        "avg_profit": round(sum(profits) / len(profits), 4),
        "max_drawdown_pct": round(max_dd * 100, 2),
        "sharpe_ratio": round(sharpe, 2),
        "sortino_ratio": round(sortino, 2) if sortino != float('inf') else "∞ (no losses)",
        "apy": round(apy, 2),
        "cagr": round(cagr, 2),
        "projections": projections,
        "first_trade": first_trade,
        "last_trade": last_trade
    }

if __name__ == "__main__":
    trades, portfolio, stats = get_data()
    
    print("=" * 60)
    print("QUANT ANALYSIS - TRADING BOT FORENSICS")
    print("=" * 60)
    
    print(f"\n📊 Database Stats:")
    print(f"   Total trades in DB: {stats.get('total', 0)}")
    print(f"   Winning trades: {stats.get('wins', 0)}")
    print(f"   Losing trades: {stats.get('losses', 0)}")
    print(f"   Total P&L: ${stats.get('total_profit', 0):.4f}")
    print(f"   Best trade: ${stats.get('best_trade', 0):.4f}")
    print(f"   Worst trade: ${stats.get('worst_trade', 0):.4f}")
    
    metrics = calculate_metrics(trades)
    
    if metrics and "error" not in metrics:
        print(f"\n📈 Performance Metrics:")
        print(f"   Trades Analyzed: {metrics['trades_analyzed']}")
        print(f"   Days Active: {metrics['days_active']}")
        print(f"   Initial Capital: ${metrics['initial_capital']}")
        print(f"   Current Capital: ${metrics['current_capital']}")
        print(f"   Total Profit: ${metrics['total_profit']}")
        print(f"   Total Return: {metrics['total_return_pct']}%")
        
        print(f"\n🎯 Risk Metrics:")
        print(f"   Win Rate: {metrics['win_rate']}%")
        print(f"   Max Drawdown: {metrics['max_drawdown_pct']}%")
        print(f"   Sharpe Ratio: {metrics['sharpe_ratio']}")
        print(f"   Sortino Ratio: {metrics['sortino_ratio']}")
        
        print(f"\n📊 Annualized Performance:")
        print(f"   APY: {metrics['apy']}%")
        print(f"   CAGR: {metrics['cagr']}%")
        
        print(f"\n🔮 Capital Projections:")
        for period, proj in metrics['projections'].items():
            print(f"   {period}: Optimistic ${proj['optimistic']} | Stress ${proj['stress']}")
    else:
        print(f"\n⚠️ {metrics}")
    
    print("\n" + "=" * 60)
    print(json.dumps(metrics, indent=2, default=str))
