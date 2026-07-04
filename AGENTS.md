# AGENTS.md — FoxTrading Bot

## Overview

FoxTrading is an automated cryptocurrency trading bot for Binance that combines 3 classic
strategies with a local AI analyst (via Ollama) to make intelligent buy/sell decisions.
It runs in **paper trading** mode by default (simulated with real Binance prices)
and can switch to **live** mode.

## Architecture (High-Level)

```
main.py                 # Main loop: orchestrates all cycles
config/settings.py      # Centralized configuration (ALL parameters here)
src/
├── ai/ollama_advisor.py    # Local LLM advisor (Ollama)
├── core/
│   ├── exchange_manager.py # Binance connection via ccxt, paper wallet simulation
│   ├── data_manager.py     # OHLCV fetching, technical indicators (RSI, MACD, BB, EMA, ATR)
│   └── state_manager.py    # SQLite persistence (positions, history, stats)
├── strategies/
│   ├── dca_strategy.py         # DCA Intelligent (40% capital)
│   ├── grid_strategy.py        # Grid Trading (30% capital)
│   └── technical_strategy.py   # RSI+MACD Technical (30% capital)
├── risk/risk_manager.py        # Stop loss, trailing stop, drawdown, pair protections
├── notifications/telegram_bot.py  # Interactive Telegram commands
└── utils/transaction_manager.py   # TX ID generation, standardized trade payloads
```

## Key Files & Responsibilities

| File | Purpose |
|---|---|
| main.py | Bot engine runs cycles (~60s each): fetch data, run strategies, execute signals, AI check, risk, notifications |
| config/settings.py | Centralized config: exchange, capital, portfolio, strategies, risk, Ollama, Telegram |
| src/core/exchange_manager.py | Singleton wrapping ccxt.binance, rate limiting, paper wallet, order placement |
| src/core/data_manager.py | OHLCV + technical indicators (RSI, MACD, BB, EMAs, ATR), 5-min cache |
| src/core/state_manager.py | SQLite persistence: positions, trade_history, strategy_state, bot_stats, portfolio_state |
| src/strategies/dca_strategy.py | DCA Intelligent: buys every 4h, dip detection, AI-driven partial sells (10/25/50%) |
| src/strategies/grid_strategy.py | Grid Trading: 7-level grid, 1.5% spacing, dynamic recentering, trend/volatility filters |
| src/strategies/technical_strategy.py | RSI+MACD: scoring system, 2-period confirmation, ATR-based SL/TP, trailing stop |
| src/ai/ollama_advisor.py | Local LLM (qwen2.5:7b) signal filter + sell analyzer + portfolio analysis, cached |
| src/risk/risk_manager.py | Position sizing, drawdown (15%/5%), dynamic trailing (profit tiers), pair protections |
| src/notifications/telegram_bot.py | Async Telegram with /informe, /estado, /posiciones, /coins, /ai, /grafico, etc. |
| src/utils/transaction_manager.py | Unique TX IDs and standardized trade payloads |

## Main Loop (per ~60s cycle)

1. Risk Check — paused, drawdown ok, consecutive losses within limits
2. Market Data — OHLCV + RSI/MACD/BB/EMA/ATR for all symbols (BTC, ETH, SOL)
3. Technical Strategy — should_enter/should_exit with AI filter approval
4. Grid Trading — check 7 levels, execute buys/sells (multiple per cycle)
5. DCA Intelligent — interval elapsed, dip multiplier, AI sell analysis, execute
6. Risk Recording — record trades, update capital, save SQLite state
7. Notifications — Telegram per trade, daily report at configured hour
8. Periodic Tasks — schedule: DCA buys, daily reports, grid recentering, state persistence

## Configuration Pattern

config/settings.py uses GROUP dictionaries:
- EXCHANGE — Binance API keys, testnet flag
- CAPITAL — Initial USD, COP rate, monthly contributions
- PORTFOLIO — Symbol allocation percentages, sell_only flags
- STRATEGIES — Per-strategy: enabled, levels, spacing, allocation_pct, thresholds
- RISK_MANAGEMENT — Position sizing, trailing (dynamic tiers), protections, drawdown
- OLLAMA — Model name, enabled, min_confidence, filter_enabled
- TELEGRAM — Bot token, chat ID, notification toggles
- TRADING_COSTS — Maker/taker fees, slippage
- OPERATION_MODE — paper/live switch

## Data Flow

1. ExchangeManager.get_ohlcv() → raw OHLCV
2. DataManager.get_market_data() → pandas DataFrame + cache
3. DataManager.add_technical_indicators(df) → RSI, MACD, BB, EMAs, ATR
4. DataManager.get_market_summary(symbol) → dict with price/indicators/trend
5. Strategy classes receive dict in analyze/should_enter/should_exit
6. If approved → ExchangeManager.place_order() or _paper_order()
7. StateManager.save_position/close_position/add_to_history
8. RiskManager.record_trade_result/record_pair_trade
9. TelegramBot notifications

## Paper Trading

When OPERATION_MODE mode = paper:
- market_exchange (public, no keys) for real prices
- _paper_order() simulates via JSON wallet (data/paper_wallet.json)
- Fees: 0.1% maker/taker, Decimal precision

## AI Advisor (Ollama)

Acts as filter, not executor:
- analyze_trade_signal(): before every trade, returns approved/confidence(1-10)/reasoning. Blocked if confidence < 5.
- analyze_sell_opportunity(): proactive DCA sells, returns should_sell/sell_pct/urgency.
- /ai Telegram command for portfolio narrative report.
- Cached: 5min (3min sells).

## Key Design Decisions

- Decimal for money (float only for SQLite/JSON persistence)
- No inline comments convention
- Singleton pattern for all managers (get_*())
- Dual persistence: SQLite tables + JSON blobs in strategy_state
- Pair protections: pause individual pairs after 3 losses in 12h
- Dynamic trailing stop: tiers tighten as profit increases (2.5% → 2.0% → 1.5% → 1.0%)

## Testing

```
pytest tests/
```