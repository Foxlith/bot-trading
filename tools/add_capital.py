import sqlite3
import json
import os
import re

DB_PATH = r'd:\USUARIOS\jostin_fuentes\OneDrive - Corporación Unificada Nacional de Educación Superior - CUN\Escritorio\BOT TRADING\data\trading_bot.db'
WALLET_PATH = r'd:\USUARIOS\jostin_fuentes\OneDrive - Corporación Unificada Nacional de Educación Superior - CUN\Escritorio\BOT TRADING\data\paper_wallet.json'
SETTINGS_PATH = r'd:\USUARIOS\jostin_fuentes\OneDrive - Corporación Unificada Nacional de Educación Superior - CUN\Escritorio\BOT TRADING\config\settings.py'
AMOUNT_TO_ADD = 100.0

print(f"Anadiendo ${AMOUNT_TO_ADD} al bot...")

# 1. Update Paper Wallet
try:
    with open(WALLET_PATH, 'r') as f:
        wallet = json.load(f)
    
    current_usdt = float(wallet.get("USDT", "0"))
    new_usdt = current_usdt + AMOUNT_TO_ADD
    wallet["USDT"] = str(new_usdt)
    
    with open(WALLET_PATH, 'w') as f:
        json.dump(wallet, f, indent=4)
    print(f"Paper Wallet actualizado: USDT {current_usdt:.2f} -> {new_usdt:.2f}")
except Exception as e:
    print(f"Error actualizando wallet: {e}")

# 2. Update Database (portfolio_state)
try:
    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()
    
    cur.execute("SELECT id, current_capital FROM portfolio_state ORDER BY updated_at DESC LIMIT 1")
    portfolio = cur.fetchone()
    if portfolio:
        p_id, current_cap = portfolio
        new_cap = current_cap + AMOUNT_TO_ADD
        cur.execute("UPDATE portfolio_state SET current_capital = ? WHERE id = ?", (new_cap, p_id))
        conn.commit()
        print(f"DB portfolio_state actualizado: Capital {current_cap:.2f} -> {new_cap:.2f}")
    conn.close()
except Exception as e:
    print(f"Error actualizando DB: {e}")

# 3. Update settings.py
try:
    with open(SETTINGS_PATH, 'r', encoding='utf-8') as f:
        content = f.read()
    
    # Update initial_usd: 300, -> initial_usd: 400,
    content = re.sub(r'("initial_usd":\s*)(\d+)', lambda m: f'{m.group(1)}{int(m.group(2)) + int(AMOUNT_TO_ADD)}', content)
    
    # Update paper_balance_usd: 300, -> paper_balance_usd: 400,
    content = re.sub(r'("paper_balance_usd":\s*)(\d+)', lambda m: f'{m.group(1)}{int(m.group(2)) + int(AMOUNT_TO_ADD)}', content)
    
    with open(SETTINGS_PATH, 'w', encoding='utf-8') as f:
        f.write(content)
    print(f"Configuracion settings.py actualizada (initial_usd +{AMOUNT_TO_ADD})")
except Exception as e:
    print(f"Error actualizando settings.py: {e}")

print("Exito! Capital inyectado correctamente. Reinicia el bot para que tome la nueva configuracion.")
