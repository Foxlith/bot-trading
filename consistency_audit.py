"""
Data Consistency Audit Script
==============================
Compares logs vs database for position tracking discrepancies
"""
import sqlite3
import re
from datetime import datetime
from pathlib import Path

# Paths
DB_PATH = "data/trading_bot.db"
LOGS_DIR = Path("logs")

def get_db_positions():
    """Get current open positions from database."""
    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()
    
    # Get open positions count from trade_history (buys without matching sells)
    cur.execute("""
        SELECT symbol, COUNT(*) as buys 
        FROM trade_history 
        WHERE side = 'buy' 
        GROUP BY symbol
    """)
    buys = {row[0]: row[1] for row in cur.fetchall()}
    
    cur.execute("""
        SELECT symbol, COUNT(*) as sells 
        FROM trade_history 
        WHERE side = 'sell' 
        GROUP BY symbol
    """)
    sells = {row[0]: row[1] for row in cur.fetchall()}
    
    # Get portfolio state
    cur.execute("SELECT * FROM portfolio_state ORDER BY id DESC LIMIT 1")
    portfolio = cur.fetchone()
    
    # Get total trades
    cur.execute("SELECT COUNT(*) FROM trade_history")
    total_trades = cur.fetchone()[0]
    
    conn.close()
    
    return {
        'buys_by_symbol': buys,
        'sells_by_symbol': sells,
        'portfolio': portfolio,
        'total_trades': total_trades
    }

def get_log_positions():
    """Parse logs to count buy/sell operations."""
    buys = {}
    sells = {}
    
    log_files = sorted(LOGS_DIR.glob("bot_2026-01-*.log"))
    
    buy_pattern = re.compile(r'\[PAPER\] Compra: [\d.]+ (\w+) @')
    sell_pattern = re.compile(r'Grid (\w+/USDT) - Venta nivel')
    dca_buy_pattern = re.compile(r'DCA (\w+/USDT): Compra')
    
    for log_file in log_files:
        try:
            with open(log_file, 'r', encoding='utf-8') as f:
                content = f.read()
                
                # Count PAPER buys
                for match in buy_pattern.finditer(content):
                    symbol = match.group(1) + '/USDT'
                    buys[symbol] = buys.get(symbol, 0) + 1
                
                # Count Grid sells
                for match in sell_pattern.finditer(content):
                    symbol = match.group(1)
                    sells[symbol] = sells.get(symbol, 0) + 1
                    
                # Count DCA buys
                for match in dca_buy_pattern.finditer(content):
                    symbol = match.group(1)
                    buys[symbol] = buys.get(symbol, 0) + 1
        except Exception as e:
            print(f"Error reading {log_file}: {e}")
    
    return {
        'buys_by_symbol': buys,
        'sells_by_symbol': sells,
        'log_files_analyzed': len(log_files)
    }

def get_strategy_state():
    """Get current strategy states from database."""
    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()
    
    cur.execute("SELECT strategy_name, state_json FROM strategy_state")
    states = {}
    for row in cur.fetchall():
        states[row[0]] = row[1]
    
    conn.close()
    return states

if __name__ == "__main__":
    print("=" * 70)
    print("DATA CONSISTENCY AUDIT")
    print("=" * 70)
    
    db_data = get_db_positions()
    log_data = get_log_positions()
    
    print("\n=== DATABASE RECORDS ===")
    print(f"Total trades in DB: {db_data['total_trades']}")
    print(f"Buys by symbol: {db_data['buys_by_symbol']}")
    print(f"Sells by symbol: {db_data['sells_by_symbol']}")
    
    print("\n=== LOG RECORDS ===")
    print(f"Log files analyzed: {log_data['log_files_analyzed']}")
    print(f"Buys in logs: {log_data['buys_by_symbol']}")
    print(f"Sells in logs: {log_data['sells_by_symbol']}")
    
    # Compare
    print("\n=== DISCREPANCY CHECK ===")
    
    all_symbols = set(list(db_data['buys_by_symbol'].keys()) + 
                      list(log_data['buys_by_symbol'].keys()))
    
    discrepancies = []
    for symbol in all_symbols:
        db_buys = db_data['buys_by_symbol'].get(symbol, 0)
        log_buys = log_data['buys_by_symbol'].get(symbol, 0)
        db_sells = db_data['sells_by_symbol'].get(symbol, 0)
        log_sells = log_data['sells_by_symbol'].get(symbol, 0)
        
        buy_match = "OK" if db_buys == log_buys else f"MISMATCH (DB:{db_buys} vs LOG:{log_buys})"
        sell_match = "OK" if db_sells == log_sells else f"MISMATCH (DB:{db_sells} vs LOG:{log_sells})"
        
        if db_buys != log_buys or db_sells != log_sells:
            discrepancies.append(symbol)
        
        print(f"{symbol}: Buys={buy_match}, Sells={sell_match}")
    
    print("\n=== VERDICT ===")
    if discrepancies:
        print(f"DISCREPANCIES FOUND in: {discrepancies}")
        print("ACTION REQUIRED: Data sync issue detected")
    else:
        print("ALL DATA CONSISTENT - No discrepancies found")
    
    # Open positions calculation
    print("\n=== OPEN POSITIONS (DB) ===")
    for symbol in all_symbols:
        db_buys = db_data['buys_by_symbol'].get(symbol, 0)
        db_sells = db_data['sells_by_symbol'].get(symbol, 0)
        open_pos = db_buys - db_sells
        print(f"{symbol}: {open_pos} open positions ({db_buys} buys - {db_sells} sells)")
