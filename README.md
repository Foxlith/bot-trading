<p align="center">
  <h1 align="center">🦊 FoxTrading Bot</h1>
  <p align="center">
    Bot de trading automatizado para criptomonedas con IA local
    <br />
    <strong>DCA + Grid + Análisis Técnico · Ollama AI · Telegram</strong>
  </p>
</p>

<p align="center">
  <img src="https://img.shields.io/badge/python-3.11+-blue?style=flat-square&logo=python" />
  <img src="https://img.shields.io/badge/exchange-Binance-yellow?style=flat-square&logo=binance" />
  <img src="https://img.shields.io/badge/AI-Ollama-green?style=flat-square" />
  <img src="https://img.shields.io/badge/notifications-Telegram-blue?style=flat-square&logo=telegram" />
  <img src="https://img.shields.io/badge/license-MIT-green?style=flat-square" />
</p>

---

## 📖 ¿Qué es FoxTrading?

FoxTrading es un bot de trading automatizado para criptomonedas que combina **3 estrategias clásicas** con un **analista de IA local** (Ollama) para tomar decisiones inteligentes de compra y venta en Binance.

### 🎯 Características principales

- 🧠 **IA Local (Ollama)** — Analista de mercado que evalúa cada operación antes de ejecutarla. Decide cuándo vender y qué porcentaje, actuando como tu "segundo par de ojos"
- 📊 **3 Estrategias simultáneas** — DCA Inteligente, Grid Trading, y Análisis Técnico (RSI + MACD)
- 📱 **Bot de Telegram** — Reportes en tiempo real, informes completos, y comandos interactivos
- 🔒 **Modo Paper Trading** — Practica sin riesgo con precios reales de Binance
- 💾 **Persistencia completa** — SQLite para posiciones, historial, y estadísticas
- 🛡️ **Gestión de riesgo** — Stop loss, trailing stop, máximo drawdown, y pausas automáticas

---

## 🏗️ Arquitectura

```
FoxTrading/
├── main.py                 # Motor principal del bot
├── config/
│   └── settings.py         # Configuración centralizada
├── src/
│   ├── ai/                 # 🧠 Ollama AI Advisor
│   │   └── ollama_advisor.py
│   ├── core/               # Núcleo del sistema
│   │   ├── data_manager.py     # Datos de mercado (Binance API)
│   │   ├── exchange_manager.py # Conexión al exchange
│   │   └── state_manager.py    # Persistencia SQLite
│   ├── strategies/         # Estrategias de trading
│   │   ├── dca_strategy.py     # DCA Inteligente
│   │   ├── grid_strategy.py    # Grid Trading
│   │   └── technical_strategy.py # RSI + MACD
│   ├── risk/               # Gestión de riesgo
│   │   └── risk_manager.py
│   ├── notifications/      # Notificaciones
│   │   └── telegram_bot.py     # Bot de Telegram interactivo
│   └── utils/              # Utilidades
│       └── transaction_manager.py
├── tools/                  # Scripts de análisis y optimización
├── tests/                  # Tests
├── data/                   # Base de datos y wallet (gitignored)
└── logs/                   # Logs de ejecución (gitignored)
```

---

## 📈 Estrategias

### 🔄 DCA Inteligente (40% del capital)
**Dollar Cost Averaging** con compras automáticas cada 4 horas. La IA evalúa oportunidades de venta cuando hay ganancia ≥ 2% y decide el porcentaje óptimo a vender (10%, 25% o 50%).

### 🔲 Grid Trading (30% del capital)
Crea una cuadrícula de órdenes de compra/venta con **7 niveles** y **1.5% de separación**. Compra en caídas y vende en subidas automáticamente.

### 📊 Técnica RSI + MACD (30% del capital)
Análisis técnico clásico:
- **Compra** cuando RSI < 30 (sobreventa) + MACD alcista
- **Vende** cuando RSI > 65 (sobrecompra) o stop loss/trailing stop
- Filtro EMA 200 para evitar entrar contra tendencia

---

## 🧠 IA Local (Ollama)

El bot incluye un **analista de mercado con IA** que corre 100% local en tu PC usando [Ollama](https://ollama.ai/):

- **Filtro de señales**: Evalúa cada trade antes de ejecutarlo (compra/venta)
- **Ventas proactivas**: Analiza RSI, MACD, Bollinger, y tendencia para decidir cuándo asegurar ganancias
- **Reportes diarios**: Genera un resumen narrativo del día con predicciones
- **Sin costo**: No necesitas API keys de OpenAI ni nada — todo corre en tu computadora

**Modelos soportados**: `qwen2.5:7b` (recomendado), `qwen3:8b`, `llama3.1:8b`

---

## 🚀 Instalación

### Requisitos previos
- Python 3.11+
- [Ollama](https://ollama.ai/) instalado (para la IA)
- Cuenta en Binance con API keys
- Bot de Telegram (opcional, para notificaciones)

### Pasos

```bash
# 1. Clonar el repositorio
git clone https://github.com/Foxlith/bot-trading.git
cd bot-trading

# 2. Crear entorno virtual
python -m venv .venv
.venv\Scripts\activate  # Windows
# source .venv/bin/activate  # Linux/Mac

# 3. Instalar dependencias
pip install -r requirements.txt

# 4. Configurar credenciales
copy .env.example .env
# Editar .env con tus API keys

# 5. Instalar modelo de IA
ollama pull qwen2.5:7b

# 6. Ejecutar en modo paper (simulación)
python main.py --mode paper
```

---

## ⚙️ Configuración

### Variables de entorno (`.env`)

```env
BINANCE_API_KEY=tu_api_key
BINANCE_API_SECRET=tu_api_secret
TELEGRAM_BOT_TOKEN=tu_bot_token
TELEGRAM_CHAT_ID=tu_chat_id
```

### Configuración del bot (`config/settings.py`)

| Parámetro | Default | Descripción |
|---|---|---|
| `initial_usd` | 300 | Capital inicial en USD |
| `buy_interval_hours` | 4 | Intervalo DCA en horas |
| `grid_levels` | 7 | Niveles del grid |
| `grid_spacing_pct` | 1.5% | Separación entre niveles |
| `max_drawdown_pct` | 15% | Drawdown máximo antes de pausar |
| `daily_report_hour` | 20 | Hora del reporte diario (8PM) |

---

## 📱 Comandos de Telegram

| Comando | Descripción |
|---|---|
| `/informe` | 📊 Análisis técnico completo |
| `/estado` | 💰 Estado rápido del bot |
| `/posiciones` | 💼 Posiciones abiertas |
| `/coins` | 🪙 Criptomonedas en posesión |
| `/mercado` | 📈 Precios del mercado |
| `/historial` | 📜 Últimos trades |
| `/ai` | 🧠 Análisis completo por IA |
| `/resumen_hoy` | 📅 P&L del día |
| `/resumen_semana` | 📆 P&L semanal |
| `/mejores` | 🏆 Top 3 mejores trades |
| `/peores` | 📉 Top 3 peores trades |
| `/fees` | 💸 Comisiones pagadas |

---

## 🛡️ Seguridad

- ❌ **NUNCA** habilites permisos de retiro en tu API de Binance
- ✅ Restringe tu API por IP si es posible
- ✅ Las credenciales se cargan desde `.env` (nunca hardcodeadas)
- ✅ El `.gitignore` excluye `.env`, `data/`, y `logs/`

---

## ⚠️ Disclaimer

> **Este software es solo para fines educativos.** El trading de criptomonedas conlleva riesgos significativos. No inviertas dinero que no puedas permitirte perder. Los resultados pasados en paper trading no garantizan resultados futuros con dinero real. El autor no se hace responsable de pérdidas financieras derivadas del uso de este software.

---

## 📄 Licencia

Este proyecto está bajo la licencia MIT. Ver [LICENSE](LICENSE) para más detalles.

---

<p align="center">
  Hecho con ❤️ y 🦊 por <a href="https://github.com/Foxlith">Foxlith</a>
</p>
