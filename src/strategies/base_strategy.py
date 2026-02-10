"""
Base Strategy
==============
Clase base para todas las estrategias de trading
"""

from abc import ABC, abstractmethod
from typing import Dict, Any, Optional, List
from loguru import logger
from datetime import datetime


class BaseStrategy(ABC):
    """
    Clase abstracta base para todas las estrategias.
    Todas las estrategias deben heredar de esta clase.
    """
    
    def __init__(self, name: str, allocation_pct: float = 0.25):
        self.name = name
        self.allocation_pct = allocation_pct  # Porcentaje del capital asignado
        self.is_active = True
        self.trades_history: List[Dict] = []
        self.current_positions: Dict[str, Dict] = {}
        self.created_at = datetime.now()
        self.last_execution = None
        
        # Métricas
        self.total_trades = 0
        self.winning_trades = 0
        self.losing_trades = 0
        self.total_profit_usd = 0.0
    
    @abstractmethod
    def analyze(self, symbol: str, data: Dict[str, Any]) -> Dict[str, Any]:
        """
        Analiza el mercado y genera señales.
        
        Args:
            symbol: Par de trading
            data: Datos del mercado incluyendo indicadores
        
        Returns:
            Dict con la señal y detalles
        """
        pass
    
    @abstractmethod
    def should_enter(self, symbol: str, data: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        """
        Determina si se debe entrar en una posición.
        
        Returns:
            Dict con detalles de la entrada o None
        """
        pass
    
    @abstractmethod
    def should_exit(self, symbol: str, position: Dict, data: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        """
        Determina si se debe salir de una posición.
        
        Returns:
            Dict con detalles de la salida o None
        """
        pass
    
    def get_position_size(self, capital: float, price: float) -> float:
        """Calcula el tamaño de la posición basado en la asignación."""
        allocated_capital = capital * self.allocation_pct
        return allocated_capital / price
    
    def record_trade(self, trade: Dict[str, Any]) -> None:
        """Registra un trade completado."""
        self.trades_history.append(trade)
        self.total_trades += 1
        
        if trade.get("profit", 0) > 0:
            self.winning_trades += 1
        else:
            self.losing_trades += 1
        
        self.total_profit_usd += trade.get("profit", 0)
        self.last_execution = datetime.now()
    
    def get_win_rate(self) -> float:
        """Calcula el win rate de la estrategia."""
        if self.total_trades == 0:
            return 0.0
        return (self.winning_trades / self.total_trades) * 100
    
    def get_stats(self) -> Dict[str, Any]:
        """Retorna estadísticas de la estrategia."""
        return {
            "name": self.name,
            "is_active": self.is_active,
            "allocation_pct": self.allocation_pct,
            "total_trades": self.total_trades,
            "winning_trades": self.winning_trades,
            "losing_trades": self.losing_trades,
            "win_rate": self.get_win_rate(),
            "total_profit_usd": self.total_profit_usd,
            "last_execution": self.last_execution,
        }


class StrategySignal:
    """Clase para representar señales de trading."""
    
    BUY = "buy"
    SELL = "sell"
    HOLD = "hold"
    
    def __init__(
        self,
        action: str,
        symbol: str,
        strength: float = 0.0,
        price: Optional[float] = None,
        amount: Optional[float] = None,
        stop_loss: Optional[float] = None,
        take_profit: Optional[float] = None,
        reason: str = ""
    ):
        self.action = action
        self.symbol = symbol
        self.strength = strength  # 0-10, mayor = más confianza
        self.price = price
        self.amount = amount
        self.stop_loss = stop_loss
        self.take_profit = take_profit
        self.reason = reason
        self.timestamp = datetime.now()
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "action": self.action,
            "symbol": self.symbol,
            "strength": self.strength,
            "price": self.price,
            "amount": self.amount,
            "stop_loss": self.stop_loss,
            "take_profit": self.take_profit,
            "reason": self.reason,
            "timestamp": self.timestamp.isoformat(),
        }
    
    def __repr__(self):
        return f"Signal({self.action}, {self.symbol}, strength={self.strength})"
