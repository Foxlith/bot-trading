"""
Optimizador Masivo de Grid Strategy (Random Search)
===================================================
Objetivo: Explorar miles de combinaciones para superar el ROI de 31.9%.
Parámetros:
- Levels: 5 a 60
- Spacing: 1% a 25%
- Take Profit: Variable
"""

import sys
import os
import pandas as pd
import numpy as np
import random
from datetime import datetime

# Añadir path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from backtest import download_binance_data, FEE_RATE

# --- CONFIG ---
CAPITAL_INITIAL = 1000.0
PAIRS = ["BTC/USDT", "ETH/USDT", "BNB/USDT", "SOL/USDT", "XRP/USDT"]
ITERATIONS = 5000  # Número de simulaciones a correr
BASELINE_ROI = 31.91

class FastGridSim:
    def __init__(self, capital, levels, spacing, tp_pct):
        self.balance = capital
        self.levels = levels
        self.spacing = spacing
        
        # Pre-calc levels structure to avoid object creation overhead
        # Just simple structure: [buy_price, sell_price, status(0=pending,1=bought), amount]
        # But per symbol.
        self.grids = {} # symbol -> { 'levels': [...], 'order_size': float }
        self.trades = 0
        
    def setup(self, symbol, price):
        n = self.levels
        space = price * self.spacing
        half_range = space * (n / 2)
        upper = price + half_range
        lower = price - half_range
        
        spacing_amt = (upper - lower) / n
        order_size = (self.balance / len(PAIRS)) / n
        if order_size < 1.0: order_size = 1.0
        
        levels = []
        for i in range(n):
            bp = lower + spacing_amt * i
            sp = bp + spacing_amt
            # [buy_price, sell_price, is_bought (bool), amount]
            levels.append([bp, sp, False, 0.0])
            
        self.grids[symbol] = {
            "levels": levels,
            "order_size": order_size
        }

    def process(self, symbol, price):
        if symbol not in self.grids:
            self.setup(symbol, price)
            return
            
        grid = self.grids[symbol]
        levels = grid["levels"]
        order_sz = grid["order_size"]
        
        # Iterate levels
        # Optimized: Only check relevant levels? 
        # For now, iterate all (fast enough for 50 levels)
        
        for lvl in levels:
            # lvl: [bp, sp, is_bought, amount]
            if lvl[2]: # is_bought
                if price >= lvl[1]: # Sell
                    rev = lvl[3] * price
                    fee = rev * FEE_RATE
                    self.balance += (rev - fee)
                    lvl[2] = False
                    lvl[3] = 0.0
                    self.trades += 1
            else: # pending
                if price <= lvl[0]: # Buy
                    if self.balance >= order_sz:
                        fee = order_sz * FEE_RATE
                        amt = (order_sz - fee) / price
                        self.balance -= order_sz
                        lvl[2] = True
                        lvl[3] = amt
                        self.trades += 1

    def get_equity(self, quantities):
        eq = self.balance
        for s, qty in quantities.items():
            # Estimate value of holdings
            # Need current price? Passed in `quantities`? No.
            # We need current prices to calc equity.
            pass
        return eq

# --- CACHE ---
def get_data_with_cache(symbol):
    clean_sym = symbol.replace("/", "_")
    path = f"data_cache/{clean_sym}_24m.csv"
    if os.path.exists(path):
        df = pd.read_csv(path)
        return df
    return pd.DataFrame()

def run_search():
    print(f"📥 Cargando datos de {len(PAIRS)} pares...")
    dfs = {}
    for s in PAIRS:
        df = get_data_with_cache(s)
        if not df.empty:
            # Convert to numpy arrays for SPEED
            # We only need 'close' price
            dfs[s] = df["close"].to_numpy()
            
    if not dfs:
        print("❌ No data.")
        return

    # Align timestamps? 
    # Valid assumption: data is hourly and aligned enough for random search approximation.
    # To be precise, we iterate by index.
    min_len = min([len(d) for d in dfs.values()])
    
    print(f"🚀 Iniciando {ITERATIONS} simulaciones (Random Search)...")
    print(f"   Baseline ROI: {BASELINE_ROI}%")
    
    top_results = []
    
    start_time = datetime.now()
    
    # Telegram Config
    bot_token = os.getenv("TELEGRAM_BOT_TOKEN")
    chat_id = os.getenv("TELEGRAM_CHAT_ID")
    
    import requests
    def send_msg(msg):
        if bot_token and chat_id:
            try:
                url = f"https://api.telegram.org/bot{bot_token}/sendMessage"
                requests.post(url, json={"chat_id": chat_id, "text": msg})
            except Exception as e:
                print(f"Telegram error: {e}")

    for i in range(1, ITERATIONS + 1):
        # ... logic ...
        # Random Params
        levels = random.randint(5, 60)
        spacing = random.uniform(0.01, 0.30) # Ampliado a 30%
        
        sim = FastGridSim(CAPITAL_INITIAL, levels, spacing, 0)
        
        # Run Sim (Inline for speed)
        # Optimized inner loop
        final_prices = {}
        for idx in range(min_len):
            for s in PAIRS:
                price = dfs[s][idx]
                sim.process(s, price)
                if idx == min_len - 1:
                    final_prices[s] = price
                    
        # Calc Equity
        equity = sim.balance
        for s, grid in sim.grids.items():
            final_p = final_prices[s]
            for lvl in grid["levels"]:
                if lvl[2]: # bought
                    equity += lvl[3] * final_p
        
        roi = ((equity - CAPITAL_INITIAL) / CAPITAL_INITIAL) * 100
        
        # Save if good
        if top_results and roi > top_results[0]['roi']:
            # New Record!
            best = {"roi": roi, "levels": levels, "spacing": spacing, "trades": sim.trades}
            record_msg = f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] 🚀 NEW RECORD: ROI {roi:.2f}% | L={levels}, S={spacing*100:.1f}% | Trades={sim.trades}\n"
            print(record_msg.strip())
            
            # Save to file immediately
            with open("optimization_records.txt", "a", encoding="utf-8") as f:
                f.write(record_msg)
            
        if roi > BASELINE_ROI:
            top_results.append({
                "roi": roi,
                "levels": levels,
                "spacing": spacing,
                "trades": sim.trades
            })
            top_results.sort(key=lambda x: x["roi"], reverse=True)
            top_results = top_results[:5]
            
        if i % 100 == 0:
            elapsed = (datetime.now() - start_time).total_seconds()
            best_roi = top_results[0]['roi'] if top_results else 0.0
            print(f"🔄 Sim #{i} | Best ROI: {best_roi:.2f}% | Time: {elapsed:.1f}s")

    print("\n🔍 --- RESULTADOS FINALES ---")
    if top_results:
        for k, res in enumerate(top_results):
            print(f"#{k+1}: ROI {res['roi']:.2f}% | Levels {res['levels']} | Spacing {res['spacing']*100:.2f}% | Trades {res['trades']}")
            
        # Recommendations
        best = top_results[0]
        print(f"\n💡 RECOMENDACIÓN: Usar Levels={best['levels']} y Spacing={best['spacing']*100:.2f}%")
        
        # Save to file
        with open("massive_opt_result.txt", "w") as f:
            for res in top_results:
                f.write(f"ROI: {res['roi']:.2f}% | L: {res['levels']} | S: {res['spacing']:.4f}\n")
    else:
        print("⚠️ No se encontró configuración mejor que el baseline.")

if __name__ == "__main__":
    run_search()
