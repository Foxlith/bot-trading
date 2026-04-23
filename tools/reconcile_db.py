import sys
import os
from loguru import logger
import sqlite3
import json

# Add project root to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from src.core.state_manager import get_state_manager
from src.core.exchange_manager import get_exchange
from src.core.data_manager import get_data_manager

def reconcile():
    logger.info("🔄 Iniciando reconciliación DB vs Wallet...")
    
    state_manager = get_state_manager()
    exchange = get_exchange()
    
    # 1. Obtener Balance Real
    wallet = exchange.get_balance()
    logger.info(f"💰 Wallet Balance: {wallet}")
    
    # 2. Obtener Posiciones SQL Abiertas
    conn = sqlite3.connect(state_manager.db_path)
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM positions WHERE status = 'open'")
    db_positions = cursor.fetchall()
    
    logger.info(f"📂 DB SQL Positions (Open): {len(db_positions)}")
    
    # 3. Verificar y Corregir
    for pos in db_positions:
        symbol = pos['symbol']
        base_asset = symbol.split('/')[0]
        
        wallet_amount = wallet.get(base_asset, 0)
        db_amount = pos['amount']
        
        # Tolerancia pequeña por redondeo
        if wallet_amount < (db_amount * 0.1): # Si tengo menos del 10% de lo que dice la DB
            logger.warning(f"⚠️ GHOST DETECTADO: {symbol} - DB: {db_amount} vs Wallet: {wallet_amount}")
            logger.info(f"🛠️ Cerrando posición fantasma ID {pos['id']}...")
            
            cursor.execute("UPDATE positions SET status = 'closed_by_audit', extra_data = ? WHERE id = ?", 
                           (json.dumps({"reason": "reconcile_script", "wallet_amount": wallet_amount}), pos['id']))
            conn.commit()
    
    logger.info("✅ Reconciliación SQL terminada.")
    
    # 4. Limpiar JSON States (Opcional, pero recomendado para evitar duplicidad)
    # Por ahora solo logueamos, la lógica de get_open_positions ya prioriza SQL si existe ID
    
    cursor.close()
    conn.close()

if __name__ == "__main__":
    reconcile()
