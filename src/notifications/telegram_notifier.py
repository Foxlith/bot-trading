"""
Telegram Notifier - VERSIÓN MEJORADA
=====================================
Sistema de notificaciones detalladas vía Telegram
"""

import asyncio
from typing import Optional, Dict, Any, List
from datetime import datetime
from loguru import logger
import sys

sys.path.insert(0, str(__file__).replace("\\src\\notifications\\telegram_notifier.py", ""))

from config.settings import TELEGRAM, CAPITAL
from src.core.state_manager import get_state_manager
from src.utils.transaction_manager import TransactionManager

# Intentar importar telegram
try:
    from telegram import Bot
    from telegram.error import TelegramError
    TELEGRAM_AVAILABLE = True
except ImportError:
    TELEGRAM_AVAILABLE = False
    logger.warning("⚠️ python-telegram-bot no instalado. Usando modo mock.")


class TelegramNotifier:
    """
    Notificaciones detalladas de trading por Telegram.
    """
    
    def __init__(self):
        self.enabled = TELEGRAM["enabled"] and TELEGRAM_AVAILABLE
        self.bot_token = TELEGRAM["bot_token"]
        self.chat_id = TELEGRAM["chat_id"]
        self.notifications = TELEGRAM["notifications"]
        
        self.bot: Optional[Bot] = None
        
        # State Manager
        self.state_manager = get_state_manager()
        
        # Cargar estado inicial desde DB
        self._sync_with_db()
        
        if self.enabled and self.bot_token and self.bot_token != "tu_bot_token_aqui":
            try:
                self.bot = Bot(token=self.bot_token)
                logger.info("✅ Telegram Notifier configurado")
            except Exception as e:
                logger.error(f"❌ Error configurando Telegram: {e}")
                self.enabled = False
        else:
            logger.info("ℹ️ Telegram Notifier no configurado")
    
    def _sync_with_db(self) -> None:
        """Sincroniza el estado local con la base de datos."""
        portfolio = self.state_manager.get_portfolio_state()
        if portfolio:
            self.portfolio_value = portfolio.get("current_capital", 75)
            self.total_profit = portfolio.get("total_profit", 0)
            self.trades_count = portfolio.get("trades_count", 0)
            
        stats = self.state_manager.get_trade_stats()
        if stats:
            self.winning_trades = stats.get("winning_trades", 0)
            self.losing_trades = stats.get("losing_trades", 0)
            
        # Recalcular holdings desde posiciones abiertas
        self.holdings = {}
        positions = self.state_manager.get_open_positions()
        for pos in positions:
            symbol = pos["symbol"]
            amount = pos["amount"]
            entry = pos["entry_price"]
            
            if symbol not in self.holdings:
                self.holdings[symbol] = {'amount': 0, 'invested': 0, 'avg_price': 0}
            
            self.holdings[symbol]['amount'] += amount
            self.holdings[symbol]['invested'] += (amount * entry)
            # Recalcular precio promedio simple para visualización
            if self.holdings[symbol]['amount'] > 0:
                self.holdings[symbol]['avg_price'] = self.holdings[symbol]['invested'] / self.holdings[symbol]['amount']
        
        self.total_invested = sum(h['invested'] for h in self.holdings.values())

    async def _send_message(self, message: str, parse_mode: str = "HTML") -> bool:
        """Envía un mensaje de forma asíncrona."""
        if not self.enabled or not self.bot:
            logger.info(f"📱 [TELEGRAM MOCK]: {message[:100]}...")
            return True
        
        try:
            await self.bot.send_message(
                chat_id=self.chat_id,
                text=message,
                parse_mode=parse_mode
            )
            return True
        except TelegramError as e:
            logger.error(f"Error enviando mensaje Telegram: {e}")
            return False
    
    def send(self, message: str) -> bool:
        """Envía un mensaje (wrapper síncrono)."""
        try:
            loop = asyncio.get_event_loop()
        except RuntimeError:
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
        
        return loop.run_until_complete(self._send_message(message))
    
    def notify_trade_open(self, trade: Dict[str, Any]) -> None:
        """
        Notifica apertura de trade con detalles completos.
        Usa TransactionManager para formato estandarizado si es posible.
        """
        if not self.notifications.get("on_trade_open"):
            return
        
        # Si tenemos tx_id, usamos el formato estandarizado del TransactionManager
        if "tx_id" in trade:
            message = TransactionManager.format_telegram_message(trade)
            self.send(message)
            return

        # Fallback a lógica anterior si no hay tx_id (para compatibilidad)
        symbol = trade.get('symbol', 'N/A')
        price = trade.get('price', 0)
        # ... (rest of old logic logic kept minimal or just skipped to avoid dulication risk if I replace huge block)
        # Actually I will replace the whole block to force usage of new format if possible or adapt old data
        
        # Generar ID temporal si no existe para uniformidad
        tx_id = TransactionManager.generate_tx_id(symbol, "buy", trade.get('strategy', 'Unknown'))
        
        # Adaptar datos al formato de TransactionManager
        payload = {
            "tx_id": tx_id,
            "timestamp": datetime.now().isoformat(),
            "symbol": symbol,
            "side": "buy",
            "price": price,
            "amount": trade.get('amount', 0),
            "value_usd": price * trade.get('amount', 0),
            "strategy": trade.get('strategy', 'N/A'),
            "status": "executed",
            "fee_paid": trade.get('fee_paid'), # Might be None
        }
        
        message = TransactionManager.format_telegram_message(payload)
        self.send(message)
    
    def notify_trade_close(self, trade: Dict[str, Any]) -> None:
        """
        Notifica cierre de trade con P&L detallado.
        Usa TransactionManager.
        """
        if not self.notifications.get("on_trade_close"):
            return
        
        # Actualizar stats internos (simplificado para no romper lógica existente)
        # ... (logic to update holdings/stats usually here, but keeping it minimal for formatting fix)
        # Note: holdings update logic is important for state tracking? Yes.
        # But user asked for format fix. I will restore state tracking headers but use new format for message.
        
        symbol = trade.get('symbol', 'N/A')
        exit_price = trade.get('price', 0)
        amount = trade.get('amount', 0)
        entry_price = trade.get('entry_price', exit_price)
        profit = trade.get('profit', 0)
        
        # Update internal stats logic (kept from original)
        self.total_profit += float(profit)
        if profit >= 0:
            self.winning_trades += 1
        else:
            self.losing_trades += 1
            
        if symbol in self.holdings:
            # amount puede ser Decimal (desde DCA/Grid), holdings usa float para reporte
            f_amount = float(amount)
            f_entry = float(entry_price)
            cost_basis = f_entry * f_amount
            
            self.holdings[symbol]['amount'] -= f_amount
            self.holdings[symbol]['invested'] -= cost_basis
            if self.holdings[symbol]['amount'] <= 0.00000001:
                del self.holdings[symbol]
                
        # Send Message using TransactionManager
        if "tx_id" in trade:
            message = TransactionManager.format_telegram_message(trade)
            self.send(message)
            return

        # Adapt payload if tx_id missing
        tx_id = TransactionManager.generate_tx_id(symbol, "sell", trade.get('strategy', 'Unknown'))
        payload = {
            "tx_id": tx_id,
            "timestamp": datetime.now().isoformat(),
            "symbol": symbol,
            "side": "sell",
            "price": float(exit_price) if exit_price else 0,
            "amount": float(amount) if amount else 0,
            "value_usd": float(exit_price) * float(amount) if exit_price and amount else 0,
            "strategy": trade.get('strategy', 'N/A'),
            "profit": float(profit) if profit else 0,
            "status": "executed",
            "fee_paid": trade.get('fee_paid')
        }
        message = TransactionManager.format_telegram_message(payload)
        self.send(message)
    
    def notify_hourly_update(self, market_data: Dict[str, Any], wallet_balance: Dict[str, float] = None) -> None:
        """
        Envía actualización cada hora con estado del mercado.
        USA DATOS REALES DEL EXCHANGE (Wallet Check).
        """
        holdings_text = ""
        portfolio_unrealized = 0
        total_wallet_value = 0
        
        # Si no se pasa balance, intentar usar el interno (fallback)
        if not wallet_balance:
            self._sync_with_db()
            current_holdings = self.holdings
        else:
            # Construir holdings desde el balance real
            current_holdings = {}
            for asset, amount in wallet_balance.items():
                if asset == "USDT" or amount <= 0:
                    continue
                # Buscar par correspondiente (ej: BTC -> BTC/USDT)
                symbol = f"{asset}/USDT" # Asumimos pares base USDT
                
                # Intentar recuperar precio promedio de DB para referencia de P&L
                avg_price = self.holdings.get(symbol, {}).get('avg_price', 0)
                
                current_holdings[symbol] = {
                    'amount': amount,
                    'avg_price': avg_price,
                    # 'invested': amount * avg_price # Costo base estimado
                }

        # Procesar cada holding detectado en la WALLET
        for symbol, data in current_holdings.items():
            amount = data['amount']
            if amount <= 0: continue
            
            current_price = market_data.get(symbol, {}).get('price', 0)
            if current_price == 0:
                 # Intentar buscar precio en holdings si no vino en market_data
                 current_price = self.holdings.get(symbol, {}).get('avg_price', 0)

            current_value = float(amount) * float(current_price)
            total_wallet_value += current_value
            
            # Cálculo de P&L (Solo si tenemos precio de entrada válido)
            avg_entry = data.get('avg_price', 0)
            if avg_entry > 0:
                cost_basis = amount * avg_entry
                unrealized = current_value - cost_basis
                unrealized_pct = ((current_value / cost_basis) - 1) * 100
                emoji = "Mw" if unrealized >= 0 else "📉"
                pnl_str = f"${unrealized:+.2f} ({unrealized_pct:+.1f}%)"
            else:
                emoji = "ℹ️"
                pnl_str = "N/A (Sin precio entrada)"
                unrealized = 0
            
            portfolio_unrealized += unrealized

            holdings_text += f"""
{emoji} <b>{symbol}:</b>
   📦 {amount:.8f}
   💵 Valor: ${current_value:.2f}
   📊 P&L: {pnl_str}
"""
        
        if not holdings_text:
            holdings_text = "\n   📭 Sin posiciones abiertas\n"
        
        # Calcular totales reales
        usdt_balance = wallet_balance.get("USDT", 0) if wallet_balance else self.portfolio_value
        total_account_value = float(usdt_balance) + float(total_wallet_value)
        
        # Calcular ROI real basado en capital inicial
        initial_capital = CAPITAL.get("initial_usd", 75)
        total_roi = ((total_account_value - initial_capital) / initial_capital) * 100
        
        message = f"""
📊 <b>═══ ACTUALIZACIÓN HORARIA ═══</b>

<b>📍 POSICIONES ABIERTAS (WALLET)</b>
{holdings_text}

<b>═══ RESUMEN DE CUENTA ═══</b>

💼 <b>Capital Inicial:</b> ${initial_capital:.2f}
💰 <b>Valor Cuenta:</b> ${total_account_value:.2f}
💵 <b>Saldo USDT:</b> ${usdt_balance:.2f}
📊 <b>P&L Latente:</b> ${portfolio_unrealized:+.2f}
🎯 <b>ROI Real:</b> {total_roi:+.2f}%

<b>═══ ESTADÍSTICAS ═══</b>

📊 <b>Trades:</b> {self.trades_count}
✅ <b>Ganadas:</b> {self.winning_trades}
❌ <b>Perdidas:</b> {self.losing_trades}

⏱️ {datetime.now().strftime('%H:%M:%S - %d/%m/%Y')}
"""
        self.send(message.strip())
    
    def notify_daily_summary(self, stats: Dict[str, Any]) -> None:
        """Envía resumen diario detallado."""
        if not self.notifications.get("daily_summary"):
            return
        
        roi = stats.get('roi_pct', 0)
        emoji = "📈" if roi >= 0 else "📉"
        
        message = f"""
{emoji} <b>═══ RESUMEN DEL DÍA ═══</b>

<b>💰 CAPITAL</b>
💼 <b>Inicial:</b> ${stats.get('initial_capital', self.portfolio_value):.2f}
💵 <b>Final:</b> ${stats.get('current_capital', self.portfolio_value):.2f}
📊 <b>P&L:</b> ${stats.get('daily_pnl', 0):+.2f}

<b>📊 RENDIMIENTO</b>
{emoji} <b>ROI Día:</b> {stats.get('daily_roi', 0):+.2f}%
📈 <b>ROI Total:</b> {roi:+.2f}%

<b>🎯 ESTADÍSTICAS</b>
📊 <b>Trades:</b> {stats.get('trades_today', self.trades_count)}
✅ <b>Win Rate:</b> {stats.get('win_rate', 0):.1f}%
💵 <b>Mejor Trade:</b> ${stats.get('best_trade', 0):+.2f}
💸 <b>Peor Trade:</b> ${stats.get('worst_trade', 0):+.2f}

📅 {datetime.now().strftime('%d/%m/%Y')}
"""
        self.send(message.strip())
    
    def notify_error(self, error: str, context: str = "") -> None:
        """Notifica un error."""
        if not self.notifications.get("on_error"):
            return
        
        message = f"""
🚨 <b>ERROR DETECTADO</b>

⚠️ <b>Error:</b> {error}
📍 <b>Contexto:</b> {context}

⏱️ {datetime.now().strftime('%H:%M:%S')}
"""
        self.send(message.strip())
    
    def notify_risk_alert(self, alert: Dict[str, Any]) -> None:
        """Notifica alerta de riesgo."""
        message = f"""
⚠️ <b>═══ ALERTA DE RIESGO ═══</b>

🔴 <b>Nivel:</b> {alert.get('level', 'N/A').upper()}
📊 <b>Score:</b> {alert.get('score', 0)}/10

<b>Factores:</b>
{chr(10).join('• ' + f for f in alert.get('factors', []))}

⏱️ {datetime.now().strftime('%H:%M:%S')}
"""
        self.send(message.strip())
    
    def notify_bot_started(self, config: Dict[str, Any] = None) -> None:
        """Notifica que el bot ha iniciado con configuración."""
        config = config or {}
        pairs = config.get('pairs', ['BTC/USDT', 'ETH/USDT', 'SOL/USDT'])
        mode = config.get('mode', 'PAPER')
        
        message = f"""
🚀 <b>═══ BOT DE TRADING INICIADO ═══</b>

<b>⚙️ CONFIGURACIÓN</b>
📊 <b>Modo:</b> {mode}
💼 <b>Capital:</b> ${self.portfolio_value:.2f}
🎯 <b>Pares:</b> {', '.join(pairs)}

<b>📋 ESTRATEGIAS ACTIVAS</b>
• DCA Inteligente (40%)
• Grid Trading (30%)
• Análisis Técnico RSI+MACD (30%)

<b>🛡️ GESTIÓN DE RIESGO</b>
• Max posición: 5%
• Stop Loss: 3%
• Take Profit: 6%

✅ <b>Sistema operativo y monitoreando</b>

⏱️ {datetime.now().strftime('%H:%M:%S - %d/%m/%Y')}
"""
        self.send(message.strip())
    
    def notify_bot_stopped(self, reason: str = "Manual", stats: Dict = None) -> None:
        """Notifica que el bot se ha detenido con resumen."""
        stats = stats or {}
        
        message = f"""
🛑 <b>═══ BOT DETENIDO ═══</b>

📋 <b>Razón:</b> {reason}

<b>═══ RESUMEN DE SESIÓN ═══</b>

💼 <b>Capital Final:</b> ${stats.get('final_capital', self.portfolio_value):.2f}
📊 <b>Trades:</b> {stats.get('total_trades', self.trades_count)}
📈 <b>P&L Total:</b> ${stats.get('total_pnl', self.total_profit):+.2f}
🎯 <b>Win Rate:</b> {stats.get('win_rate', 0):.1f}%

⏱️ {datetime.now().strftime('%H:%M:%S - %d/%m/%Y')}
"""
        self.send(message.strip())
    
    def notify_market_analysis(self, analysis: Dict[str, Any]) -> None:
        """Envía análisis del mercado."""
        symbol = analysis.get('symbol', 'N/A')
        price = analysis.get('price', 0)
        rsi = analysis.get('rsi', 50)
        trend = analysis.get('trend', 'sideways')
        signal = analysis.get('signal', 'hold')
        
        # Determinar emojis según condiciones
        if rsi < 30:
            rsi_emoji = "🟢 Sobreventa"
        elif rsi > 70:
            rsi_emoji = "🔴 Sobrecompra"
        else:
            rsi_emoji = "🟡 Neutral"
        
        trend_emoji = {
            'strong_uptrend': '🚀 Tendencia Alcista Fuerte',
            'uptrend': '📈 Tendencia Alcista',
            'sideways': '➡️ Lateral',
            'downtrend': '📉 Tendencia Bajista',
            'strong_downtrend': '💥 Tendencia Bajista Fuerte'
        }.get(trend, '❓ Desconocido')
        
        message = f"""
📊 <b>ANÁLISIS: {symbol}</b>

💵 <b>Precio:</b> ${price:,.2f}
📈 <b>RSI:</b> {rsi:.0f} - {rsi_emoji}
📊 <b>Tendencia:</b> {trend_emoji}
🎯 <b>Señal:</b> {signal.upper()}

⏱️ {datetime.now().strftime('%H:%M:%S')}
"""
        self.send(message.strip())

    def notify_inefficiency_warning(self, data: Dict[str, Any]) -> None:
        """
        Alerta cuando las comisiones superan el 10% de las ganancias.
        """
        fees = data.get('fees', 0)
        gross = data.get('gross', 0)
        impact = data.get('impact_pct', 0)
        
        message = f"""
⚠️ <b>ALERTA DE INEFICIENCIA</b>

💸 <b>Comisiones Altas Detectadas</b>
Las comisiones acumuladas hoy superan el 10% de las ganancias brutas.

📊 <b>Fees Hoy:</b> ${fees:.2f}
💰 <b>Gross Profit:</b> ${gross:.2f}
📉 <b>Impacto:</b> {impact:.1f}%

<b>Acción Sugerida:</b>
• Revisar Take Profit (posiblemente muy bajo)
• Revisar spread/slippage del mercado
• Considerar pausar si el impacto sube de 20%

⏱️ {datetime.now().strftime('%H:%M:%S')}
"""
        self.send(message.strip())

    def notify_weekly_report(self, stats: Dict[str, Any]) -> None:
        """
        Envía reporte semanal (Domingo 19:00).
        """
        net_profit = stats.get('net_profit', 0)
        total_fees = stats.get('total_fees', 0)
        best_coin = stats.get('best_coin', 'N/A')
        best_coin_profit = stats.get('best_coin_profit', 0)
        win_rate = stats.get('win_rate', 0)
        
        emoji = "🚀" if net_profit >= 0 else "📉"
        
        message = f"""
📅 <b>REPORTE SEMANAL</b>
<i>Resumen de rendimiento (Ultimos 7 días)</i>

<b>💰 RENDIMIENTO NETO</b>
{emoji} <b>Total Net Profit:</b> ${net_profit:+.2f}
💸 <b>Total Fees Pagados:</b> ${total_fees:.2f}

<b>🏆 MEJOR ACTIVO</b>
🥇 <b>{best_coin}</b>
   Profit Neto: ${best_coin_profit:+.2f}

<b>📊 ESTADÍSTICAS</b>
✅ <b>Trades Ganadores:</b> {stats.get('wins', 0)}
❌ <b>Trades Perdedores:</b> {stats.get('losses', 0)}
🎯 <b>Win Rate:</b> {win_rate:.1f}%

⏱️ {datetime.now().strftime('%d/%m/%Y')}
"""
        self.send(message.strip())


# Singleton
_notifier: Optional[TelegramNotifier] = None

def get_notifier() -> TelegramNotifier:
    global _notifier
    if _notifier is None:
        _notifier = TelegramNotifier()
    return _notifier
