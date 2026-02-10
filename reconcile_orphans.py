"""Script para reconciliar activos huérfanos e inyectarlos en la estrategia DCA."""
import sys, os, json, sqlite3
from datetime import datetime
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from src.core.state_manager import get_state_manager
from src.core.data_manager import get_data_manager
from src.core.exchange_manager import get_exchange

# Inicializar componentes
sm = get_state_manager()
dm = get_data_manager()
ex = get_exchange()

DB_PATH = "data/trading_bot.db"

def get_grid_tracked_amounts(conn):
    """Calcula la cantidad de activos atrapados en Grid Strategy."""
    tracked = {}
    cursor = conn.cursor()
    cursor.execute("SELECT state_data FROM strategy_state WHERE strategy_name = 'grid_trading'")
    row = cursor.fetchone()
    if row:
        try:
            grid_state = json.loads(row[0])
            for symbol, grid_data in grid_state.get("grids", {}).items():
                levels = grid_data.get("levels", [])
                bought = 0
                for lvl in levels:
                    if lvl.get("status") == "bought":
                        bought += float(lvl.get("amount", 0))
                if bought > 0:
                    tracked[symbol] = bought
        except Exception as e:
            print(f"Error parsing Grid state: {e}")
    return tracked

def reconcile():
    print("="*60)
    print("RECONCILIACIÓN DE ACTIVOS HUÉRFANOS")
    print("="*60)
    
    conn = sqlite3.connect(DB_PATH)
    
    # 1. Obtener balance real (Wallet)
    balance = ex.get_balance()
    print(f"Wallet Balance: {json.dumps(balance, indent=2)}")
    
    # 2. Obtener lo que ya está trackeado
    grid_tracked = get_grid_tracked_amounts(conn)
    print(f"Grid Tracked: {grid_tracked}")
    
    # Obtener estado actual de DCA
    cursor = conn.cursor()
    cursor.execute("SELECT state_data FROM strategy_state WHERE strategy_name = 'dca_intelligent'")
    row = cursor.fetchone()
    if row:
        dca_state = json.loads(row[0])
    else:
        dca_state = {
            "accumulated": {},
            "entry_prices": {},
            "last_buy_time": {},
            "price_history": {}
        }
    
    dca_accumulated = dca_state.get("accumulated", {})
    dca_entry_prices = dca_state.get("entry_prices", {})
    
    # 3. Calcular huérfanos y actualizar DCA
    updates_made = False
    
    for asset, amount_str in balance.items():
        if asset == "USDT": continue
        
        wallet_amount = float(amount_str)
        if wallet_amount <= 0: continue
        
        symbol = f"{asset}/USDT"
        
        # Cantidad ya trackeada
        grid_amt = grid_tracked.get(symbol, 0)
        dca_amt = float(dca_accumulated.get(symbol, 0))
        total_tracked = grid_amt + dca_amt
        
        orphaned = wallet_amount - total_tracked
        
        # Umbral mínimo para considerar (evitar polvo)
        if orphaned > 0.00001: 
            print(f"\nDetectado huérfano en {symbol}:")
            print(f"  Wallet: {wallet_amount:.8f}")
            print(f"  Tracked: {total_tracked:.8f} (Grid: {grid_amt:.8f}, DCA: {dca_amt:.8f})")
            print(f"  Orphaned: {orphaned:.8f}")
            
            # Obtener precio actual para cost basis
            try:
                mkt = dm.get_market_summary(symbol)
                current_price = float(mkt['price'])
                print(f"  Precio Mercado (Nuevo Entry): ${current_price:.2f}")
                
                # Calcular nuevo precio promedio ponderado para DCA
                # (ExistingDCA * ExistingPrice + Orphaned * CurrentPrice) / (ExistingDCA + Orphaned)
                old_dca_amt = dca_amt
                old_dca_price = float(dca_entry_prices.get(symbol, 0))
                
                new_total_dca = old_dca_amt + orphaned
                new_avg_price = ((old_dca_amt * old_dca_price) + (orphaned * current_price)) / new_total_dca
                
                # Actualizar estado DCA
                dca_accumulated[symbol] = new_total_dca
                dca_entry_prices[symbol] = new_avg_price
                
                print(f"  --> ASIGNADO A DCA: Nuevo Total: {new_total_dca:.8f}, Nuevo Precio: ${new_avg_price:.2f}")
                updates_made = True
                
            except Exception as e:
                print(f"Error obteniendo precio para {symbol}: {e}")
                
    if updates_made:
        # Guardar en DB
        dca_state["accumulated"] = dca_accumulated
        dca_state["entry_prices"] = dca_entry_prices
        
        json_state = json.dumps(dca_state)
        
        # Upsert
        cursor.execute("SELECT 1 FROM strategy_state WHERE strategy_name = 'dca_intelligent'")
        if cursor.fetchone():
            cursor.execute("UPDATE strategy_state SET state_data = ?, updated_at = ? WHERE strategy_name = 'dca_intelligent'", 
                           (json_state, datetime.now().isoformat()))
        else:
            cursor.execute("INSERT INTO strategy_state (strategy_name, state_data, updated_at) VALUES (?, ?, ?)",
                           ('dca_intelligent', json_state, datetime.now().isoformat()))
        
        conn.commit()
        print("\n✅ Base de datos actualizada con éxito.")
    else:
        print("\n✅ No se encontraron activos huérfanos significativos.")
        
    conn.close()

if __name__ == "__main__":
    reconcile()
