"""
Grid Trading Strategy
=====================
Estrategia de Grid Trading automatizada
Ideal para mercados laterales con alta volatilidad
"""

from decimal import Decimal, ROUND_DOWN
from typing import Dict, Any, Optional, List
from datetime import datetime
from loguru import logger
import sys

sys.path.insert(0, str(__file__).replace("\\src\\strategies\\grid_strategy.py", ""))

from src.strategies.base_strategy import BaseStrategy, StrategySignal
from config.settings import STRATEGIES, RISK_MANAGEMENT
from src.core.state_manager import get_state_manager

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


class GridTradingStrategy(BaseStrategy):
    """
    Estrategia Grid Trading.
    
    Funciona creando una "rejilla" de órdenes de compra y venta
    a intervalos regulares de precio. Cuando el precio baja,
    compra. Cuando sube, vende.
    
    Ejemplo con grid de 10 niveles y spacing 1%:
    - Compra a $99, vende a $100
    - Compra a $98, vende a $99
    - etc.
    """
    
    def __init__(self):
        config = STRATEGIES.get("grid_trading", {})
        super().__init__(
            name="Grid Trading",
            allocation_pct=config.get("allocation_pct", 0.30)
        )
        
        self.grid_levels = config.get("grid_levels", 10)
        self.grid_spacing_pct = config.get("grid_spacing_pct", 0.01)  # 1%
        self.min_volatility_atr = config.get("min_volatility_atr", 0.5)  # Mínimo ATR como % del precio
        
        # Estado de la grid por symbol
        self.grids: Dict[str, Dict] = {}
        self.active_orders: Dict[str, List[Dict]] = {}
        
        # State Manager para persistencia
        self.state_manager = get_state_manager()
        self._load_state()
        
        logger.info(f"✅ Estrategia Grid Trading iniciada - {self.grid_levels} niveles, {self.grid_spacing_pct*100}% spacing, min ATR: {self.min_volatility_atr}%")
    
    def _load_state(self) -> None:
        """Carga el estado guardado de las grids."""
        state = self.state_manager.load_strategy_state("grid_trading")
        if state:
            for symbol, grid_data in state.get("grids", {}).items():
                # Restaurar grid
                grid_data["created_at"] = datetime.fromisoformat(grid_data["created_at"])
                
                # Restaurar tiempos de compra en niveles
                for level in grid_data.get("levels", []):
                    if "buy_time" in level and level["buy_time"]:
                        try:
                            level["buy_time"] = datetime.fromisoformat(level["buy_time"])
                        except ValueError as e:
                            logger.debug(f"Error parsing buy_time for level: {e}")
                            level["buy_time"] = None
                
                self.grids[symbol] = grid_data
            
            logger.info(f"📂 Grid: Estado restaurado - {len(self.grids)} grids activas")
    
    def _save_state(self) -> None:
        """Guarda el estado actual de las grids."""
        grids_serializable = {}
        for symbol, grid in self.grids.items():
            grid_copy = grid.copy()
            grid_copy["created_at"] = grid["created_at"].isoformat()
            
            # Serializar niveles
            levels_copy = []
            for level in grid.get("levels", []):
                level_copy = level.copy()
                if "buy_time" in level_copy and level_copy["buy_time"]:
                    level_copy["buy_time"] = level_copy["buy_time"].isoformat()
                levels_copy.append(level_copy)
            grid_copy["levels"] = levels_copy
            
            grids_serializable[symbol] = grid_copy
        
        self.state_manager.save_strategy_state("grid_trading", {"grids": grids_serializable})
    
    def setup_grid(self, symbol: str, current_price: float, capital: float, high_24h: float = 0, low_24h: float = 0) -> Dict[str, Any]:
        """
        Configura una nueva grid para un par.
        """
        # Convertir a Decimal
        current_price_d = safe_decimal(current_price)
        capital_d = safe_decimal(capital)
        high_24h_d = safe_decimal(high_24h)
        low_24h_d = safe_decimal(low_24h)
        
        # Calcular rango dinámico
        if high_24h > 0 and low_24h > 0:
            upper_limit = high_24h_d * Decimal('1.02')  # +2% buffer
            lower_limit = low_24h_d * Decimal('0.98')   # -2% buffer
            grid_range = upper_limit - lower_limit
            spacing_amount = grid_range / safe_decimal(self.grid_levels, '1')
        else:
            # Fallback a porcentaje fijo si no hay datos
            spacing_amount = current_price_d * safe_decimal(self.grid_spacing_pct)
            upper_limit = current_price_d * (Decimal('1') + (safe_decimal(self.grid_spacing_pct) * safe_decimal(self.grid_levels)/Decimal('2')))
            lower_limit = current_price_d * (Decimal('1') - (safe_decimal(self.grid_spacing_pct) * safe_decimal(self.grid_levels)/Decimal('2')))

        # Calcular niveles de precio
        levels = []
        
        # Generar niveles desde abajo hacia arriba
        for i in range(self.grid_levels):
            # Precio base del nivel
            level_price = lower_limit + (spacing_amount * safe_decimal(i))
            buy_price = level_price
            sell_price = level_price + spacing_amount
            
            # Determinar si es un nivel por debajo o encima del precio actual
            # 0 es el nivel base
            level_index = i - (self.grid_levels // 2)
            
            levels.append({
                "level": level_index,
                "buy_price": float(round(buy_price, 2)), # Mantener float para persistencia JSON simple por ahora
                "sell_price": float(round(sell_price, 2)),
                "status": "pending",
                "amount": 0,
            })
        
        # Ordenar por nivel
        levels.sort(key=lambda x: x["level"])
        
        # Calcular tamaño de orden por nivel
        order_size_usd = capital_d / safe_decimal(self.grid_levels, '1')
        
        grid_config = {
            "symbol": symbol,
            "center_price": float(current_price_d),
            "levels": levels,
            "order_size_usd": float(order_size_usd),
            "created_at": datetime.now(),
            "total_trades": 0,
            "total_profit": 0,
        }
        
        self.grids[symbol] = grid_config
        self._save_state()  # Guardar estado
        logger.info(f"🔲 Grid configurada para {symbol} - Centro: ${current_price:.2f}, ${order_size_usd:.2f}/nivel")
        
        return grid_config
    
    def analyze(self, symbol: str, data: Dict[str, Any]) -> Dict[str, Any]:
        """Analiza el estado actual de la grid."""
        if symbol not in self.grids:
            return {"needs_setup": True}
        
        grid = self.grids[symbol]
        current_price = data.get("price", 0)
        
        # Encontrar niveles activos
        triggered_buys = []
        triggered_sells = []
        
        for level in grid["levels"]:
            if level["status"] == "pending" and current_price <= level["buy_price"]:
                triggered_buys.append(level)
            elif level["status"] == "bought" and current_price >= level["sell_price"]:
                triggered_sells.append(level)
        # Calcular P&L latente de la grid
        total_invested = Decimal('0')
        total_current_value = Decimal('0')
        
        # Función segura para convertir a Decimal
        def safe_decimal(value, default='0'):
            try:
                if value is None or value == '' or (isinstance(value, float) and str(value) == 'nan'):
                    return Decimal(default)
                return Decimal(str(value))
            except Exception:
                return Decimal(default)
        
        current_price_d = safe_decimal(current_price, '0')
        
        for level in grid["levels"]:
            if level["status"] == "bought":
                buy_price = safe_decimal(level.get("buy_executed_price", level.get("buy_price", 0)))
                amount = safe_decimal(level.get("amount", 0))
                if amount > Decimal('0') and buy_price > Decimal('0'):
                    total_invested += (buy_price * amount)
                    total_current_value += (current_price_d * amount)
        
        unrealized_pnl = total_current_value - total_invested
        unrealized_pnl_pct = (unrealized_pnl / total_invested * 100) if total_invested > Decimal('0') else Decimal('0')
        
        # STOP-LOSS DE EMERGENCIA: Si pérdida latente > 10%
        emergency_stop = unrealized_pnl_pct < Decimal('-10')
        if emergency_stop:
            logger.warning(f"🛑 GRID STOP-LOSS: {symbol} pérdida latente {unrealized_pnl_pct:.2f}% > -10%")
        
        return {
            "symbol": symbol,
            "current_price": current_price,
            "center_price": grid["center_price"],
            "triggered_buys": triggered_buys,
            "triggered_sells": triggered_sells,
            "grid_profit": grid["total_profit"],
            "grid_trades": grid["total_trades"],
            "unrealized_pnl": float(unrealized_pnl),
            "unrealized_pnl_pct": float(unrealized_pnl_pct),
            "emergency_stop": emergency_stop,
        }
    
    def should_enter(self, symbol: str, data: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        """Verifica si hay órdenes de compra por ejecutar."""
        analysis = self.analyze(symbol, data)
        
        if analysis.get("needs_setup"):
            return None
        
        # Filtro de Tendencia (EMA 50 > EMA 200) y Volatilidad
        # Solo comprar si estamos en tendencia alcista o lateral, evitar caídas libres
        ema_50 = safe_decimal(data.get("ema_50", 0))
        ema_200 = safe_decimal(data.get("ema_200", 0))
        price = safe_decimal(data.get("price", 0))
        atr = safe_decimal(data.get("atr", 0))
        
        if ema_50 > Decimal('0') and ema_200 > Decimal('0') and ema_50 < ema_200:
             # Permitir compras solo si el precio está muy por debajo (reboteoversold)
             # O si estamos muy cerca del soporte de la grid
             # Por ahora, ser conservadores:
             logger.debug(f"🔲 Grid {symbol} pausada: Tendencia BAJISTA (EMA 50 < EMA 200)")
             return None

        # Filtro de volatilidad: pausar si mercado muy quieto
        if price > 0 and atr > 0:
            atr_pct = (atr / price) * 100
            if atr_pct < self.min_volatility_atr:
                logger.debug(f"🔲 Grid {symbol} pausada: ATR {atr_pct:.2f}% < {self.min_volatility_atr}% (volatilidad insuficiente)")
                return None
        
        triggered_buys = analysis.get("triggered_buys", [])
        if not triggered_buys:
            return None
        
        # Tomar el nivel más bajo disponible
        level = min(triggered_buys, key=lambda x: x["buy_price"])
        
        return {
            "action": "buy",
            "symbol": symbol,
            "price": level["buy_price"],
            "level": level["level"],
            "reason": f"Grid nivel {level['level']} alcanzado"
        }
    
    def should_exit(self, symbol: str, position: Dict, data: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        """Verifica si hay órdenes de venta por ejecutar."""
        analysis = self.analyze(symbol, data)
        
        if analysis.get("needs_setup"):
            return None
        
        triggered_sells = analysis.get("triggered_sells", [])
        if not triggered_sells:
            return None
        
        # Tomar el nivel más alto disponible
        level = max(triggered_sells, key=lambda x: x["sell_price"])
        
        return {
            "action": "sell",
            "symbol": symbol,
            "price": level["sell_price"],
            "level": level["level"],
            "reason": f"Grid nivel {level['level']} take profit"
        }
    
    def execute_grid_buy(self, symbol: str, level_num: int, amount: float, price: float) -> None:
        """Registra una compra en un nivel de la grid."""
        if symbol not in self.grids:
            return
        
        # 1. Guardar en Base de Datos (Tabla positions)
        pos_id = self.state_manager.save_position(
            symbol=symbol,
            strategy="Grid Trading",
            entry_price=price,
            amount=amount,
            extra_data={"level": level_num}
        )
        
        for level in self.grids[symbol]["levels"]:
            if level["level"] == level_num:
                level["status"] = "bought"
                level["amount"] = amount
                level["buy_executed_price"] = price
                level["bought_amount"] = amount
                level["bought_price"] = price
                level["buy_time"] = datetime.now()
                level["pos_id"] = pos_id  # Guardar ID de DB para cerrar luego
                break
        
        self._save_state()  # Guardar estado
        
        # Guardar en historial (Solo log de evento de compra)
        self.state_manager.add_trade_to_history(
            symbol=symbol,
            strategy="Grid Trading",
            side="buy",
            price=price,
            amount=amount
        )
        
        logger.info(f"🔲 Grid {symbol} - Compra nivel {level_num}: {amount:.6f} @ ${price:.2f}")
    
    def execute_grid_sell(self, symbol: str, level_num: int, price: float) -> float:
        """Registra una venta en un nivel de la grid."""
        if symbol not in self.grids:
            return 0
        
        profit = Decimal('0')
        fee_paid = Decimal('0')
        for level in self.grids[symbol]["levels"]:
            if level["level"] == level_num and level["status"] == "bought":
                d_buy_price = safe_decimal(level.get("buy_executed_price", level["buy_price"]))
                d_amount = safe_decimal(level["amount"])
                d_price = safe_decimal(price)
                
                # Cálculo de PROFIT NETO usando Decimal
                gross_profit = ((d_price - d_buy_price) * d_amount).quantize(MONEY_PRECISION, rounding=ROUND_DOWN)
                
                # Comisiones: 0.1% entrada + 0.1% salida
                entry_fee = (d_buy_price * d_amount * FEE_RATE).quantize(MONEY_PRECISION, rounding=ROUND_DOWN)
                exit_fee = (d_price * d_amount * FEE_RATE).quantize(MONEY_PRECISION, rounding=ROUND_DOWN)
                fee_paid = entry_fee + exit_fee
                
                # Profit NETO = Bruto - Comisiones
                profit = gross_profit - fee_paid
                
                level["status"] = "pending"  # Reset para próximo ciclo
                level["amount"] = 0
                
                self.grids[symbol]["total_trades"] += 1
                self.grids[symbol]["total_profit"] = safe_decimal(self.grids[symbol].get("total_profit", 0)) + profit
                
                self._save_state()  # Guardar estado JSON
                
                # Cerrar posición en DB SQL (UPDATE positions SET status='closed')
                if "pos_id" in level:
                    self.state_manager.close_position(
                        position_id=level["pos_id"],
                        exit_price=float(d_price),
                        profit=float(profit),
                        fee_paid=float(fee_paid)
                    )
                    # Limpiar ID
                    del level["pos_id"]
                else:
                    # Fallback legado (Solo insertar history)
                    self.state_manager.add_trade_to_history(
                        symbol=symbol,
                        strategy="Grid Trading",
                        side="sell",
                        price=float(d_price),
                        amount=float(d_amount),
                        profit=float(profit),
                        entry_price=float(d_buy_price),
                        fee_paid=float(fee_paid)
                    )
                
                logger.info(f"🔲 Grid {symbol} - Venta nivel {level_num}: ${price:.2f} | Gross: ${gross_profit:.4f} | Fees: ${fee_paid:.4f} | NET: ${profit:.4f}")
                break
        
        return profit
    
    def recenter_grid(self, symbol: str, new_center: float) -> None:
        """
        Recentra la grid cuando el precio se mueve mucho.
        Útil cuando el precio sale del rango de la grid.
        """
        if symbol not in self.grids:
            return
        
        old_center = self.grids[symbol]["center_price"]
        capital = self.grids[symbol]["order_size_usd"] * self.grid_levels
        
        # Guardar stats antes de recentrar
        old_profit = self.grids[symbol]["total_profit"]
        old_trades = self.grids[symbol]["total_trades"]
        
        # Recrear grid con nuevo centro
        self.setup_grid(symbol, new_center, capital)
        
        # Restaurar stats
        self.grids[symbol]["total_profit"] = old_profit
        self.grids[symbol]["total_trades"] = old_trades
        
        logger.info(f"🔄 Grid {symbol} recentrada: ${old_center:.2f} -> ${new_center:.2f}")
    
    def intelligent_recenter_grid(self, symbol: str, current_price: float, 
                                   trend: str, data_manager=None) -> Dict[str, Any]:
        """
        Recentrado inteligente con filtros de seguridad.
        
        Reglas:
        1. Solo recentra si tendencia es 'uptrend' o 'sideways'
        2. Cooldown de 24h entre recentrados
        3. Solo recentra si precio > centro anterior * 1.05 (subió 5%+)
        4. Notifica antes de ejecutar
        
        Returns:
            Dict con status, action, reason
        """
        if symbol not in self.grids:
            return {"status": "skip", "reason": "Grid no configurada"}
        
        grid = self.grids[symbol]
        old_center = grid["center_price"]
        
        # Calcular niveles comprados
        bought_levels = len([l for l in grid["levels"] if l["status"] == "bought"])
        total_levels = len(grid["levels"])
        grid_full = bought_levels == total_levels
        grid_empty = bought_levels == 0
        
        # === REGLA 0 (NUEVA): NO recentrar si hay posiciones abiertas ===
        # Esto protege las posiciones existentes de ser "olvidadas"
        if bought_levels > 0:
            return {
                "status": "blocked",
                "reason": f"Grid tiene {bought_levels}/{total_levels} posiciones abiertas. Esperando ventas antes de recentrar.",
                "action": "wait_for_sells",
                "bought_levels": bought_levels,
                "total_levels": total_levels
            }
        
        # REGLA 1: Filtro de tendencia - NO recentrar en downtrend
        if trend in ["downtrend", "strong_downtrend"]:
            return {
                "status": "blocked",
                "reason": f"Tendencia bajista ({trend}). Recentrado bloqueado para proteger capital.",
                "action": "wait"
            }
        
        # REGLA 2: Cooldown de 24h
        last_recenter = grid.get("last_recenter")
        if last_recenter:
            from datetime import datetime, timedelta
            if datetime.now() - last_recenter < timedelta(hours=24):
                hours_left = 24 - (datetime.now() - last_recenter).total_seconds() / 3600
                return {
                    "status": "cooldown",
                    "reason": f"Cooldown activo. Próximo recentrado en {hours_left:.1f}h",
                    "action": "wait"
                }
        
        # REGLA 3: Solo recentrar hacia ARRIBA si el precio subió significativamente
        price_change_pct = (current_price - old_center) / old_center
        
        if price_change_pct > 0.05:  # Subió más de 5%
            # Recentrar hacia arriba (trailing bullish)
            new_center = current_price
            self.recenter_grid(symbol, new_center)
            grid["last_recenter"] = datetime.now()
            self._save_state()
            
            return {
                "status": "executed",
                "reason": f"Precio subió +{price_change_pct*100:.1f}%. Grid recentrada hacia arriba.",
                "action": "recenter_up",
                "old_center": old_center,
                "new_center": new_center,
                "change_pct": price_change_pct * 100
            }
        
        # Si el precio bajó mucho y la grid está llena, solo notificar (no recentrar)
        if price_change_pct < -0.10 and grid_full:
            return {
                "status": "alert",
                "reason": f"⚠️ Grid llena y precio -{abs(price_change_pct)*100:.1f}% del centro. Esperando recuperación.",
                "action": "wait_recovery",
                "bought_levels": bought_levels,
                "total_levels": total_levels
            }
        
        # Estado normal - no requiere acción
        return {
            "status": "ok",
            "reason": "Grid operando normalmente",
            "action": "none"
        }
    
    def get_grid_status(self, symbol: str) -> Dict[str, Any]:
        """Obtiene el estado detallado de una grid."""
        if symbol not in self.grids:
            return {"error": "Grid no configurada"}
        
        grid = self.grids[symbol]
        bought_levels = [l for l in grid["levels"] if l["status"] == "bought"]
        pending_levels = [l for l in grid["levels"] if l["status"] == "pending"]
        
        return {
            "symbol": symbol,
            "center_price": grid["center_price"],
            "total_levels": len(grid["levels"]),
            "bought_levels": len(bought_levels),
            "pending_levels": len(pending_levels),
            "order_size_usd": grid["order_size_usd"],
            "total_trades": grid["total_trades"],
            "total_profit": grid["total_profit"],
            "created_at": grid["created_at"].isoformat(),
        }
