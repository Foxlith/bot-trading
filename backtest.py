"""
=============================================
  BACKTESTER - Bot de Trading
=============================================
Simula las 3 estrategias del bot contra datos
históricos reales de Binance.

Uso:
  python backtest.py                    # 6 meses, $200 capital
  python backtest.py --months 12        # 12 meses
  python backtest.py --capital 500      # Capital inicial $500
  python backtest.py --symbol BTC/USDT  # Solo BTC
"""

import argparse
import math
import sys
from datetime import datetime, timedelta
from decimal import Decimal
from typing import Dict, List, Any, Optional

import pandas as pd
import numpy as np
import requests
import ta


# =============================================================================
# CONFIGURACIÓN (MISMA QUE settings.py)
# =============================================================================
FEE_RATE = 0.001          # 0.1% por trade
ROUNDTRIP_FEE = 0.002     # 0.2% roundtrip

STRATEGIES_CONFIG = {
    "dca": {
        "allocation_pct": 0.40,
        "buy_interval_hours": 4,
        "dip_threshold_pct": 0.03,
    },
    "grid": {
        "allocation_pct": 0.30,
        "grid_levels": 5,
        "grid_spacing_pct": 0.02,
        "take_profit_pct": 0.03,
        "min_volatility_atr_pct": 0.003,
    },
    "technical": {
        "allocation_pct": 0.30,
        "rsi_oversold": 30,
        "rsi_overbought": 70,
        "stop_loss_pct": 0.03,
        "take_profit_pct": 0.06,
        "trailing_stop_pct": 0.02,
    },
}

PORTFOLIO_ALLOC = {
    "BTC/USDT": 0.45,
    "ETH/USDT": 0.55,
}


# =============================================================================
# DESCARGA DE DATOS HISTÓRICOS
# =============================================================================
def download_binance_data(symbol: str, interval: str = "1h", months: int = 6) -> pd.DataFrame:
    """Descarga datos OHLCV de Binance API pública."""
    binance_symbol = symbol.replace("/", "")
    url = "https://api.binance.com/api/v3/klines"
    
    end_time = int(datetime.now().timestamp() * 1000)
    start_time = int((datetime.now() - timedelta(days=months * 30)).timestamp() * 1000)
    
    all_data = []
    current_start = start_time
    
    print(f"  📥 Descargando {symbol} ({months} meses)...", end=" ", flush=True)
    
    while current_start < end_time:
        params = {
            "symbol": binance_symbol,
            "interval": interval,
            "startTime": current_start,
            "endTime": end_time,
            "limit": 1000,
        }
        
        try:
            resp = requests.get(url, params=params, timeout=15)
            resp.raise_for_status()
            data = resp.json()
        except Exception as e:
            print(f"\n  ❌ Error descargando datos: {e}")
            sys.exit(1)
        
        if not data:
            break
        
        all_data.extend(data)
        current_start = data[-1][0] + 1  # Siguiente ms después del último
        
        if len(data) < 1000:
            break
    
    if not all_data:
        print(f"\n  ❌ No se obtuvieron datos para {symbol}")
        sys.exit(1)
    
    df = pd.DataFrame(all_data, columns=[
        "timestamp", "open", "high", "low", "close", "volume",
        "close_time", "quote_volume", "trades",
        "taker_buy_base", "taker_buy_quote", "ignore"
    ])
    
    df["timestamp"] = pd.to_datetime(df["timestamp"], unit="ms")
    for col in ["open", "high", "low", "close", "volume"]:
        df[col] = df[col].astype(float)
    
    df = df.drop_duplicates(subset=["timestamp"]).sort_values("timestamp").reset_index(drop=True)
    
    print(f"✅ {len(df)} velas")
    return df


def add_indicators(df: pd.DataFrame) -> pd.DataFrame:
    """Calcula indicadores técnicos (mismo enfoque que data_manager.py)."""
    df["rsi"] = ta.momentum.RSIIndicator(df["close"], window=14).rsi()
    
    macd = ta.trend.MACD(df["close"], window_slow=26, window_fast=12, window_sign=9)
    df["macd"] = macd.macd()
    df["macd_signal"] = macd.macd_signal()
    df["macd_hist"] = macd.macd_diff()
    
    bb = ta.volatility.BollingerBands(df["close"], window=20, window_dev=2)
    df["bb_upper"] = bb.bollinger_hband()
    df["bb_lower"] = bb.bollinger_lband()
    df["bb_middle"] = bb.bollinger_mavg()
    
    df["ema_50"] = ta.trend.EMAIndicator(df["close"], window=50).ema_indicator()
    df["ema_200"] = ta.trend.EMAIndicator(df["close"], window=200).ema_indicator()
    
    df["atr"] = ta.volatility.AverageTrueRange(df["high"], df["low"], df["close"], window=14).average_true_range()
    
    # Tendencia
    df["trend"] = "sideways"
    df.loc[(df["ema_50"] > df["ema_200"]) & (df["close"] > df["ema_50"]), "trend"] = "strong_uptrend"
    df.loc[(df["ema_50"] > df["ema_200"]) & (df["close"] <= df["ema_50"]), "trend"] = "uptrend"
    df.loc[(df["ema_50"] < df["ema_200"]) & (df["close"] < df["ema_50"]), "trend"] = "strong_downtrend"
    df.loc[(df["ema_50"] < df["ema_200"]) & (df["close"] >= df["ema_50"]), "trend"] = "downtrend"
    
    # BB Position
    df["bb_position"] = "middle"
    df.loc[df["close"] <= df["bb_lower"], "bb_position"] = "oversold"
    df.loc[df["close"] >= df["bb_upper"], "bb_position"] = "overbought"
    
    # Prev MACD hist (para detectar cruces)
    df["prev_macd_hist"] = df["macd_hist"].shift(1)
    
    df = df.dropna().reset_index(drop=True)
    return df


# =============================================================================
# SIMULACIÓN DCA
# =============================================================================
class DCASimulator:
    """Simula la estrategia DCA Inteligente."""
    
    def __init__(self, capital: float, config: dict):
        self.capital = capital
        self.available = capital
        self.config = config
        self.positions: Dict[str, dict] = {}  # symbol -> {amount, avg_price, invested}
        self.trades: List[dict] = []
        self.last_buy_time: Dict[str, datetime] = {}
        self.price_history: Dict[str, list] = {}
    
    def process_tick(self, symbol: str, row: pd.Series, can_buy: bool, timestamp=None):
        """Procesa un tick para DCA."""
        price = row["close"]
        rsi = row["rsi"]
        
        # Mantener historial de precios (últimos 180 ticks ≈ 30 días en 4h)
        if symbol not in self.price_history:
            self.price_history[symbol] = []
        self.price_history[symbol].append(price)
        if len(self.price_history[symbol]) > 180:
            self.price_history[symbol] = self.price_history[symbol][-180:]
        
        avg_price_hist = sum(self.price_history[symbol]) / len(self.price_history[symbol])
        price_vs_avg = (price - avg_price_hist) / avg_price_hist
        
        is_dip = price_vs_avg < -self.config["dip_threshold_pct"]
        
        # --- Verificar VENTA ---
        if symbol in self.positions:
            pos = self.positions[symbol]
            if pos["avg_price"] > 0:
                profit_pct = (price - pos["avg_price"]) / pos["avg_price"]
                
                # Vender 25% si ganancia > 50% y RSI > 80
                if profit_pct > 0.50 and rsi > 80:
                    self._execute_sell(symbol, 0.25, price, timestamp)
                # Vender 50% si ganancia > 100%
                elif profit_pct > 1.0:
                    self._execute_sell(symbol, 0.50, price, timestamp)
        
        # --- Verificar COMPRA ---
        if not can_buy:
            return
        
        # Intervalo de tiempo
        can_buy_time = True
        if symbol in self.last_buy_time:
            elapsed = (timestamp - self.last_buy_time[symbol]).total_seconds() / 3600
            can_buy_time = elapsed >= self.config["buy_interval_hours"]
        
        if not can_buy_time and not is_dip:
            return
        
        # EMA 200 filter
        ema_200 = row.get("ema_200", 0)
        if ema_200 > 0 and price < ema_200:
            return
        
        # Calcular monto de compra
        buy_usd = min(5.0, self.available * 0.05)  # Max $5 o 5% del disponible
        if buy_usd < 1.0 or self.available < buy_usd:
            return
        
        # Multiplicador por dip
        if price_vs_avg < -(self.config["dip_threshold_pct"] * 2):
            buy_usd = min(buy_usd * 3, self.available * 0.10)
        elif is_dip:
            buy_usd = min(buy_usd * 2, self.available * 0.08)
        elif rsi < 35:
            buy_usd = min(buy_usd * 1.5, self.available * 0.06)
        
        self._execute_buy(symbol, buy_usd, price, timestamp)
    
    def _execute_buy(self, symbol: str, usd: float, price: float, timestamp):
        fee = usd * FEE_RATE
        amount = (usd - fee) / price
        
        if symbol not in self.positions:
            self.positions[symbol] = {"amount": 0, "avg_price": 0, "invested": 0}
        
        pos = self.positions[symbol]
        total_value = pos["amount"] * pos["avg_price"] + amount * price
        pos["amount"] += amount
        pos["avg_price"] = total_value / pos["amount"] if pos["amount"] > 0 else price
        pos["invested"] += usd
        
        self.available -= usd
        self.last_buy_time[symbol] = timestamp
        
        self.trades.append({
            "symbol": symbol, "side": "buy", "price": price,
            "amount": amount, "usd": usd, "fee": fee,
            "timestamp": timestamp, "strategy": "DCA"
        })
    
    def _execute_sell(self, symbol: str, pct: float, price: float, timestamp):
        pos = self.positions[symbol]
        sell_amount = pos["amount"] * pct
        sell_usd = sell_amount * price
        fee = sell_usd * FEE_RATE
        
        gross_profit = (price - pos["avg_price"]) * sell_amount
        entry_fee = pos["avg_price"] * sell_amount * FEE_RATE
        net_profit = gross_profit - entry_fee - fee
        
        pos["amount"] -= sell_amount
        self.available += sell_usd - fee
        
        self.trades.append({
            "symbol": symbol, "side": "sell", "price": price,
            "amount": sell_amount, "usd": sell_usd, "fee": fee + entry_fee,
            "profit": net_profit, "timestamp": timestamp, "strategy": "DCA"
        })
    
    def get_equity(self, prices: Dict[str, float]) -> float:
        """Retorna el valor total del portfolio."""
        equity = self.available
        for symbol, pos in self.positions.items():
            if symbol in prices:
                equity += pos["amount"] * prices[symbol]
        return equity


# =============================================================================
# SIMULACIÓN GRID
# =============================================================================
class GridSimulator:
    """Simula la estrategia Grid Trading."""
    
    def __init__(self, capital: float, config: dict):
        self.capital = capital
        self.available = capital
        self.config = config
        self.grids: Dict[str, dict] = {}  # symbol -> grid config
        self.trades: List[dict] = []
    
    def _setup_grid(self, symbol: str, price: float, high: float, low: float):
        """Configura una nueva grid."""
        n_levels = self.config["grid_levels"]
        
        if high > 0 and low > 0:
            upper = high * 1.02
            lower = low * 0.98
        else:
            spacing = price * self.config["grid_spacing_pct"]
            upper = price + spacing * n_levels / 2
            lower = price - spacing * n_levels / 2
        
        spacing_amt = (upper - lower) / n_levels
        order_size_usd = self.capital / n_levels
        
        levels = []
        for i in range(n_levels):
            bp = lower + spacing_amt * i
            sp = bp + spacing_amt
            levels.append({
                "level": i - n_levels // 2,
                "buy_price": bp,
                "sell_price": sp,
                "status": "pending",
                "amount": 0,
                "bought_price": 0,
            })
        
        self.grids[symbol] = {
            "levels": levels,
            "order_size_usd": order_size_usd,
            "center_price": price,
        }
    
    def process_tick(self, symbol: str, row: pd.Series, can_buy: bool, timestamp=None):
        """Procesa un tick para Grid."""
        price = row["close"]
        high = row["high"]
        low = row["low"]
        ema_50 = row.get("ema_50", 0)
        ema_200 = row.get("ema_200", 0)
        atr = row.get("atr", 0)
        
        # Setup grid si no existe (y podemos comprar)
        if can_buy and symbol not in self.grids:
            self._setup_grid(symbol, price, high, low)
        
        if symbol not in self.grids:
            return
        
        grid = self.grids[symbol]
        
        # --- Verificar VENTAS (siempre) ---
        for level in grid["levels"]:
            if level["status"] == "bought" and price >= level["sell_price"]:
                self._sell_level(symbol, level, price, timestamp)
                break  # Un trade por tick
        
        # --- Verificar COMPRAS (solo si can_buy) ---
        if not can_buy:
            return
        
        # Filtro EMA 200
        if ema_200 > 0 and price < ema_200:
            return
        
        # Filtro EMA 50 < EMA 200 (tendencia bajista)
        if ema_50 > 0 and ema_200 > 0 and ema_50 < ema_200:
            return
        
        # Filtro volatilidad mínima
        if price > 0 and atr > 0:
            atr_pct = atr / price
            if atr_pct < self.config["min_volatility_atr_pct"]:
                return
        
        for level in grid["levels"]:
            if level["status"] == "pending" and price <= level["buy_price"]:
                self._buy_level(symbol, level, price, timestamp)
                break  # Un trade por tick
    
    def _buy_level(self, symbol: str, level: dict, price: float, timestamp):
        order_usd = self.grids[symbol]["order_size_usd"]
        if order_usd > self.available or order_usd < 1.0:
            return
        
        fee = order_usd * FEE_RATE
        amount = (order_usd - fee) / price
        
        level["status"] = "bought"
        level["amount"] = amount
        level["bought_price"] = price
        
        self.available -= order_usd
        
        self.trades.append({
            "symbol": symbol, "side": "buy", "price": price,
            "amount": amount, "usd": order_usd, "fee": fee,
            "timestamp": timestamp, "strategy": "Grid",
            "level": level["level"]
        })
    
    def _sell_level(self, symbol: str, level: dict, price: float, timestamp):
        amount = level["amount"]
        sell_usd = amount * price
        fee = sell_usd * FEE_RATE
        entry_fee = level["bought_price"] * amount * FEE_RATE
        
        gross = (price - level["bought_price"]) * amount
        net = gross - fee - entry_fee
        
        level["status"] = "pending"
        level["amount"] = 0
        
        self.available += sell_usd - fee
        
        self.trades.append({
            "symbol": symbol, "side": "sell", "price": price,
            "amount": amount, "usd": sell_usd, "fee": fee + entry_fee,
            "profit": net, "timestamp": timestamp, "strategy": "Grid",
            "level": level["level"]
        })
    
    def get_equity(self, prices: Dict[str, float]) -> float:
        equity = self.available
        for symbol, grid in self.grids.items():
            if symbol in prices:
                for level in grid["levels"]:
                    if level["status"] == "bought":
                        equity += level["amount"] * prices[symbol]
        return equity


# =============================================================================
# SIMULACIÓN TECHNICAL
# =============================================================================
class TechnicalSimulator:
    """Simula la estrategia Technical RSI+MACD."""
    
    def __init__(self, capital: float, config: dict):
        self.capital = capital
        self.available = capital
        self.config = config
        self.positions: Dict[str, dict] = {}
        self.trades: List[dict] = []
        self.pending_signals: Dict[str, str] = {}
    
    def _calculate_score(self, row: pd.Series) -> tuple:
        """Calcula score técnico."""
        score = 0.0
        reasons = []
        
        rsi = row["rsi"]
        macd = row["macd"]
        macd_signal = row["macd_signal"]
        macd_hist = row["macd_hist"]
        prev_macd_hist = row.get("prev_macd_hist", 0)
        bb_position = row["bb_position"]
        trend = row["trend"]
        
        # RSI
        if rsi < 25:
            score += 3; reasons.append("RSI muy bajo")
        elif rsi < self.config["rsi_oversold"]:
            score += 2; reasons.append("RSI oversold")
        elif rsi > 75:
            score -= 3; reasons.append("RSI muy alto")
        elif rsi > self.config["rsi_overbought"]:
            score -= 2; reasons.append("RSI overbought")
        
        # MACD
        if macd > macd_signal:
            if macd_hist > 0 and prev_macd_hist <= 0:
                score += 3; reasons.append("MACD cruce alcista")
            else:
                score += 1
        elif macd < macd_signal:
            if macd_hist < 0 and prev_macd_hist >= 0:
                score -= 3; reasons.append("MACD cruce bajista")
            else:
                score -= 1
        
        # Bollinger
        if bb_position == "oversold":
            score += 2; reasons.append("BB inferior")
        elif bb_position == "overbought":
            score -= 2; reasons.append("BB superior")
        
        # Tendencia
        if trend == "strong_uptrend":
            score += 1
        elif trend == "uptrend":
            score += 0.5
        elif trend == "strong_downtrend":
            score -= 1
        elif trend == "downtrend":
            score -= 0.5
        
        if score >= 4:
            signal = "strong_buy"
        elif score >= 2:
            signal = "buy"
        elif score <= -4:
            signal = "strong_sell"
        elif score <= -2:
            signal = "sell"
        else:
            signal = "hold"
        
        return signal, score, reasons
    
    def process_tick(self, symbol: str, row: pd.Series, can_buy: bool, timestamp=None):
        """Procesa un tick para Technical."""
        price = row["close"]
        atr = row.get("atr", 0)
        ema_200 = row.get("ema_200", 0)
        
        signal, score, reasons = self._calculate_score(row)
        
        # --- Verificar SALIDA de posición existente ---
        if symbol in self.positions:
            pos = self.positions[symbol]
            pnl_pct = (price - pos["entry_price"]) / pos["entry_price"]
            
            # Stop loss
            if price <= pos["stop_loss"]:
                self._close_position(symbol, price, timestamp, "Stop Loss")
                return
            
            # Take profit
            if price >= pos["take_profit"]:
                self._close_position(symbol, price, timestamp, "Take Profit")
                return
            
            # Señal de venta fuerte
            if signal in ("sell", "strong_sell") and score <= -4:
                self._close_position(symbol, price, timestamp, "Señal Técnica")
                return
            
            # Trailing stop
            if pnl_pct > 0.02:
                if price > pos.get("high_watermark", pos["entry_price"]):
                    pos["high_watermark"] = price
                new_stop = pos.get("high_watermark", price) * (1 - self.config["trailing_stop_pct"])
                if new_stop > pos["stop_loss"]:
                    pos["stop_loss"] = new_stop
                if price <= pos["stop_loss"]:
                    self._close_position(symbol, price, timestamp, "Trailing Stop")
                    return
            return
        
        # --- Verificar ENTRADA ---
        if not can_buy:
            return
        
        if signal in ("buy", "strong_buy"):
            # Confirmación (2 señales consecutivas)
            if symbol in self.pending_signals and self.pending_signals[symbol] in ("buy", "strong_buy"):
                del self.pending_signals[symbol]
                
                # EMA 200 filter
                if ema_200 > 0 and price < ema_200:
                    return
                
                self._open_position(symbol, price, atr, timestamp)
            else:
                self.pending_signals[symbol] = signal
        else:
            if symbol in self.pending_signals:
                del self.pending_signals[symbol]
    
    def _open_position(self, symbol: str, price: float, atr: float, timestamp):
        buy_usd = min(10.0, self.available * 0.15)
        if buy_usd < 1.0 or self.available < buy_usd:
            return
        
        fee = buy_usd * FEE_RATE
        amount = (buy_usd - fee) / price
        
        # SL/TP dinámico con ATR
        if atr > 0 and (atr / price) > 0.005:
            stop_loss = price - atr * 2.0
            take_profit = price + atr * 4.0
        else:
            stop_loss = price * (1 - self.config["stop_loss_pct"])
            take_profit = price * (1 + self.config["take_profit_pct"])
        
        # Asegurar ratio 1:1.5
        risk = price - stop_loss
        reward = take_profit - price
        if risk > 0 and reward / risk < 1.5:
            take_profit = price + risk * 1.5
        
        self.positions[symbol] = {
            "amount": amount,
            "entry_price": price,
            "stop_loss": stop_loss,
            "take_profit": take_profit,
            "high_watermark": price,
            "timestamp": timestamp,
        }
        
        self.available -= buy_usd
        
        self.trades.append({
            "symbol": symbol, "side": "buy", "price": price,
            "amount": amount, "usd": buy_usd, "fee": fee,
            "timestamp": timestamp, "strategy": "Technical"
        })
    
    def _close_position(self, symbol: str, price: float, timestamp, reason: str):
        pos = self.positions[symbol]
        sell_usd = pos["amount"] * price
        fee = sell_usd * FEE_RATE
        entry_fee = pos["entry_price"] * pos["amount"] * FEE_RATE
        
        gross = (price - pos["entry_price"]) * pos["amount"]
        net = gross - fee - entry_fee
        
        self.available += sell_usd - fee
        
        self.trades.append({
            "symbol": symbol, "side": "sell", "price": price,
            "amount": pos["amount"], "usd": sell_usd, "fee": fee + entry_fee,
            "profit": net, "timestamp": timestamp, "strategy": "Technical",
            "reason": reason,
        })
        
        del self.positions[symbol]
    
    def get_equity(self, prices: Dict[str, float]) -> float:
        equity = self.available
        for symbol, pos in self.positions.items():
            if symbol in prices:
                equity += pos["amount"] * prices[symbol]
        return equity


# =============================================================================
# MOTOR PRINCIPAL DE BACKTEST
# =============================================================================
class BacktestEngine:
    """Motor principal del backtester."""
    
    def __init__(self, initial_capital: float, months: int, symbols: List[str]):
        self.initial_capital = initial_capital
        self.months = months
        self.symbols = symbols
        self.data: Dict[str, pd.DataFrame] = {}
        self.equity_curve: List[dict] = []
    
    def download_data(self):
        """Descarga datos para todos los símbolos."""
        print("\n📥 DESCARGANDO DATOS HISTÓRICOS")
        print("=" * 50)
        for symbol in self.symbols:
            df = download_binance_data(symbol, "1h", self.months)
            df = add_indicators(df)
            self.data[symbol] = df
            print(f"     Rango: {df['timestamp'].iloc[0].strftime('%Y-%m-%d')} → {df['timestamp'].iloc[-1].strftime('%Y-%m-%d')}")
    
    def run(self) -> dict:
        """Ejecuta el backtesting completo."""
        print("\n🚀 EJECUTANDO BACKTEST")
        print("=" * 50)
        
        capital = self.initial_capital
        
        # Distribuir capital por estrategia
        dca_capital = capital * STRATEGIES_CONFIG["dca"]["allocation_pct"]
        grid_capital = capital * STRATEGIES_CONFIG["grid"]["allocation_pct"]
        tech_capital = capital * STRATEGIES_CONFIG["technical"]["allocation_pct"]
        
        # Inicializar simuladores
        dca = DCASimulator(dca_capital, STRATEGIES_CONFIG["dca"])
        grid = GridSimulator(grid_capital, STRATEGIES_CONFIG["grid"])
        tech = TechnicalSimulator(tech_capital, STRATEGIES_CONFIG["technical"])
        
        # Alinear datos: usar el rango de timestamps comunes
        common_timestamps = None
        for symbol, df in self.data.items():
            ts_set = set(df["timestamp"])
            if common_timestamps is None:
                common_timestamps = ts_set
            else:
                common_timestamps = common_timestamps.intersection(ts_set)
        
        common_timestamps = sorted(common_timestamps)
        total_ticks = len(common_timestamps)
        
        print(f"  📊 {total_ticks} ticks comunes entre {len(self.symbols)} pares")
        print(f"  💰 Capital inicial: ${capital:.2f}")
        print(f"     DCA: ${dca_capital:.2f} | Grid: ${grid_capital:.2f} | Technical: ${tech_capital:.2f}")
        print()
        
        # Indexar datos por timestamp
        indexed_data = {}
        for symbol, df in self.data.items():
            indexed_data[symbol] = df.set_index("timestamp")
        
        # --- LOOP PRINCIPAL ---
        peak_equity = capital
        max_drawdown = 0
        
        for i, ts in enumerate(common_timestamps):
            prices = {}
            for symbol in self.symbols:
                if ts not in indexed_data[symbol].index:
                    continue
                row = indexed_data[symbol].loc[ts]
                prices[symbol] = row["close"]
                
                # EMA 200 filter: can_buy si precio > EMA 200
                ema_200 = row.get("ema_200", 0)
                can_buy = ema_200 <= 0 or row["close"] >= ema_200
                
                # Ejecutar estrategias (pasar ts como argumento separado)
                dca.process_tick(symbol, row, can_buy, ts)
                grid.process_tick(symbol, row, can_buy, ts)
                tech.process_tick(symbol, row, can_buy, ts)
            
            # Calcular equity total
            equity = dca.get_equity(prices) + grid.get_equity(prices) + tech.get_equity(prices)
            
            # Track drawdown
            if equity > peak_equity:
                peak_equity = equity
            drawdown = (peak_equity - equity) / peak_equity
            if drawdown > max_drawdown:
                max_drawdown = drawdown
            
            self.equity_curve.append({
                "timestamp": ts,
                "equity": equity,
                "drawdown": drawdown,
            })
            
            # Progreso
            if (i + 1) % (total_ticks // 10 or 1) == 0:
                pct = (i + 1) / total_ticks * 100
                ret = (equity / capital - 1) * 100
                print(f"  ⏳ {pct:.0f}% | Equity: ${equity:.2f} | Return: {ret:+.2f}% | DD: {drawdown*100:.1f}%")
        
        # --- Equity final ---
        final_prices = {}
        for symbol in self.symbols:
            final_prices[symbol] = self.data[symbol]["close"].iloc[-1]
        
        final_equity = dca.get_equity(final_prices) + grid.get_equity(final_prices) + tech.get_equity(final_prices)
        
        # Recopilar todos los trades
        all_trades = dca.trades + grid.trades + tech.trades
        
        return {
            "initial_capital": capital,
            "final_equity": final_equity,
            "max_drawdown": max_drawdown,
            "equity_curve": self.equity_curve,
            "trades": all_trades,
            "dca_trades": dca.trades,
            "grid_trades": grid.trades,
            "tech_trades": tech.trades,
            "months": self.months,
            "symbols": self.symbols,
            "start_date": common_timestamps[0],
            "end_date": common_timestamps[-1],
        }


# =============================================================================
# REPORTE DE RESULTADOS
# =============================================================================
def generate_report(results: dict):
    """Genera reporte completo del backtest."""
    print("\n")
    print("=" * 60)
    print("  📊 REPORTE DE BACKTEST")
    print("=" * 60)
    
    capital = results["initial_capital"]
    final = results["final_equity"]
    ret = (final / capital - 1) * 100
    dd = results["max_drawdown"] * 100
    
    print(f"\n  📅 Período: {results['start_date'].strftime('%Y-%m-%d')} → {results['end_date'].strftime('%Y-%m-%d')} ({results['months']} meses)")
    print(f"  💰 Capital Inicial: ${capital:.2f}")
    print(f"  💰 Capital Final:   ${final:.2f}")
    print(f"  📈 Retorno Total:   {ret:+.2f}%")
    print(f"  📉 Max Drawdown:    {dd:.1f}%")
    
    # Calcular Sharpe Ratio
    curve = results["equity_curve"]
    if len(curve) > 1:
        returns = []
        for i in range(1, len(curve)):
            r = (curve[i]["equity"] / curve[i-1]["equity"]) - 1
            returns.append(r)
        avg_ret = np.mean(returns)
        std_ret = np.std(returns)
        # Anualizar (1h data → ~8760 horas/año)
        sharpe = (avg_ret / std_ret) * np.sqrt(8760) if std_ret > 0 else 0
        print(f"  📐 Sharpe Ratio:    {sharpe:.2f}")
    
    # Análisis de trades
    all_trades = results["trades"]
    sells = [t for t in all_trades if t["side"] == "sell"]
    buys = [t for t in all_trades if t["side"] == "buy"]
    
    if sells:
        profits = [t.get("profit", 0) for t in sells]
        wins = [p for p in profits if p > 0]
        losses = [p for p in profits if p < 0]
        total_fees = sum(t.get("fee", 0) for t in all_trades)
        
        win_rate = len(wins) / len(sells) * 100 if sells else 0
        avg_win = np.mean(wins) if wins else 0
        avg_loss = np.mean(losses) if losses else 0
        profit_factor = abs(sum(wins) / sum(losses)) if losses else float('inf')
        
        print(f"\n  {'─' * 56}")
        print(f"  📋 RESUMEN DE TRADES")
        print(f"  {'─' * 56}")
        print(f"  Total Compras:      {len(buys)}")
        print(f"  Total Ventas:       {len(sells)}")
        print(f"  ✅ Ganadores:       {len(wins)}")
        print(f"  ❌ Perdedores:      {len(losses)}")
        print(f"  🎯 Win Rate:        {win_rate:.1f}%")
        print(f"  💵 Profit Total:    ${sum(profits):.2f}")
        print(f"  💸 Fees Totales:    ${total_fees:.2f}")
        print(f"  📈 Avg Win:         ${avg_win:.4f}")
        print(f"  📉 Avg Loss:        ${avg_loss:.4f}")
        print(f"  ⚖️  Profit Factor:   {profit_factor:.2f}")
        
        if wins:
            print(f"  🏆 Mejor Trade:     ${max(profits):.4f}")
        if losses:
            print(f"  💀 Peor Trade:      ${min(profits):.4f}")
    
    # Desglose por estrategia
    print(f"\n  {'─' * 56}")
    print(f"  📊 DESGLOSE POR ESTRATEGIA")
    print(f"  {'─' * 56}")
    
    for name, key in [("DCA Intelligent", "dca_trades"), ("Grid Trading", "grid_trades"), ("Technical RSI+MACD", "tech_trades")]:
        strat_trades = results[key]
        strat_sells = [t for t in strat_trades if t["side"] == "sell"]
        strat_buys = [t for t in strat_trades if t["side"] == "buy"]
        
        if strat_sells:
            profits = [t.get("profit", 0) for t in strat_sells]
            wins = [p for p in profits if p > 0]
            wr = len(wins) / len(strat_sells) * 100
            total_p = sum(profits)
            print(f"\n  🔹 {name}")
            print(f"     Compras: {len(strat_buys)} | Ventas: {len(strat_sells)}")
            print(f"     Win Rate: {wr:.1f}% | Profit: ${total_p:.2f}")
        else:
            print(f"\n  🔹 {name}")
            print(f"     Compras: {len(strat_buys)} | Ventas: 0 (sin cierres)")
    
    # Veredicto
    print(f"\n  {'═' * 56}")
    if ret > 5 and dd < 15:
        print(f"  ✅ VEREDICTO: ESTRATEGIA VIABLE")
        print(f"     Retorno positivo con drawdown controlado.")
    elif ret > 0:
        print(f"  ⚠️  VEREDICTO: MARGINAL")
        print(f"     Retorno positivo pero insuficiente o riesgo alto.")
    else:
        print(f"  ❌ VEREDICTO: NO RENTABLE")
        print(f"     La estrategia pierde dinero en este período.")
        print(f"     Recomendación: ajustar parámetros y re-testear.")
    print(f"  {'═' * 56}")
    print()


# =============================================================================
# MAIN
# =============================================================================
def main():
    parser = argparse.ArgumentParser(description="Backtester - Bot de Trading")
    parser.add_argument("--months", type=int, default=6, help="Meses de datos históricos (default: 6)")
    parser.add_argument("--capital", type=float, default=200.0, help="Capital inicial en USD (default: 200)")
    parser.add_argument("--symbol", type=str, default=None, help="Par específico (ej: BTC/USDT)")
    args = parser.parse_args()
    
    symbols = [args.symbol] if args.symbol else list(PORTFOLIO_ALLOC.keys())
    
    print("\n" + "=" * 60)
    print("  🔬 BACKTESTER - Bot de Trading")
    print("=" * 60)
    print(f"  Capital: ${args.capital:.2f}")
    print(f"  Período: {args.months} meses")
    print(f"  Pares:   {', '.join(symbols)}")
    
    engine = BacktestEngine(args.capital, args.months, symbols)
    engine.download_data()
    results = engine.run()
    generate_report(results)
    
    # Guardar resumen a archivo
    try:
        capital = results["initial_capital"]
        final = results["final_equity"]
        ret = (final / capital - 1) * 100
        dd = results["max_drawdown"] * 100
        all_trades = results["trades"]
        sells = [t for t in all_trades if t["side"] == "sell"]
        buys = [t for t in all_trades if t["side"] == "buy"]
        wins = [t for t in sells if t.get("profit", 0) > 0]
        wr = len(wins) / len(sells) * 100 if sells else 0
        total_profit = sum(t.get("profit", 0) for t in sells)
        total_fees = sum(t.get("fee", 0) for t in all_trades)
        
        with open("backtest_result.txt", "w", encoding="utf-8") as f:
            f.write(f"=== BACKTEST REPORT ===\n")
            f.write(f"Period: {results['start_date']} -> {results['end_date']} ({results['months']} months)\n")
            f.write(f"Symbols: {', '.join(results['symbols'])}\n")
            f.write(f"Initial Capital: ${capital:.2f}\n")
            f.write(f"Final Capital: ${final:.2f}\n")
            f.write(f"Return: {ret:+.2f}%\n")
            f.write(f"Max Drawdown: {dd:.1f}%\n")
            f.write(f"Total Buys: {len(buys)}\n")
            f.write(f"Total Sells: {len(sells)}\n")
            f.write(f"Win Rate: {wr:.1f}%\n")
            f.write(f"Total Profit: ${total_profit:.2f}\n")
            f.write(f"Total Fees: ${total_fees:.2f}\n")
            
            for name, key in [("DCA", "dca_trades"), ("Grid", "grid_trades"), ("Technical", "tech_trades")]:
                strat_sells = [t for t in results[key] if t["side"] == "sell"]
                strat_buys = [t for t in results[key] if t["side"] == "buy"]
                strat_wins = [t for t in strat_sells if t.get("profit", 0) > 0]
                strat_wr = len(strat_wins) / len(strat_sells) * 100 if strat_sells else 0
                strat_p = sum(t.get("profit", 0) for t in strat_sells)
                f.write(f"\n--- {name} ---\n")
                f.write(f"Buys: {len(strat_buys)} | Sells: {len(strat_sells)}\n")
                f.write(f"Win Rate: {strat_wr:.1f}% | Profit: ${strat_p:.2f}\n")
            
            f.write(f"\nVerdict: {'VIABLE' if ret > 5 and dd < 15 else 'MARGINAL' if ret > 0 else 'NOT PROFITABLE'}\n")
        print("  [Resultados guardados en backtest_result.txt]")
    except Exception as e:
        print(f"  [Error guardando resultados: {e}]")


if __name__ == "__main__":
    main()
