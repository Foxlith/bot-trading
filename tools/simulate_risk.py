"""
Simulador de Estrategia Risk-Based
==================================
Objetivo: Probar si el sizing dinámico mejora el rendimiento vs Grid estático.
Estrategia: Technical RSI+MACD con Risk Sizing (2% riesgo por trade).
"""

import sys
import os
import pandas as pd
import numpy as np
from datetime import datetime, timedelta

# Añadir path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from backtest import download_binance_data, FEE_RATE

# Configuración
RISK_PER_TRADE = 0.02  # 2%
CAPITAL_INITIAL = 75.0
MONTHLY_CONTRIBUTION = 75.0

class RiskSimulator:
    def __init__(self):
        self.capital = CAPITAL_INITIAL
        self.total_deposited = CAPITAL_INITIAL
        self.positions = {} # symbol -> {entry, amount, sl, tp}
        self.monthly_profits = {}
        self.last_contribution_month = -1
        self.equity_curve = []
        
        # Technical State
        self.indicators = {} 

    def get_equity(self, current_prices):
        eq = self.capital
        for s, pos in self.positions.items():
            if s in current_prices:
                cp = current_prices[s]
                # Valor actual - Comisiones salida
                val = pos["amount"] * cp * (1 - FEE_RATE)
                eq += val
        return eq

    def process_tick(self, symbol, row, timestamp):
        price = row["close"]
        month_idx = timestamp.year * 12 + timestamp.month
        
        # Aporte Mensual
        if month_idx > self.last_contribution_month and self.last_contribution_month != -1:
             self.capital += MONTHLY_CONTRIBUTION
             self.total_deposited += MONTHLY_CONTRIBUTION
             self.last_contribution_month = month_idx
        
        if self.last_contribution_month == -1: self.last_contribution_month = month_idx

        # === ESTRATEGIA TÉCNICA SIMPLIFICADA ===
        # Necesitamos indicadores. Como backtest.py ya los calcula, asumimos que 'row' tiene RSI, etc.
        # Pero 'row' es raw OHLCV si usamos download_binance_data.
        # Necesitamos calcular indicadores al vuelo o pre-calcular.
        # Para simplificar, usaremos lógica simple:
        # Buy: RSI < 30
        # Sell: RSI > 70 or SL/TP
        
        # Nota: download_binance_data devuelve DataFrame con indicadores si usamos la lógica de backtest.py
        # Pero 'get_data_with_cache' devuelve CSV.
        # Vamos a asumir que calculamos RSI simple aqui.
        
        # Check Exit
        if symbol in self.positions:
            pos = self.positions[symbol]
            pnl_pct = (price - pos["entry"]) / pos["entry"]
            
            # SL
            if price <= pos["sl"]:
                self._close(symbol, price, "SL")
                return
            # TP
            if price >= pos["tp"]:
                self._close(symbol, price, "TP")
                return
            # RSI Sell condition
            if row.get("rsi", 50) > 70:
                 self._close(symbol, price, "RSI-Overbought")
                 return
                 
        # Check Entry
        elif self.capital > 10: # Min balance
            if row.get("rsi", 50) < 30: # Oversold
                self._open(symbol, price, timestamp)

    def _open(self, symbol, price, timestamp):
        # Risk Sizing Logic
        # SL = 3% below price (Simple approach for sim)
        sl_pct = 0.03
        sl_price = price * (1 - sl_pct)
        tp_price = price * (1 + 0.06) # 1:2 Risk/Reward
        
        # Risk Amount = Capital * Risk%
        # Equity approx = self.capital (cash) + positions value. 
        # Usamos Cash para simplificar, o mejor estimated equity.
        equity = self.capital # Aproximación conservadora (solo cash disponible)
        
        risk_amt = equity * RISK_PER_TRADE
        risk_per_share = price - sl_price
        
        if risk_per_share <= 0: return
        
        amount = risk_amt / risk_per_share
        
        # Verificar max allocation (e.g. 30% capital)
        max_alloc = equity * 0.30
        cost = amount * price
        
        if cost > max_alloc:
            amount = max_alloc / price
            
        if cost > self.capital:
            amount = self.capital / price
            
        if amount * price < 5: return # Min order
        
        fee = amount * price * FEE_RATE
        self.capital -= (amount * price + fee)
        
        self.positions[symbol] = {
            "entry": price,
            "amount": amount,
            "sl": sl_price,
            "tp": tp_price
        }

    def _close(self, symbol, price, reason):
        pos = self.positions[symbol]
        value = pos["amount"] * price
        fee = value * FEE_RATE
        net = value - fee
        
        entry_val = pos["amount"] * pos["entry"]
        profit = net - entry_val
        
        self.capital += net
        del self.positions[symbol]
        
        # Record daily/monthly profit not implemented fully yet, just tracking capital
        # But we act primarily on capital curve

# --- DATOS CACHE + INDICADORES ---
# Necesitamos TA Lib o calc manual. 
# Reusamos backtest.py logic si es posible, pero es clase.
# Copiamos calc rapido.

def add_indicators(df):
    close = df["close"]
    # RSI 14
    delta = close.diff()
    gain = (delta.where(delta > 0, 0)).rolling(window=14).mean()
    loss = (-delta.where(delta < 0, 0)).rolling(window=14).mean()
    rs = gain / loss
    df["rsi"] = 100 - (100 / (1 + rs))
    return df

def get_data_with_cache(symbol, months):
    clean_sym = symbol.replace("/", "_")
    path = f"data_cache/{clean_sym}_{months}m.csv"
    if os.path.exists(path):
        df = pd.read_csv(path)
        df["timestamp"] = pd.to_datetime(df["timestamp"])
        return add_indicators(df)
    
    # Descargar y guardar
    print(f"  📥 Descargando {symbol} ({months} meses)...")
    df = download_binance_data(symbol, "1h", months)
    if not df.empty:
        df.to_csv(path, index=False)
        return add_indicators(df)
        
    return pd.DataFrame() 

def run_simulation():
    print("\n" + "="*60)
    print(f"  🚀 SIMULADOR RISK-BASED: Risk {RISK_PER_TRADE*100}% per Trade")
    print(f"  Aporte Mensual: ${MONTHLY_CONTRIBUTION}")
    print("="*60)
    
    PAIRS = ["BTC/USDT", "ETH/USDT", "SOL/USDT", "BNB/USDT", "XRP/USDT"]
    months = 24
    
    dfs = {}
    print(f"📥 Cargando datos...")
    for s in PAIRS:
        df = get_data_with_cache(s, months)
        if not df.empty:
            dfs[s] = df.set_index("timestamp")
            
    if not dfs:
        print("❌ No hay datos cacheados. Ejecuta simulate_salary.py primero.")
        return

    common_ts = sorted(list(set.intersection(*[set(df.index) for df in dfs.values()])))
    sim = RiskSimulator()
    
    start_date = common_ts[0]
    last_month = start_date.month
    
    for ts in common_ts:
        current_prices = {}
        for s in PAIRS:
            if ts in dfs[s].index:
                row = dfs[s].loc[ts]
                sim.process_tick(s, row, ts)
                current_prices[s] = row["close"]
                
        if ts.month != last_month:
            equity = sim.get_equity(current_prices)
            print(f"  📅 {ts.strftime('%Y-%m')} | Equity: ${equity:,.2f} | Aportado: ${sim.total_deposited:.0f}")
            last_month = ts.month

    final_equity = sim.get_equity(current_prices)
    profit = final_equity - sim.total_deposited
    roi = (profit / sim.total_deposited) * 100
    
    print("\n" + "="*60)
    print(f"  🏁 RESULTADO FINAL (Risk-Based):")
    print(f"  Total Depositado:  ${sim.total_deposited:,.2f}")
    print(f"  Capital Final:     ${final_equity:,.2f}")
    print(f"  Ganancia Total:    ${profit:,.2f}")
    print(f"  ROI Total:         {roi:.2f}%")
    
    # Save
    with open("risk_simulation_result.txt", "w") as f:
        f.write(f"Risk Strategy ROI: {roi:.2f}%\n")
        f.write(f"Capital Final: ${final_equity:.2f}\n")

if __name__ == "__main__":
    run_simulation()
