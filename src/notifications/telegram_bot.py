"""
Telegram Bot Interactivo
=========================
Bot de Telegram con comandos para análisis en tiempo real
Comando principal: /informe - Análisis técnico completo
"""

import asyncio
import os
import sys
from datetime import datetime, timedelta
from typing import Dict, Any, Optional
from loguru import logger

# Agregar path del proyecto
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from telegram import Update, Bot
from telegram.ext import Application, CommandHandler, ContextTypes

from config.settings import TELEGRAM, PORTFOLIO, CAPITAL, STRATEGIES
from src.core.data_manager import get_data_manager
from src.core.state_manager import get_state_manager
from src.core.exchange_manager import get_exchange


class TelegramBotInteractivo:
    """
    Bot de Telegram interactivo para consultar estado del trading bot.
    
    Comandos disponibles:
    /informe - Análisis técnico completo
    /estado - Estado rápido del bot
    /posiciones - Posiciones abiertas
    /mercado - Estado del mercado actual
    /ayuda - Lista de comandos
    """
    
    def __init__(self):
        self.bot_token = TELEGRAM["bot_token"]
        self.chat_id = TELEGRAM["chat_id"]
        self.data_manager = get_data_manager()
        self.state_manager = get_state_manager()
        self.exchange = get_exchange()
        
        self.app: Optional[Application] = None
        
        logger.info("✅ Telegram Bot Interactivo iniciado")
    
    async def start(self) -> None:
        """Inicia el bot de Telegram."""
        if not self.bot_token:
            logger.warning("⚠️ Token de Telegram no configurado")
            return
        
        self.app = Application.builder().token(self.bot_token).build()
        
        # Registrar handlers de comandos
        self.app.add_handler(CommandHandler("start", self.cmd_start))
        self.app.add_handler(CommandHandler("informe", self.cmd_informe))
        self.app.add_handler(CommandHandler("estado", self.cmd_estado))
        self.app.add_handler(CommandHandler("posiciones", self.cmd_posiciones))
        self.app.add_handler(CommandHandler("coins", self.cmd_coins))
        self.app.add_handler(CommandHandler("mercado", self.cmd_mercado))
        self.app.add_handler(CommandHandler("historial", self.cmd_historial))
        self.app.add_handler(CommandHandler("ayuda", self.cmd_ayuda))
        self.app.add_handler(CommandHandler("help", self.cmd_ayuda))
        
        # Nuevos comandos de reportes
        self.app.add_handler(CommandHandler("resumen_hoy", self.cmd_resumen_hoy))
        self.app.add_handler(CommandHandler("resumen_semana", self.cmd_resumen_semana))
        self.app.add_handler(CommandHandler("mejores", self.cmd_mejores))
        self.app.add_handler(CommandHandler("peores", self.cmd_peores))
        self.app.add_handler(CommandHandler("fees", self.cmd_fees))
        
        logger.info("🤖 Comandos de Telegram registrados")
        
        # Iniciar polling
        await self.app.initialize()
        await self.app.start()
        await self.app.updater.start_polling()
        
        logger.info("📱 Telegram Bot escuchando comandos...")
    
    async def stop(self) -> None:
        """Detiene el bot de Telegram."""
        if self.app:
            await self.app.updater.stop()
            await self.app.stop()
            await self.app.shutdown()
    
    # =========================================================================
    # COMANDOS
    # =========================================================================
    
    async def cmd_start(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        """Comando /start - Bienvenida."""
        message = """
🤖 <b>¡Bot de Trading Activado!</b>

<b>═══ COMANDOS DISPONIBLES ═══</b>

📊 /informe - Análisis técnico COMPLETO
💰 /coins - Mis criptomonedas (holdings)
💼 /posiciones - Posiciones abiertas
📈 /estado - Estado rápido del bot
📉 /mercado - Precios del mercado
📜 /historial - Últimos trades

<b>═══ REPORTES ═══</b>
📅 /resumen_hoy - P&L del día
📆 /resumen_semana - P&L semanal
🏆 /mejores - Top 3 mejores trades
📉 /peores - Top 3 peores trades
💸 /fees - Comisiones pagadas

❓ /help - Esta lista de comandos

<i>Escribe cualquier comando para comenzar.</i>
"""
        await update.message.reply_text(message.strip(), parse_mode="HTML")
    
    async def cmd_ayuda(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        """Comando /ayuda - Lista de comandos."""
        await self.cmd_start(update, context)
    
    async def cmd_coins(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        """Comando /coins - Muestra las criptomonedas en posesión."""
        try:
            # Obtener posiciones de todas las estrategias
            dca_state = self.state_manager.load_strategy_state("dca_intelligent") or {}
            grid_state = self.state_manager.load_strategy_state("grid_trading") or {}
            tech_state = self.state_manager.load_strategy_state("technical_rsi_macd") or {}
            
            # Consolidar holdings
            holdings = {}
            
            # DCA positions
            for symbol, pos in dca_state.get("positions", {}).items():
                coin = symbol.split("/")[0]
                if coin not in holdings:
                    holdings[coin] = {"amount": 0, "cost": 0}
                holdings[coin]["amount"] += pos.get("amount", 0)
                holdings[coin]["cost"] += pos.get("avg_price", 0) * pos.get("amount", 0)
            
            # Grid positions (bought levels)
            for symbol, grid in grid_state.get("grids", {}).items():
                coin = symbol.split("/")[0]
                for level in grid.get("levels", []):
                    if level.get("status") == "bought":
                        if coin not in holdings:
                            holdings[coin] = {"amount": 0, "cost": 0}
                        holdings[coin]["amount"] += level.get("amount", 0)
                        holdings[coin]["cost"] += level.get("buy_price", 0) * level.get("amount", 0)
            
            # Technical positions
            for symbol, pos in tech_state.get("positions", {}).items():
                coin = symbol.split("/")[0]
                if coin not in holdings:
                    holdings[coin] = {"amount": 0, "cost": 0}
                holdings[coin]["amount"] += pos.get("amount", 0)
                holdings[coin]["cost"] += pos.get("entry_price", 0) * pos.get("amount", 0)
            
            if not holdings:
                await update.message.reply_text("📭 <b>No tienes criptomonedas compradas actualmente.</b>", parse_mode="HTML")
                return
            
            # Formatear mensaje
            coins_text = ""
            total_invested = 0
            
            for coin, data in holdings.items():
                amount = data["amount"]
                cost = data["cost"]
                avg_price = cost / amount if amount > 0 else 0
                total_invested += cost
                
                coins_text += f"""
🪙 <b>{coin}</b>
   📦 Cantidad: {amount:.8f}
   💵 Costo Promedio: ${avg_price:,.2f}
   💰 Invertido: ${cost:.2f}
"""
            
            message = f"""
💰 <b>═══ MIS CRIPTOMONEDAS ═══</b>
{coins_text}
<b>═══ RESUMEN ═══</b>
📊 <b>Total Invertido:</b> ${total_invested:.2f}
🪙 <b>Monedas Diferentes:</b> {len(holdings)}

⏰ {datetime.now().strftime('%H:%M:%S - %d/%m/%Y')}
"""
            await update.message.reply_text(message.strip(), parse_mode="HTML")
            
        except Exception as e:
            logger.error(f"Error en cmd_coins: {e}")
            await update.message.reply_text(f"❌ Error: {str(e)}")
    
    async def cmd_estado(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        """Comando /estado - Estado rápido."""
        try:
            trade_stats = self.state_manager.get_trade_stats()
            
            # Calcular capital real desde wallet (misma lógica que /informe)
            balance = self.exchange.get_balance()
            liquid_usdt = balance.get("USDT", 0)
            assets_value = 0
            crypto_assets = {k: v for k, v in balance.items() if k != "USDT" and v > 0}
            for asset, amount in crypto_assets.items():
                symbol = f"{asset}/USDT"
                try:
                    data = self.data_manager.get_market_summary(symbol)
                    current_price = data.get("price", 0)
                    assets_value += (float(amount) * float(current_price))
                except:
                    pass
            
            capital = float(liquid_usdt) + float(assets_value)
            initial = float(CAPITAL["initial_usd"])
            profit = capital - initial
            roi = (profit / initial) * 100 if initial > 0 else 0
            
            # Conversión COP
            cop_rate = float(CAPITAL.get("usd_cop_rate", 3652))
            capital_cop = capital * cop_rate
            profit_cop = profit * cop_rate
            
            win_rate = float(trade_stats.get("win_rate", 0) or 0)
            total_trades = int(trade_stats.get("total_trades", 0) or 0)
            
            emoji_profit = "🟢" if profit >= 0 else "🔴"
            
            message = f"""
📊 <b>ESTADO DEL BOT</b>

💰 <b>Capital:</b> ${capital:.2f} (${capital_cop:,.0f} COP)
{emoji_profit} <b>P&L:</b> ${profit:+.2f} ({roi:+.2f}%) | {profit_cop:+,.0f} COP
📈 <b>Trades:</b> {total_trades}
🎯 <b>Win Rate:</b> {win_rate:.1f}%

⏰ {datetime.now().strftime('%H:%M:%S - %d/%m/%Y')}
"""
            await update.message.reply_text(message.strip(), parse_mode="HTML")
        except Exception as e:
            await update.message.reply_text(f"❌ Error: {str(e)}")
    
    async def cmd_informe(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        """
        Comando /informe - ANÁLISIS TÉCNICO COMPLETO
        Este es el comando principal con toda la información.
        """
        try:
            await update.message.reply_text("🔄 Generando informe completo...")
            
            # Obtener datos
            portfolio = self.state_manager.get_portfolio_state()
            trade_stats = self.state_manager.get_trade_stats()
            open_positions = self.state_manager.get_open_positions()
            
            # Estado de estrategias
            dca_state = self.state_manager.load_strategy_state("dca_intelligent") or {}
            grid_state = self.state_manager.load_strategy_state("grid_trading") or {}
            tech_state = self.state_manager.load_strategy_state("technical_rsi_macd") or {}
            
            # ========== PARTE 1: RESUMEN GENERAL ==========
            
            # 1. Obtener Balance Real (paper_wallet.json)
            balance = self.exchange.get_balance()
            liquid_usdt = balance.get("USDT", 0)
            
            # 2. Calcular Valor de Activos desde BALANCE REAL
            assets_value = 0
            crypto_assets = {k: v for k, v in balance.items() if k != "USDT" and v > 0}
            for asset, amount in crypto_assets.items():
                symbol = f"{asset}/USDT"
                try:
                    data = self.data_manager.get_market_summary(symbol)
                    current_price = data.get("price", 0)
                    assets_value += (float(amount) * float(current_price))
                except Exception as e:
                    logger.warning(f"Error getting price for {symbol} in report: {e}")

            # 3. Calcular Capital Total Real
            total_capital = float(liquid_usdt) + float(assets_value)
            
            # 4. P&L CORREGIDO - Fórmula matemáticamente consistente:
            #    P&L Total = Capital Actual - Capital Inicial (fuente de verdad única)
            #    P&L Latente = P&L Total - P&L Realizado (derivado, no calculado de invested_cost)
            initial_capital = float(CAPITAL['initial_usd'])
            realized_profit = float(trade_stats.get("total_profit", 0))  # Fuente de verdad: SQL trade_history
            real_pnl = total_capital - initial_capital  # Fuente de verdad: wallet real
            latent_pnl = real_pnl - realized_profit  # Derivado: lo que falta por realizar
            real_roi = (real_pnl / initial_capital) * 100 if initial_capital > 0 else 0

            # Conversión COP
            cop_rate = float(CAPITAL.get("usd_cop_rate", 3652))
            capital_cop = initial_capital * cop_rate
            valor_cop = total_capital * cop_rate
            liquid_cop = float(liquid_usdt) * cop_rate
            assets_cop = float(assets_value) * cop_rate
            pnl_cop = real_pnl * cop_rate

            # 5. Estadísticas de Trading
            win_rate = float(trade_stats.get("win_rate", 0) or 0)
            total_trades = int(trade_stats.get("total_trades", 0) or 0)
            winning = int(trade_stats.get("winning_trades", 0) or 0)
            losing = int(trade_stats.get("losing_trades", 0) or 0)

            emoji_profit = "🟢" if real_pnl >= 0 else "🔴"
            
            message_1 = f"""
📊 <b>═══ INFORME COMPLETO ═══</b>
⏰ {datetime.now().strftime('%H:%M:%S - %d/%m/%Y')}

<b>══ 💰 CAPITAL (REAL) ══</b>

💵 <b>Capital Inicial:</b> ${initial_capital:.2f} (${capital_cop:,.0f} COP)
💰 <b>Capital Actual:</b> ${total_capital:.2f} (${valor_cop:,.0f} COP)
   ├ 🟢 Liquidez: ${liquid_usdt:.2f} (${liquid_cop:,.0f} COP)
   └ 📦 Activos: ${assets_value:.2f} (${assets_cop:,.0f} COP)

{emoji_profit} <b>P&L Total:</b> ${real_pnl:+.2f} ({real_roi:+.2f}%) | {pnl_cop:+,.0f} COP
   └ 📉 Realizado (Cerrados): ${realized_profit:+.2f}
   └ 📈 Latente (Abiertos): ${latent_pnl:+.2f}

<b>══ 📈 ESTADÍSTICAS ══</b>

📊 <b>Total Trades:</b> {total_trades}
✅ <b>Ganados:</b> {winning}
❌ <b>Perdidos:</b> {losing}
🎯 <b>Win Rate:</b> {win_rate:.1f}%
"""
            await update.message.reply_text(message_1.strip(), parse_mode="HTML")
            
            # ========== PARTE 2: ANÁLISIS DE MERCADO ==========
            market_analysis = []
            for symbol in PORTFOLIO.keys():
                try:
                    data = self.data_manager.get_market_summary(symbol)
                    if "error" not in data:
                        price = float(data.get("price", 0) or 0)
                        rsi = float(data.get("rsi", 50) or 50)
                        trend = data.get("trend", "sideways") or "sideways"
                        change_24h = float(data.get("change_24h", 0) or 0)
                        
                        # Determinar señal
                        if rsi < 30:
                            signal = "🟢 COMPRA"
                        elif rsi > 70:
                            signal = "🔴 VENTA"
                        elif rsi < 40:
                            signal = "🟡 Posible compra"
                        elif rsi > 60:
                            signal = "🟠 Posible venta"
                        else:
                            signal = "⚪ Neutral"
                        
                        # Emoji de tendencia
                        trend_str = str(trend).lower()
                        trend_emoji = "📈" if "up" in trend_str else "📉" if "down" in trend_str else "➡️"
                        
                        market_analysis.append(f"""
<b>{symbol.replace('/USDT', '')}</b>
└ 💵 ${price:,.2f} ({change_24h:+.2f}%)
└ 📊 RSI: {rsi:.0f} | {trend_emoji} {trend}
└ 🎯 {signal}
""")
                except Exception as e:
                    logger.error(f"Error obteniendo datos de {symbol}: {e}")
            
            message_2 = f"""
<b>══ 📉 ANÁLISIS DE MERCADO ══</b>
{"".join(market_analysis) if market_analysis else "No hay datos disponibles"}
"""
            await update.message.reply_text(message_2.strip(), parse_mode="HTML")
            
            # ========== PARTE 3: POSICIONES Y ESTRATEGIAS ==========
            
            # DCA Positions
            dca_accumulated = dca_state.get("accumulated", {})
            dca_entries = dca_state.get("entry_prices", {})
            dca_last_buy = dca_state.get("last_buy_time", {})
            
            dca_info = []
            for symbol, amount in dca_accumulated.items():
                f_amount = float(amount) if amount else 0
                if f_amount > 0:
                    entry = float(dca_entries.get(symbol, 0) or 0)
                    # Calcular próxima compra
                    last_buy_str = dca_last_buy.get(symbol)
                    next_buy = "Ahora"
                    if last_buy_str:
                        try:
                            last_buy = datetime.fromisoformat(last_buy_str)
                            next_buy_time = last_buy + timedelta(hours=24)
                            if next_buy_time > datetime.now():
                                hours_remaining = (next_buy_time - datetime.now()).total_seconds() / 3600
                                next_buy = f"en {hours_remaining:.1f}h"
                            else:
                                next_buy = "Próximo ciclo"
                        except ValueError as e:
                            logger.debug(f"Error parsing last_buy date for {symbol}: {e}")
                            pass
                    
                    dca_info.append(f"""
└ <b>{symbol.replace('/USDT', '')}:</b> {f_amount:.8f}
  └ Precio entrada: ${entry:.2f}
  └ Próxima compra: {next_buy}
""")
            
            # Grid Status
            grids = grid_state.get("grids", {})
            grid_info = []
            for symbol, grid in grids.items():
                levels = grid.get("levels", [])
                bought = sum(1 for l in levels if l.get("status") == "bought")
                pending = sum(1 for l in levels if l.get("status") == "pending")
                center = float(grid.get("center_price", 0) or 0)
                grid_profit = float(grid.get("total_profit", 0) or 0)
                
                # Calcular próximos precios de compra/venta
                buy_prices = [l["buy_price"] for l in levels if l.get("status") == "pending"]
                sell_prices = [l["sell_price"] for l in levels if l.get("status") == "bought"]
                
                next_buy = f"${min(buy_prices):,.2f}" if buy_prices else "N/A"
                next_sell = f"${max(sell_prices):,.2f}" if sell_prices else "N/A"
                
                grid_info.append(f"""
└ <b>{symbol.replace('/USDT', '')}:</b>
  └ Centro: ${center:,.2f}
  └ Niveles comprados: {bought}/{len(levels)}
  └ 🟢 Próxima compra: {next_buy}
  └ 🔴 Próxima venta: {next_sell}
  └ Profit Grid: ${grid_profit:.2f}
""")
            
            # Technical Positions
            tech_positions = tech_state.get("positions", {})
            tech_info = []
            for symbol, pos in tech_positions.items():
                entry = pos.get("entry_price", 0)
                amount = pos.get("amount", 0)
                sl = pos.get("stop_loss", 0)
                tp = pos.get("take_profit", 0)
                tech_info.append(f"""
└ <b>{symbol.replace('/USDT', '')}:</b> {amount:.8f}
  └ Entrada: ${entry:.2f}
  └ 🔴 Stop Loss: ${sl:.2f}
  └ 🟢 Take Profit: ${tp:.2f}
""")
            
            message_3 = f"""
<b>══ 💼 POSICIONES ACTIVAS ══</b>

<b>📊 DCA Intelligent:</b>
{chr(10).join(dca_info) if dca_info else "└ Sin posiciones"}

<b>🔲 Grid Trading:</b>
{chr(10).join(grid_info) if grid_info else "└ Sin grids activas"}

<b>📈 Technical RSI+MACD:</b>
{chr(10).join(tech_info) if tech_info else "└ Sin posiciones"}
"""
            await update.message.reply_text(message_3.strip(), parse_mode="HTML")
            
            # ========== PARTE 4: PREDICCIONES ==========
            predictions = []
            for symbol in PORTFOLIO.keys():
                try:
                    data = self.data_manager.get_market_summary(symbol)
                    if "error" not in data:
                        price = data.get("price", 0)
                        rsi = data.get("rsi", 50)
                        trend = data.get("trend", "sideways")
                        
                        # Predicción de compra
                        if rsi < 35:
                            prediction = f"🟢 <b>COMPRAR PRONTO</b> - RSI bajo ({rsi:.0f})"
                        elif rsi > 65:
                            prediction = f"⏳ Esperar corrección - RSI alto ({rsi:.0f})"
                        elif "down" in trend.lower():
                            # Calcular precio objetivo de compra (5% abajo)
                            target = price * 0.95
                            prediction = f"🟡 Esperar baja a ~${target:,.2f}"
                        else:
                            prediction = f"⚪ Mantener - mercado estable"
                        
                        predictions.append(f"<b>{symbol.replace('/USDT', '')}:</b> {prediction}")
                except Exception as e:
                    logger.warning(f"Error generating prediction for {symbol}: {e}")
                    pass
            
            message_4 = f"""
<b>══ 🔮 PREDICCIONES ══</b>

{chr(10).join(predictions) if predictions else "No hay predicciones disponibles"}

<b>══ 📝 NOTAS ══</b>

• El bot compra cada 24h (DCA)
• Grid compra en caídas, vende en subidas
• RSI &lt; 30 = señal de compra fuerte
• RSI &gt; 70 = señal de venta fuerte

<i>Usa /mercado para ver precios en vivo</i>
"""
            await update.message.reply_text(message_4.strip(), parse_mode="HTML")
            
        except Exception as e:
            logger.error(f"Error generando informe: {e}")
            await update.message.reply_text(f"❌ Error generando informe: {str(e)}")
    
    async def cmd_posiciones(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        """Comando /posiciones - Posiciones abiertas."""
        try:
            positions = self.state_manager.get_open_positions()
            
            if not positions:
                await update.message.reply_text("📭 No hay posiciones abiertas actualmente.")
                return
            
            message = "<b>💼 POSICIONES ABIERTAS</b>\n\n"
            
            for pos in positions:
                symbol = pos.get("symbol", "N/A")
                strategy = pos.get("strategy", "N/A")
                entry = pos.get("entry_price", 0)
                amount = pos.get("amount", 0)
                
                message += f"""
<b>{symbol}</b> ({strategy})
└ 📊 Cantidad: {amount:.8f}
└ 💵 Entrada: ${entry:.2f}
"""
            
            await update.message.reply_text(message.strip(), parse_mode="HTML")
        except Exception as e:
            await update.message.reply_text(f"❌ Error: {str(e)}")
    
    async def cmd_mercado(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        """Comando /mercado - Estado del mercado."""
        try:
            message = "<b>📈 ESTADO DEL MERCADO</b>\n\n"
            
            for symbol in PORTFOLIO.keys():
                try:
                    data = self.data_manager.get_market_summary(symbol)
                    if "error" not in data:
                        price = data.get("price", 0)
                        rsi = data.get("rsi", 50)
                        trend = data.get("trend", "sideways")
                        high_24h = data.get("high_24h", price)
                        low_24h = data.get("low_24h", price)
                        
                        trend_emoji = "📈" if "up" in trend.lower() else "📉" if "down" in trend.lower() else "➡️"
                        
                        message += f"""
<b>{symbol}</b>
└ 💵 Precio: ${price:,.2f}
└ 📊 RSI: {rsi:.0f}
└ {trend_emoji} Tendencia: {trend}
└ ⬆️ 24h High: ${high_24h:,.2f}
└ ⬇️ 24h Low: ${low_24h:,.2f}
"""
                except Exception as e:
                    logger.warning(f"Error fetching coin data for {symbol}: {e}")
                    message += f"\n<b>{symbol}</b>\n└ ❌ Sin datos\n"
            
            message += f"\n⏰ {datetime.now().strftime('%H:%M:%S')}"
            await update.message.reply_text(message.strip(), parse_mode="HTML")
        except Exception as e:
            await update.message.reply_text(f"❌ Error: {str(e)}")
    
    async def cmd_historial(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        """Comando /historial - Últimos trades."""
        try:
            trades = self.state_manager.get_trade_history(limit=10)
            
            if not trades:
                await update.message.reply_text("📭 No hay trades en el historial.")
                return
            
            message = "<b>📜 ÚLTIMOS 10 TRADES</b>\n\n"
            
            for trade in trades[:10]:
                symbol = trade.get("symbol", "N/A")
                side = trade.get("side", "N/A")
                price = trade.get("exit_price") or trade.get("entry_price", 0)
                profit = trade.get("profit", 0)
                closed_at = trade.get("closed_at", "")
                
                emoji = "🟢" if side == "buy" else "🔴"
                profit_emoji = "✅" if profit > 0 else "❌" if profit < 0 else ""
                
                try:
                    time_str = datetime.fromisoformat(closed_at).strftime("%d/%m %H:%M")
                except ValueError:
                    time_str = "N/A"
                
                message += f"{emoji} {symbol[:3]} @ ${price:.2f}"
                if side == "sell":
                    message += f" | {profit_emoji} ${profit:+.2f}"
                message += f" | {time_str}\n"
            
            await update.message.reply_text(message.strip(), parse_mode="HTML")
        except Exception as e:
            await update.message.reply_text(f"❌ Error: {str(e)}")
    
    # =========================================================================
    # NUEVOS COMANDOS DE REPORTES
    # =========================================================================
    
    async def cmd_resumen_hoy(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        """Comando /resumen_hoy - Resumen del día actual."""
        try:
            stats = self.state_manager.get_trades_by_period(days=1)
            
            emoji = "🟢" if stats["total_profit"] >= 0 else "🔴"
            
            message = f"""
📊 <b>═══ RESUMEN DE HOY ═══</b>
⏰ {datetime.now().strftime('%d/%m/%Y')}

<b>📈 ACTIVIDAD</b>
├ Trades: {stats['total_trades']}
├ ✅ Ganados: {stats['winning_trades']}
└ ❌ Perdidos: {stats['losing_trades']}

<b>💰 RESULTADOS</b>
├ {emoji} P&L: ${stats['total_profit']:+.2f}
├ 🎯 Win Rate: {stats['win_rate']:.1f}%
└ 💸 Fees: ${stats['total_fees']:.4f}
"""
            await update.message.reply_text(message.strip(), parse_mode="HTML")
        except Exception as e:
            await update.message.reply_text(f"❌ Error: {str(e)}")
    
    async def cmd_resumen_semana(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        """Comando /resumen_semana - Resumen de los últimos 7 días."""
        try:
            stats = self.state_manager.get_trades_by_period(days=7)
            
            emoji = "🟢" if stats["total_profit"] >= 0 else "🔴"
            avg_daily = stats["total_profit"] / 7
            
            message = f"""
📊 <b>═══ RESUMEN SEMANAL ═══</b>
📅 Últimos 7 días

<b>📈 ACTIVIDAD</b>
├ Trades Totales: {stats['total_trades']}
├ ✅ Ganados: {stats['winning_trades']}
├ ❌ Perdidos: {stats['losing_trades']}
└ 📊 Promedio/día: {stats['total_trades']/7:.1f}

<b>💰 RESULTADOS</b>
├ {emoji} P&L Total: ${stats['total_profit']:+.2f}
├ 📈 Promedio/día: ${avg_daily:+.2f}
├ 🎯 Win Rate: {stats['win_rate']:.1f}%
└ 💸 Fees Total: ${stats['total_fees']:.4f}
"""
            await update.message.reply_text(message.strip(), parse_mode="HTML")
        except Exception as e:
            await update.message.reply_text(f"❌ Error: {str(e)}")
    
    async def cmd_mejores(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        """Comando /mejores - Top 3 trades más rentables."""
        try:
            trades = self.state_manager.get_top_trades(limit=3, best=True)
            
            if not trades:
                await update.message.reply_text("📭 No hay trades cerrados aún.")
                return
            
            message = "🏆 <b>═══ TOP 3 MEJORES TRADES ═══</b>\n\n"
            
            for i, trade in enumerate(trades, 1):
                medal = ["🥇", "🥈", "🥉"][i-1] if i <= 3 else f"{i}."
                profit = trade.get("profit", 0)
                profit_pct = trade.get("profit_pct", 0)
                symbol = trade.get("symbol", "N/A")
                strategy = trade.get("strategy", "N/A")
                
                message += f"""
{medal} <b>{symbol}</b>
   💰 Profit: ${profit:+.2f} ({profit_pct:+.1f}%)
   📋 Estrategia: {strategy}
"""
            
            await update.message.reply_text(message.strip(), parse_mode="HTML")
        except Exception as e:
            await update.message.reply_text(f"❌ Error: {str(e)}")
    
    async def cmd_peores(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        """Comando /peores - Top 3 peores trades."""
        try:
            trades = self.state_manager.get_top_trades(limit=3, best=False)
            
            if not trades:
                await update.message.reply_text("📭 No hay trades cerrados aún.")
                return
            
            message = "📉 <b>═══ TOP 3 PEORES TRADES ═══</b>\n\n"
            
            for i, trade in enumerate(trades, 1):
                symbol = trade.get("symbol", "N/A")
                profit = trade.get("profit", 0)
                profit_pct = trade.get("profit_pct", 0)
                strategy = trade.get("strategy", "N/A")
                
                message += f"""
{i}. <b>{symbol}</b>
   💸 Pérdida: ${profit:.2f} ({profit_pct:.1f}%)
   📋 Estrategia: {strategy}
"""
            
            await update.message.reply_text(message.strip(), parse_mode="HTML")
        except Exception as e:
            await update.message.reply_text(f"❌ Error: {str(e)}")
    
    async def cmd_fees(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        """Comando /fees - Total de comisiones pagadas."""
        try:
            fees = self.state_manager.get_total_fees()
            
            by_strategy_text = ""
            for strategy, amount in fees.get("by_strategy", {}).items():
                short_name = strategy.split()[0] if strategy else "N/A"
                by_strategy_text += f"\n   ├ {short_name}: ${amount:.4f}"
            
            if not by_strategy_text:
                by_strategy_text = "\n   └ Sin datos"
            
            message = f"""
💸 <b>═══ COMISIONES PAGADAS ═══</b>

<b>📊 RESUMEN</b>
├ Total Pagado: ${fees['total_fees']:.4f}
└ Trades con Fee: {fees['trades_with_fees']}

<b>📋 POR ESTRATEGIA</b>{by_strategy_text}

💡 <i>Fee rate: 0.1% por trade</i>
"""
            await update.message.reply_text(message.strip(), parse_mode="HTML")
        except Exception as e:
            await update.message.reply_text(f"❌ Error: {str(e)}")


async def main():
    """Ejecuta el bot de Telegram de forma independiente."""
    bot = TelegramBotInteractivo()
    
    try:
        await bot.start()
        
        # Mantener el bot corriendo
        while True:
            await asyncio.sleep(1)
    except KeyboardInterrupt:
        logger.info("Bot detenido por usuario")
    finally:
        await bot.stop()


if __name__ == "__main__":
    asyncio.run(main())
