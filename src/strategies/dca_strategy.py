"""
DCA Intelligent Strategy
=========================
Dollar Cost Averaging con compras inteligentes en caídas
Ideal para acumulación a largo plazo con aportes mensuales
"""

from decimal import Decimal, ROUND_DOWN
from typing import Dict, Any, Optional
from datetime import datetime, timedelta
from loguru import logger
import sys

sys.path.insert(0, str(__file__).replace("\\src\\strategies\\dca_strategy.py", ""))

from src.strategies.base_strategy import BaseStrategy, StrategySignal
from config.settings import STRATEGIES, RISK_MANAGEMENT
from src.core.state_manager import get_state_manager
from src.risk.risk_manager import get_risk_manager

# Precisión financiera
MONEY_PRECISION = Decimal('0.00000001')
FEE_RATE = Decimal('0.001')  # 0.1%


def safe_decimal(value, default='0') -> Decimal:
    """Convierte un valor a Decimal de forma segura, evitando InvalidOperation."""
    try:
        if value is None or value == '':
            return Decimal(default)
        # Verificar si es float NaN
        if isinstance(value, float):
            import math
            if math.isnan(value) or math.isinf(value):
                return Decimal(default)
        return Decimal(str(value))
    except Exception:
        return Decimal(default)


class DCAIntelligentStrategy(BaseStrategy):
    """
    Estrategia DCA Inteligente.
    
    - Compra regular cada X horas/días
    - Compra extra cuando hay caídas significativas
    - Vende parcialmente en subidas extremas
    - Ideal para acumulación con aportes mensuales recurrentes
    """
    
    def __init__(self):
        config = STRATEGIES.get("dca_intelligent", {})
        super().__init__(
            name="DCA Intelligent",
            allocation_pct=config.get("allocation_pct", 0.40)
        )
        
        self.buy_interval_hours = config.get("buy_interval_hours", 24)
        self.dip_threshold_pct = safe_decimal(config.get("dip_threshold_pct", 0.05), '0.05')
        self.last_buy_time: Dict[str, datetime] = {}
        self.entry_prices: Dict[str, Decimal] = {}  # Decimal para precisión
        self.accumulated: Dict[str, Decimal] = {}   # Decimal para precisión
        
        # Para DCA inteligente
        self.price_history: Dict[str, list] = {}
        self.dip_multiplier = Decimal('2.0')
        
        # State Manager para persistencia
        self.state_manager = get_state_manager()
        self.risk_manager = get_risk_manager()
        self._load_state()
        
        logger.info(f"✅ Estrategia DCA Inteligente iniciada - Intervalo: {self.buy_interval_hours}h")
    
    def _get_db_pos_id(self, symbol: str) -> Optional[int]:
        """Busca el ID de la posición SQL para un símbolo."""
        positions = self.state_manager.get_open_positions("DCA Intelligent")
        # Filter for actual SQL positions (sanity check if source key exists)
        for pos in positions:
            if pos["symbol"] == symbol and pos.get("source") != "strategy_state": 
                 # 'source' es añadido por get_open_positions para las JSON. Las SQL no tienen o es diferente.
                 # Revisando state_manager:215 (JSON) añade status='open' y source='strategy_state' o similar.
                 # Las SQL vienen directo de DB.
                 # En get_open_positions (Step 1962), las JSON tienen 'source'. Las SQL NO (line 158).
                 if "id" in pos:
                     return pos["id"]
        return None
    
    def _load_state(self) -> None:
        """Carga el estado guardado con conversión a Decimal."""
        state = self.state_manager.load_strategy_state("dca_intelligent")
        if state:
            # Restaurar tiempos de última compra
            for symbol, time_str in state.get("last_buy_time", {}).items():
                try:
                    self.last_buy_time[symbol] = datetime.fromisoformat(time_str)
                except ValueError as e:
                    logger.warning(f"Error parsing buy_time for {symbol}: {e}")
            
            # Restaurar precios de entrada (convertir a Decimal)
            for symbol, price in state.get("entry_prices", {}).items():
                self.entry_prices[symbol] = safe_decimal(price)
            
            # Restaurar acumulados (convertir a Decimal)
            for symbol, amount in state.get("accumulated", {}).items():
                self.accumulated[symbol] = safe_decimal(amount)
            
            # Restaurar historial de precios
            self.price_history = state.get("price_history", {})
            
            logger.info(f"📂 DCA: Estado restaurado - {len(self.accumulated)} posiciones")
    
    def _save_state(self) -> None:
        """Guarda el estado actual (convierte Decimal a float para JSON)."""
        state = {
            "last_buy_time": {k: v.isoformat() for k, v in self.last_buy_time.items()},
            "entry_prices": {k: float(v) for k, v in self.entry_prices.items()},
            "accumulated": {k: float(v) for k, v in self.accumulated.items()},
            "price_history": self.price_history
        }
        self.state_manager.save_strategy_state("dca_intelligent", state)
    
    def analyze(self, symbol: str, data: Dict[str, Any]) -> Dict[str, Any]:
        """Analiza si es momento de hacer DCA."""
        # Convertir datos de mercado a Decimal
        current_price = safe_decimal(data.get("price", 0))
        rsi = safe_decimal(data.get("rsi", 50), '50')
        
        trend = data.get("trend", "sideways")
        
        # Guardar historial de precios
        if symbol not in self.price_history:
            self.price_history[symbol] = []
        self.price_history[symbol].append(float(current_price)) # Guardar como float en historial simple
        
        # Mantener solo últimos 30 días de precios (720 horas / intervalo)
        max_history = int(720 / self.buy_interval_hours)
        if len(self.price_history[symbol]) > max_history:
            self.price_history[symbol] = self.price_history[symbol][-max_history:]
        
        # Calcular precio promedio y detectar caídas (Usando floats para historial simple)
        avg_price_float = sum(self.price_history[symbol]) / len(self.price_history[symbol])
        avg_price = safe_decimal(avg_price_float)
        
        price_vs_avg = (current_price - avg_price) / avg_price
        
        # Verificar si es hora de comprar
        can_buy = self._can_buy_now(symbol)
        
        # Detectar oportunidad de compra en caída
        is_dip = price_vs_avg < -self.dip_threshold_pct
        is_strong_dip = price_vs_avg < -(self.dip_threshold_pct * Decimal('2'))
        
        return {
            "symbol": symbol,
            "current_price": float(current_price),
            "avg_price": float(avg_price),
            "price_vs_avg_pct": float(price_vs_avg * 100),
            "rsi": float(rsi),
            "trend": trend,
            "can_buy": can_buy,
            "is_dip": is_dip,
            "is_strong_dip": is_strong_dip,
            "accumulated": self.accumulated.get(symbol, 0),
            "total_invested": self.accumulated.get(symbol, Decimal('0')) * (self.entry_prices.get(symbol, current_price)),
        }
    
    def _can_buy_now(self, symbol: str) -> bool:
        """Verifica si ha pasado suficiente tiempo desde la última compra."""
        if symbol not in self.last_buy_time:
            return True
        
        elapsed = datetime.now() - self.last_buy_time[symbol]
        return elapsed >= timedelta(hours=self.buy_interval_hours)
    
    def should_enter(self, symbol: str, data: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        """
        Determina si debemos comprar ahora.
        
        Condiciones para compra:
        1. Ha pasado el intervalo de tiempo definido
        2. O hay una caída significativa (compra extra)
        """
        analysis = self.analyze(symbol, data)
        
        if not analysis["can_buy"] and not analysis["is_dip"]:
            return None
        
        current_price = data.get("price", 0)
        rsi = data.get("rsi", 50)
        
        # Calcular multiplicador de compra
        buy_multiplier = 1.0
        reason = "DCA regular"
        
        if analysis["is_strong_dip"]:
            buy_multiplier = self.dip_multiplier * Decimal('1.5')
            reason = f"Caída fuerte detectada ({analysis['price_vs_avg_pct']:.1f}%)"
        elif analysis["is_dip"]:
            buy_multiplier = self.dip_multiplier
            reason = f"Caída detectada ({analysis['price_vs_avg_pct']:.1f}%)"
        elif rsi < 35:
            buy_multiplier = Decimal('1.5')
            reason = f"RSI bajo ({rsi:.0f})"
        
        return {
            "action": "buy",
            "symbol": symbol,
            "price": current_price,
            "multiplier": buy_multiplier,
            "reason": reason,
            "is_dip_buy": analysis["is_dip"],
        }
    
    def should_exit(self, symbol: str, position: Dict, data: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        """
        En DCA, vendemos parcialmente solo en condiciones extremas.
        
        Condiciones de venta:
        1. Ganancia > 50% y RSI > 80 (extremadamente sobrecomprado)
        2. O take profit definido alcanzado
        """
        if symbol not in self.entry_prices or self.accumulated.get(symbol, 0) == 0:
            return None
        
        current_price = safe_decimal(data.get("price", 0))
        entry_price = self.entry_prices[symbol]  # Ya es Decimal
        rsi = data.get("rsi", 50)
        
        # Cálculo seguro con Decimal
        if entry_price > Decimal('0'):
            profit_pct = (current_price - entry_price) / entry_price
        else:
            profit_pct = Decimal('0')
        
        # Vender 25% si ganancia > 50% y RSI muy alto
        if profit_pct > 0.50 and rsi > 80:
            return {
                "action": "sell",
                "symbol": symbol,
                "sell_pct": 0.25,  # Vender solo 25%
                "price": current_price,
                "profit_pct": profit_pct * 100,
                "reason": f"Take profit parcial: +{profit_pct*100:.1f}%, RSI={rsi:.0f}"
            }
        
        # Vender 50% si ganancia > 100% (duplicó)
        if profit_pct > 1.0:
            return {
                "action": "sell",
                "symbol": symbol,
                "sell_pct": 0.50,  # Vender 50%
                "price": current_price,
                "profit_pct": profit_pct * 100,
                "reason": f"Objetivo alcanzado: +{profit_pct*100:.1f}%"
            }
        
        return None
    
    def execute_buy(self, symbol: str, amount: float, price: float) -> None:
        """Registra una compra DCA usando Decimal."""
        d_amount = safe_decimal(amount)
        d_price = safe_decimal(price)
        
        # Actualizar precio promedio de entrada
        current_accumulated = self.accumulated.get(symbol, Decimal('0'))
        current_entry = self.entry_prices.get(symbol, d_price)
        
        # Calcular nuevo precio promedio ponderado con Decimal
        total_value = (current_accumulated * current_entry) + (d_amount * d_price)
        new_accumulated = current_accumulated + d_amount
        
        if new_accumulated > Decimal('0'):
            self.entry_prices[symbol] = (total_value / new_accumulated).quantize(MONEY_PRECISION, rounding=ROUND_DOWN)
        
        self.accumulated[symbol] = new_accumulated
        self.last_buy_time[symbol] = datetime.now()
        
        # --- PERSISTENCIA SQL START ---
        # Buscar si ya existe posición abierta en DB
        pos_id = self._get_db_pos_id(symbol)
        
        # IMPORTANTE: SQLite no soporta Decimal, convertir a float
        db_amount = float(new_accumulated)
        db_entry_price = float(self.entry_prices[symbol])
        
        if pos_id:
            # UPDATE: Actualizar cantidad y precio promedio
            self.state_manager.update_position(
                position_id=pos_id,
                amount=db_amount,
                entry_price=db_entry_price,
                extra_data={"last_buy": datetime.now().isoformat()}
            )
        else:
            # INSERT: Crear nueva posición
            self.state_manager.save_position(
                symbol=symbol,
                strategy="DCA Intelligent",
                entry_price=price,
                amount=amount,
                extra_data={"last_buy": datetime.now().isoformat()}
            )
        # --- PERSISTENCIA SQL END ---
        
        # Guardar estado JSON (Backup)
        self._save_state()
        
        # Guardar en historial
        self.state_manager.add_trade_to_history(
            symbol=symbol,
            strategy="DCA Intelligent",
            side="buy",
            price=price,
            amount=amount
        )
        
        logger.info(f"📈 DCA {symbol}: Compra {amount:.6f} @ ${price:.2f}")
        logger.info(f"   Acumulado: {new_accumulated:.6f} | Precio promedio: ${self.entry_prices[symbol]:.2f}")
    
    def execute_sell(self, symbol: str, sell_pct: float, price: float) -> float:
        """Registra una venta parcial DCA usando Decimal."""
        if symbol not in self.accumulated or self.accumulated[symbol] == Decimal('0'):
            return 0.0
        
        # Convertir inputs a Decimal
        d_sell_pct = safe_decimal(sell_pct)
        d_price = safe_decimal(price)
        
        # Calcular cantidad a vender
        sell_amount = (self.accumulated[symbol] * d_sell_pct).quantize(MONEY_PRECISION, rounding=ROUND_DOWN)
        self.accumulated[symbol] -= sell_amount
        
        # Obtener precio promedio en Decimal
        avg_price = self.entry_prices.get(symbol, d_price)
        amount = sell_amount 
        
        # Calcular profit NETO (restando comisiones)
        gross_profit = (d_price - avg_price) * amount
        
        # Comisiones: 0.1% entrada (ya pagada, pero se resta aquí para PnL) + 0.1% salida
        entry_fee = (avg_price * amount * FEE_RATE).quantize(MONEY_PRECISION, rounding=ROUND_DOWN)
        exit_fee = (d_price * amount * FEE_RATE).quantize(MONEY_PRECISION, rounding=ROUND_DOWN)
        fee_paid = entry_fee + exit_fee
        
        net_profit = gross_profit - fee_paid
        profit = net_profit # Alias para evitar NameError
        
        # Avoid division by zero if avg_price * amount is 0
        invested = avg_price * amount
        profit_pct = (net_profit / invested) * 100 if invested != Decimal('0') else Decimal('0')
        
        # Update strategy-level statistics (assuming self.state exists and is initialized)
        if not hasattr(self, 'state'):
            self.state = {"total_profit": 0, "trades_count": 0, "winning_trades": 0, "losing_trades": 0}
        
        # Importante: state usa floats para compatibilidad JSON
        self.state["total_profit"] = float(safe_decimal(self.state.get("total_profit", 0)) + net_profit)
        self.state["trades_count"] += 1
        
        if net_profit > Decimal('0'):
            self.state["winning_trades"] += 1
        else:
            self.state["losing_trades"] += 1
        
        # Record trade in internal history (if self.record_trade is still desired)
        self.record_trade({
            "symbol": symbol,
            "action": "sell",
            "amount": float(amount),
            "entry_price": float(avg_price),
            "exit_price": float(d_price),
            "profit": float(net_profit),
            "timestamp": datetime.now().isoformat(),
            "fee_paid": float(fee_paid),
            "profit_pct": float(profit_pct)
        })
        
        # Guardar estado JSON
        self._save_state()
        
        # --- PERSISTENCIA SQL START ---
        pos_id = self._get_db_pos_id(symbol)
        remaining_amount = self.accumulated.get(symbol, 0)
        
        if pos_id:
            if remaining_amount <= 0.000001: # Epsilon
                # Cierre Total
                self.state_manager.close_position(
                    position_id=pos_id,
                    exit_price=price,
                    profit=net_profit, # Nota: Esto asume que el profit pasado es del trade total, pero aqui es parcial.
                    # En close_position de StateManager, profit se guarda en history.
                    # Pero si cierro la posición, el history se genera.
                    # WAIT: Close position generates history for the OPEN amount? No, close_position reads 'amount' from DB.
                    # If I updated amount incrementally, the DB amount is the REMAINING amount.
                    # This logic is tricky for partial sells.
                    
                    # CORRECCIÓN: Para ventas parciales, NO uso close_position excepto al final.
                    # Siempre inserto HISTORIAL de la venta parcial.
                    # Y actualizo AMOUNT en DB.
                    fee_paid=fee_paid
                )
            else:
                # Venta Parcial: Actualizar DB y añadir historial manual
                self.state_manager.update_position(
                    position_id=pos_id,
                    amount=remaining_amount
                )
                # Registrar el trade parcial en history
                self.state_manager.add_trade_to_history(
                    symbol=symbol,
                    strategy="DCA Intelligent",
                    side="sell",
                    entry_price=float(avg_price),
                    price=float(d_price),
                    amount=float(amount),
                    profit=float(net_profit),
                    profit_pct=float(profit_pct),
                    fee_paid=float(fee_paid)
                )
        else:
            # Fallback legacy (No hay ID BD)
            self.state_manager.add_trade_to_history(
                symbol=symbol,
                strategy="DCA Intelligent",
                side="sell",
                price=float(d_price),
                amount=float(amount),
                profit=float(net_profit),
                profit_pct=float(profit_pct),
                entry_price=float(avg_price),
                fee_paid=float(fee_paid)
            )
        # --- PERSISTENCIA SQL END ---
        
        logger.info(f"📉 DCA {symbol}: Venta {sell_amount:.6f} @ ${price:.2f} | Profit: ${net_profit:.2f} ({profit_pct:.2f}%)")
        
        return sell_amount
    
    def get_dca_schedule(self) -> Dict[str, Any]:
        """Retorna el horario de próximas compras DCA."""
        schedule = {}
        for symbol in self.last_buy_time:
            next_buy = self.last_buy_time[symbol] + timedelta(hours=self.buy_interval_hours)
            schedule[symbol] = {
                "last_buy": self.last_buy_time[symbol].isoformat(),
                "next_buy": next_buy.isoformat(),
                "hours_remaining": max(0, (next_buy - datetime.now()).total_seconds() / 3600)
            }
        return schedule
