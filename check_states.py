import sqlite3, json, os

db_path = "data/trading_bot.db"

def check_states():
    if not os.path.exists(db_path):
        print("DB not found")
        return

    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()
    
    print("--- GRID TRADING STATE ---")
    cursor.execute("SELECT state_data FROM strategy_state WHERE strategy_name = 'grid_trading'")
    row = cursor.fetchone()
    if row:
        grid_data = json.loads(row[0])
        for symbol, data in grid_data.get("grids", {}).items():
            bought_count = sum(1 for l in data.get("levels", []) if l.get("status") == "bought")
            print(f"Symbol: {symbol} | Levels Bought: {bought_count}")
    else:
        print("Grid state not found")

    print("\n--- DCA STATE ---")
    cursor.execute("SELECT state_data FROM strategy_state WHERE strategy_name = 'dca_intelligent'")
    row = cursor.fetchone()
    if row:
        dca_data = json.loads(row[0])
        accumulated = dca_data.get("accumulated", {})
        entry_prices = dca_data.get("entry_prices", {})
        
        if not accumulated:
            print("DCA state empty (no accumulated positions)")
            
        for symbol, amount in accumulated.items():
            amount = float(amount)
            if amount > 0:
                price = float(entry_prices.get(symbol, 0))
                print(f"Symbol: {symbol} | Amount: {amount:.8f} | Avg Price: {price:.2f}")
    else:
        print("DCA state not found")
        
    print("\n--- POSITIONS TABLE ---")
    cursor.execute("SELECT symbol, strategy, amount, entry_price FROM positions WHERE status = 'open'")
    rows = cursor.fetchall()
    for r in rows:
        print(f"Symbol: {r[0]} | Strategy: {r[1]} | Amount: {r[2]} | Price: {r[3]}")

    conn.close()

if __name__ == "__main__":
    check_states()
