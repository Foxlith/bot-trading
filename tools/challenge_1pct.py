"""
Challenge 1%: Generar $200 con $1000 usando 1% por operación
============================================================
Estrategia V3: Grid Trading Multi-Par
- Capital: $1000
- Allocation: $100 por par (10 pares)
- Grid: 10 niveles por par
- Order Size: $10 por nivel (1% del capital total)
"""

import sys
import os
import pandas as pd
import numpy as np

# Añadir path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from backtest import download_binance_data, FEE_RATE

# Configuración
INITIAL_CAPITAL = 1000.0
PAIRS_COUNT = 10
CAPITAL_PER_PAIR = INITIAL_CAPITAL / PAIRS_COUNT # $100
LEVELS = 10
ORDER_SIZE = CAPITAL_PER_PAIR / LEVELS # $10 (1% de Capital total)

class GridChallengeSimulator:
    def __init__(self):
        self.capital = INITIAL_CAPITAL
        self.available = INITIAL_CAPITAL
        self.grids = {} # symbol -> {levels: [], ...}
        self.trades = []
        self.total_profit = 0.0

    def _setup_grid(self, symbol, price):
        # Grid range: +/- 15% del precio inicial
        upper = price * 1.15
        lower = price * 0.85
        spacing = (upper - lower) / LEVELS
        
        levels = []
        for i in range(LEVELS):
            bp = lower + spacing * i
            sp = bp + spacing
            levels.append({
                "buy_price": bp, "sell_price": sp,
                "status": "pending", "amount": 0, "bought_price": 0
            })
        
        self.grids[symbol] = {"levels": levels}
        # Reservar capital (simulado) para comprar la mitad de la grid???
        # En Grid normal, se compra a medida que baja. Asumimos start neutral.
        
    def process_tick(self, symbol, row, timestamp):
        price = row["close"]
        
        # Init Grid
        if symbol not in self.grids:
            self._setup_grid(symbol, price)
            return

        grid = self.grids[symbol]
        
        # Check Sells
        for level in grid["levels"]:
            if level["status"] == "bought" and price >= level["sell_price"]:
                self._sell(symbol, level, price, timestamp)
        
        # Check Buys
        for level in grid["levels"]:
            if level["status"] == "pending" and price <= level["buy_price"]:
                self._buy(symbol, level, price, timestamp)

    def _buy(self, symbol, level, price, timestamp):
        usd = ORDER_SIZE
        if self.available < usd: return 
        
        fee = usd * FEE_RATE
        amount = (usd - fee) / price
        
        level["status"] = "bought"
        level["amount"] = amount
        level["bought_price"] = price
        
        self.available -= usd
        self.trades.append({"side": "buy", "symbol": symbol, "price": price, "usd": usd, "timestamp": timestamp})

    def _sell(self, symbol, level, price, timestamp):
        amount = level["amount"]
        usd = amount * price
        fee = usd * FEE_RATE
        cost = level["bought_price"] * amount
        entry_fee = cost * FEE_RATE
        
        net_profit = usd - fee - cost - entry_fee
        
        level["status"] = "pending"
        level["amount"] = 0
        
        self.available += usd - fee
        self.total_profit += net_profit
        
        self.trades.append({
            "side": "sell", "symbol": symbol, "price": price, 
            "profit": net_profit, "timestamp": timestamp
        })

def run_challenge():
    print("\n" + "="*60)
    print("  🏆 CHALLENGE V3: Grid Trading (1% por nivel)")
    print("="*60)
    
    symbols = [
        "BTC/USDT", "ETH/USDT", "SOL/USDT", "BNB/USDT", 
        "XRP/USDT", "ADA/USDT", "DOGE/USDT", "AVAX/USDT",
        "DOT/USDT", "MATIC/USDT"
    ]
    
    # Reutilizar datos descargados si existen (la funcion download maneja cache si no se fuerza)
    # Pero aqui llamamos a download_binance_data que descarga fresco. 
    # Truco: como el script anterior ya corrió, si comento la descarga y cargo de disco seria mas rapido.
    # Pero download_binance_data no guarda CSV. Descarga a memoria.
    # Toca descargar de nuevo (rapido si binance no banea).
    
    
    # Caching simple
    def get_data_with_cache(symbol, months):
        clean_sym = symbol.replace("/", "_")
        path = f"data_cache/{clean_sym}_{months}m.csv"
        os.makedirs("data_cache", exist_ok=True)
        
        if os.path.exists(path):
            print(f"  📂 Cargando {symbol} desde cache...")
            df = pd.read_csv(path)
            df["timestamp"] = pd.to_datetime(df["timestamp"])
            return df
        else:
            df = download_binance_data(symbol, "1h", months)
            df.to_csv(path, index=False)
            return df

    print(f"📥 Cargando datos para {len(symbols)} pares...")
    dfs = {}
    for s in symbols:
        try:
            # Usar 18 meses
            df = get_data_with_cache(s, 18)
            dfs[s] = df.set_index("timestamp")
            print(f"  ✅ {s}: {len(df)} velas")
        except Exception as e:
            print(f"  ❌ Error {s}: {e}")

    common_ts = set.intersection(*[set(df.index) for df in dfs.values()])
    common_ts = sorted(list(common_ts))
    print(f"📊 {len(common_ts)} horas sincronizadas")

    sim = GridChallengeSimulator()
    
    print("\n🚀 Ejecutando Grid...")
    # Loop optimizado
    step = 0
    for ts in common_ts:
        for s in symbols:
            if ts in dfs[s].index:
                sim.process_tick(s, dfs[s].loc[ts], ts)
        step += 1
        if step % 2000 == 0:
            print(f"  ⏳ {ts} | Profit: ${sim.total_profit:.2f}")

    # Cierre final (valorar posiciones abiertas)
    open_pnl = 0
    final_prices = {s: dfs[s].loc[common_ts[-1]]["close"] for s in symbols}
    
    for s, grid in sim.grids.items():
        if s in final_prices:
            cp = final_prices[s]
            for level in grid["levels"]:
                if level["status"] == "bought":
                    val = level["amount"] * cp
                    cost = level["amount"] * level["bought_price"]
                    open_pnl += (val - cost)

    total_net = sim.total_profit + open_pnl
    
    print("\n" + "="*60)
    print(f"  🥇 RESULTADO FINAL:")
    print(f"  Realized Profit: ${sim.total_profit:.2f}")
    print(f"  Unrealized PnL:  ${open_pnl:.2f}")
    print(f"  TOTAL RETURN:    ${total_net:.2f} (Target: $200)")
    print(f"  Trades:          {len([t for t in sim.trades if t['side']=='sell'])}")
    print("="*60)
    
    with open("challenge_result.txt", "w", encoding="utf-8") as f:
        f.write(f"CHALLENGE V3 GRID RESULTS\n")
        f.write(f"Total Return: ${total_net:.2f}\n")
        f.write(f"Realized Profit: ${sim.total_profit:.2f}\n")
        f.write(f"Trades: {len([t for t in sim.trades if t['side']=='sell'])}\n")
        f.write(f"Config: Grid 10 pairs, $10/level (1%)\n")

if __name__ == "__main__":
    run_challenge()
