# AGENTS.md — FoxTrading Bot

## Overview

FoxTrading is an automated cryptocurrency trading bot for Binance that combines 3 classic strategies with a local AI analyst (via Ollama) to make intelligent buy/sell decisions.

## Architecture

main.py orchestrates all cycles. config/settings.py centralizes all parameters.

## Main Loop (~60s cycle)
1. Risk Check
2. Market Data (OHLCV + RSI/MACD/BB/EMA/ATR)
3. Technical Strategy (should_enter/should_exit + AI filter)
4. Grid Trading (7-level grid)
5. DCA Intelligent (interval + dip multiplier + AI sells)
6. Risk Recording
7. Notifications

## Key Components
- src/core/exchange_manager.py: ccxt.binance wrapper, paper wallet
- src/core/data_manager.py: OHLCV + ta indicators (RSI, MACD, BB, EMA, ATR)
- src/core/state_manager.py: SQLite persistence
- src/strategies/dca_strategy.py: DCA every 4h, dips, AI partial sells
- src/strategies/grid_strategy.py: 7-level grid, 1.5% spacing
- src/strategies/technical_strategy.py: RSI+MACD scoring system
- src/ai/ollama_advisor.py: LLM signal filter + sell analyzer
- src/risk/risk_manager.py: drawdown, trailing, pair protections
- src/notifications/telegram_bot.py: async commands

## AI Advisor
Signal filter (min conf 5/10), proactive DCA sell analysis, /ai command. Cached 5min/3min.

## Design
Decimal for money, singleton managers, dual persistence, pair protections, dynamic trailing.
