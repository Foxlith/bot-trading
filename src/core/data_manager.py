"""
Data Manager
============
Gestiona la obtención y procesamiento de datos de mercado
"""

import pandas as pd
import ta
from typing import Dict, List, Optional, Any
from datetime import datetime, timedelta
from loguru import logger
import sys

sys.path.insert(0, str(__file__).replace("\\src\\core\\data_manager.py", ""))

from src.core.exchange_manager import get_exchange
from config.settings import TIMEFRAMES, PORTFOLIO


class DataManager:
    """
    Clase para gestionar datos de mercado y calcular indicadores técnicos.
    """
    
    def __init__(self):
        self.exchange = get_exchange()
        self.cache: Dict[str, pd.DataFrame] = {}
        self.cache_time: Dict[str, datetime] = {}
        self.cache_duration = timedelta(minutes=5)
    
    def get_market_data(
        self,
        symbol: str,
        timeframe: str = "1h",
        limit: int = 200,
        use_cache: bool = True
    ) -> pd.DataFrame:
        """
        Obtiene datos OHLCV y los convierte a DataFrame.
        
        Args:
            symbol: Par de trading
            timeframe: Intervalo de tiempo
            limit: Número de velas
            use_cache: Usar datos en cache si están disponibles
        
        Returns:
            DataFrame con columnas: timestamp, open, high, low, close, volume
        """
        cache_key = f"{symbol}_{timeframe}"
        
        # Verificar cache
        if use_cache and cache_key in self.cache:
            if datetime.now() - self.cache_time[cache_key] < self.cache_duration:
                return self.cache[cache_key]
        
        # Obtener datos frescos
        ohlcv = self.exchange.get_ohlcv(symbol, timeframe, limit)
        
        if not ohlcv:
            logger.warning(f"No se obtuvieron datos para {symbol}")
            return pd.DataFrame()
        
        df = pd.DataFrame(
            ohlcv,
            columns=["timestamp", "open", "high", "low", "close", "volume"]
        )
        df["timestamp"] = pd.to_datetime(df["timestamp"], unit="ms")
        df.set_index("timestamp", inplace=True)
        
        # Guardar en cache
        self.cache[cache_key] = df
        self.cache_time[cache_key] = datetime.now()
        
        return df
    
    def add_technical_indicators(self, df: pd.DataFrame) -> pd.DataFrame:
        """
        Agrega indicadores técnicos al DataFrame.
        
        Indicadores incluidos:
        - RSI (14 períodos)
        - MACD (12, 26, 9)
        - Bollinger Bands (20, 2)
        - EMA (9, 21, 50)
        - ATR (14)
        - Volume SMA (20)
        """
        if df.empty:
            return df
        
        df = df.copy()
        
        # RSI
        df["rsi"] = ta.momentum.RSIIndicator(df["close"], window=14).rsi()
        
        # MACD
        macd_indicator = ta.trend.MACD(df["close"], window_slow=26, window_fast=12, window_sign=9)
        df["macd"] = macd_indicator.macd()
        df["macd_signal"] = macd_indicator.macd_signal()
        df["macd_hist"] = macd_indicator.macd_diff()
        
        # Bollinger Bands
        bb_indicator = ta.volatility.BollingerBands(df["close"], window=20, window_dev=2)
        df["bb_upper"] = bb_indicator.bollinger_hband()
        df["bb_middle"] = bb_indicator.bollinger_mavg()
        df["bb_lower"] = bb_indicator.bollinger_lband()
        
        # EMAs
        df["ema_9"] = ta.trend.EMAIndicator(df["close"], window=9).ema_indicator()
        df["ema_21"] = ta.trend.EMAIndicator(df["close"], window=21).ema_indicator()
        df["ema_50"] = ta.trend.EMAIndicator(df["close"], window=50).ema_indicator()
        df["ema_200"] = ta.trend.EMAIndicator(df["close"], window=200).ema_indicator()
        
        # ATR (Average True Range) - para volatilidad
        df["atr"] = ta.volatility.AverageTrueRange(df["high"], df["low"], df["close"], window=14).average_true_range()
        
        # Volume SMA
        df["volume_sma"] = ta.trend.SMAIndicator(df["volume"], window=20).sma_indicator()
        
        return df
    
    def get_market_summary(self, symbol: str) -> Dict[str, Any]:
        """
        Obtiene un resumen del mercado para un par.
        
        Returns:
            Dict con precio actual, cambio %, indicadores clave
        """
        # FIX Bug 2: Pedir 250 velas (antes 100) para que EMA 200 no sea NaN
        df = self.get_market_data(symbol, "1h", 250)
        
        if df.empty:
            return {"error": "No hay datos disponibles"}
        
        df = self.add_technical_indicators(df)
        last = df.iloc[-1]
        prev = df.iloc[-2] if len(df) > 1 else last
        
        # FIX Bug 7: Usar precio del OHLCV como base, ticker solo como enriquecimiento
        # get_ticker se llama solo si necesitamos datos de 24h (high/low/volume)
        # El precio actual se toma del close de la última vela para evitar doble API call
        current_price = float(last["close"])
        
        # Solo llamar a ticker si no está en cache reciente (aprovecha cache de 5min del exchange)
        try:
            ticker = self.exchange.get_ticker(symbol)
            ticker_price = ticker.get("last", current_price)
            change_24h = ticker.get("change_pct", 0)
            high_24h = ticker.get("high", 0)
            low_24h = ticker.get("low", 0)
            volume_24h = ticker.get("volume", 0)
        except Exception:
            ticker_price = current_price
            change_24h = 0
            high_24h = 0
            low_24h = 0
            volume_24h = 0
        
        # Manejar EMA200 NaN: si aún no hay suficientes datos, usar 0
        ema_200 = last.get("ema_200", 0)
        if pd.isna(ema_200):
            ema_200 = 0
        
        return {
            "symbol": symbol,
            "price": ticker_price,
            "change_24h": change_24h,
            "high_24h": high_24h,
            "low_24h": low_24h,
            "volume_24h": volume_24h,
            "rsi": round(last.get("rsi", 50), 2),
            "macd": last.get("macd", 0),
            "macd_signal": last.get("macd_signal", 0),
            "macd_hist": last.get("macd_hist", 0),
            "prev_macd_hist": prev.get("macd_hist", 0),
            "macd_trend": "bullish" if last.get("macd", 0) > last.get("macd_signal", 0) else "bearish",
            "bb_position": self._get_bb_position(last),
            "trend": self._get_trend(last),
            "atr": round(last.get("atr", 0), 4),
            "volatility": round(last.get("atr", 0), 4),
            "ema_50": last.get("ema_50", 0),
            "ema_200": ema_200,
        }
    
    def _get_bb_position(self, row: pd.Series) -> str:
        """Determina la posición respecto a Bollinger Bands."""
        close = row.get("close", 0)
        upper = row.get("bb_upper", close)
        lower = row.get("bb_lower", close)
        middle = row.get("bb_middle", close)
        
        if close >= upper:
            return "overbought"
        elif close <= lower:
            return "oversold"
        elif close > middle:
            return "upper_half"
        else:
            return "lower_half"
    
    def _get_trend(self, row: pd.Series) -> str:
        """Determina la tendencia basada en EMAs."""
        ema_9 = row.get("ema_9", 0)
        ema_21 = row.get("ema_21", 0)
        ema_50 = row.get("ema_50", 0)
        
        if ema_9 > ema_21 > ema_50:
            return "strong_uptrend"
        elif ema_9 > ema_21:
            return "uptrend"
        elif ema_9 < ema_21 < ema_50:
            return "strong_downtrend"
        elif ema_9 < ema_21:
            return "downtrend"
        else:
            return "sideways"
    
    def get_all_portfolio_data(self) -> Dict[str, Dict]:
        """Obtiene datos de todos los pares del portafolio."""
        portfolio_data = {}
        
        for symbol in PORTFOLIO.keys():
            try:
                portfolio_data[symbol] = self.get_market_summary(symbol)
            except Exception as e:
                logger.error(f"Error obteniendo datos de {symbol}: {e}")
                portfolio_data[symbol] = {"error": str(e)}
        
        return portfolio_data
    
    def detect_signals(self, symbol: str) -> Dict[str, Any]:
        """
        Detecta señales de trading basadas en indicadores técnicos.
        
        Returns:
            Dict con señales detectadas y su fuerza
        """
        df = self.get_market_data(symbol, "1h", 100)
        if df.empty:
            return {"signal": "none", "strength": 0}
        
        df = self.add_technical_indicators(df)
        last = df.iloc[-1]
        prev = df.iloc[-2]
        
        signals = []
        
        # RSI Señales
        rsi = last.get("rsi", 50)
        if rsi < 30:
            signals.append(("RSI oversold", 2, "buy"))
        elif rsi > 70:
            signals.append(("RSI overbought", 2, "sell"))
        
        # MACD Crossover
        macd = last.get("macd", 0)
        macd_signal = last.get("macd_signal", 0)
        prev_macd = prev.get("macd", 0)
        prev_macd_signal = prev.get("macd_signal", 0)
        
        if prev_macd < prev_macd_signal and macd > macd_signal:
            signals.append(("MACD bullish crossover", 3, "buy"))
        elif prev_macd > prev_macd_signal and macd < macd_signal:
            signals.append(("MACD bearish crossover", 3, "sell"))
        
        # Bollinger Bands
        close = last.get("close", 0)
        bb_lower = last.get("bb_lower", close)
        bb_upper = last.get("bb_upper", close)
        
        if close <= bb_lower:
            signals.append(("Price at BB lower", 2, "buy"))
        elif close >= bb_upper:
            signals.append(("Price at BB upper", 2, "sell"))
        
        # EMA Trend
        if last.get("ema_9", 0) > last.get("ema_21", 0) > last.get("ema_50", 0):
            signals.append(("Strong uptrend (EMA)", 1, "buy"))
        elif last.get("ema_9", 0) < last.get("ema_21", 0) < last.get("ema_50", 0):
            signals.append(("Strong downtrend (EMA)", 1, "sell"))
        
        # Calcular señal final
        buy_strength = sum(s[1] for s in signals if s[2] == "buy")
        sell_strength = sum(s[1] for s in signals if s[2] == "sell")
        
        if buy_strength > sell_strength and buy_strength >= 3:
            return {
                "signal": "buy",
                "strength": buy_strength,
                "reasons": [s[0] for s in signals if s[2] == "buy"]
            }
        elif sell_strength > buy_strength and sell_strength >= 3:
            return {
                "signal": "sell",
                "strength": sell_strength,
                "reasons": [s[0] for s in signals if s[2] == "sell"]
            }
        else:
            return {
                "signal": "hold",
                "strength": 0,
                "reasons": ["No clear signal"]
            }


# Singleton
_data_manager: Optional[DataManager] = None

def get_data_manager() -> DataManager:
    """Obtiene la instancia singleton del Data Manager."""
    global _data_manager
    if _data_manager is None:
        _data_manager = DataManager()
    return _data_manager
