"""
State Manager - Persistencia de Estado
======================================
Guarda y restaura el estado del bot de trading
para mantener continuidad entre reinicios.
"""

import json
import sqlite3
from datetime import datetime
from decimal import Decimal
from pathlib import Path
from typing import Dict, Any, Optional, List, Union
from loguru import logger

from config.settings import DATABASE, CAPITAL


def _to_float(value: Any) -> Optional[float]:
    """Convierte cualquier valor numérico a float para SQLite (no soporta Decimal)."""
    if value is None:
        return None
    try:
        if isinstance(value, Decimal):
            return float(value)
        return float(value)
    except (ValueError, TypeError):
        return 0.0


class StateManager:
    """
    Gestiona la persistencia del estado del bot.
    
    Almacena:
    - Posiciones abiertas
    - Historial de trades
    - Estado de estrategias
    - Estadísticas generales
    """
    
    def __init__(self):
        self.db_path = DATABASE["path"]
        self._ensure_db_directory()
        self._init_database()
        logger.info(f"✅ State Manager iniciado - DB: {self.db_path}")
    
    def _ensure_db_directory(self) -> None:
        """Asegura que el directorio de la base de datos exista."""
        Path(self.db_path).parent.mkdir(parents=True, exist_ok=True)
    
    def _init_database(self) -> None:
        """Inicializa las tablas de la base de datos."""
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()
            
            # Enable WAL mode for better concurrency
            cursor.execute("PRAGMA journal_mode=WAL;")
            
            # Tabla de posiciones abiertas
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS positions (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    symbol TEXT NOT NULL,
                    strategy TEXT NOT NULL,
                    entry_price REAL NOT NULL,
                    amount REAL NOT NULL,
                    stop_loss REAL,
                    take_profit REAL,
                    opened_at TEXT NOT NULL,
                    status TEXT DEFAULT 'open',
                    extra_data TEXT
                )
            """)
            
            # Tabla de historial de trades
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS trade_history (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    symbol TEXT NOT NULL,
                    strategy TEXT NOT NULL,
                    side TEXT NOT NULL,
                    entry_price REAL,
                    exit_price REAL,
                    amount REAL NOT NULL,
                    profit REAL DEFAULT 0,
                    profit_pct REAL DEFAULT 0,
                    fee_paid REAL DEFAULT 0,
                    opened_at TEXT,
                    closed_at TEXT,
                    extra_data TEXT
                )
            """)
            
            # Migración: Verificar si existe columna fee_paid y agregarla si no
            try:
                cursor.execute("SELECT fee_paid FROM trade_history LIMIT 1")
            except sqlite3.OperationalError:
                logger.warning("⚠️ Columna 'fee_paid' no encontrada en trade_history - Agregando...")
                cursor.execute("ALTER TABLE trade_history ADD COLUMN fee_paid REAL DEFAULT 0")
            
            # Tabla de estado de estrategias
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS strategy_state (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    strategy_name TEXT UNIQUE NOT NULL,
                    state_data TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                )
            """)
            
            # Tabla de estadísticas generales
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS bot_stats (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    key TEXT UNIQUE NOT NULL,
                    value TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                )
            """)
            
            # Tabla de estado general del portfolio
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS portfolio_state (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    current_capital REAL NOT NULL,
                    total_invested REAL NOT NULL,
                    total_profit REAL NOT NULL,
                    trades_count INTEGER NOT NULL,
                    winning_trades INTEGER NOT NULL,
                    losing_trades INTEGER NOT NULL,
                    updated_at TEXT NOT NULL
                )
            """)
            
            conn.commit()
    
    # =========================================================================
    # POSICIONES
    # =========================================================================
    
    def save_position(self, symbol: str, strategy: str, entry_price: float,
                     amount: float, stop_loss: float = None, 
                     take_profit: float = None, extra_data: Dict = None) -> int:
        """Guarda una nueva posición abierta."""
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()
            cursor.execute("""
                INSERT INTO positions 
                (symbol, strategy, entry_price, amount, stop_loss, take_profit, opened_at, extra_data)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                symbol, strategy, 
                _to_float(entry_price), 
                _to_float(amount), 
                _to_float(stop_loss), 
                _to_float(take_profit),
                datetime.now().isoformat(),
                json.dumps(extra_data) if extra_data else None
            ))
            conn.commit()
            position_id = cursor.lastrowid
            logger.debug(f"📝 Posición guardada: {symbol} ({strategy}) - ID: {position_id}")
            return position_id
    
    def get_open_positions(self, strategy: str = None) -> List[Dict]:
        """
        Obtiene todas las posiciones abiertas.
        Combina tabla 'positions' (Technical) y 'strategy_state' (Grid/DCA).
        """
        positions = []
        
        with sqlite3.connect(self.db_path) as conn:
            conn.row_factory = sqlite3.Row
            cursor = conn.cursor()
            
            # 1. Obtener de tabla POSITIONS (Technical Strategy)
            query = "SELECT * FROM positions WHERE status = 'open'"
            params = []
            if strategy:
                query += " AND strategy = ?"
                params.append(strategy)
            
            cursor.execute(query, tuple(params))
            for row in cursor.fetchall():
                pos = dict(row)
                if pos['extra_data']:
                    pos['extra_data'] = json.loads(pos['extra_data'])
                positions.append(pos)
            
            # 2. Obtener de STRATEGY_STATE (DCA)
            if not strategy or strategy == "dca_intelligent":
                cursor.execute("SELECT state_data FROM strategy_state WHERE strategy_name = 'dca_intelligent'")
                row = cursor.fetchone()
                if row:
                    try:
                        dca_state = json.loads(row[0])
                        dca_positions = dca_state.get("positions", {})
                        for symbol, data in dca_positions.items():
                            if data.get("amount", 0) > 0:
                                positions.append({
                                    "symbol": symbol,
                                    "strategy": "DCA Intelligent",
                                    "entry_price": data.get("avg_price", 0),
                                    "amount": data.get("amount", 0),
                                    "opened_at": datetime.now().isoformat(), # Estimado
                                    "status": "open",
                                    "source": "strategy_state"
                                })
                    except Exception as e:
                        logger.error(f"Error parseando DCA state: {e}")

            # 3. Obtener de STRATEGY_STATE (Grid)
            if not strategy or strategy == "grid_trading":
                cursor.execute("SELECT state_data FROM strategy_state WHERE strategy_name = 'grid_trading'")
                row = cursor.fetchone()
                if row:
                    try:
                        grid_state = json.loads(row[0])
                        grids = grid_state.get("grids", {})
                        for symbol, grid_data in grids.items():
                            levels = grid_data.get("levels", [])
                            # Sumarizar todos los niveles comprados como una posición agregada por símbolo
                            total_amount = 0
                            total_cost = 0
                            for lvl in levels:
                                if lvl.get("status") == "bought":
                                    amt = lvl.get("amount", 0)
                                    price = lvl.get("buy_executed_price", lvl.get("buy_price", 0))
                                    total_amount += amt
                                    total_cost += (amt * price)
                            
                            if total_amount > 0:
                                avg_price = total_cost / total_amount
                                positions.append({
                                    "symbol": symbol,
                                    "strategy": "Grid Trading",
                                    "entry_price": avg_price,
                                    "amount": total_amount,
                                    "opened_at": datetime.now().isoformat(),
                                    "status": "open", 
                                    "source": "strategy_state"
                                })
                    except Exception as e:
                        logger.error(f"Error parseando Grid state: {e}")
            
            return positions
    
    def close_position(self, position_id: int, exit_price: float, profit: float, fee_paid: float = 0) -> None:
        """Cierra una posición y la mueve al historial."""
        with sqlite3.connect(self.db_path) as conn:
            conn.row_factory = sqlite3.Row
            cursor = conn.cursor()
            
            # Obtener posición
            cursor.execute("SELECT * FROM positions WHERE id = ?", (position_id,))
            pos = cursor.fetchone()
            
            if pos:
                pos = dict(pos)
                profit_pct = ((exit_price / pos['entry_price']) - 1) * 100 if pos['entry_price'] > 0 else 0
                
                # Agregar al historial
                cursor.execute("""
                    INSERT INTO trade_history 
                    (symbol, strategy, side, entry_price, exit_price, amount, profit, profit_pct, fee_paid, opened_at, closed_at, extra_data)
                    VALUES (?, ?, 'sell', ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """, (
                    pos['symbol'], pos['strategy'], 
                    _to_float(pos['entry_price']), 
                    _to_float(exit_price),
                    _to_float(pos['amount']), 
                    _to_float(profit), 
                    _to_float(profit_pct), 
                    _to_float(fee_paid), 
                    pos['opened_at'],
                    datetime.now().isoformat(), pos['extra_data']
                ))
                
                # Marcar posición como cerrada
                cursor.execute(
                    "UPDATE positions SET status = 'closed' WHERE id = ?",
                    (position_id,)
                )
                
                conn.commit()
                logger.debug(f"📝 Posición cerrada: ID {position_id} - Profit: ${profit:.2f} - Fees: ${fee_paid:.4f}")
    
    def update_position(self, position_id: int, **kwargs) -> None:
        """Actualiza una posición existente."""
        valid_fields = ['amount', 'stop_loss', 'take_profit', 'extra_data']
        updates = {k: v for k, v in kwargs.items() if k in valid_fields}
        
        if not updates:
            return
        
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()
            
            set_clause = ", ".join([f"{k} = ?" for k in updates.keys()])
            values = []
            for k, v in updates.items():
                if k == 'extra_data' and isinstance(v, dict):
                    values.append(json.dumps(v))
                elif k in ['amount', 'stop_loss', 'take_profit', 'entry_price']:
                    values.append(_to_float(v))
                else:
                    values.append(v)
            
            values.append(position_id)
            
            cursor.execute(
                f"UPDATE positions SET {set_clause} WHERE id = ?",
                values
            )
            conn.commit()
    
    # =========================================================================
    # ESTADO DE ESTRATEGIAS
    # =========================================================================
    
    def save_strategy_state(self, strategy_name: str, state_data: Dict) -> None:
        """Guarda el estado de una estrategia."""
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()
            cursor.execute("""
                INSERT OR REPLACE INTO strategy_state (strategy_name, state_data, updated_at)
                VALUES (?, ?, ?)
            """, (
                strategy_name,
                json.dumps(state_data, default=str),
                datetime.now().isoformat()
            ))
            conn.commit()
            logger.debug(f"📝 Estado de {strategy_name} guardado")
    
    def load_strategy_state(self, strategy_name: str) -> Optional[Dict]:
        """Carga el estado de una estrategia."""
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()
            cursor.execute(
                "SELECT state_data FROM strategy_state WHERE strategy_name = ?",
                (strategy_name,)
            )
            row = cursor.fetchone()
            
            if row:
                state = json.loads(row[0])
                logger.debug(f"📂 Estado de {strategy_name} cargado")
                return state
            
            return None
    
    # =========================================================================
    # HISTORIAL DE TRADES
    # =========================================================================
    
    def add_trade_to_history(self, symbol: str, strategy: str, side: str,
                            price: float = None, amount: float = 0, profit: float = 0,
                            entry_price: float = None, fee_paid: float = 0, exit_price: float = None,
                            profit_pct: float = None) -> None:
        """Agrega un trade al historial."""
        # Compatibilidad: permitir 'price' o 'exit_price' para el precio de ejecución
        exec_price = exit_price if exit_price is not None else price
        if exec_price is None:
            exec_price = 0.0

        if profit_pct is None:
            profit_pct = 0.0
            if entry_price and entry_price > 0 and side == 'sell' and exec_price > 0:
                profit_pct = ((exec_price / entry_price) - 1) * 100
        
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()
            cursor.execute("""
                INSERT INTO trade_history 
                (symbol, strategy, side, entry_price, exit_price, amount, profit, profit_pct, fee_paid, closed_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                symbol, strategy, side, 
                _to_float(entry_price), 
                _to_float(exec_price), 
                _to_float(amount), 
                _to_float(profit), 
                _to_float(profit_pct), 
                _to_float(fee_paid),
                datetime.now().isoformat()
            ))
            conn.commit()
    
    def get_trade_history(self, limit: int = 100, symbol: str = None) -> List[Dict]:
        """Obtiene el historial de trades."""
        with sqlite3.connect(self.db_path) as conn:
            conn.row_factory = sqlite3.Row
            cursor = conn.cursor()
            
            if symbol:
                cursor.execute(
                    "SELECT * FROM trade_history WHERE symbol = ? ORDER BY id DESC LIMIT ?",
                    (symbol, limit)
                )
            else:
                cursor.execute(
                    "SELECT * FROM trade_history ORDER BY id DESC LIMIT ?",
                    (limit,)
                )
            
            return [dict(row) for row in cursor.fetchall()]
    
    def get_trade_stats(self) -> Dict:
        """Obtiene estadísticas de trading."""
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()
            
            # Total trades
            cursor.execute("SELECT COUNT(*) FROM trade_history")
            total_trades = cursor.fetchone()[0]
            
            # Trades ganadores
            cursor.execute("SELECT COUNT(*) FROM trade_history WHERE profit > 0")
            winning_trades = cursor.fetchone()[0]
            
            # Trades perdedores
            cursor.execute("SELECT COUNT(*) FROM trade_history WHERE profit < 0")
            losing_trades = cursor.fetchone()[0]
            
            # Profit total
            cursor.execute("SELECT SUM(profit) FROM trade_history")
            total_profit = cursor.fetchone()[0] or 0
            
            # Mejor trade
            cursor.execute("SELECT MAX(profit) FROM trade_history")
            best_trade = cursor.fetchone()[0] or 0
            
            # Peor trade
            cursor.execute("SELECT MIN(profit) FROM trade_history")
            worst_trade = cursor.fetchone()[0] or 0
            
            win_rate = (winning_trades / total_trades * 100) if total_trades > 0 else 0
            
            return {
                "total_trades": total_trades,
                "winning_trades": winning_trades,
                "losing_trades": losing_trades,
                "win_rate": win_rate,
                "total_profit": total_profit,
                "best_trade": best_trade,
                "worst_trade": worst_trade
            }
    
    def get_trades_by_period(self, days: int = 1) -> Dict:
        """Obtiene estadísticas de trading para un período específico."""
        from datetime import datetime, timedelta
        
        cutoff_date = (datetime.now() - timedelta(days=days)).isoformat()
        
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()
            
            # Trades en el período
            cursor.execute("""
                SELECT COUNT(*), SUM(profit), SUM(CASE WHEN profit > 0 THEN 1 ELSE 0 END),
                       SUM(CASE WHEN profit < 0 THEN 1 ELSE 0 END), SUM(fee_paid)
                FROM trade_history 
                WHERE closed_at >= ? OR (closed_at IS NULL AND opened_at >= ?)
            """, (cutoff_date, cutoff_date))
            
            row = cursor.fetchone()
            total_trades = row[0] or 0
            total_profit = row[1] or 0
            winning = row[2] or 0
            losing = row[3] or 0
            total_fees = row[4] or 0
            
            win_rate = (winning / total_trades * 100) if total_trades > 0 else 0
            
            return {
                "period_days": days,
                "total_trades": total_trades,
                "winning_trades": winning,
                "losing_trades": losing,
                "win_rate": win_rate,
                "total_profit": total_profit,
                "total_fees": total_fees
            }
    
    def get_top_trades(self, limit: int = 3, best: bool = True) -> List[Dict]:
        """Obtiene los mejores o peores trades."""
        order = "DESC" if best else "ASC"
        
        with sqlite3.connect(self.db_path) as conn:
            conn.row_factory = sqlite3.Row
            cursor = conn.cursor()
            cursor.execute(f"""
                SELECT symbol, strategy, entry_price, exit_price, amount, profit, 
                       profit_pct, fee_paid, closed_at
                FROM trade_history 
                WHERE exit_price IS NOT NULL AND profit IS NOT NULL
                ORDER BY profit {order}
                LIMIT ?
            """, (limit,))
            
            return [dict(row) for row in cursor.fetchall()]
    
    def get_total_fees(self) -> Dict:
        """Obtiene el total de fees pagados."""
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()
            
            # Total fees
            cursor.execute("SELECT SUM(fee_paid), COUNT(*) FROM trade_history WHERE fee_paid > 0")
            row = cursor.fetchone()
            
            # Fees por estrategia
            cursor.execute("""
                SELECT strategy, SUM(fee_paid) as fees 
                FROM trade_history 
                WHERE fee_paid > 0 
                GROUP BY strategy
            """)
            by_strategy = {r[0]: r[1] for r in cursor.fetchall()}
            
            return {
                "total_fees": row[0] or 0,
                "trades_with_fees": row[1] or 0,
                "by_strategy": by_strategy
            }
    
    # =========================================================================
    # ESTADO DEL PORTFOLIO
    # =========================================================================
    
    def save_portfolio_state(self, current_capital: float, total_invested: float,
                            total_profit: float, trades_count: int,
                            winning_trades: int, losing_trades: int) -> None:
        """Guarda el estado actual del portfolio."""
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()
            cursor.execute("""
                INSERT INTO portfolio_state 
                (current_capital, total_invested, total_profit, trades_count, winning_trades, losing_trades, updated_at)
                VALUES (?, ?, ?, ?, ?, ?, ?)
            """, (
                _to_float(current_capital), 
                _to_float(total_invested), 
                _to_float(total_profit),
                trades_count, winning_trades, losing_trades,
                datetime.now().isoformat()
            ))
            conn.commit()
    
    def get_portfolio_state(self) -> Optional[Dict]:
        """Obtiene el último estado del portfolio."""
        with sqlite3.connect(self.db_path) as conn:
            conn.row_factory = sqlite3.Row
            cursor = conn.cursor()
            cursor.execute(
                "SELECT * FROM portfolio_state ORDER BY id DESC LIMIT 1"
            )
            row = cursor.fetchone()
            
            if row:
                return dict(row)
            
            # Estado inicial
            return {
                "current_capital": CAPITAL.get("initial_usd", 75),
                "total_invested": 0,
                "total_profit": 0,
                "trades_count": 0,
                "winning_trades": 0,
                "losing_trades": 0
            }
    
    # =========================================================================
    # BOT STATS GENÉRICAS
    # =========================================================================
    
    def set_stat(self, key: str, value: Any) -> None:
        """Guarda una estadística genérica."""
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()
            cursor.execute("""
                INSERT OR REPLACE INTO bot_stats (key, value, updated_at)
                VALUES (?, ?, ?)
            """, (key, json.dumps(value, default=str), datetime.now().isoformat()))
            conn.commit()
    
    def get_stat(self, key: str, default: Any = None) -> Any:
        """Obtiene una estadística genérica."""
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT value FROM bot_stats WHERE key = ?", (key,))
            row = cursor.fetchone()
            
            if row:
                return json.loads(row[0])
            
            return default
    
    # =========================================================================
    # UTILIDADES
    # =========================================================================
    
    def clear_all_data(self) -> None:
        """Limpia todos los datos (usar con precaución)."""
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()
            cursor.execute("DELETE FROM positions")
            cursor.execute("DELETE FROM trade_history")
            cursor.execute("DELETE FROM strategy_state")
            cursor.execute("DELETE FROM bot_stats")
            cursor.execute("DELETE FROM portfolio_state")
            conn.commit()
            logger.warning("⚠️ Todos los datos han sido eliminados")
    
    def get_summary(self) -> Dict:
        """Obtiene un resumen completo del estado."""
        portfolio = self.get_portfolio_state()
        trade_stats = self.get_trade_stats()
        open_positions = self.get_open_positions()
        
        return {
            "portfolio": portfolio,
            "trade_stats": trade_stats,
            "open_positions_count": len(open_positions),
            "open_positions": open_positions
        }


# Singleton
_state_manager: Optional[StateManager] = None


def get_state_manager() -> StateManager:
    """Obtiene la instancia del State Manager."""
    global _state_manager
    if _state_manager is None:
        _state_manager = StateManager()
    return _state_manager
