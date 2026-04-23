"""
Optimizador de Estrategia Grid Trading
======================================
Objetivo: Encontrar la mejor combinación de Grid Levels y Spacing para maximizar ROI.
Datos: 24 meses (caché).
"""

import sys
import os
import pandas as pd
import numpy as np
from datetime import datetime
import itertools
from decimal import Decimal

# Añadir path para importar descargas si es necesario
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from backtest import download_binance_data, FEE_RATE

# --- CONFIGURACIÓN BASE ---
CAPITAL_INITIAL = 1000.0  # Simular con $1000 para ver números claros
PAIRS = ["BTC/USDT", "ETH/USDT", "BNB/USDT", "SOL/USDT", "XRP/USDT"]

# --- PARÁMETROS A PROBAR ---
GRID_LEVELS = [5, 10, 20]
GRID_SPACING = [0.01, 0.02, 0.03, 0.05] # 1% a 5%
TAKE_PROFIT = [0.02, 0.03, 0.05]        # 2% a 5%

class GridOptimizer:
    def __init__(self, capital, levels, spacing, tp_pct):
        self.capital = capital
        self.balance = capital
        self.levels_cfg = levels
        self.spacing = spacing
        self.tp_pct = tp_pct
        
        self.grids = {} # symbol -> grid state
        self.trades_count = 0
        self.total_profit = 0.0
        
    def setup_grid(self, symbol, price):
        n_levels = self.levels_cfg
        spacing_val = price * self.spacing
        
        # Grid centrada
        upper = price + spacing_val * (n_levels / 2)
        lower = price - spacing_val * (n_levels / 2)
        
        spacing_amt = (upper - lower) / n_levels
        # Dividir capital entre pares y luego entre niveles
        # Asumimos alocación igualitaria por par para simplificar test
        alloc_per_pair = self.capital / len(PAIRS) 
        order_size_usd = alloc_per_pair / n_levels
        
        if order_size_usd < 1.0: order_size_usd = 1.0
        
        levels = []
        for i in range(n_levels):
            bp = lower + spacing_amt * i
            sp = bp * (1 + self.tp_pct) # Sell at Buy Price + TP% (Standard Grid sells at next level, but let's test fixed TP)
            # Actually, standard grid sells at next level. Let's stick to standard grid logic from backtest.py
            # Standard: Sell = Buy + (Spacing or TP)
            # backtest.py logic: sp = bp + spacing_amt. 
            # But here we want to test TP impact.
            # Let's use max(spacing_amt, bp * tp_pct) logic?
            # No, standard grid is purely geometric.
            # But the user wants "more profit".
            # Let's use backtest.py logic: Sell at next level.
            # So 'tp_pct' might be irrelevant for pure grid unless we use it for "Grid + Take Profit" logic.
            # Let's assumes sp = bp + spacing_amt (pure grid) for now.
            sp = bp + spacing_amt
            
            levels.append({
                "level": i,
                "buy_price": bp,
                "sell_price": sp,
                "status": "pending",
                "amount": 0,
                "bought_price": 0
            })
            
        self.grids[symbol] = {
            "levels": levels,
            "order_size_usd": order_size_usd
        }

    def process_tick(self, symbol, price):
        if symbol not in self.grids:
            self.setup_grid(symbol, price)
            return

        grid = self.grids[symbol]
        
        # Check Sells
        for level in grid["levels"]:
            if level["status"] == "bought" and price >= level["sell_price"]:
                # Sell
                revenue = level["amount"] * price
                fee = revenue * FEE_RATE
                profit = revenue - fee - (level["bought_price"] * level["amount"])
                
                self.balance += revenue - fee
                self.total_profit += profit
                
                level["status"] = "pending"
                level["amount"] = 0
                self.trades_count += 1
                
        # Check Buys
        for level in grid["levels"]:
            if level["status"] == "pending" and price <= level["buy_price"]:
                # Buy
                cost = grid["order_size_usd"]
                if self.balance >= cost:
                    fee = cost * FEE_RATE
                    amount = (cost - fee) / price
                    
                    self.balance -= cost
                    level["status"] = "bought"
                    level["amount"] = amount
                    level["bought_price"] = price
                    self.trades_count += 1

    def get_equity(self, current_prices):
        equity = self.balance
        for s, grid in self.grids.items():
            if s in current_prices:
                cp = current_prices[s]
                for lvl in grid["levels"]:
                    if lvl["status"] == "bought":
                        equity += lvl["amount"] * cp
        return equity

# --- CACHE LOGIC ---
def get_data_with_cache(symbol, months=24):
    clean_sym = symbol.replace("/", "_")
    path = f"data_cache/{clean_sym}_{months}m.csv"
    if os.path.exists(path):
        df = pd.read_csv(path)
        df["timestamp"] = pd.to_datetime(df["timestamp"])
        return df
    # Fallback (should exist)
    print(f"⚠️ Missing cache for {symbol}")
    return pd.DataFrame()

def run_optimization():
    print(f"📥 Cargando datos de {len(PAIRS)} pares...")
    dfs = {}
    for s in PAIRS:
        df = get_data_with_cache(s)
        if not df.empty:
            dfs[s] = df.set_index("timestamp")
            
    if not dfs:
        print("❌ No hay datos. Ejecuta simulate_risk.py primero.")
        return

    common_ts = sorted(list(set.intersection(*[set(df.index) for df in dfs.values()])))
    # Downsample to 1H to speed up? They are 1H already.
    # 24m * 30d * 24h = 17k candles.
    # 36 configs * 17k steps = 600k operations. Fast.
    
    results = []
    
    # Generate combinations
    # For pure grid, 'tp_pct' is redundant if we define sell = buy + interval.
    # So valid params are levels and spacing.
    # Let's ignore 'tp_pct' for this pure grid test.
    
    combinations = list(itertools.product(GRID_LEVELS, GRID_SPACING))
    print(f"🚀 Iniciando optimización con {len(combinations)} combinaciones...")
    
    for levels, spacing in combinations:
        sim = GridOptimizer(CAPITAL_INITIAL, levels, spacing, 0)
        
        for ts in common_ts:
            current_prices = {}
            for s in PAIRS:
                if ts in dfs[s].index:
                    price = dfs[s].loc[ts]["close"]
                    sim.process_tick(s, price)
                    current_prices[s] = price
                    
        equity = sim.get_equity(current_prices)
        profit = equity - CAPITAL_INITIAL
        roi = (profit / CAPITAL_INITIAL) * 100
        
        print(f"  👉 L={levels} S={spacing*100}% | ROI={roi:.2f}% Trades={sim.trades_count}")
        
        results.append({
            "levels": levels,
            "spacing": spacing,
            "roi": roi,
            "trades": sim.trades_count
        })
        
    # Sort by ROI
    results.sort(key=lambda x: x["roi"], reverse=True)
    
    print("\n🏆 TOP 3 CONFIGURACIONES:")
    for i, res in enumerate(results[:3]):
        print(f"#{i+1}: ROI {res['roi']:.2f}% | Levels {res['levels']} | Spacing {res['spacing']*100}%")
        
    # Save best
    with open("grid_optimization_best.txt", "w") as f:
        best = results[0]
        f.write(f"Best Grid Strategy:\nLevels: {best['levels']}\nSpacing: {best['spacing']}\nROI: {best['roi']:.2f}%\n")

if __name__ == "__main__":
    run_optimization()
