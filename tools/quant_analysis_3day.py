"""
Quant Analysis Script - 3-Day Performance Report
=================================================
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
    cur.execute("SELECT * FROM trade_history WHERE side = 'sell' ORDER BY closed_at ASC")
    trades = [dict(r) for r in cur.fetchall()]
    
    # Get portfolio state
    cur.execute("SELECT * FROM portfolio_state ORDER BY id DESC LIMIT 1")
    row = cur.fetchone()
    portfolio = dict(row) if row else {"current_capital": 75, "total_profit": 0}
    
    conn.close()
    return trades, portfolio

def calculate_metrics(trades, initial_capital=75):
    if not trades:
        return {"error": "No completed trades found"}
    
    profits = [t["profit"] for t in trades if t.get("profit") is not None]
    
    if not profits:
        return {"error": "No profit data found"}
    
    total_profit = sum(profits)
    
    # Calculate returns per trade
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
    
    # Sharpe Ratio (annualized, assuming risk-free = 0)
    if len(returns) > 1:
        avg_return = sum(returns) / len(returns)
        variance = sum((r - avg_return)**2 for r in returns) / len(returns)
        std_return = math.sqrt(variance)
        sharpe = (avg_return / std_return) * math.sqrt(252) if std_return > 0 else 0
    else:
        sharpe = 0
        avg_return = returns[0] if returns else 0
    
    # Sortino Ratio
    negative_returns = [r for r in returns if r < 0]
    if negative_returns:
        downside_variance = sum(r**2 for r in negative_returns) / len(negative_returns)
        downside_std = math.sqrt(downside_variance)
        sortino = (avg_return / downside_std) * math.sqrt(252) if downside_std > 0 else 0
    else:
        sortino = float('inf')
    
    # Time analysis
    first_trade = trades[0].get("closed_at", "")
    last_trade = trades[-1].get("closed_at", "")
    
    try:
        start = datetime.fromisoformat(first_trade.replace("Z", ""))
        end = datetime.fromisoformat(last_trade.replace("Z", ""))
        days_active = max((end - start).days, 1)
        hours_active = (end - start).total_seconds() / 3600
    except:
        days_active = 1
        hours_active = 24
    
    # Win rate
    wins = len([p for p in profits if p > 0])
    losses = len([p for p in profits if p < 0])
    win_rate = (wins / len(profits)) * 100 if profits else 0
    
    # Profit factor
    gross_profit = sum(p for p in profits if p > 0)
    gross_loss = abs(sum(p for p in profits if p < 0))
    profit_factor = gross_profit / gross_loss if gross_loss > 0 else float('inf')
    
    # Trade analysis by symbol
    by_symbol = {}
    for t in trades:
        sym = t.get("symbol", "UNKNOWN")
        if sym not in by_symbol:
            by_symbol[sym] = {"trades": 0, "profit": 0, "wins": 0, "losses": 0}
        by_symbol[sym]["trades"] += 1
        by_symbol[sym]["profit"] += t.get("profit", 0)
        if t.get("profit", 0) > 0:
            by_symbol[sym]["wins"] += 1
        else:
            by_symbol[sym]["losses"] += 1
    
    # Trade analysis by hour
    by_hour = {}
    for t in trades:
        try:
            dt = datetime.fromisoformat(t.get("closed_at", "").replace("Z", ""))
            hour = dt.hour
            if hour not in by_hour:
                by_hour[hour] = {"trades": 0, "profit": 0}
            by_hour[hour]["trades"] += 1
            by_hour[hour]["profit"] += t.get("profit", 0)
        except:
            pass
    
    current_capital = initial_capital + total_profit
    roi_pct = (total_profit / initial_capital) * 100
    
    return {
        "trades_analyzed": len(profits),
        "days_active": days_active,
        "hours_active": round(hours_active, 1),
        "initial_capital": initial_capital,
        "current_capital": round(current_capital, 4),
        "total_profit": round(total_profit, 4),
        "roi_pct": round(roi_pct, 2),
        "win_rate": round(win_rate, 1),
        "wins": wins,
        "losses": losses,
        "best_trade": round(max(profits), 4),
        "worst_trade": round(min(profits), 4),
        "avg_trade": round(sum(profits) / len(profits), 4),
        "max_drawdown_pct": round(max_dd * 100, 2),
        "sharpe_ratio": round(sharpe, 2),
        "sortino_ratio": round(sortino, 2) if sortino != float('inf') else "Infinite (no losses)",
        "profit_factor": round(profit_factor, 2) if profit_factor != float('inf') else "Infinite",
        "by_symbol": by_symbol,
        "by_hour": by_hour,
        "first_trade": first_trade,
        "last_trade": last_trade,
        "all_trades": trades
    }

if __name__ == "__main__":
    trades, portfolio = get_data()
    metrics = calculate_metrics(trades)
    
    print("=" * 60)
    print("3-DAY QUANT ANALYSIS REPORT")
    print("=" * 60)
    
    if "error" in metrics:
        print(f"Error: {metrics['error']}")
    else:
        print(f"\n=== PERFORMANCE SUMMARY ===")
        print(f"Period: {metrics['hours_active']} hours ({metrics['days_active']} days)")
        print(f"Trades: {metrics['trades_analyzed']}")
        print(f"Capital: ${metrics['initial_capital']} -> ${metrics['current_capital']}")
        print(f"P&L: ${metrics['total_profit']} ({metrics['roi_pct']}%)")
        
        print(f"\n=== RISK METRICS ===")
        print(f"Win Rate: {metrics['win_rate']}%")
        print(f"Max Drawdown: {metrics['max_drawdown_pct']}%")
        print(f"Sharpe Ratio: {metrics['sharpe_ratio']}")
        print(f"Sortino Ratio: {metrics['sortino_ratio']}")
        print(f"Profit Factor: {metrics['profit_factor']}")
        
        print(f"\n=== BY SYMBOL ===")
        for sym, data in metrics['by_symbol'].items():
            wr = (data['wins']/data['trades'])*100 if data['trades'] > 0 else 0
            print(f"{sym}: {data['trades']} trades, ${data['profit']:.4f}, WR: {wr:.0f}%")
        
        print(f"\n=== BY HOUR (Losses) ===")
        losing_hours = {h: d for h, d in metrics['by_hour'].items() if d['profit'] < 0}
        for hour in sorted(losing_hours.keys()):
            data = losing_hours[hour]
            print(f"Hour {hour:02d}: {data['trades']} trades, ${data['profit']:.4f}")
        
        print(f"\n=== INDIVIDUAL TRADES ===")
        for t in metrics['all_trades']:
            emoji = "✅" if t.get('profit', 0) > 0 else "❌"
            print(f"{emoji} {t['symbol']}: ${t.get('profit', 0):.4f} @ {t.get('closed_at', 'N/A')}")
    
    print("\n" + "=" * 60)
    print("JSON OUTPUT:")
    print(json.dumps({k: v for k, v in metrics.items() if k != 'all_trades'}, indent=2, default=str))
