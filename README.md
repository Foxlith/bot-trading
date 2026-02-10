# 🤖 Bot de Trading Automatizado para Criptomonedas

Bot de trading 100% automatizado para Binance con múltiples estrategias y gestión de riesgo avanzada.

## 🎯 Objetivo
Duplicar capital en 1-2 años mediante estrategias conservadoras y gestión de riesgo.

## 📊 Estrategias Implementadas

| Estrategia | Descripción | ROI Esperado |
|------------|-------------|--------------|
| **DCA Inteligente** | Compras regulares + extra en caídas | 15-30% anual |
| **Grid Trading** | Compra/vende en rangos de precio | 20-40% anual |
| **Técnica (RSI+MACD)** | Señales técnicas con confirmación | 25-50% anual |

## 🛡️ Gestión de Riesgo
- Stop loss automáticos (3%)
- Trailing stop (2%)
- Máximo drawdown 15%
- Pausa automática tras 3 pérdidas consecutivas
- Position sizing: máximo 5% por trade

## 🚀 Inicio Rápido

### 1. Configurar entorno
```bash
cd "BOT TRADING"
python setup.py
```

### 2. Configurar credenciales
Edita el archivo `.env`:
```
BINANCE_API_KEY=tu_api_key
BINANCE_API_SECRET=tu_secret
TELEGRAM_BOT_TOKEN=tu_token  # opcional
TELEGRAM_CHAT_ID=tu_chat_id  # opcional
```

### 3. Ejecutar en modo simulación (Paper Trading)
```bash
python main.py --mode paper
```

### 4. Ejecutar en modo real
```bash
python main.py --mode live
```

## 📁 Estructura del Proyecto

```
BOT TRADING/
├── config/
│   └── settings.py        # Configuración principal
├── src/
│   ├── core/
│   │   ├── exchange_manager.py   # Conexión a Binance
│   │   └── data_manager.py       # Datos de mercado
│   ├── strategies/
│   │   ├── dca_strategy.py       # DCA Inteligente
│   │   ├── grid_strategy.py      # Grid Trading
│   │   └── technical_strategy.py # RSI + MACD
│   ├── risk/
│   │   └── risk_manager.py       # Gestión de riesgo
│   └── notifications/
│       └── telegram_notifier.py  # Alertas Telegram
├── main.py               # Motor principal
├── setup.py              # Configuración inicial
├── requirements.txt      # Dependencias
└── .env                  # Credenciales (NO subir a git)
```

## 📱 Notificaciones Telegram

Para recibir alertas en Telegram:
1. Habla con @BotFather y crea un bot
2. Habla con @userinfobot para obtener tu chat_id
3. Añade las credenciales al `.env`

## ⚠️ Advertencias

> **IMPORTANTE**: El trading conlleva riesgos. Este bot no garantiza ganancias.

- Empieza con Paper Trading para probar
- No inviertas dinero que no puedas perder
- NUNCA compartas tus API keys
- Monitorea el bot regularmente

## 📈 Portafolio Recomendado

- **BTC/USDT**: 60% - Base sólida
- **ETH/USDT**: 30% - Segunda cripto estable
- **SOL/USDT**: 10% - Mayor potencial

---

*Desarrollado con ❤️ para traders inteligentes*
