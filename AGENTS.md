# AGENTS.md — FoxTrading Bot

## Descripción General

FoxTrading es un bot de trading automatizado para criptomonedas en Binance que combina
3 estrategias clásicas con un analista de IA local (via Ollama) para tomar decisiones
inteligentes de compra/venta. Por defecto corre en modo **paper trading** (simulado con
precios reales de Binance) y puede cambiarse a modo **live**.

## Arquitectura (Alto Nivel)

```
main.py                 # Bucle principal: orquesta todos los ciclos
config/settings.py      # Configuración centralizada (TODOS los parámetros aquí)
src/
├── ai/ollama_advisor.py    # Asesor IA local (Ollama)
├── core/
│   ├── exchange_manager.py # Conexión Binance via ccxt, simulación paper wallet
│   ├── data_manager.py     # Obtención OHLCV, indicadores técnicos (RSI, MACD, BB, EMA, ATR)
│   └── state_manager.py    # Persistencia SQLite (posiciones, historial, estadísticas)
├── strategies/
│   ├── dca_strategy.py         # DCA Inteligente (40% del capital)
│   ├── grid_strategy.py        # Grid Trading (30% del capital)
│   └── technical_strategy.py   # RSI+MACD Técnico (30% del capital)
├── risk/risk_manager.py        # Stop loss, trailing stop, drawdown, protecciones por par
├── notifications/telegram_bot.py  # Comandos interactivos de Telegram
└── utils/transaction_manager.py   # Generación de TX ID, payloads estandarizados
```

## Archivos Clave y Responsabilidades

| Archivo | Propósito |
|---|---|
| main.py | Motor del bot: ciclos (~60s) de datos, estrategias, IA, riesgo, notificaciones |
| config/settings.py | Config central: exchange, capital, portafolio, estrategias, riesgo, Ollama, Telegram |
| src/core/exchange_manager.py | Singleton de ccxt.binance, rate limiting, paper wallet, órdenes |
| src/core/data_manager.py | OHLCV + indicadores (RSI, MACD, BB, EMAs, ATR), caché de 5 min |
| src/core/state_manager.py | SQLite: posiciones, trade_history, strategy_state, bot_stats, portfolio_state |
| src/strategies/dca_strategy.py | DCA Inteligente: compras cada 4h, detección de caídas, ventas parciales con IA |
| src/strategies/grid_strategy.py | Grid Trading: 7 niveles, 1.5% spacing, recentrado dinámico, filtros |
| src/strategies/technical_strategy.py | RSI+MACD: sistema de puntuación, confirmación de 2 períodos, SL/TP dinámico |
| src/ai/ollama_advisor.py | LLM local (qwen2.5:7b): filtro de señales + análisis de ventas + análisis de portafolio |
| src/risk/risk_manager.py | Tamaño de posición, drawdown (15%/5%), trailing dinámico, protecciones por par |
| src/notifications/telegram_bot.py | Telegram asíncrono: /informe, /estado, /posiciones, /coins, /ai, /grafico |
| src/utils/transaction_manager.py | IDs únicos TX y payloads estandarizados |

## Bucle Principal (ciclo ~60s)

1. **Verificación de Riesgo** — ¿Trading pausado? ¿Drawdown ok? ¿Pérdidas consecutivas dentro del límite?
2. **Datos de Mercado** — OHLCV + RSI/MACD/BB/EMA/ATR para todos los símbolos (BTC, ETH, SOL)
3. **Estrategia Técnica** — should_enter/should_exit con aprobación del filtro IA
4. **Grid Trading** — revisar 7 niveles, ejecutar compras/ventas (varias por ciclo)
5. **DCA Inteligente** — intervalo transcurrido, multiplicador por caída, análisis de venta IA, ejecutar
6. **Registro de Riesgo** — guardar resultados, actualizar capital, persistir en SQLite
7. **Notificaciones** — Telegram por cada trade, reporte diario a la hora configurada
8. **Tareas Periódicas** — schedule: compras DCA, reportes diarios, recentrado de grid, persistencia

## Patrón de Configuración

config/settings.py usa diccionarios GRUPO:
- EXCHANGE — API keys de Binance, bandera testnet
- CAPITAL — USD inicial, tasa COP, aportes mensuales
- PORTFOLIO — Porcentajes de asignación por símbolo, flags sell_only
- STRATEGIES — Por estrategia: habilitada, niveles, spacing, allocation_pct, umbrales
- RISK_MANAGEMENT — Tamaño de posición, trailing (tiers dinámicos), protecciones, drawdown
- OLLAMA — Nombre del modelo, habilitado, min_confidence, filter_enabled
- TELEGRAM — Token del bot, chat ID, notificaciones activadas
- TRADING_COSTS — Comisiones maker/taker, slippage
- OPERATION_MODE — Modo paper/live

## Flujo de Datos

1. ExchangeManager.get_ohlcv() → lista OHLCV cruda
2. DataManager.get_market_data() → pandas DataFrame + caché
3. DataManager.add_technical_indicators(df) → RSI, MACD, BB, EMAs, ATR
4. DataManager.get_market_summary(symbol) → dict con precio/indicadores/tendencia
5. Las estrategias reciben el dict en analyze/should_enter/should_exit
6. Si es aprobado → ExchangeManager.place_order() o _paper_order()
7. StateManager.save_position/close_position/add_to_history
8. RiskManager.record_trade_result/record_pair_trade
9. TelegramBot envía notificaciones

## Paper Trading

Cuando OPERATION_MODE mode = paper:
- market_exchange (público, sin keys) para precios reales
- _paper_order() simula via JSON wallet (data/paper_wallet.json)
- Comisiones: 0.1% maker/taker, precisión Decimal

## Asesor IA (Ollama)

Actúa como filtro, no ejecutor:
- analyze_trade_signal(): antes de cada trade, retorna approved/confidence(1-10)/reasoning. Bloqueado si confidence < 5.
- analyze_sell_opportunity(): ventas DCA proactivas, retorna should_sell/sell_pct/urgency.
- Comando /ai de Telegram para reporte narrativo del portafolio.
- Caché: 5min (3min para ventas).

## Decisiones de Diseño Clave

- Decimal para dinero (float solo para persistencia SQLite/JSON)
- Sin comentarios en código (convención del proyecto)
- Patrón Singleton para todos los managers (get_*())
- Persistencia dual: tablas SQLite + blobs JSON en strategy_state
- Protecciones por par: pausar pares individuales tras 3 pérdidas en 12h
- Trailing stop dinámico: niveles se ajustan según ganancia (2.5% → 2.0% → 1.5% → 1.0%)

## Pruebas

```
pytest tests/
```