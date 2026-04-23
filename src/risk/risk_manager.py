"""
Risk Manager
============
Gestión de riesgo para proteger el capital
"""

from decimal import Decimal, ROUND_DOWN
from typing import Dict, Any, Optional, List
from datetime import datetime, timedelta
from loguru import logger
import sys

sys.path.insert(0, str(__file__).replace("\\src\\risk\\risk_manager.py", ""))

from config.settings import RISK_MANAGEMENT, CAPITAL
from src.core.state_manager import get_state_manager
from src.core.exchange_manager import get_exchange

# Precisión financiera
MONEY_PRECISION = Decimal('0.00000001')


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


class RiskManager:
    """
    Gestiona el riesgo del portafolio.
    
    Funciones principales:
    - Calcular tamaño de posiciones
    - Gestionar stop losses
    - Proteger contra drawdown excesivo
    - Pausar trading después de pérdidas consecutivas
    """
    
    def __init__(self):
        self.max_position_pct = safe_decimal(RISK_MANAGEMENT["max_position_size_pct"])
        self.max_drawdown = safe_decimal(RISK_MANAGEMENT["max_drawdown_pct"])
        self.max_daily_drawdown = safe_decimal(RISK_MANAGEMENT.get("max_daily_drawdown_pct", 0.01))
        self.pause_after_losses = RISK_MANAGEMENT["pause_after_losses"]
        self.pause_duration = RISK_MANAGEMENT["pause_duration_hours"]
        
        # Estado usando Decimal
        self.initial_capital = safe_decimal(CAPITAL["initial_usd"])
        self.current_capital = safe_decimal(CAPITAL["initial_usd"])
        self.peak_capital = safe_decimal(CAPITAL["initial_usd"])
        self.daily_start_capital = safe_decimal(CAPITAL["initial_usd"])
        self.daily_start_date = datetime.now().date()
        self.consecutive_losses = 0
        self.is_paused = False
        self.pause_until: Optional[datetime] = None
        
        # Historial
        self.trade_history: List[Dict] = []
        self.daily_pnl: Dict[str, Decimal] = {}
        
        # === PROTECCIONES POR PAR ===
        self.pair_protections_config = RISK_MANAGEMENT.get("pair_protections", {})
        self.pair_losses: Dict[str, List[datetime]] = {}  # {symbol: [timestamps de pérdidas]}
        self.pair_paused_until: Dict[str, datetime] = {}   # {symbol: datetime de reanudación}
        self.pair_trade_results: Dict[str, List[float]] = {}  # {symbol: [profits recientes]}
        
        # === TRAILING DINÁMICO ===
        self.dynamic_trailing_config = RISK_MANAGEMENT.get("dynamic_trailing", {})
        self.total_trades = 0
        self.winning_trades = 0
        self.losing_trades = 0
        
        # Dependency Injection
        self.state_manager = get_state_manager()
        self.exchange = get_exchange()
        self._load_state()
        
        logger.info(f"✅ Risk Manager iniciado - Max posición: {self.max_position_pct*100}%")
    
    def _load_state(self) -> None:
        """Carga el estado guardado."""
        portfolio = self.state_manager.get_portfolio_state()
        if portfolio:
            self.current_capital = safe_decimal(portfolio.get("current_capital", CAPITAL["initial_usd"]))
            self.peak_capital = max(self.current_capital, self.initial_capital)
            self.total_trades = portfolio.get("trades_count", 0)
            self.winning_trades = portfolio.get("winning_trades", 0)
            self.losing_trades = portfolio.get("losing_trades", 0)
            
            # FIX: Sincronizar daily_start_capital con el capital REAL restaurado
            # Sin esto, daily_start_capital quedaba en el capital inicial ($75)
            # causando un falso drawdown diario gigante al arrancar.
            self.daily_start_capital = self.current_capital
            
            if self.current_capital != self.initial_capital:
                logger.info(f"📂 Risk Manager: Estado restaurado - Capital: ${self.current_capital:.2f}")
    
    def _save_state(self) -> None:
        """Guarda el estado actual."""
        self.state_manager.save_portfolio_state(
            current_capital=self.current_capital,
            total_invested=self.initial_capital - self.current_capital + sum(self.daily_pnl.values()),
            total_profit=self.current_capital - self.initial_capital,
            trades_count=self.total_trades,
            winning_trades=self.winning_trades,
            losing_trades=self.losing_trades
        )
    
    def calculate_position_size(
        self,
        symbol: str,
        price: float,
        strategy_allocation: float = 0.25
    ) -> Dict[str, Any]:
        """
        Calcula el tamaño óptimo de posición usando Decimal.
        """
        if self.is_paused:
            return {"amount": Decimal('0'), "reason": "Trading pausado"}
        
        # Convertir inputs a Decimal inmediatamente
        d_price = safe_decimal(price)
        d_allocation = safe_decimal(strategy_allocation)
        
        # 1. Calcular alocación teórica basada en capital TOTAL (Equity)
        theoretical_allocation = (self.current_capital * d_allocation).quantize(MONEY_PRECISION, rounding=ROUND_DOWN)
        max_theoretical = (theoretical_allocation * self.max_position_pct).quantize(MONEY_PRECISION, rounding=ROUND_DOWN)
        
        # 2. Verificar LIQUIDEZ REAL (USDT en wallet)
        balance = self.exchange.get_balance()
        liquid_usdt = safe_decimal(balance.get("USDT", 0))
        
        # Buffer de seguridad del 1% para fees y slippage
        max_liquid = (liquid_usdt * Decimal('0.99')).quantize(MONEY_PRECISION, rounding=ROUND_DOWN)
        
        # Tomar el MENOR entre la alocación teórica y la liquidez real
        max_for_trade = min(max_theoretical, max_liquid)
        
        if max_for_trade < Decimal('5.0'):
            return {
                "symbol": symbol,
                "amount": Decimal('0'),
                "usd_value": Decimal('0'),
                "price": d_price,
                "reason": f"Capital insuficiente (Req $5, Disp ${max_for_trade:.2f})"
            }
        
        # Calcular cantidad
        amount = (max_for_trade / d_price).quantize(MONEY_PRECISION, rounding=ROUND_DOWN)
        
        return {
            "symbol": symbol,
            "amount": amount,
            "usd_value": max_for_trade,
            "price": d_price, # Devolver Decimal
            "position_pct": float(self.max_position_pct * 100),
        }
    
    def calculate_stop_loss(self, entry_price: float, side: str = "long") -> float:
        """Calcula el stop loss para una posición."""
        sl_pct = safe_decimal(RISK_MANAGEMENT["default_stop_loss_pct"])
        d_price = safe_decimal(entry_price)
        
        if side == "long":
            return float(d_price * (Decimal('1') - sl_pct))
        else:
            return float(d_price * (Decimal('1') + sl_pct))
    
    def calculate_take_profit(self, entry_price: float, side: str = "long") -> float:
        """Calcula el take profit para una posición."""
        tp_pct = safe_decimal(RISK_MANAGEMENT["default_take_profit_pct"])
        d_price = safe_decimal(entry_price)
        
        if side == "long":
            return float(d_price * (Decimal('1') + tp_pct))
        else:
            return float(d_price * (Decimal('1') - tp_pct))
    
    def calculate_trailing_stop(self, current_price: float, high_watermark: float, 
                                 entry_price: float, side: str = "long") -> Dict[str, Any]:
        """
        Calcula el trailing stop dinámico.
        
        El trailing stop se mueve hacia arriba cuando el precio sube,
        pero nunca hacia abajo, protegiendo las ganancias.
        
        Args:
            current_price: Precio actual del activo
            high_watermark: Precio más alto alcanzado desde la entrada
            entry_price: Precio de entrada original
            side: "long" o "short"
        
        Returns:
            Dict con trailing_stop_price, triggered, profit_protected_pct
        """
        d_current = safe_decimal(current_price)
        d_high = safe_decimal(high_watermark)
        d_entry = safe_decimal(entry_price)
        
        # Calcular profit actual para seleccionar tier de trailing
        current_profit_pct = (d_current - d_entry) / d_entry if d_entry > 0 else Decimal('0')
        
        # === TRAILING DINÁMICO ===
        trailing_pct = self._get_dynamic_trailing_pct(float(current_profit_pct))
        
        # Actualizar high watermark si el precio actual es mayor
        new_high = max(d_high, d_current) if side == "long" else min(d_high, d_current)
        
        # Calcular trailing stop desde el high watermark
        if side == "long":
            trailing_stop = new_high * (Decimal('1') - trailing_pct)
            triggered = d_current <= trailing_stop
            profit_protected = ((new_high - d_entry) / d_entry) * 100 if d_entry > 0 else Decimal('0')
        else:
            trailing_stop = new_high * (Decimal('1') + trailing_pct)
            triggered = d_current >= trailing_stop
            profit_protected = ((d_entry - new_high) / d_entry) * 100 if d_entry > 0 else Decimal('0')
        
        return {
            "trailing_stop_price": float(trailing_stop),
            "high_watermark": float(new_high),
            "triggered": triggered,
            "profit_protected_pct": float(profit_protected),
            "current_gain_pct": float(current_profit_pct * 100),
            "trailing_pct_used": float(trailing_pct * 100),
        }
    
    def should_activate_trailing(self, current_price: float, entry_price: float, 
                                  activation_pct: float = 0.02) -> bool:
        """
        Determina si el trailing stop debería activarse.
        Solo se activa después de un mínimo de ganancia (por defecto 2%).
        """
        d_current = safe_decimal(current_price)
        d_entry = safe_decimal(entry_price)
        d_activation = safe_decimal(activation_pct)
        
        if d_entry <= 0:
            return False
        
        gain_pct = (d_current - d_entry) / d_entry
        return gain_pct >= d_activation
    
    def update_capital(self, new_capital: float) -> None:
        """Actualiza el capital actual y verifica drawdown."""
        # Convertir a Decimal
        d_new_capital = safe_decimal(new_capital)
        
        old_capital = self.current_capital
        self.current_capital = d_new_capital
        
        # Actualizar peak
        if d_new_capital > self.peak_capital:
            self.peak_capital = d_new_capital
        
        # Calcular drawdown
        drawdown = (self.peak_capital - self.current_capital) / self.peak_capital
        
        if drawdown >= self.max_drawdown:
            self._pause_trading(f"Drawdown máximo alcanzado: {drawdown*100:.1f}%")
    
    def record_trade_result(self, profit: float, fee_paid: float = 0, gross_profit: float = 0) -> Dict[str, Any]:
        """
        Registra el resultado de un trade usando Decimal para precisión.
        Retorna alertas si se detectan anomalías.
        """
        d_profit = safe_decimal(profit)
        d_fee = safe_decimal(fee_paid)
        d_gross = safe_decimal(gross_profit)
        
        self.current_capital += d_profit
        
        # Verificar si es un nuevo día y resetear capital diario
        today = datetime.now().date()
        today_str = datetime.now().strftime("%Y-%m-%d")
        
        if today != self.daily_start_date:
            self.daily_start_capital = self.current_capital
            self.daily_start_date = today
            # Clean old daily stats if needed, or just rely on keys
            logger.info(f"📅 Nuevo día de trading - Capital inicio: ${self.daily_start_capital:.2f}")
        
        # Registrar en historial diario
        current_daily = self.daily_pnl.get(today_str, Decimal('0'))
        self.daily_pnl[today_str] = current_daily + d_profit
        
        # Track diario de fees y gross para alertas de eficiencia
        # Inicializar si no existe (usamos un dict separado o extendemos self.daily_pnl structure?)
        # Optamos por atributos simples en memoria para el día actual
        if not hasattr(self, 'daily_stats') or self.daily_stats.get('date') != today:
            self.daily_stats = {'fees': Decimal('0'), 'gross': Decimal('0'), 'date': today}
        
        self.daily_stats['fees'] += d_fee
        # Solo acumular gross si es positivo (ganancia real para calcular ratio de fees)
        if d_gross > Decimal('0'):
            self.daily_stats['gross'] += d_gross
        
        alerts = {}
        
        # Check Inefficiency Alert (Fee > 10% of Profits)
        # Solo checkear si hay ganancia significativa para evitar ruido con $0.01
        if self.daily_stats['gross'] > Decimal('1.0') and self.daily_stats['fees'] > Decimal('0'):
            fee_impact = (self.daily_stats['fees'] / self.daily_stats['gross']) * Decimal('100')
            if fee_impact > Decimal('10.0'):
                alerts['inefficiency'] = {
                    'fees': float(self.daily_stats['fees']),
                    'gross': float(self.daily_stats['gross']),
                    'impact_pct': float(fee_impact)
                }
        
        if profit < 0:
            self.consecutive_losses += 1
            self.losing_trades += 1
            if self.consecutive_losses >= self.pause_after_losses:
                self._pause_trading(f"{self.consecutive_losses} pérdidas consecutivas")
        else:
            self.consecutive_losses = 0
            self.winning_trades += 1
        
        self.total_trades += 1
        
        # Actualizar peak capital
        if self.current_capital > self.peak_capital:
            self.peak_capital = self.current_capital
        
        # Check Daily Drawdown (pausa si perdemos más del límite diario)
        if self.daily_start_capital > 0:
            daily_dd = (self.daily_start_capital - self.current_capital) / self.daily_start_capital
            if daily_dd >= self.max_daily_drawdown:
                self._pause_trading(f"DD diario {daily_dd*100:.2f}% >= {self.max_daily_drawdown*100:.1f}%")
        
        # Guardar estado (CRÍTICO: debe ejecutarse siempre)
        self._save_state()
        
        return alerts
    
    def _pause_trading(self, reason: str) -> None:
        """Pausa el trading temporalmente."""
        self.is_paused = True
        self.pause_until = datetime.now() + timedelta(hours=self.pause_duration)
        logger.warning(f"⚠️ Trading PAUSADO: {reason}")
        logger.warning(f"   Reanudar en: {self.pause_until.strftime('%Y-%m-%d %H:%M')}")
    
    def check_pause_status(self) -> bool:
        """Verifica si debemos seguir pausados."""
        if not self.is_paused:
            return False
        
        if self.pause_until and datetime.now() >= self.pause_until:
            self.is_paused = False
            self.pause_until = None
            self.consecutive_losses = 0
            logger.info("✅ Trading REANUDADO")
            return False
        
        return True
    
    def can_trade(self) -> Dict[str, Any]:
        """Verifica si es seguro hacer trading."""
        self.check_pause_status()
        
        if self.is_paused:
            remaining = (self.pause_until - datetime.now()).total_seconds() / 3600
            return {
                "can_trade": False,
                "reason": f"Pausado ({remaining:.1f}h restantes)",
            }
        
        drawdown = (self.peak_capital - self.current_capital) / self.peak_capital
        
        if drawdown >= self.max_drawdown * Decimal('0.8'):
            return {
                "can_trade": True,
                "warning": f"Drawdown alto: {drawdown*100:.1f}%",
            }
        
        return {"can_trade": True}
    
    def get_portfolio_stats(self) -> Dict[str, Any]:
        """Obtiene estadísticas del portafolio."""
        drawdown = (self.peak_capital - self.current_capital) / self.peak_capital
        total_pnl = self.current_capital - self.initial_capital
        roi = (total_pnl / self.initial_capital) * 100
        
        win_rate = (self.winning_trades / self.total_trades * 100) if self.total_trades > 0 else 0
        
        return {
            "initial_capital": self.initial_capital,
            "current_capital": self.current_capital,
            "peak_capital": self.peak_capital,
            "total_pnl": total_pnl,
            "total_profit": total_pnl,  # Alias para compatibilidad
            "roi_pct": roi,
            "current_drawdown_pct": drawdown * 100,
            "max_drawdown_limit_pct": self.max_drawdown * 100,
            "consecutive_losses": self.consecutive_losses,
            "is_paused": self.is_paused,
            "total_trades": self.total_trades,
            "winning_trades": self.winning_trades,
            "losing_trades": self.losing_trades,
            "win_rate": win_rate,
        }
    
    def get_risk_score(self) -> Dict[str, Any]:
        """
        Calcula un score de riesgo actual (1-10).
        1 = Muy seguro, 10 = Muy riesgoso
        """
        score = 0
        factors = []
        
        # Drawdown
        drawdown = (self.peak_capital - self.current_capital) / self.peak_capital
        if drawdown > 0.10:
            score += 3
            factors.append(f"Drawdown alto ({drawdown*100:.1f}%)")
        elif drawdown > 0.05:
            score += 1
            factors.append(f"Drawdown moderado ({drawdown*100:.1f}%)")
        
        # Pérdidas consecutivas
        if self.consecutive_losses >= 2:
            score += 2
            factors.append(f"{self.consecutive_losses} pérdidas consecutivas")
        
        # Capital bajo
        if self.current_capital < self.initial_capital * Decimal('0.9'):
            score += 2
            factors.append("Capital bajo")
        
        return {
            "score": min(10, score),
            "level": "alto" if score >= 5 else "medio" if score >= 3 else "bajo",
            "factors": factors,
        }
    
    # =========================================================================
    # TRAILING STOP DINÁMICO
    # =========================================================================
    def _get_dynamic_trailing_pct(self, current_profit_pct: float) -> Decimal:
        """
        Selecciona el trailing % basado en cuánto profit lleva el trade.
        A más profit → trailing más tight → protege más ganancia.
        """
        if not self.dynamic_trailing_config.get("enabled", False):
            return safe_decimal(RISK_MANAGEMENT.get("trailing_stop_pct", 0.03))
        
        tiers = self.dynamic_trailing_config.get("tiers", [])
        # Ordenar de mayor a menor profit para encontrar el tier correcto
        selected_trailing = safe_decimal(RISK_MANAGEMENT.get("trailing_stop_pct", 0.03))
        
        for tier in sorted(tiers, key=lambda x: x["min_profit_pct"]):
            if current_profit_pct >= tier["min_profit_pct"]:
                selected_trailing = safe_decimal(tier["trailing_pct"])
        
        return selected_trailing
    
    # =========================================================================
    # PROTECCIONES POR PAR
    # =========================================================================
    def record_pair_trade(self, symbol: str, profit: float) -> None:
        """
        Registra el resultado de un trade para un par específico.
        Controla las protecciones por par.
        """
        if not self.pair_protections_config.get("enabled", False):
            return
        
        now = datetime.now()
        
        # Registrar en historial de profits por par
        if symbol not in self.pair_trade_results:
            self.pair_trade_results[symbol] = []
        self.pair_trade_results[symbol].append(profit)
        # Mantener solo los últimos 20 trades por par
        self.pair_trade_results[symbol] = self.pair_trade_results[symbol][-20:]
        
        if profit < 0:
            # Registrar pérdida con timestamp
            if symbol not in self.pair_losses:
                self.pair_losses[symbol] = []
            self.pair_losses[symbol].append(now)
            
            # Limpiar pérdidas antiguas (fuera del lookback)
            lookback_hours = self.pair_protections_config.get("lookback_hours", 12)
            cutoff = now - timedelta(hours=lookback_hours)
            self.pair_losses[symbol] = [t for t in self.pair_losses[symbol] if t > cutoff]
            
            # Verificar si se excedió el límite de pérdidas
            max_losses = self.pair_protections_config.get("max_losses_per_pair", 3)
            if len(self.pair_losses[symbol]) >= max_losses:
                pause_hours = self.pair_protections_config.get("pause_pair_hours", 6)
                self.pair_paused_until[symbol] = now + timedelta(hours=pause_hours)
                logger.warning(
                    f"🛡️ PROTECCIÓN: {symbol} PAUSADO por {pause_hours}h "
                    f"({len(self.pair_losses[symbol])} pérdidas en {lookback_hours}h)"
                )
                # Limpiar contador para evitar re-pausar inmediatamente al reanudar
                self.pair_losses[symbol] = []
        else:
            # Reset pérdidas consecutivas en caso de ganancia
            if symbol in self.pair_losses:
                self.pair_losses[symbol] = []
        
        # Verificar rendimiento promedio (low profit protection)
        min_trades = self.pair_protections_config.get("low_profit_min_trades", 5)
        results = self.pair_trade_results.get(symbol, [])
        if len(results) >= min_trades:
            avg_profit = sum(results[-min_trades:]) / min_trades
            threshold = self.pair_protections_config.get("low_profit_threshold_pct", -1.0)
            if avg_profit < threshold:
                pause_hours = self.pair_protections_config.get("pause_pair_hours", 6)
                self.pair_paused_until[symbol] = now + timedelta(hours=pause_hours)
                logger.warning(
                    f"🛡️ PROTECCIÓN: {symbol} PAUSADO por bajo rendimiento "
                    f"(avg profit: {avg_profit:.2f}% en últimos {min_trades} trades)"
                )
    
    def can_trade_pair(self, symbol: str) -> Dict[str, Any]:
        """
        Verifica si un par específico puede operar o está pausado por protección.
        """
        if not self.pair_protections_config.get("enabled", False):
            return {"can_trade": True}
        
        if symbol in self.pair_paused_until:
            pause_end = self.pair_paused_until[symbol]
            if datetime.now() < pause_end:
                remaining = (pause_end - datetime.now()).total_seconds() / 3600
                return {
                    "can_trade": False,
                    "reason": f"🛡️ {symbol} pausado por protección ({remaining:.1f}h restantes)",
                }
            else:
                # Expiró la pausa, limpiar
                del self.pair_paused_until[symbol]
                logger.info(f"✅ PROTECCIÓN: {symbol} reanudado tras pausa")
        
        return {"can_trade": True}
    
    def get_pair_protection_status(self) -> Dict[str, Any]:
        """
        Retorna el estado de protecciones de todos los pares.
        Útil para reportes de Telegram.
        """
        status = {}
        now = datetime.now()
        for symbol, pause_end in self.pair_paused_until.items():
            if now < pause_end:
                remaining = (pause_end - now).total_seconds() / 3600
                status[symbol] = {
                    "paused": True,
                    "remaining_hours": round(remaining, 1),
                    "resume_at": pause_end.strftime("%H:%M"),
                }
        return status


# Singleton
_risk_manager: Optional[RiskManager] = None

def get_risk_manager() -> RiskManager:
    global _risk_manager
    if _risk_manager is None:
        _risk_manager = RiskManager()
    return _risk_manager
