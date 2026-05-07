import sqlite3

DB = r'd:\USUARIOS\jostin_fuentes\OneDrive - Corporación Unificada Nacional de Educación Superior - CUN\Escritorio\BOT TRADING\data\trading_bot.db'

def clean_database():
    conn = sqlite3.connect(DB)
    cur = conn.cursor()
    
    print("Iniciando limpieza de la base de datos...")
    
    # 1. Identificar trades de polvo
    cur.execute("SELECT COUNT(*), SUM(profit) FROM trade_history WHERE side='sell' AND amount < 0.00001")
    dust_count, dust_profit = cur.fetchone()
    
    if dust_profit is None:
        dust_profit = 0
        
    print(f"Se encontraron {dust_count} trades de polvo para eliminar.")
    print(f"Profit a descontar: ${dust_profit:.6f}")
    
    if dust_count == 0:
        print("No hay polvo para limpiar.")
        conn.close()
        return

    # 2. Eliminar trades de polvo
    cur.execute("DELETE FROM trade_history WHERE side='sell' AND amount < 0.00001")
    
    # 3. Recalcular métricas de trade_history
    cur.execute("SELECT COUNT(*) FROM trade_history")
    total_trades = cur.fetchone()[0]
    
    cur.execute("SELECT COUNT(*) FROM trade_history WHERE profit > 0")
    total_wins = cur.fetchone()[0]
    
    cur.execute("SELECT COUNT(*) FROM trade_history WHERE profit <= 0 AND side='sell'")
    total_losses = cur.fetchone()[0]
    
    # 4. Actualizar portfolio_state (se asume que la id más reciente es la actual o se actualiza todo)
    # Por seguridad actualizaremos el registro más reciente
    cur.execute("SELECT id, current_capital, total_profit FROM portfolio_state ORDER BY updated_at DESC LIMIT 1")
    portfolio = cur.fetchone()
    
    if portfolio:
        p_id, current_capital, total_profit = portfolio
        
        new_capital = current_capital - dust_profit
        new_total_profit = total_profit - dust_profit
        
        cur.execute("""
            UPDATE portfolio_state 
            SET current_capital = ?, 
                total_profit = ?, 
                trades_count = ?, 
                winning_trades = ?, 
                losing_trades = ?
            WHERE id = ?
        """, (new_capital, new_total_profit, total_trades, total_wins, total_losses, p_id))
        
        print("\nNuevas estadísticas:")
        print(f"  - Total Trades: {total_trades}")
        print(f"  - Wins: {total_wins}")
        print(f"  - Losses: {total_losses}")
        print(f"  - Total Profit Corregido: ${new_total_profit:.6f}")
    
    # Guardar cambios
    conn.commit()
    conn.close()
    print("\nBase de datos limpiada y sincronizada correctamente.")

if __name__ == "__main__":
    clean_database()
