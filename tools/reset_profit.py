"""
Profit Reset Script
===================
Resets total profit and ROI to zero for fresh tracking with new fee logic.
"""
import sqlite3
import json

DB_PATH = "data/trading_bot.db"

def reset_profit():
    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()
    
    print("Resetting profit metrics...")
    
    # 1. Reset portfolio stats
    cur.execute("SELECT current_capital FROM portfolio_state ORDER BY id DESC LIMIT 1")
    row = cur.fetchone()
    current_capital = row[0] if row else 75
    
    # Reset to current capital, but 0 profit
    # Using correct columns including updated_at
    cur.execute("""
        INSERT INTO portfolio_state (
            current_capital, total_invested, total_profit,
            trades_count, winning_trades, losing_trades, updated_at
        ) VALUES (?, 0, 0, 0, 0, 0, datetime('now'))
    """, (current_capital,))
    
    # 2. Reset strategy states (only profit counters, not positions)
    cur.execute("SELECT strategy_name, state_data FROM strategy_state")
    strategies = cur.fetchall()
    
    for strategy, state_json in strategies:
        try:
            state = json.loads(state_json)
            # Reset metrics
            state["total_profit"] = 0
            state["total_trades"] = 0
            if "winning_trades" in state: state["winning_trades"] = 0
            if "losing_trades" in state: state["losing_trades"] = 0
            
            # Update DB
            cur.execute(
                "UPDATE strategy_state SET state_data = ? WHERE strategy_name = ?",
                (json.dumps(state), strategy)
            )
            print(f"Reset metrics for {strategy}")
        except Exception as e:
            print(f"Error resetting {strategy}: {e}")
            
    conn.commit()
    conn.close()
    print("PROFIT RESET COMPLETE. Ready for new test cycle.")

if __name__ == "__main__":
    reset_profit()
