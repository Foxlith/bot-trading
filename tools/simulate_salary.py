"""
Simulador de Objetivo: Salario Mínimo Colombiano
================================================
Objetivo: Generar 1 SMLV (~$350 USD) mensual.
Aporte mensual: 300,000 COP (~$75 USD).
Estrategia: Grid Trading (Interés Compuesto).
"""

import sys
import os
import pandas as pd
import numpy as np
from datetime import datetime, timedelta

# Añadir path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from backtest import download_binance_data, FEE_RATE

# Configuración Económica
EXCHANGE_RATE_COP = 4000  # 1 USD = 4000 COP (Aprox)
MONTHLY_CONTRIBUTION_COP = 300000
MONTHLY_CONTRIBUTION_USD = MONTHLY_CONTRIBUTION_COP / EXCHANGE_RATE_COP # $75
TARGET_MONTHLY_INCOME_USD = 1300000 / EXCHANGE_RATE_COP # ~$325 (redondeamos a $350)

# Configuración de Trading
PAIRS = ["BTC/USDT", "ETH/USDT", "SOL/USDT", "BNB/USDT", "XRP/USDT"]
GRID_LEVELS = 20
GRID_RANGE = 0.20 # +/- 20%

class SalarySimulator:
    def __init__(self):
        self.capital = 75.0 # Primer aporte
        self.total_deposited = 75.0
        self.grids = {}
        self.monthly_profits = {} # mes -> profit
        self.equity_curve = []
        self.last_contribution_month = -1
        
    def get_equity(self, current_prices):
        eq = self.capital
        for s, grid in self.grids.items():
            if s in current_prices:
                cp = current_prices[s]
                for level in grid["levels"]:
                    if level["status"] == "bought":
                        eq += level["amount"] * cp
        return eq

    def process_tick(self, symbol, row, timestamp):
        price = row["close"]
        month_idx = timestamp.year * 12 + timestamp.month
        
        # Aporte Mensual (Día 1 de cada mes)
        if month_idx > self.last_contribution_month and self.last_contribution_month != -1:
             self.capital += MONTHLY_CONTRIBUTION_USD
             self.total_deposited += MONTHLY_CONTRIBUTION_USD
             # Rebalancear? No, simple accumulation.
             self.last_contribution_month = month_idx
        
        if self.last_contribution_month == -1: self.last_contribution_month = month_idx

        # Init/Update Grid
        if symbol not in self.grids:
            self._setup_grid(symbol, price)
        
        # Grid Logic
        grid = self.grids[symbol]
        
        # Check Sells
        current_daily_profit = 0
        for level in grid["levels"]:
            if level["status"] == "bought" and price >= level["sell_price"]:
                profit = self._sell(symbol, level, price, timestamp)
                current_daily_profit += profit
                
                # Regla de Re-inversión: El capital liberado + profit vuelve al pool general
                # Si el precio se aleja, resetear grid? 
                # Simplificación: Grid Estático Infinite Loop (Buy Low Sell High en rango)
                
        # Check Buys
        for level in grid["levels"]:
            if level["status"] == "pending" and price <= level["buy_price"]:
                self._buy(symbol, level, price, timestamp)
        
        # Track monthly profit
        month_key = timestamp.strftime("%Y-%m")
        self.monthly_profits[month_key] = self.monthly_profits.get(month_key, 0) + current_daily_profit

    def _setup_grid(self, symbol, price):
        # Asignar capital por par (dinámico)
        # Allocation ideal: Capital Total / Num Pares
        # Pero eso cambia cada mes.
        # Simplificación: Grid Levels tienen fixed USD size calculado al INICIO de la grid?
        # NO, mejor: Fixed USD size basado en el capital ACTUAL.
        
        # Si configuro una grid ahora, uso el capital disponible.
        # Digamos $10 per level.
        
        upper = price * (1 + GRID_RANGE)
        lower = price * (1 - GRID_RANGE)
        spacing = (upper - lower) / GRID_LEVELS
        
        levels = []
        for i in range(GRID_LEVELS):
            bp = lower + spacing * i
            sp = bp + spacing
            levels.append({
                "buy_price": bp, "sell_price": sp,
                "status": "pending", "amount": 0, "bought_price": 0
            })
        self.grids[symbol] = {"levels": levels}

    def _buy(self, symbol, level, price, timestamp):
        # Dynamic Sizing: 1% del Equity actual
        # equity = self.capital (aprox, cash)
        # Supongamos que queremos usar todo el cash en orders dudosas.
        # Order Size = Cash Disponible / (Pares * Niveles / 2) ?
        # Mejor: Fixed $10 para empezar, escalando con Capital.
        
        # Scaling: Order Size = Total Equity * 0.01
        order_size = max(10.0, self.get_estimated_equity() * 0.01)
        
        if self.capital < order_size: return
        
        fee = order_size * FEE_RATE
        amount = (order_size - fee) / price
        
        level["status"] = "bought"
        level["amount"] = amount
        level["bought_price"] = price
        
        self.capital -= order_size
        
    def _sell(self, symbol, level, price, timestamp):
        amount = level["amount"]
        usd = amount * price
        fee = usd * FEE_RATE
        cost = level["bought_price"] * amount
        net = usd - fee - cost - (cost * FEE_RATE)
        
        level["status"] = "pending"
        level["amount"] = 0
        
        self.capital += usd - fee
        return net

    def get_estimated_equity(self):
        # Estimación rápida usando saldo + valor compra (sin precio actual para velocidad)
        eq = self.capital
        for s, grid in self.grids.items():
            for level in grid["levels"]:
                if level["status"] == "bought":
                    eq += level["amount"] * level["bought_price"] # A costo
        return eq

# --- DATOS CACHE ---
def get_data_with_cache(symbol, months):
    clean_sym = symbol.replace("/", "_")
    path = f"data_cache/{clean_sym}_{months}m.csv"
    os.makedirs("data_cache", exist_ok=True)
    if os.path.exists(path):
        df = pd.read_csv(path)
        df["timestamp"] = pd.to_datetime(df["timestamp"])
        return df
    return download_binance_data(symbol, "1h", months)

def run_simulation():
    print("\n" + "="*60)
    print(f"  💰 SIMULADOR DE SALARIO: Aporte ${MONTHLY_CONTRIBUTION_USD:.0f}/mes")
    print(f"     Meta: ${TARGET_MONTHLY_INCOME_USD:.0f}/mes de ganancia")
    print("="*60)
    
    # 2 Years Data
    months = 24
    dfs = {}
    print(f"📥 Cargando datos de 2 años para {len(PAIRS)} pares...")
    for s in PAIRS:
        try:
            df = get_data_with_cache(s, months)
            dfs[s] = df.set_index("timestamp")
        except: pass
        
    common_ts = sorted(list(set.intersection(*[set(df.index) for df in dfs.values()])))
    
    sim = SalarySimulator()
    
    print("🚀 Ejecutando simulación mes a mes...")
    
    start_date = common_ts[0]
    last_month = start_date.month
    
    for ts in common_ts:
        # Precios actuales dict
        current_prices = {}
        for s in PAIRS:
            if ts in dfs[s].index:
                row = dfs[s].loc[ts]
                sim.process_tick(s, row, ts)
                current_prices[s] = row["close"]
        
        # Reporte Mensual
        if ts.month != last_month:
            equity = sim.get_equity(current_prices)
            prev_key = (ts.replace(day=1) - timedelta(days=1)).strftime("%Y-%m")
            profit = sim.monthly_profits.get(prev_key, 0)
            
            # Calcular ROI mensual real
            roi = (profit / equity) * 100 if equity > 0 else 0
            
            print(f"  📅 {ts.strftime('%Y-%m')} | Equity: ${equity:,.2f} | Profit Mes: ${profit:6.2f} ({roi:4.1f}%) | Aportado: ${sim.total_deposited:.0f}")
            
            last_month = ts.month

    # Final Report
    final_equity = sim.get_equity(current_prices)
    final_profit = sum(sim.monthly_profits.values())
    
    print("\n" + "="*60)
    print(f"  🏁 RESULTADO FINAL (1 AÑO):")
    print(f"  Total Depositado:  ${sim.total_deposited:,.2f}")
    print(f"  Capital Final:     ${final_equity:,.2f}")
    print(f"  Ganancia Total:    ${final_equity - sim.total_deposited:,.2f}")
    print(f"  Profit Mensual Promedio: ${final_profit/12:.2f}")
    
    # Proyección
    avg_monthly_roi_pct = ((final_equity - sim.total_deposited) / sim.total_deposited) / 12 * 100
    # O mejor: promedio de los ROIs mensuales
    
    print(f"\n  🔮 PROYECCIÓN PARA ALCANZAR ${TARGET_MONTHLY_INCOME_USD:.0f}/mes:")
    if avg_monthly_roi_pct > 0:
        required_capital = (TARGET_MONTHLY_INCOME_USD / avg_monthly_roi_pct) * 100
        print(f"  ROI Mensual Est:   {avg_monthly_roi_pct:.2f}%")
        print(f"  Capital Necesario: ${required_capital:,.2f}")
        
        # Calculo simple de tiempo
        # VF = VP * (1 + r)^t + PMT * ...
        print(f"  Con aporte de ${MONTHLY_CONTRIBUTION_USD:.0f}/mes y re-inversión...")
        
        equity_proj = final_equity
        months_needed = 0
        while equity_proj * (avg_monthly_roi_pct/100) < TARGET_MONTHLY_INCOME_USD:
            equity_proj = equity_proj * (1 + avg_monthly_roi_pct/100) + MONTHLY_CONTRIBUTION_USD
            months_needed += 1
            if months_needed > 120: break
            
        years = months_needed / 12
        print(f"  ⏳ Tiempo estimado: {years:.1f} años adicionales (Total {years + 1:.1f} años)")
    else:
        print("  ❌ Estrategia no rentable, no se puede proyectar.")
    print("="*60)
    
    # Save to file
    with open("salary_projection.txt", "w", encoding="utf-8") as f:
        f.write(f"PROYECCION SALARIO MINIMO (${TARGET_MONTHLY_INCOME_USD:.0f}/mes)\n")
        f.write(f"Capital Final (1 año): ${final_equity:.2f}\n")
        if avg_monthly_roi_pct > 0:
             f.write(f"Tiempo estimado: {years + 1:.1f} años\n")
        else:
             f.write(f"Tiempo estimado: N/A (No rentable)\n")

if __name__ == "__main__":
    run_simulation()
