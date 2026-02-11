"""
Technical Analysis Strategy
============================
Estrategia basada en indicadores técnicos (RSI, MACD, Bollinger Bands)
"""

from typing import Dict, Any, Optional
from datetime import datetime
from loguru import logger
from decimal import Decimal
import sys

sys.path.insert(0, str(__file__).replace("\\src\\strategies\\technical_strategy.py", ""))

from src.strategies.base_strategy import BaseStrategy, StrategySignal
from config.settings import STRATEGIES, RISK_MANAGEMENT
from src.core.state_manager import get_state_manager
from src.risk.risk_manager import get_risk_manager


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


class TechnicalStrategy(BaseStrategy):
    """
    Estrategia basada en análisis técnico.
    
    Utiliza una combinación de indicadores:
    - RSI para detectar sobrecompra/sobreventa
    - MACD para confirmar tendencia
    - Bollinger Bands para detectar volatilidad
    - EMAs para confirmar dirección
    """
    
    def __init__(self):
        config = STRATEGIES.get("technical_rsi_macd", {})
        super().__init__(
            name="Technical RSI+MACD",
            allocation_pct=config.get("allocation_pct", 0.30)
        )
        
        # Parámetros RSI
        self.rsi_oversold = config.get("rsi_oversold", 30)
        self.rsi_overbought = config.get("rsi_overbought", 70)
        
        # Parámetros MACD
        self.macd_signal_threshold = config.get("macd_signal_threshold", 0)
        
        # Estado de posiciones
        self.positions: Dict[str, Dict] = {}
        
        # Señales previas para confirmar
        self.pending_signals: Dict[str, Dict] = {}
        
        # State Manager para persistencia
        self.state_manager = get_state_manager()
        self.risk_manager = get_risk_manager()
        self._load_state()
        
        logger.info(f"✅ Estrategia Técnica iniciada - RSI: {self.rsi_oversold}/{self.rsi_overbought}")
    
    def _load_state(self) -> None:
        """Carga el estado guardado."""
        state = self.state_manager.load_strategy_state("technical_rsi_macd")
        if state:
            for symbol, pos_data in state.get("positions", {}).items():
                pos_data["opened_at"] = datetime.fromisoformat(pos_data["opened_at"])
                self.positions[symbol] = pos_data
            
            if self.positions:
                logger.info(f"📂 Technical: Estado restaurado - {len(self.positions)} posiciones abiertas")
    
    def _save_state(self) -> None:
        """Guarda el estado actual."""
        positions_serializable = {}
        for symbol, pos in self.positions.items():
            pos_copy = pos.copy()
            pos_copy["opened_at"] = pos["opened_at"].isoformat()
            positions_serializable[symbol] = pos_copy
        
        self.state_manager.save_strategy_state("technical_rsi_macd", {
            "positions": positions_serializable
        })
    
    def analyze(self, symbol: str, data: Dict[str, Any]) -> Dict[str, Any]:
        """
        Analiza el mercado usando múltiples indicadores.
        
        Retorna un puntaje de -10 a +10:
        - Positivo = señal de compra
        - Negativo = señal de venta
        - Cerca de 0 = sin señal clara
        """
        score = Decimal('0')
        reasons = []
        
        # Datos necesarios - convertir a float de forma segura
        def safe_decimal(value, default="0"):
            try:
                if value is None or (isinstance(value, float) and str(value) == 'nan'):
                    return Decimal(default)
                return Decimal(str(value))
            except (ValueError, TypeError, Exception):
                return Decimal(default)
        
        rsi = safe_decimal(data.get("rsi"), "50")
        macd = safe_decimal(data.get("macd"), "0")
        macd_signal = safe_decimal(data.get("macd_signal"), "0")
        macd_hist = safe_decimal(data.get("macd_hist"), "0")
        bb_position = data.get("bb_position", "middle")
        trend = data.get("trend", "sideways")
        price = safe_decimal(data.get("price"), "0")
        
        # === Análisis RSI ===
        if rsi < self.rsi_oversold:
            if rsi < 25:
                score += Decimal('3')
                reasons.append(f"RSI muy bajo ({rsi:.0f})")
            else:
                score += Decimal('2')
                reasons.append(f"RSI oversold ({rsi:.0f})")
        elif rsi > self.rsi_overbought:
            if rsi > 75:
                score -= Decimal('3')
                reasons.append(f"RSI muy alto ({rsi:.0f})")
            else:
                score -= Decimal('2')
                reasons.append(f"RSI overbought ({rsi:.0f})")
        
        # === Análisis MACD ===
        prev_macd_hist = safe_decimal(data.get("prev_macd_hist"), "0")
        if macd > macd_signal:
            if macd_hist > 0 and prev_macd_hist <= 0:
                score += Decimal('3')
                reasons.append("MACD cruce alcista")
            else:
                score += Decimal('1')
                reasons.append("MACD positivo")
        elif macd < macd_signal:
            if macd_hist < 0 and prev_macd_hist >= 0:
                score -= Decimal('3')
                reasons.append("MACD cruce bajista")
            else:
                score -= Decimal('1')
                reasons.append("MACD negativo")
        
        # === Análisis Bollinger Bands ===
        if bb_position == "oversold":
            score += Decimal('2')
            reasons.append("Precio en BB inferior")
        elif bb_position == "overbought":
            score -= Decimal('2')
            reasons.append("Precio en BB superior")
        
        # === Análisis de Tendencia ===
        if trend == "strong_uptrend":
            score += Decimal('1')
            reasons.append("Tendencia alcista fuerte")
        elif trend == "uptrend":
            score += Decimal('0.5')
        elif trend == "strong_downtrend":
            score -= Decimal('1')
            reasons.append("Tendencia bajista fuerte")
        elif trend == "downtrend":
            score -= Decimal('0.5')
        
        # Determinar señal final
        if score >= Decimal('4'):
            signal = "strong_buy"
        elif score >= Decimal('2'):
            signal = "buy"
        elif score <= Decimal('-4'):
            signal = "strong_sell"
        elif score <= Decimal('-2'):
            signal = "sell"
        else:
            signal = "hold"
        
        return {
            "symbol": symbol,
            "price": price,
            "score": score,
            "signal": signal,
            "reasons": reasons,
            "indicators": {
                "rsi": rsi,
                "macd": macd,
                "macd_signal": macd_signal,
                "bb_position": bb_position,
                "trend": trend,
            }
        }
    
    def should_enter(self, symbol: str, data: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        """
        Determina si debemos entrar en una posición.
        
        Requiere confirmación: la señal debe mantenerse por 2 períodos.
        """
        analysis = self.analyze(symbol, data)
        
        # Ya tenemos posición?
        if symbol in self.positions:
            return None
        
        signal = analysis["signal"]
        
        # Señales de compra
        if signal in ["buy", "strong_buy"]:
            # Verificar confirmación
            if symbol in self.pending_signals:
                prev_signal = self.pending_signals[symbol]
                if prev_signal["signal"] in ["buy", "strong_buy"]:
                    # Señal confirmada!
                    del self.pending_signals[symbol]
                    
                    price_d = safe_decimal(analysis["price"])
                    
                    # Filtro de Tendencia: No entrar si EMA 50 < EMA 200 (tendencia bajista)
                    ema_50 = safe_decimal(data.get("ema_50", 0))
                    ema_200 = safe_decimal(data.get("ema_200", 0))
                    if ema_50 > 0 and ema_200 > 0 and ema_50 < ema_200:
                        logger.info(f"🚫 Señal ignorada: {symbol} - EMA50 < EMA200 (cruce bajista)")
                        return None
                    
                    # Filtro de Tendencia Macro (precio debajo de EMA 200)
                    if ema_200 > 0 and price_d < ema_200:
                        logger.info(f"🚫 Señal ignorada: {symbol} debajo de EMA 200 (Tendencia bajista macro)")
                        return None
                    
                    # Gestión de Riesgo Dinámica (ATR)
                    atr = safe_decimal(data.get("atr", 0))
                    if atr > 0 and (atr / price_d) > Decimal('0.005'):  # ATR > 0.5% del precio
                        # Usar ATR dinámico
                        stop_loss = price_d - (atr * Decimal('2.0'))
                        take_profit = price_d + (atr * Decimal('4.0'))
                        risk_reason = f"ATR Dynamic (SL: -{((price_d-stop_loss)/price_d)*100:.1f}%)"
                    else:
                        # Fallback a porcentaje fijo si no hay ATR suficiente
                        sl_pct_d = safe_decimal(RISK_MANAGEMENT["default_stop_loss_pct"])
                        tp_pct_d = safe_decimal(RISK_MANAGEMENT["default_take_profit_pct"])
                        
                        stop_loss = price_d * (Decimal('1') - sl_pct_d)
                        take_profit = price_d * (Decimal('1') + tp_pct_d)
                        risk_reason = "Fixed Risk"
                    
                    # Asegurar ratio mínimo 1:1.5
                    risk = price_d - stop_loss
                    reward = take_profit - price_d
                    if risk > 0 and (reward / risk) < Decimal('1.5'):
                         take_profit = price_d + (risk * Decimal('1.5'))
                    
                    return {
                        "action": "buy",
                        "symbol": symbol,
                        "price": float(price_d), # Return float for compatibility with main loop execution but calculated with Decimal
                        "score": analysis["score"],
                        "stop_loss": float(stop_loss),
                        "take_profit": float(take_profit),
                        "reason": " + ".join(analysis["reasons"]),
                    }
            
            # Guardar señal pendiente para confirmación
            self.pending_signals[symbol] = {
                "signal": signal,
                "score": analysis["score"],
                "timestamp": datetime.now(),
            }
        else:
            # Limpiar señal pendiente si no se mantiene
            if symbol in self.pending_signals:
                del self.pending_signals[symbol]
        
        return None
    
    def should_exit(self, symbol: str, position: Dict, data: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        """
        Determina si debemos salir de una posición.
        
        Condiciones de salida:
        1. Stop loss alcanzado
        2. Take profit alcanzado
        3. Señal de venta confirmada
        """
        if symbol not in self.positions:
            return None
        
        pos = self.positions[symbol]
        analysis = self.analyze(symbol, data)
        current_price = analysis["price"]
        entry_price = pos["entry_price"]
        
        # Calcular profit/loss actual
        pnl_pct = (current_price - entry_price) / entry_price
        
        # Check stop loss
        if current_price <= pos.get("stop_loss", 0):
            return {
                "action": "sell",
                "symbol": symbol,
                "price": current_price,
                "reason": f"Stop loss alcanzado ({pnl_pct*100:.1f}%)",
                "pnl_pct": pnl_pct * 100,
            }
        
        # Check take profit
        if current_price >= pos.get("take_profit", float("inf")):
            return {
                "action": "sell",
                "symbol": symbol,
                "price": current_price,
                "reason": f"Take profit alcanzado ({pnl_pct*100:.1f}%)",
                "pnl_pct": pnl_pct * 100,
            }
        
        # Check señal de venta
        if analysis["signal"] in ["sell", "strong_sell"] and analysis["score"] <= -4:
            return {
                "action": "sell",
                "symbol": symbol,
                "price": current_price,
                "reason": f"Señal técnica de venta: {' + '.join(analysis['reasons'])}",
                "pnl_pct": pnl_pct * 100,
            }
        
        # Trailing stop mejorado con high watermark
        # Solo activar si hay al menos 2% de ganancia
        if pnl_pct > 0.02:
            # Obtener o inicializar high watermark
            if "high_watermark" not in pos:
                pos["high_watermark"] = entry_price
            
            # Actualizar high watermark si el precio actual es mayor
            if current_price > pos["high_watermark"]:
                pos["high_watermark"] = current_price
                logger.debug(f"📈 {symbol} nuevo high watermark: ${current_price:.2f}")
            
            # Calcular trailing stop desde el high watermark
            trailing_pct = RISK_MANAGEMENT.get("trailing_stop_pct", 0.02)
            new_stop = pos["high_watermark"] * (1 - trailing_pct)
            
            # Solo subir el stop, nunca bajarlo
            if new_stop > pos.get("stop_loss", 0):
                old_stop = pos.get("stop_loss", 0)
                pos["stop_loss"] = new_stop
                profit_protected = ((new_stop - entry_price) / entry_price) * 100
                logger.info(f"🎯 {symbol} TRAILING STOP: ${old_stop:.2f} → ${new_stop:.2f} (Protege +{profit_protected:.1f}%)")
            
            # Verificar si el trailing stop fue activado
            if current_price <= pos.get("stop_loss", 0):
                return {
                    "action": "sell",
                    "symbol": symbol,
                    "price": current_price,
                    "reason": f"Trailing stop activado (protegió +{((pos['stop_loss'] - entry_price) / entry_price * 100):.1f}%)",
                    "pnl_pct": pnl_pct * 100,
                }
        
        return None
    
    
    def open_position(
        self,
        symbol: str,
        amount: float,
        price: float,
        stop_loss: float,
        take_profit: float
    ) -> None:
        # Usar Decimal para persistencia precisa y cálculos internos
        d_amount = safe_decimal(amount)
        d_price = safe_decimal(price)
        
        # 1. Guardar en Base de Datos (Tabla positions)
        pos_id = self.state_manager.save_position(
            symbol=symbol,
            strategy="Technical RSI+MACD",
            entry_price=price,
            amount=amount,
            stop_loss=stop_loss,
            take_profit=take_profit
        )

        # 2. Guardar en estado local (JSON)
        # Nota: almacenamos como floats en JSON para facilidad, pero calculamos con Decimal
        self.positions[symbol] = {
            "id": pos_id,  # Importante: Guardar ID para cierre
            "amount": amount,
            "entry_price": price,
            "stop_loss": stop_loss,
            "take_profit": take_profit,
            "opened_at": datetime.now(),
        }
        
        self._save_state()  # Guardar estado JSON
        
        # 3. Guardar evento de Compra en Historial
        self.state_manager.add_trade_to_history(
            symbol=symbol,
            strategy="Technical RSI+MACD",
            side="buy",
            price=price,
            amount=amount
        )
        
        logger.info(f"📈 Posición abierta {symbol}: {amount:.6f} @ ${price:.2f}")
        logger.info(f"   SL: ${stop_loss:.2f} | TP: ${take_profit:.2f}")
    
    def close_position(self, symbol: str, price: float) -> float:
        """Cierra una posición y retorna el profit."""
        if symbol not in self.positions:
            return 0.0
        
        pos = self.positions[symbol]
        
        # Usar Decimal para todos los cálculos financieros
        d_price = safe_decimal(price)
        d_entry_price = safe_decimal(pos["entry_price"])
        d_amount = safe_decimal(pos["amount"])
        
        # Calcular profit NETO (restando comisiones)
        # Precisión de 8 decimales
        gross_profit = ((d_price - d_entry_price) * d_amount).quantize(Decimal('0.00000001'))
        
        # Comisiones: 0.1% entrada + 0.1% salida
        fee_rate = Decimal('0.001')
        entry_fee = (d_entry_price * d_amount * fee_rate).quantize(Decimal('0.00000001'))
        exit_fee = (d_price * d_amount * fee_rate).quantize(Decimal('0.00000001'))
        fee_paid = entry_fee + exit_fee
        
        net_profit = gross_profit - fee_paid
        profit = net_profit
        
        # Avoid division by zero
        invested = d_entry_price * d_amount
        if invested > 0:
            profit_pct = (net_profit / invested) * 100
        else:
            profit_pct = Decimal('0')
        
        self.record_trade({
            "symbol": symbol,
            "strategy": "technical",
            "amount": float(d_amount),
            "entry_price": float(d_entry_price),
            "exit_price": float(d_price),
            "gross_profit": float(gross_profit),
            "fee_paid": float(fee_paid),
            "profit": float(net_profit),  # Profit NETO
            "profit_pct": float(profit_pct),
            "duration": (datetime.now() - pos["opened_at"]).total_seconds() / 3600,
            "timestamp": datetime.now().isoformat(),
        })
        
        # Guardar cierre en DB
        if "id" in pos:
            self.state_manager.close_position(
                position_id=pos["id"], 
                exit_price=float(d_price), 
                profit=float(net_profit),
                fee_paid=float(fee_paid)
            )
        else:
            # Fallback legado
            self.state_manager.add_trade_to_history(
                symbol=symbol,
                strategy="Technical RSI+MACD",
                side="sell",
                entry_price=float(d_entry_price),
                price=float(d_price),
                amount=float(d_amount),
                profit=float(net_profit),
                profit_pct=float(profit_pct),
                fee_paid=float(fee_paid)
            )

        del self.positions[symbol]
        self._save_state()
        
        logger.info(f"📉 Posición cerrada {symbol} @ ${d_price:.2f}")
        logger.info(f"   Profit: ${net_profit:.2f} ({profit_pct:.2f}%) | Fees: ${fee_paid:.4f}")
        
        return float(profit)
    
    def get_open_positions(self) -> Dict[str, Dict]:
        """Retorna todas las posiciones abiertas."""
        return self.positions.copy()
