"""
🧹 Limpieza de Base de Datos - Bot Trading
============================================
Cierra posiciones fantasma y reconcilia el capital real.
"""
import sqlite3
import json
from datetime import datetime

DB_PATH = 'data/trading_bot.db'
conn = sqlite3.connect(DB_PATH)
cur = conn.cursor()

print("=" * 70)
print("🧹 LIMPIEZA DE BASE DE DATOS - BOT TRADING")
print("=" * 70)

# ═══════════════════════════════════════════════════════════
# PASO 1: Diagnóstico
# ═══════════════════════════════════════════════════════════
print("\n📋 PASO 1: Diagnóstico Actual")

cur.execute("SELECT COUNT(*) FROM positions WHERE status = 'open'")
total_open = cur.fetchone()[0]
print(f"  Posiciones 'open' en DB: {total_open}")

cur.execute("""
    SELECT symbol, COUNT(*), SUM(entry_price * amount) 
    FROM positions WHERE status = 'open' 
    GROUP BY symbol
""")
for sym, count, value in cur.fetchall():
    print(f"    {sym}: {count} posiciones = ${value:.2f}")

# Grid state real
cur.execute("SELECT state_data FROM strategy_state WHERE strategy_name = 'grid_trading'")
row = cur.fetchone()
grid_state = json.loads(row[0]) if row else {}

real_bought = {}
print(f"\n🔲 Grid REAL (strategy_state):")
if 'grids' in grid_state:
    for sym, grid in grid_state['grids'].items():
        levels = grid.get('levels', [])
        bought = [l for l in levels if l.get('status') == 'bought']
        real_bought[sym] = bought
        print(f"    {sym}: {len(bought)} niveles comprados")

# ═══════════════════════════════════════════════════════════
# PASO 2: Cerrar TODAS las posiciones fantasma
# ═══════════════════════════════════════════════════════════
print(f"\n🧹 PASO 2: Cerrando TODAS las posiciones 'open' (son fantasma)")

cur.execute("UPDATE positions SET status = 'closed' WHERE status = 'open'")
closed = cur.rowcount
print(f"  ✅ Cerradas {closed} posiciones fantasma")

# ═══════════════════════════════════════════════════════════
# PASO 3: Recrear SOLO las posiciones reales
# ═══════════════════════════════════════════════════════════
print(f"\n📊 PASO 3: Recreando SOLO posiciones reales del Grid")

now = datetime.now().isoformat()
created = 0

for sym, bought_levels in real_bought.items():
    for level in bought_levels:
        buy_price = level.get('buy_executed_price', level.get('buy_price', 0))
        amount = level.get('amount', 0)
        level_num = level.get('level', 0)
        
        if float(str(amount)) > 0 and float(str(buy_price)) > 0:
            cur.execute("""
                INSERT INTO positions (symbol, strategy, entry_price, amount, status, opened_at, extra_data)
                VALUES (?, 'Grid Trading', ?, ?, 'open', ?, ?)
            """, (sym, float(str(buy_price)), float(str(amount)), now, 
                  json.dumps({"level": level_num, "source": "db_cleanup"})))
            val = float(str(buy_price)) * float(str(amount))
            print(f"  ✅ {sym} nivel {level_num}: precio=${float(str(buy_price)):.2f} cant={float(str(amount)):.8f} (${val:.4f})")
            created += 1

print(f"  Total restauradas: {created}")

# ═══════════════════════════════════════════════════════════
# PASO 4: Actualizar grid params (10 niveles -> 5)
# ═══════════════════════════════════════════════════════════
print(f"\n⚙️ PASO 4: Verificando grid state")

# Los grids actuales tienen 10 niveles pero la config ahora dice 5
# No tocar el grid state por ahora, dejarlo como está
if 'grids' in grid_state:
    for sym, grid in grid_state['grids'].items():
        levels = grid.get('levels', [])
        bought = sum(1 for l in levels if l.get('status') == 'bought')
        print(f"  {sym}: {len(levels)} niveles en grid, {bought} comprados")

# ═══════════════════════════════════════════════════════════
# PASO 5: Verificación final
# ═══════════════════════════════════════════════════════════
print(f"\n✅ PASO 5: Verificación Final")

cur.execute("SELECT COUNT(*) FROM positions WHERE status = 'open'")
new_open = cur.fetchone()[0]

cur.execute("""
    SELECT symbol, COUNT(*), SUM(entry_price * amount) 
    FROM positions WHERE status = 'open' 
    GROUP BY symbol
""")
total_val = 0
for sym, count, value in cur.fetchall():
    total_val += value
    print(f"  {sym}: {count} posiciones = ${value:.4f}")

print(f"\n  📊 Posiciones abiertas: {total_open} → {new_open}")
print(f"  💰 Valor total en posiciones: ${total_val:.4f}")

cur.execute("SELECT COUNT(*) FROM positions WHERE status = 'closed'")
total_closed = cur.fetchone()[0]
print(f"  📁 Total historial cerradas: {total_closed}")

# COMMIT
conn.commit()
print(f"\n🎉 LIMPIEZA COMPLETADA - DB guardada exitosamente")
conn.close()
