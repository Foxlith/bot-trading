"""
Exchange Manager
================
Gestiona la conexión y operaciones con Binance
"""

import ccxt
import time
import random
from decimal import Decimal, ROUND_DOWN
from typing import Optional, Dict, Any, List, Callable, TypeVar
from loguru import logger
from pathlib import Path
import sys

# Constantes de precisión financiera
MONEY_PRECISION = Decimal('0.00000001')  # 8 decimales para cripto
FEE_RATE = Decimal('0.001')  # 0.1%


def safe_decimal(value, default='0') -> Decimal:
    """Convierte un valor a Decimal de forma segura, evitando InvalidOperation."""
    try:
        if value is None or value == '':
            return Decimal(default)
        if isinstance(value, float):
            import math
            if math.isnan(value) or math.isinf(value):
                return Decimal(default)
        return Decimal(str(value))
    except Exception:
        return Decimal(default)

# Constantes de Rate Limiting
MAX_RETRIES = 5
BASE_DELAY = 1.0  # segundos

# Agregar el directorio raíz al path
sys.path.insert(0, str(__file__).replace("\\src\\core\\exchange_manager.py", ""))

from config.settings import EXCHANGE, OPERATION_MODE

T = TypeVar('T')

def with_exponential_backoff(
    func: Callable[[], T],
    max_retries: int = MAX_RETRIES,
    base_delay: float = BASE_DELAY,
    operation_name: str = "API call"
) -> T:
    """
    Ejecuta una función con exponential backoff en caso de rate limiting.
    
    Args:
        func: Función a ejecutar
        max_retries: Número máximo de reintentos
        base_delay: Delay base en segundos
        operation_name: Nombre de la operación para logging
    
    Returns:
        Resultado de la función
    
    Raises:
        Exception si se agotan los reintentos
    """
    last_exception = None
    
    for attempt in range(max_retries):
        try:
            return func()
        except ccxt.RateLimitExceeded as e:
            last_exception = e
            wait_time = (2 ** attempt) * base_delay + random.uniform(0, 1)
            logger.warning(f"⚠️ Rate limit en {operation_name}, esperando {wait_time:.1f}s (intento {attempt + 1}/{max_retries})")
            time.sleep(wait_time)
        except ccxt.NetworkError as e:
            last_exception = e
            wait_time = (2 ** attempt) * base_delay + random.uniform(0, 1)
            logger.warning(f"⚠️ Error de red en {operation_name}, reintentando en {wait_time:.1f}s (intento {attempt + 1}/{max_retries})")
            time.sleep(wait_time)
        except ccxt.ExchangeNotAvailable as e:
            last_exception = e
            wait_time = (2 ** attempt) * base_delay * 2  # Mayor espera para exchange no disponible
            logger.warning(f"⚠️ Exchange no disponible en {operation_name}, esperando {wait_time:.1f}s")
            time.sleep(wait_time)
    
    # Si llegamos aquí, agotamos los reintentos
    logger.error(f"❌ {operation_name} falló después de {max_retries} intentos: {last_exception}")
    raise last_exception


class ExchangeManager:
    """
    Clase principal para interactuar con el exchange (Binance).
    Soporta modo paper trading y modo real.
    """
    
    def __init__(self):
        self.exchange_name = EXCHANGE["name"]
        self.testnet = EXCHANGE["testnet"]
        self.exchange: Optional[ccxt.Exchange] = None
        self.market_exchange: Optional[ccxt.Exchange] = None  # Para datos reales
        self.paper_mode = OPERATION_MODE["mode"] == "paper"
        # Paper balance usando Decimal para precisión
        self.paper_balance = {
            "USDT": safe_decimal(OPERATION_MODE["paper_balance_usd"]),
            "BTC": Decimal('0'),
            "ETH": Decimal('0'),
            "SOL": Decimal('0'),
            "BNB": Decimal('0'),
            "XRP": Decimal('0'),
            "ADA": Decimal('0'),
            "DOGE": Decimal('0'),
        }
        self.paper_wallet_file = str(Path(__file__).resolve().parent.parent.parent / "data" / "paper_wallet.json")
        
        # Cargar estado si existe y estamos en paper mode
        if self.paper_mode:
            self._load_paper_wallet()
            
        self._initialize_exchange()
    
    def _initialize_exchange(self) -> None:
        """Inicializa la conexión con el exchange."""
        try:
            exchange_class = getattr(ccxt, self.exchange_name)
            
            config = {
                "apiKey": EXCHANGE["api_key"],
                "secret": EXCHANGE["api_secret"],
                "sandbox": self.testnet,
                "options": EXCHANGE["options"],
                "enableRateLimit": True,
            }
            
            self.exchange = exchange_class(config)
            
            # Cargar mercados
            self.exchange.load_markets()
            
            # En modo PAPER, inicializar una conexión pública a producción para datos reales
            if self.paper_mode:
                self.market_exchange = exchange_class({
                    "enableRateLimit": True,
                    # Sin API keys para acceso público
                })
                self.market_exchange.load_markets()
                logger.info(f"✅ Datos de mercado: CONECTADO A PRODUCCIÓN (Precios Reales)")
            else:
                self.market_exchange = self.exchange
            
            mode = "PAPER" if self.paper_mode else ("TESTNET" if self.testnet else "PRODUCCIÓN")
            logger.info(f"✅ Conectado a {self.exchange_name.upper()} en modo {mode}")
            
        except Exception as e:
            logger.error(f"❌ Error conectando a {self.exchange_name}: {e}")
            raise
    
    def get_balance(self) -> Dict[str, float]:
        """
        Obtiene el balance de la cuenta.
        En paper mode, retorna el balance simulado.
        """
        if self.paper_mode:
            return {k: float(v) for k, v in self.paper_balance.items()}
        
        try:
            balance = self.exchange.fetch_balance()
            return {
                asset: info["free"] 
                for asset, info in balance["total"].items() 
                if info > 0
            }
        except Exception as e:
            logger.error(f"Error obteniendo balance: {e}")
            return {}
    
    def get_ticker(self, symbol: str) -> Dict[str, Any]:
        """
        Obtiene el precio actual de un par con exponential backoff.
        """
        def _fetch():
            exchange = self.market_exchange if self.market_exchange else self.exchange
            ticker = exchange.fetch_ticker(symbol)
            return {
                "symbol": symbol,
                "last": ticker["last"],
                "bid": ticker["bid"],
                "ask": ticker["ask"],
                "high": ticker["high"],
                "low": ticker["low"],
                "volume": ticker["baseVolume"],
                "change_pct": ticker["percentage"],
            }
        
        try:
            return with_exponential_backoff(_fetch, operation_name=f"get_ticker({symbol})")
        except Exception as e:
            logger.error(f"Error obteniendo ticker de {symbol} después de reintentos: {e}")
            return {}
    
    def get_ohlcv(self, symbol: str, timeframe: str = "1h", limit: int = 100) -> List[List]:
        """
        Obtiene datos históricos OHLCV con exponential backoff.
        """
        def _fetch():
            exchange = self.market_exchange if self.market_exchange else self.exchange
            return exchange.fetch_ohlcv(symbol, timeframe, limit=limit)
        
        try:
            return with_exponential_backoff(_fetch, operation_name=f"get_ohlcv({symbol})")
        except Exception as e:
            logger.error(f"Error obteniendo OHLCV de {symbol} después de reintentos: {e}")
            return []
            
    def _load_paper_wallet(self) -> None:
        """Carga el estado de la paper wallet desde disco."""
        import json
        import os
        
        try:
            logger.debug(f"🔍 Buscando paper wallet en: {self.paper_wallet_file}")
            if os.path.exists(self.paper_wallet_file):
                with open(self.paper_wallet_file, 'r') as f:
                    saved_balance = json.load(f)
                    # Merge con default para asegurar todas las keys
                    for k, v in saved_balance.items():
                        self.paper_balance[k] = safe_decimal(v)
                logger.info(f"📂 Paper Wallet cargada: USDT={float(self.paper_balance.get('USDT', 0)):.2f}")
            else:
                logger.warning(f"⚠️ Archivo no encontrado: {self.paper_wallet_file}")
                logger.info("🆕 Paper Wallet iniciada con balance default")
                self._save_paper_wallet()
        except Exception as e:
            logger.error(f"Error cargando paper wallet: {e}")

    def _save_paper_wallet(self) -> None:
        """Guarda el estado de la paper wallet a disco."""
        import json
        import os
        
        try:
            os.makedirs(os.path.dirname(self.paper_wallet_file), exist_ok=True)
            # Usar default=str para serializar Decimal como string automáticamente
            with open(self.paper_wallet_file, 'w') as f:
                json.dump(self.paper_balance, f, indent=4, default=str)
        except Exception as e:
            logger.error(f"Error guardando paper wallet: {e}")
    
    def place_order(
        self,
        symbol: str,
        side: str,
        amount: float,
        order_type: str = "market",
        price: Optional[float] = None
    ) -> Dict[str, Any]:
        """
        Coloca una orden en el exchange.
        
        Args:
            symbol: Par de trading (ej: "BTC/USDT")
            side: "buy" o "sell"
            amount: Cantidad a comprar/vender
            order_type: "market" o "limit"
            price: Precio para órdenes limit
        
        Returns:
            Dict con información de la orden
        """
        if self.paper_mode:
            return self._paper_order(symbol, side, amount, order_type, price)
        
        try:
            if order_type == "market":
                order = self.exchange.create_market_order(symbol, side, amount)
            else:
                if price is None:
                    raise ValueError("Precio requerido para órdenes limit")
                order = self.exchange.create_limit_order(symbol, side, amount, price)
            
            logger.info(f"✅ Orden ejecutada: {side.upper()} {amount} {symbol} @ {order.get('price', 'market')}")
            return order
            
        except Exception as e:
            logger.error(f"❌ Error colocando orden: {e}")
            return {"error": str(e)}
    
    def _paper_order(
        self,
        symbol: str,
        side: str,
        amount: float,
        order_type: str,
        price: Optional[float]
    ) -> Dict[str, Any]:
        """Simula una orden en paper trading."""
        ticker = self.get_ticker(symbol)
        if not ticker:
            return {"error": "No se pudo obtener precio"}
        
        exec_price = price if price else ticker["last"]
        base, quote = symbol.split("/")
        
        if side == "buy":
            # Convertir a Decimal para precisión
            d_amount = safe_decimal(amount)
            d_price = safe_decimal(exec_price)
            
            cost = (d_amount * d_price).quantize(MONEY_PRECISION, rounding=ROUND_DOWN)
            total_cost = (cost * (Decimal('1') + FEE_RATE)).quantize(MONEY_PRECISION, rounding=ROUND_DOWN)
            
            available = self.paper_balance.get(quote, Decimal('0'))
            
            if available >= total_cost:
                self.paper_balance[quote] -= total_cost
                self.paper_balance[base] = self.paper_balance.get(base, Decimal('0')) + d_amount
                
                logger.info(f"📝 [PAPER] Compra: {d_amount} {base} @ {d_price} {quote} | Costo total: {total_cost} (Fee incluido)")
                self._save_paper_wallet()
            else:
                logger.error(f"❌ BALANCE INSUFICIENTE: Req {total_cost} {quote} vs Disp {available} {quote}")
                return {"error": "Balance insuficiente"}
        else:  # sell
            d_amount = safe_decimal(amount)
            d_price = safe_decimal(exec_price)
            
            available_asset = self.paper_balance.get(base, Decimal('0'))
            
            # Tolerancia para errores de redondeo (float vs decimal)
            if d_amount > available_asset and d_amount < available_asset * Decimal('1.01'):
                logger.warning(f"⚠️ Ajustando venta al balance disponible: {d_amount} -> {available_asset}")
                d_amount = available_asset

            if available_asset >= d_amount:
                self.paper_balance[base] -= d_amount
                
                revenue = (d_amount * d_price).quantize(MONEY_PRECISION, rounding=ROUND_DOWN)
                revenue_after_fee = (revenue * (Decimal('1') - FEE_RATE)).quantize(MONEY_PRECISION, rounding=ROUND_DOWN)
                
                self.paper_balance[quote] = self.paper_balance.get(quote, Decimal('0')) + revenue_after_fee
                logger.info(f"📝 [PAPER] Venta: {d_amount} {base} @ {d_price} {quote} | Recibido: {revenue_after_fee} (Fee descontado)")
                self._save_paper_wallet()
            else:
                logger.error(f"❌ BALANCE INSUFICIENTE: Req {d_amount} {base} vs Disp {available_asset} {base}")
                return {"error": "Balance insuficiente"}
        
        return {
            "id": f"paper_{int(time.time()*1000)}",
            "symbol": symbol,
            "side": side,
            "type": order_type,
            "amount": amount,
            "price": exec_price,
            "status": "closed",
            "paper": True,
        }
    
    def get_open_orders(self, symbol: Optional[str] = None) -> List[Dict]:
        """Obtiene las órdenes abiertas."""
        try:
            orders = self.exchange.fetch_open_orders(symbol)
            return orders
        except Exception as e:
            logger.error(f"Error obteniendo órdenes abiertas: {e}")
            return []
    
    def cancel_order(self, order_id: str, symbol: str) -> bool:
        """Cancela una orden."""
        try:
            self.exchange.cancel_order(order_id, symbol)
            logger.info(f"✅ Orden {order_id} cancelada")
            return True
        except Exception as e:
            logger.error(f"Error cancelando orden {order_id}: {e}")
            return False
    
    def get_min_order_amount(self, symbol: str) -> float:
        """Obtiene el mínimo de orden para un par."""
        try:
            market = self.exchange.market(symbol)
            return market["limits"]["amount"]["min"]
        except Exception as e:
            logger.error(f"Error obteniendo min order para {symbol}: {e}")
            return 0.0


# Singleton para usar en todo el proyecto
_exchange_manager: Optional[ExchangeManager] = None

def get_exchange() -> ExchangeManager:
    """Obtiene la instancia singleton del Exchange Manager."""
    global _exchange_manager
    if _exchange_manager is None:
        _exchange_manager = ExchangeManager()
    return _exchange_manager
