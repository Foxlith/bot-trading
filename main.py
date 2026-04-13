"""
Trading Bot - Motor Principal
==============================
Bot de trading automatizado para criptomonedas
Objetivo: Duplicar capital en 1-2 años
"""

import time
import signal
import sys
import threading
import asyncio
from decimal import Decimal
from datetime import datetime, timedelta
from typing import Dict, Any
from loguru import logger

# Configurar logging
logger.remove()
logger.add(
    sys.stdout,
    format="<green>{time:HH:mm:ss}</green> | <level>{level: <8}</level> | <cyan>{message}</cyan>",
    level="INFO"
)
logger.add(
    "logs/bot_{time:YYYY-MM-DD}.log",
    rotation="1 day",
    retention="30 days",
    level="DEBUG"
)

# Imports del proyecto
from config.settings import PORTFOLIO, OPERATION_MODE, STRATEGIES, TRADING_COSTS, CAPITAL, OLLAMA
from src.core.state_manager import get_state_manager
from src.core.exchange_manager import get_exchange
from src.core.data_manager import get_data_manager
from src.strategies.dca_strategy import DCAIntelligentStrategy
from src.strategies.grid_strategy import GridTradingStrategy
from src.strategies.technical_strategy import TechnicalStrategy
from src.risk.risk_manager import get_risk_manager
from src.notifications.telegram_notifier import get_notifier
from src.notifications.telegram_bot import TelegramBotInteractivo
from src.utils.transaction_manager import TransactionManager
from src.ai.ollama_advisor import get_ai_advisor


class TradingBot:
    """
    Motor principal del bot de trading.
    
    Coordina todas las estrategias, gestión de riesgo y ejecución.
    """
    
    def __init__(self):
        logger.info("=" * 50)
        logger.info("🤖 INICIANDO BOT DE TRADING")
        logger.info("=" * 50)
        
        # Componentes principales
        self.state_manager = get_state_manager()
        self.exchange = get_exchange()
        self.data_manager = get_data_manager()
        self.risk_manager = get_risk_manager()
        self.notifier = get_notifier()
        
        # 🧠 AI Advisor (Ollama)
        self.ai_advisor = get_ai_advisor()
        
        # Estrategias
        self.strategies = {
            "dca": DCAIntelligentStrategy(),
            "grid": GridTradingStrategy(),
            "technical": TechnicalStrategy(),
        }
        
        # Estado
        self.is_running = False
        self.last_cycle = None
        self.cycle_interval = 60  # segundos entre ciclos
        self.last_hourly_update = datetime.now()
        
        # Inicializar reportes con fecha de ayer para que se puedan enviar el día que se inicia el bot
        yesterday = datetime.now().date() - timedelta(days=1)
        self.last_weekly_check = yesterday
        self.last_ai_report = yesterday
        
        # Cooldown tras stop-loss de emergencia (símbolo -> datetime)
        self._grid_stoploss_cooldowns = {}
        
        # Cooldown para ventas activadas por IA (evita vender en micro-lotes cada ciclo)
        # La IA solo puede recomendar una venta cada 4h por símbolo (igual que el DCA buy interval)
        self._ai_sell_cooldowns: dict = {}
        
        # Estadísticas
        self.stats = {
            "start_time": datetime.now(),
            "cycles": 0,
            "trades": 0,
            "errors": 0,
        }
        
        # Configurar señal de parada
        signal.signal(signal.SIGINT, self._handle_shutdown)
        signal.signal(signal.SIGTERM, self._handle_shutdown)
        
        # === FASE 2: RECONCILIACIÓN AL INICIO ===
        self._reconcile_on_startup()
        
        logger.info(f"📊 Modo: {OPERATION_MODE['mode'].upper()}")
        logger.info(f"📈 Pares: {list(PORTFOLIO.keys())}")
        self._log_strategies()
    
    def _reconcile_on_startup(self) -> None:
        """
        Reconciliación al inicio: Compara posiciones en Binance vs DB local.
        Detecta trades huérfanos (existentes en exchange pero no en DB).
        """
        logger.info("🔍 Ejecutando reconciliación de posiciones...")
        
        try:
            # 1. Obtener balance actual del exchange
            exchange_balance = self.exchange.get_balance()
            
            # 2. Obtener posiciones abiertas en DB
            db_positions = self.state_manager.get_open_positions()
            
            # Crear set de símbolos en DB
            db_symbols = {pos.get('symbol') for pos in db_positions}
            
            # 3. Verificar cada asset con balance > 0
            discrepancies = []
            for asset, amount in exchange_balance.items():
                if asset == "USDT" or float(amount) < 0.000001:
                    continue
                
                symbol = f"{asset}/USDT"
                
                # Verificar si hay balance en exchange pero no en DB
                if symbol not in db_symbols and float(amount) > 0:
                    discrepancies.append({
                        "type": "ORPHAN_IN_EXCHANGE",
                        "symbol": symbol,
                        "amount": float(amount),
                        "action": "IMPORT_TO_DB"
                    })
            
            # 4. Verificar posiciones en DB que no existen en exchange
            for pos in db_positions:
                symbol = pos.get('symbol', '')
                base = symbol.split('/')[0] if '/' in symbol else symbol
                exchange_amount = float(exchange_balance.get(base, 0))
                db_amount = float(pos.get('amount', 0))
                
                if exchange_amount < db_amount * 0.99:  # 1% tolerance
                    discrepancies.append({
                        "type": "ORPHAN_IN_DB", 
                        "symbol": symbol,
                        "db_amount": db_amount,
                        "exchange_amount": exchange_amount,
                        "action": "REVIEW_REQUIRED"
                    })
            
            # 5. Reportar discrepancias
            if discrepancies:
                logger.warning(f"⚠️ DISCREPANCIAS DETECTADAS: {len(discrepancies)}")
                for d in discrepancies:
                    if d["type"] == "ORPHAN_IN_EXCHANGE":
                        logger.warning(f"   📍 {d['symbol']}: {d['amount']:.6f} en Exchange pero NO en DB")
                        # En modo PAPER, importar automáticamente
                        if OPERATION_MODE['mode'] == 'paper':
                            ticker = self.exchange.get_ticker(d['symbol'])
                            if ticker and ticker.get('last'):
                                self.state_manager.save_position(
                                    symbol=d['symbol'],
                                    strategy="Reconciled",
                                    entry_price=ticker['last'],
                                    amount=d['amount'],
                                    extra_data={"reconciled": True, "reconciled_at": datetime.now().isoformat()}
                                )
                                logger.info(f"   ✅ Posición importada automáticamente a DB")
                    else:
                        logger.warning(f"   📍 {d['symbol']}: DB tiene {d['db_amount']:.6f} pero Exchange {d['exchange_amount']:.6f}")
                        
                        # En modo PAPER: "Trust Exchange"
                        # Si DB dice que tenemos más de lo que realmente hay, cerramos la posición en DB
                        # y dejamos que en el siguiente ciclo se re-importe lo que sí hay (si aplica)
                        if OPERATION_MODE['mode'] == 'paper':
                            # Buscar todas las posiciones de este símbolo y cerrarlas para limpiar estado
                            positions_to_close = [p for p in db_positions if p['symbol'] == d['symbol']]
                            for pos in positions_to_close:
                                if 'id' in pos:
                                    self.state_manager.close_position(
                                        position_id=pos['id'],
                                        exit_price=0, 
                                        profit=0,
                                        fee_paid=0
                                    )
                            logger.info(f"   🗑️ {len(positions_to_close)} posiciones fantasma cerradas en DB. (Sincronización forzada)")
                            
                            # Si queda saldo real en exchange, lo re-importamos como nueva posición limpia
                            if d['exchange_amount'] > 0.00001:  # Ignorar polvo
                                ticker = self.exchange.get_ticker(d['symbol'])
                                price = ticker['last'] if ticker else 0
                                self.state_manager.save_position(
                                    symbol=d['symbol'],
                                    strategy="Reconciled",
                                    entry_price=price,
                                    amount=d['exchange_amount'], # FIX: Usar la cantidad REAL del exchange, no la del dict original
                                    extra_data={"reconciled": True, "reconciled_after_fix": True}
                                )
                                logger.info(f"   ✨ Saldo remanente ({d['amount']:.6f}) re-importado correctamente.")
                
                # Notificar por Telegram
                self.notifier.notify_error(
                    f"Reconciliación encontró {len(discrepancies)} discrepancias",
                    "Startup Sync"
                )
            else:
                logger.info("✅ Reconciliación completada: Sin discrepancias")
                
        except Exception as e:
            logger.error(f"❌ Error en reconciliación: {e}")
            # No fatalizar el bot, solo alertar
    
    def _log_strategies(self) -> None:
        """Muestra las estrategias activas."""
        logger.info("📋 Estrategias activas:")
        for name, strategy in self.strategies.items():
            if strategy.is_active:
                logger.info(f"   ✅ {strategy.name} ({strategy.allocation_pct*100:.0f}%)")
    
    def _handle_shutdown(self, signum, frame) -> None:
        """Maneja el cierre ordenado del bot."""
        logger.info("🛑 Señal de cierre recibida...")
        self.stop()
    
    def start(self) -> None:
        """Inicia el bot."""
        self.is_running = True
        self.notifier.notify_bot_started({
            'mode': OPERATION_MODE['mode'].upper(),
            'pairs': list(PORTFOLIO.keys())
        })
        
        logger.info("🚀 Bot iniciado - Entrando en loop principal")
        
        try:
            self._main_loop()
        except Exception as e:
            logger.error(f"❌ Error fatal: {e}")
            self.notifier.notify_error(str(e), "Main loop")
        finally:
            self._cleanup()
    
    def stop(self) -> None:
        """Detiene el bot."""
        self.is_running = False
        logger.info("🛑 Deteniendo bot...")
    
    def _main_loop(self) -> None:
        """Loop principal del bot."""
        while self.is_running:
            try:
                self._run_cycle()
                self._wait_for_next_cycle()
            except KeyboardInterrupt:
                break
            except Exception as e:
                self.stats["errors"] += 1
                logger.exception(f"Error en ciclo: {e}")
                self.notifier.notify_error(str(e), "Trading cycle")
                time.sleep(30)  # Esperar antes de reintentar
    
    def _run_cycle(self) -> None:
        """Ejecuta un ciclo de trading."""
        self.stats["cycles"] += 1
        cycle_start = datetime.now()
        
        logger.info(f"🔄 Ciclo #{self.stats['cycles']} - {cycle_start.strftime('%H:%M:%S')}")
        
        # Verificar si podemos tradear
        risk_check = self.risk_manager.can_trade()
        if not risk_check["can_trade"]:
            logger.warning(f"⚠️ Trading pausado: {risk_check['reason']}")
            return
        
        # Procesar cada par del portafolio
        for symbol, config in PORTFOLIO.items():
            try:
                self._process_symbol(symbol, config)
            except Exception as e:
                import traceback
                logger.error(f"Error procesando {symbol}: {e}")
                logger.error(traceback.format_exc())
        
        # Actualizar estadísticas
        self.last_cycle = cycle_start
        
        # Log de estado
        self._log_status()
        
        # Actualización horaria de Telegram
        if datetime.now() - self.last_hourly_update >= timedelta(hours=1):
            self._send_hourly_update()
            self.last_hourly_update = datetime.now()
            
        # Reporte semanal (Domingo 19:00)
        self._check_weekly_report()
        
        # 🧠 Reporte diario IA
        self._check_ai_daily_report()
    
    def _process_symbol(self, symbol: str, config: Dict) -> None:
        """Procesa un par de trading."""
        # Obtener datos del mercado
        data = self.data_manager.get_market_summary(symbol)
        
        if "error" in data:
            logger.warning(f"⚠️ No hay datos para {symbol}")
            return
        
        logger.debug(f"📊 {symbol}: ${data['price']:.2f} | RSI:{data['rsi']:.0f} | {data['trend']}")
        
        # ===== FILTRO EMA 200 + SELL-ONLY MODE =====
        ema_200 = float(data.get("ema_200", 0))
        current_price = float(data.get("price", 0))
        is_sell_only = config.get("sell_only", False)
        
        # Determinar si podemos comprar (Grid & Technical)
        can_buy = True
        if is_sell_only:
            can_buy = False
            logger.debug(f"🔒 {symbol}: Modo SELL-ONLY (solo ventas)")
        elif ema_200 > 0 and current_price < ema_200 * 0.995:  # 0.5% margen de tolerancia
            can_buy = False
            logger.info(f"⛔ {symbol}: Precio ${current_price:.2f} < EMA200 ${ema_200:.2f} (margen 0.5%) → Solo ventas")
        
        # Inyectar flag para Grid y Technical
        data["can_buy"] = can_buy
        
        # Pre-chequeo de balance USDT (una sola consulta por ciclo, compartida por todas las estrategias)
        # Evita que la IA pierda 20-30s consultando cuando no hay saldo para comprar
        balance = self.exchange.get_balance()
        available_usdt = float(balance.get("USDT", 0))
        data["available_usdt"] = available_usdt  # Inyectar para que las estrategias lo usen
        MIN_ORDER_USD = 3.0  # Mínimo para ejecutar cualquier compra
        
        if available_usdt < MIN_ORDER_USD:
            logger.debug(f"💤 {symbol}: Sin saldo suficiente (${available_usdt:.2f} < ${MIN_ORDER_USD:.2f}) - IA no consultada")
        
        # DCA: SIEMPRE puede comprar (excepto sell_only)
        # La filosofía DCA requiere compras regulares en TODAS las condiciones de mercado
        dca_can_buy = not is_sell_only and available_usdt >= MIN_ORDER_USD
        
        # Ejecutar estrategias
        # NOTA: La IA se consulta DENTRO de cada estrategia solo cuando hay señal real
        # (no preventivamente cada ciclo, ahorrando ~30s de latencia)
        if STRATEGIES["dca_intelligent"]["enabled"]:
            self._run_dca_strategy(symbol, data, config, dca_can_buy=dca_can_buy)
        
        if STRATEGIES["grid_trading"]["enabled"] and available_usdt >= MIN_ORDER_USD:
            self._run_grid_strategy(symbol, data, config)
        
        if STRATEGIES["technical_rsi_macd"]["enabled"] and can_buy and available_usdt >= MIN_ORDER_USD:
            self._run_technical_strategy(symbol, data, config)
    
    def _run_dca_strategy(self, symbol: str, data: Dict, config: Dict, dca_can_buy: bool = True) -> None:
        """Ejecuta la estrategia DCA.
        
        NOTA: DCA está EXENTO del filtro EMA-200. Solo se bloquea si sell_only=True.
        La filosofía DCA es acumular en todas las condiciones de mercado.
        """
        dca = self.strategies["dca"]
        
        # DCA usa su propio flag (exento de EMA-200)
        if dca_can_buy:
            entry_signal = dca.should_enter(symbol, data)
        else:
            entry_signal = None
        if entry_signal:
            # 🧠 AI Filter: Solo consultar cuando hay señal REAL y hay saldo suficiente
            if self.ai_advisor.is_available() and OLLAMA.get("filter_enabled", False):
                ai_result = self.ai_advisor.analyze_trade_signal(
                    symbol=symbol,
                    strategy="DCA",
                    signal_type="buy",
                    market_data=data,
                )
                if not ai_result.get("approved", True):
                    logger.info(f"🧠 AI BLOQUEÓ DCA {symbol}: {ai_result.get('reasoning', '')}")
                    return
            # Calcular tamaño de posición
            position = self.risk_manager.calculate_position_size(
                symbol,
                data["price"],
                dca.allocation_pct * config["allocation"]
            )
            
            if position["amount"] > 0:
                # Ejecutar compra
                order = self.exchange.place_order(
                    symbol,
                    "buy",
                    position["amount"]
                )
                
                if "error" not in order:
                    dca.execute_buy(symbol, position["amount"], data["price"])
                    
                    # Calcular fee y generar ID para notificación
                    # position["amount"] es Decimal, data["price"] es float (o Decimal str), TRADING_COSTS es float
                    fee_paid = float(position["amount"]) * float(data["price"]) * TRADING_COSTS["taker_fee_pct"]
                    tx_id = TransactionManager.generate_tx_id(symbol, "buy", "DCA")
                    
                    self.notifier.notify_trade_open({
                        "tx_id": tx_id,
                        "symbol": symbol,
                        "side": "buy",
                        "price": data["price"],
                        "amount": position["amount"],
                        "strategy": "DCA Intelligent",
                        "fee_paid": fee_paid,
                        "value_usd": float(position["amount"]) * data["price"]
                    })
                    self.stats["trades"] += 1
        
        # Verificar salida normal (DCA reglas fallback: +15% ganancia + RSI>75)
        exit_signal = dca.should_exit(symbol, {}, data)
        
        # 🧠 AI Sell DCA — Cerebro principal de decisiones de venta
        # Filosofía: La IA analiza el mercado completo y decide si es buen momento para vender.
        # Condiciones para consultar: cooldown 4h + ganancia >= 2%
        if not exit_signal and self.ai_advisor.is_available() and OLLAMA.get("filter_enabled", False):
            accumulated = float(dca.accumulated.get(symbol, 0))
            if accumulated > 0:
                entry_price = float(dca.entry_prices.get(symbol, 0))
                current_price = float(data.get("price", 0))
                profit_pct = ((current_price - entry_price) / entry_price * 100) if entry_price > 0 else 0
                
                # Cooldown de 4h (alineado con el intervalo de compra DCA)
                ai_sell_key = f"ai_sell_{symbol}"
                last_ai_eval = self._ai_sell_cooldowns.get(ai_sell_key)
                cooldown_ok = (
                    last_ai_eval is None or
                    (datetime.now() - last_ai_eval).total_seconds() >= 4 * 3600
                )
                
                # Consultar IA si hay ganancia >= 2% y el cooldown lo permite
                # La IA decide si vale la pena vender según el contexto completo del mercado
                if cooldown_ok and profit_pct >= 2.0:
                    logger.info(
                        f"🧠 AI evaluando venta DCA {symbol}: "
                        f"Ganancia {profit_pct:.1f}% | Acumulado: {accumulated:.8f}"
                    )
                    ai_sell = self.ai_advisor.analyze_sell_opportunity(
                        symbol=symbol,
                        strategy="DCA",
                        market_data=data,
                        position_data={
                            "entry_price": entry_price,
                            "accumulated": accumulated,
                        },
                    )
                    # Registrar cooldown SIEMPRE (consultó, no vuelve hasta dentro de 4h)
                    self._ai_sell_cooldowns[ai_sell_key] = datetime.now()
                    
                    if ai_sell.get("should_sell", False):
                        urgency = ai_sell.get("urgency", 0)
                        ai_sell_pct = ai_sell.get("sell_pct", 0.25)
                        
                        # Calcular valores para el log
                        sell_amount_preview = accumulated * ai_sell_pct
                        sell_value_preview = sell_amount_preview * current_price
                        
                        logger.info(
                            f"🧠 AI OPORTUNIDAD VENTA DCA {symbol} | "
                            f"Urgencia: {urgency}/10 | Vender {int(ai_sell_pct*100)}% | "
                            f"Ganancia: {profit_pct:.1f}% | "
                            f"Valor venta: ~${sell_value_preview:.2f} | "
                            f"{ai_sell.get('reasoning', '')}"
                        )
                        exit_signal = {
                            "sell_pct": ai_sell_pct,
                            "reason": f"IA: {ai_sell.get('reasoning', '')} (+{profit_pct:.1f}%, urgencia {urgency}/10)"
                        }
                    else:
                        logger.info(
                            f"🧠 AI recomienda MANTENER {symbol} | "
                            f"Ganancia actual: {profit_pct:.1f}% | {ai_sell.get('reasoning', '')}"
                        )

        
        if exit_signal:
            # FIX Bug 6: Primero ejecutar la orden en el exchange, LUEGO actualizar estado interno
            # Calcular la cantidad a vender antes de modificar el estado
            sell_pct = exit_signal["sell_pct"]
            # DCA guarda acumulado en dca.accumulated (no dca.positions)
            total_amount = float(dca.accumulated.get(symbol, 0))
            sell_amount = total_amount * sell_pct
            
            if sell_amount > 0:
                order = self.exchange.place_order(symbol, "sell", sell_amount)
                
                if "error" not in order:
                    # Orden exitosa -> ahora sí actualizar estado interno del DCA
                    dca.execute_sell(
                        symbol,
                        exit_signal["sell_pct"],
                        data["price"]
                    )
                    
                    # Calcular Net Profit y Fees
                    entry_price = float(dca.entry_prices.get(symbol, data["price"]))
                    f_sell_amount = float(sell_amount)
                    gross_profit = (data["price"] - entry_price) * f_sell_amount
                    fee_paid = (data["price"] + entry_price) * f_sell_amount * TRADING_COSTS["taker_fee_pct"]
                    net_profit = gross_profit - fee_paid
                    
                    # Registrar P&L en Risk Manager
                    self.risk_manager.record_trade_result(net_profit, fee_paid, gross_profit)
                    
                    tx_id = TransactionManager.generate_tx_id(symbol, "sell", "DCA")
                    
                    self.notifier.notify_trade_close({
                        "tx_id": tx_id,
                        "symbol": symbol,
                        "side": "sell",
                        "price": data["price"],
                        "amount": sell_amount,
                        "profit": net_profit,
                        "fee_paid": fee_paid,
                        "entry_price": entry_price,
                        "strategy": "DCA Intelligent"
                    })
                else:
                    logger.warning(f"⚠️ DCA {symbol}: Orden de venta rechazada: {order}")
    
    def _run_grid_strategy(self, symbol: str, data: Dict, config: Dict) -> None:
        """Ejecuta la estrategia Grid."""
        grid = self.strategies["grid"]
        
        # === COOLDOWN POST STOP-LOSS: No configurar grid si está en cooldown ===
        if symbol in self._grid_stoploss_cooldowns:
            cooldown_until = self._grid_stoploss_cooldowns[symbol]
            if datetime.now() < cooldown_until:
                remaining = (cooldown_until - datetime.now()).total_seconds() / 3600
                logger.debug(f"⏳ Grid {symbol}: Cooldown post stop-loss activo. Faltan {remaining:.1f}h")
                return  # No hacer NADA con este símbolo
            else:
                # Cooldown expiró, limpiar y permitir reconfiguración
                del self._grid_stoploss_cooldowns[symbol]
                logger.info(f"✅ Grid {symbol}: Cooldown expirado. Permitiendo reconfiguración.")
        
        # Configurar grid si no existe (solo si can_buy)
        if data.get("can_buy", True) and symbol not in grid.grids:
            capital = float(self.risk_manager.current_capital) * grid.allocation_pct * config["allocation"]
            grid.setup_grid(
                symbol, 
                data["price"], 
                capital,
                high_24h=data.get("high_24h", 0),
                low_24h=data.get("low_24h", 0)
            )
        
        # Si no hay grid configurada (y no podemos comprar), no hay nada que hacer
        if symbol not in grid.grids:
            return
        
        # Analizar estado de la grid
        analysis = grid.analyze(symbol, data)
        
        # STOP-LOSS PARCIAL: Si pérdida entre -8% y -20%, cerrar peor nivel
        if analysis.get("partial_stop", False):
            worst_level = analysis.get("worst_level")
            if worst_level:
                self._close_worst_grid_level(symbol, data, grid, worst_level)
                return  # No procesar más señales este ciclo
        
        # STOP-LOSS TOTAL DE EMERGENCIA: Si pérdida > 20% (crash real), cerrar TODO
        if analysis.get("emergency_stop", False):
            logger.warning(f"🛑 EJECUTANDO STOP-LOSS DE EMERGENCIA TOTAL para Grid {symbol}")
            self._close_all_grid_positions(symbol, data, grid)
            return  # No procesar más señales para este símbolo
        
        # Verificar compras (solo si can_buy)
        if data.get("can_buy", True):
            buy_signal = grid.should_enter(symbol, data)
        else:
            buy_signal = None
        if buy_signal:
            # 🧠 AI Filter: Solo consultar cuando hay señal REAL de compra Grid
            if self.ai_advisor.is_available() and OLLAMA.get("filter_enabled", False):
                ai_result = self.ai_advisor.analyze_trade_signal(
                    symbol=symbol,
                    strategy="Grid",
                    signal_type="buy",
                    market_data=data,
                )
                if not ai_result.get("approved", True):
                    logger.info(f"🧠 AI BLOQUEÓ Grid {symbol}: {ai_result.get('reasoning', '')}")
                    return
            
            # grid.grids uses float logic mostly, but if order_size_usd became Decimal in future, convert
            order_size_usd = float(grid.grids[symbol]["order_size_usd"])
            order_size = order_size_usd / data["price"]
            
            # Verificar balance ANTES de intentar comprar (evita errores innecesarios)
            balance = self.exchange.get_balance()
            available_usdt = float(balance.get("USDT", 0))
            if available_usdt < order_size_usd:
                logger.debug(f"💤 Grid {symbol}: Balance insuficiente (${available_usdt:.2f} < ${order_size_usd:.2f}). Esperando liquidez.")
                return
            
            order = self.exchange.place_order(
                symbol,
                "buy",
                order_size,
                "limit",
                buy_signal["price"]
            )
            
            # Validación robusta de orden ejecutada
            order_valid = (
                "error" not in order and 
                order is not None and
                (order.get("id") or order.get("filled", 0) > 0 or order.get("status") == "closed")
            )
            
            if order_valid:
                # Usar precio ejecutado real si está disponible, sino usar señal
                exec_price = order.get("price") or order.get("average") or buy_signal["price"]
                exec_amount = order.get("filled") or order_size
                
                grid.execute_grid_buy(
                    symbol,
                    buy_signal["level"],
                    exec_amount,
                    exec_price
                )
                
                # Calcular fee y generar ID para notificación
                fee_paid = exec_amount * exec_price * TRADING_COSTS["taker_fee_pct"]
                tx_id = TransactionManager.generate_tx_id(symbol, "buy", "Grid")
                
                self.notifier.notify_trade_open({
                    "tx_id": tx_id,
                    "symbol": symbol,
                    "side": "buy",
                    "price": exec_price,
                    "amount": exec_amount,
                    "strategy": "Grid Trading",
                    "fee_paid": fee_paid,
                    "value_usd": exec_amount * exec_price
                })
                
                self.stats["trades"] += 1
            else:
                logger.warning(f"⚠️ Grid {symbol}: Orden no válida o rechazada: {order}")
        
        # Verificar ventas (ahora should_exit retorna una LISTA de niveles)
        sell_signals = grid.should_exit(symbol, {}, data)
        if sell_signals:
            for sell_signal in sell_signals:
                # Buscar el nivel correcto en la lista
                level_data = next((l for l in grid.grids[symbol]["levels"] if l["level"] == sell_signal["level"]), {})
                sell_amount = level_data.get("bought_amount", 0)
                entry_price_level = level_data.get("bought_price", data["price"])
                
                profit = grid.execute_grid_sell(
                    symbol,
                    sell_signal["level"],
                    sell_signal["price"]
                )
                
                # Calcular fee estimado (entrada + salida)
                estimated_fee = float(sell_signal["price"]) * float(sell_amount) * 0.002
                f_profit = float(profit)
                
                if f_profit != 0:
                    alerts = self.risk_manager.record_trade_result(f_profit, fee_paid=estimated_fee, gross_profit=f_profit + estimated_fee)
                    
                    # Check Inefficiency Alert
                    if "inefficiency" in alerts:
                        self.notifier.notify_inefficiency_warning(alerts["inefficiency"])
                    
                    self.stats["trades"] += 1
                    
                    # Notificar venta de Grid
                    tx_id = TransactionManager.generate_tx_id(symbol, "sell", "Grid")
                    
                    self.notifier.notify_trade_close({
                        "tx_id": tx_id,
                        "symbol": symbol,
                        "side": "sell",
                        "price": sell_signal["price"],
                        "entry_price": entry_price_level,
                        "amount": sell_amount,
                        "profit": profit,
                        "fee_paid": estimated_fee,
                        "strategy": "Grid Trading"
                    })
                    logger.info(f"📉 Grid {symbol} - Venta nivel {sell_signal['level']}: Profit ${profit:.2f}")
        
        # === RECENTRADO INTELIGENTE ===
        # Verificar si la grid necesita recentrarse (solo en condiciones seguras)
        trend = data.get("trend", "unknown")
        recenter_result = grid.intelligent_recenter_grid(
            symbol, 
            data["price"], 
            trend,
            self.data_manager
        )
        
        # Notificar según el resultado
        if recenter_result["status"] == "executed":
            self.notifier.send(
                f"🔄 <b>GRID RECENTRADA - {symbol}</b>\n\n"
                f"📈 {recenter_result['reason']}\n"
                f"📍 Centro anterior: ${recenter_result['old_center']:,.2f}\n"
                f"📍 Nuevo centro: ${recenter_result['new_center']:,.2f}\n"
                f"📊 Cambio: +{recenter_result['change_pct']:.1f}%"
            )
        elif recenter_result["status"] == "alert":
            # Solo loguear alertas, no spamear Telegram
            logger.warning(f"⚠️ Grid {symbol}: {recenter_result['reason']}")
    
    def _close_worst_grid_level(self, symbol: str, data: Dict, grid, worst_level: Dict) -> None:
        """Cierra solo el peor nivel de la Grid (Stop-Loss Parcial)."""
        if symbol not in grid.grids:
            return
        
        current_price = data["price"]
        sell_amount = worst_level.get("bought_amount", 0)
        
        if sell_amount <= 0:
            return
        
        order = self.exchange.place_order(
            symbol,
            "sell",
            sell_amount,
            "market"
        )
        
        if "error" not in order:
            buy_price = worst_level.get("bought_price", current_price)
            loss = (current_price - buy_price) * sell_amount
            
            try:
                d_loss = Decimal(str(loss)) if loss is not None and loss == loss else Decimal('0')
            except Exception:
                d_loss = Decimal('0')
            
            # Registrar en historial
            self.state_manager.add_trade_to_history(
                symbol=symbol,
                strategy="Grid Trading",
                side="sell",
                entry_price=buy_price,
                exit_price=current_price,
                amount=sell_amount,
                profit=float(loss),
                profit_pct=((current_price - buy_price) / buy_price) * 100 if buy_price > 0 else 0
            )
            
            # Reset solo este nivel
            worst_level["status"] = "pending"
            worst_level["amount"] = 0
            grid._save_state()
            
            logger.warning(f"⚠️ GRID STOP PARCIAL: Cerrado nivel {worst_level['level']} de {symbol}. Pérdida: ${float(d_loss):.2f}")
            self.notifier.send(
                f"⚠️ <b>STOP-LOSS PARCIAL</b>\n\n"
                f"📊 <b>Símbolo:</b> {symbol}\n"
                f"📉 <b>Nivel cerrado:</b> {worst_level['level']}\n"
                f"💸 <b>Pérdida:</b> ${float(d_loss):.2f}\n\n"
                f"💡 Se cerró solo la peor posición para reducir riesgo."
            )
    
    def _close_all_grid_positions(self, symbol: str, data: Dict, grid) -> None:
        """Cierra todas las posiciones de Grid para un símbolo (Stop-Loss de Emergencia)."""
        if symbol not in grid.grids:
            return
        
        total_loss = Decimal('0')
        closed_count = 0
        
        for level in grid.grids[symbol]["levels"]:
            if level["status"] == "bought":
                sell_amount = level.get("bought_amount", 0)
                if sell_amount > 0:
                    # Ejecutar venta al precio actual
                    current_price = data["price"]
                    
                    order = self.exchange.place_order(
                        symbol,
                        "sell",
                        sell_amount,
                        "market"  # Market order para salida rápida
                    )
                    
                    if "error" not in order:
                        # Calcular pérdida con safe_decimal
                        buy_price = level.get("bought_price", current_price)
                        loss = (current_price - buy_price) * sell_amount
                        try:
                            from decimal import InvalidOperation
                            d_loss = Decimal(str(loss)) if loss is not None and loss == loss else Decimal('0')
                        except (InvalidOperation, Exception):
                            d_loss = Decimal('0')
                        total_loss += d_loss
                        
                        # Registrar en historial
                        self.state_manager.add_trade_to_history(
                            symbol=symbol,
                            strategy="Grid Trading",
                            side="sell",
                            entry_price=buy_price,
                            exit_price=current_price,
                            amount=sell_amount,
                            profit=float(loss),
                            profit_pct=((current_price - buy_price) / buy_price) * 100 if buy_price > 0 else 0
                        )
                        
                        # Reset nivel
                        level["status"] = "pending"
                        level["amount"] = 0
                        closed_count += 1
        
        # Guardar estado y notificar
        grid._save_state()
        
        if closed_count > 0:
            logger.warning(f"🛑 GRID STOP-LOSS: Cerradas {closed_count} posiciones de {symbol}. Pérdida total: ${float(total_loss):.2f}")
            self.notifier.send(
                f"🛑 <b>STOP-LOSS DE EMERGENCIA ACTIVADO</b>\n\n"
                f"📊 <b>Símbolo:</b> {symbol}\n"
                f"📉 <b>Posiciones cerradas:</b> {closed_count}\n"
                f"💸 <b>Pérdida realizada:</b> ${float(total_loss):.2f}\n\n"
                f"⚠️ Grid pausada por 24h"
            )
            
            # Eliminar grid y activar cooldown de 24h
            del grid.grids[symbol]
            grid._save_state()
            
            # === ACTIVAR COOLDOWN DE 24H ===
            self._grid_stoploss_cooldowns[symbol] = datetime.now() + timedelta(hours=24)
            logger.warning(f"⏳ Grid {symbol}: Cooldown de 24h activado hasta {self._grid_stoploss_cooldowns[symbol].strftime('%Y-%m-%d %H:%M')}")
    
    def _run_technical_strategy(self, symbol: str, data: Dict, config: Dict) -> None:
        """Ejecuta la estrategia técnica."""
        tech = self.strategies["technical"]
        
        # Verificar entrada
        entry_signal = tech.should_enter(symbol, data)
        if entry_signal:
            # 🧠 AI Filter: Solo consultar cuando hay señal REAL de compra Technical
            if self.ai_advisor.is_available() and OLLAMA.get("filter_enabled", False):
                ai_result = self.ai_advisor.analyze_trade_signal(
                    symbol=symbol,
                    strategy="Technical",
                    signal_type="buy",
                    market_data=data,
                )
                if not ai_result.get("approved", True):
                    logger.info(f"🧠 AI BLOQUEÓ Technical {symbol}: {ai_result.get('reasoning', '')}")
                    return
            
            position = self.risk_manager.calculate_position_size(
                symbol,
                data["price"],
                tech.allocation_pct * config["allocation"]
            )
            
            if position["amount"] > 0:
                order = self.exchange.place_order(
                    symbol,
                    "buy",
                    position["amount"]
                )
                
                if "error" not in order:
                    tech.open_position(
                        symbol,
                        position["amount"],
                        data["price"],
                        entry_signal["stop_loss"],
                        entry_signal["take_profit"]
                    )
                    # Calcular fee y generar ID
                    fee_paid = float(position["amount"]) * data["price"] * TRADING_COSTS["taker_fee_pct"]
                    tx_id = TransactionManager.generate_tx_id(symbol, "buy", "Technical")
                    
                    self.notifier.notify_trade_open({
                        "tx_id": tx_id,
                        "symbol": symbol,
                        "side": "buy",
                        "price": data["price"],
                        "amount": position["amount"],
                        "strategy": "Technical RSI+MACD",
                        "fee_paid": fee_paid,
                        "value_usd": float(position["amount"]) * data["price"]
                    })
                    self.stats["trades"] += 1
        
        # Verificar salida
        positions = tech.get_open_positions()
        if symbol in positions:
            exit_signal = tech.should_exit(symbol, positions[symbol], data)
            if exit_signal:
                profit = tech.close_position(symbol, data["price"])
                
                # Estimate fee for record keeping
                est_fee = (data["price"] + float(positions[symbol]["entry_price"])) * float(positions[symbol]["amount"]) * TRADING_COSTS["taker_fee_pct"]
                
                alerts = self.risk_manager.record_trade_result(profit, fee_paid=est_fee, gross_profit=profit + est_fee)
                if "inefficiency" in alerts:
                    self.notifier.notify_inefficiency_warning(alerts["inefficiency"])
                
                # Calcular Fees (profit ya debería ser neto en technical_strategy fix, pero verifiquemos)
                # En paso 1276 actualicé close_position para retornar NET profit.
                # Estimamos fee reporte
                # est_fee = (data["price"] + positions[symbol]["entry_price"]) * positions[symbol]["amount"] * TRADING_COSTS["taker_fee_pct"] # This line is redundant now
                tx_id = TransactionManager.generate_tx_id(symbol, "sell", "Technical")
                
                self.notifier.notify_trade_close({
                    "tx_id": tx_id,
                    "symbol": symbol,
                    "side": "sell",
                    "price": data["price"],
                    "entry_price": positions[symbol]["entry_price"],
                    "amount": positions[symbol]["amount"],
                    "profit": profit,
                    "fee_paid": est_fee,
                    "strategy": "Technical RSI+MACD",
                    "reason": exit_signal.get("reason", "N/A")  # Muestra si fue Trailing Stop, Take Profit, etc.
                })
    
    def _wait_for_next_cycle(self) -> None:
        """Espera hasta el próximo ciclo."""
        time.sleep(self.cycle_interval)
    
    def _log_status(self) -> None:
        """Muestra estado actual del bot (capital real desde wallet)."""
        balance = self.exchange.get_balance()
        liquid = float(balance.get("USDT", 0))
        assets = 0
        for asset, amount in balance.items():
            if asset != "USDT" and float(amount) > 0:
                try:
                    data = self.data_manager.get_market_summary(f"{asset}/USDT")
                    assets += float(amount) * float(data.get("price", 0))
                except Exception as e:
                    logger.debug(f"Error obteniendo precio de {asset}: {e}")
        total_capital = liquid + assets
        initial = float(CAPITAL['initial_usd'])
        roi = ((total_capital - initial) / initial) * 100 if initial > 0 else 0
        
        logger.info(f"💼 Capital: ${total_capital:.2f} | "
                   f"ROI: {roi:.2f}% | "
                   f"Trades: {self.stats['trades']}")
    
    def _send_hourly_update(self) -> None:
        """Envía actualización horaria a Telegram."""
        market_data = {}
        failed_symbols = []
        
        for symbol in PORTFOLIO.keys():
            try:
                data = self.data_manager.get_market_summary(symbol)
                market_data[symbol] = data
            except Exception as e:
                # Log error en lugar de silenciarlo
                logger.warning(f"⚠️ Error obteniendo datos de {symbol}: {e}")
                failed_symbols.append(symbol)
                market_data[symbol] = {"error": str(e), "stale": True}
        
        # Alertar si >50% de símbolos fallaron
        if len(failed_symbols) > len(PORTFOLIO) / 2:
            logger.error(f"🚨 Más de 50% de símbolos fallaron: {failed_symbols}")
            self.notifier.notify_error(
                f"Fallo de datos en {len(failed_symbols)}/{len(PORTFOLIO)} símbolos",
                "Hourly Update"
            )
        
        # Obtener balance real del exchange (Wallet Check)
        wallet_balance = self.exchange.get_balance()
        self.notifier.notify_hourly_update(market_data, wallet_balance)
        logger.info("📱 Actualización horaria enviada a Telegram")
    
    def _check_weekly_report(self) -> None:
        """Verifica si es Domingo 19:00 para enviar reporte semanal."""
        now = datetime.now()
        is_sunday = now.weekday() == 6
        is_time = now.hour == 19
        
        # Enviar solo una vez al día
        if is_sunday and is_time and self.last_weekly_check != now.date():
            # Recopilar estadísticas
                # Nota: Esto es una estimación. Idealmente StateManager tendría query de 7 días.
                # Usamos acumulados globales.
                stats = self.risk_manager.get_portfolio_stats()
                
                report_data = {
                    "net_profit": stats.get('total_profit', 0),
                    "total_fees": self.risk_manager.daily_stats.get('fees', 0) * 7 if hasattr(self.risk_manager, 'daily_stats') else 0, # Estimación cruda
                    "best_coin": "N/A", # No trackeado por moneda aún
                    "best_coin_profit": 0,
                    "wins": stats.get('winning_trades', 0),
                    "losses": stats.get('losing_trades', 0),
                    "win_rate": stats.get('win_rate', 0)
                }
                
                self.notifier.notify_weekly_report(report_data)
                self.last_weekly_check = now.date()
                logger.info("📱 Reporte semanal enviado a Telegram")
    
    def _check_ai_daily_report(self) -> None:
        """Verifica si es hora de enviar el reporte diario de IA."""
        if not self.ai_advisor.is_available():
            return
        
        now = datetime.now()
        report_hour = OLLAMA.get("daily_report_hour", 20)
        
        # Enviar solo una vez al día a la hora configurada
        if now.hour == report_hour and self.last_ai_report != now.date():
            try:
                logger.info("🧠 Generando reporte diario de IA...")
                
                # Recopilar datos
                daily_stats = self.state_manager.get_trades_by_period(days=1)
                portfolio_stats = self.risk_manager.get_portfolio_stats()
                
                market_data = {}
                for symbol in PORTFOLIO.keys():
                    try:
                        market_data[symbol] = self.data_manager.get_market_summary(symbol)
                    except Exception:
                        pass
                
                portfolio_info = {
                    "current_capital": float(portfolio_stats.get("current_capital", 0)),
                    "roi": float(portfolio_stats.get("roi_pct", 0)),
                }
                
                report = self.ai_advisor.generate_daily_report(
                    daily_stats=daily_stats,
                    market_data=market_data,
                    portfolio_info=portfolio_info,
                )
                
                if report:
                    self.notifier.send(report)
                    logger.info("🧠 Reporte diario IA enviado a Telegram")
                
                self.last_ai_report = now.date()
                
            except Exception as e:
                logger.error(f"Error generando reporte IA: {e}")
        
    def _cleanup(self) -> None:
        """Limpieza al cerrar el bot."""
        runtime = datetime.now() - self.stats["start_time"]
        
        logger.info("=" * 50)
        logger.info("📊 RESUMEN DE SESIÓN")
        logger.info(f"   ⏱️ Duración: {runtime}")
        logger.info(f"   🔄 Ciclos: {self.stats['cycles']}")
        logger.info(f"   📈 Trades: {self.stats['trades']}")
        logger.info(f"   ❌ Errores: {self.stats['errors']}")
        logger.info("=" * 50)
        
        # Obtener estadísticas finales
        portfolio_stats = self.risk_manager.get_portfolio_stats()
        self.notifier.notify_bot_stopped("Cierre controlado", {
            "final_capital": portfolio_stats.get('current_capital', 75),
            "total_trades": self.stats['trades'],
            "total_pnl": portfolio_stats.get('total_profit', 0),
            "win_rate": portfolio_stats.get('win_rate', 0)
        })



def run_telegram_bot():
    """Ejecuta el bot de Telegram en un hilo separado."""
    async def start_bot():
        bot = TelegramBotInteractivo()
        await bot.start()
        # Mantener corriendo
        while True:
            await asyncio.sleep(1)
    
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    try:
        loop.run_until_complete(start_bot())
    except Exception as e:
        logger.error(f"Error en Telegram Bot: {e}")


def main():
    """Punto de entrada principal."""
    import argparse
    
    parser = argparse.ArgumentParser(description="Bot de Trading Automatizado")
    parser.add_argument("--mode", choices=["paper", "live"], default="paper",
                       help="Modo de operación")
    parser.add_argument("--interval", type=int, default=60,
                       help="Intervalo entre ciclos (segundos)")
    parser.add_argument("--no-telegram", action="store_true",
                       help="Desactivar bot interactivo de Telegram")
    
    args = parser.parse_args()
    
    # Actualizar configuración si se pasaron argumentos
    if args.mode:
        OPERATION_MODE["mode"] = args.mode
    
    # Iniciar bot de Telegram interactivo en hilo separado
    if not args.no_telegram:
        telegram_thread = threading.Thread(target=run_telegram_bot, daemon=True)
        telegram_thread.start()
        logger.info("📱 Bot de Telegram iniciado - Usa /informe para análisis")
    
    # Crear e iniciar bot de trading
    bot = TradingBot()
    bot.cycle_interval = args.interval
    bot.start()


if __name__ == "__main__":
    main()
