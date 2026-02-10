"""
Configuración principal del Bot de Trading
==========================================
Bot automatizado para criptomonedas en Binance
Objetivo: Duplicar capital en 1-2 años
"""

import os
from pathlib import Path
from dotenv import load_dotenv

# Cargar variables de entorno
load_dotenv()

# Directorio base del proyecto
BASE_DIR = Path(__file__).resolve().parent.parent

# =============================================================================
# CONFIGURACIÓN DEL EXCHANGE
# =============================================================================
EXCHANGE = {
    "name": "binance",
    "testnet": True,  # Cambiar a False para producción
    "api_key": os.getenv("BINANCE_API_KEY", ""),
    "api_secret": os.getenv("BINANCE_API_SECRET", ""),
    "options": {
        "defaultType": "spot",  # spot, future, margin
        "adjustForTimeDifference": True,
    }
}

# =============================================================================
# CONFIGURACIÓN DE CAPITAL Y APORTES
# =============================================================================
CAPITAL = {
    "initial_cop": 300_000,  # Pesos colombianos
    "monthly_contribution_cop": 300_000,
    "usd_cop_rate": 4_000,  # Tasa aproximada COP/USD
    "initial_usd": 75,  # ~$75 USD
    "monthly_contribution_usd": 75,
}

# =============================================================================
# PORTAFOLIO - DISTRIBUCIÓN RECOMENDADA
# =============================================================================
PORTFOLIO = {
    "BTC/USDT": {
        "allocation": 0.35,  # 35% del capital (bajado de 60% - ETH rinde mejor en Grid)
        "min_order_usd": 10,
        "description": "Bitcoin - Base sólida, menor volatilidad"
    },
    "ETH/USDT": {
        "allocation": 0.40,  # 40% del capital (subido de 30% - mejor WR en Grid)
        "min_order_usd": 10,
        "description": "Ethereum - Mayor volatilidad, mejor para Grid"
    },
    "SOL/USDT": {
        "allocation": 0.25,  # 25% del capital (subido de 10% - diversificación)
        "min_order_usd": 10,
        "description": "Solana - Alto potencial de crecimiento"
    },
}

# =============================================================================
# COSTOS DE TRADING (NUEVO - Comisiones y Slippage)
# =============================================================================
TRADING_COSTS = {
    # Comisiones de Binance (0.1% maker/taker estándar)
    "maker_fee_pct": 0.001,  # 0.1%
    "taker_fee_pct": 0.001,  # 0.1%
    
    # Slippage tolerance para cálculos pesimistas
    "slippage_tolerance_pct": 0.0005,  # 0.05%
    
    # Fee total estimado por roundtrip (compra + venta)
    "roundtrip_fee_pct": 0.002,  # 0.2% total
}

# =============================================================================
# GESTIÓN DE RIESGO
# =============================================================================
RISK_MANAGEMENT = {
    # Máximo porcentaje del capital por trade
    # AUMENTADO: De 15% a 40% para alcanzar 10-15% utilización total
    "max_position_size_pct": 0.40,  # 40% del capital asignado a estrategia por trade
    
    # Tamaño mínimo de orden en USD (nuevo)
    "min_order_size_usd": 1.00,  # Mínimo $1 por orden (antes era ~$0.15)
    
    # Stop loss por defecto (usado como fallback si ATR no disponible)
    "default_stop_loss_pct": 0.03,  # 3%
    
    # Take profit por defecto
    "default_take_profit_pct": 0.06,  # 6%
    
    # Trailing stop
    "trailing_stop_pct": 0.02,  # 2%
    
    # Máximo drawdown permitido antes de pausar
    "max_drawdown_pct": 0.15,  # 15%
    
    # Drawdown DIARIO máximo (nuevo trigger de pausa)
    "max_daily_drawdown_pct": 0.01,  # 1% diario - Pausa si se pierde 1% en un día
    
    # Número máximo de trades abiertos simultáneamente
    "max_open_trades": 5,
    
    # Pausa después de X pérdidas consecutivas
    "pause_after_losses": 5,  # Subido de 3 a 5 para evitar pausas por pérdidas pequeñas
    
    # Tiempo de pausa en horas
    "pause_duration_hours": 24,
}

# =============================================================================
# CONFIGURACIÓN DE ESTRATEGIAS
# =============================================================================
STRATEGIES = {
    "grid_trading": {
        "enabled": True,
        "grid_levels": 10,
        "grid_spacing_pct": 0.005,  # 0.5% entre niveles
        "take_profit_pct": 0.008,  # SUBIDO: 0.8% (antes 0.5%) para margen seguro
        "allocation_pct": 0.30,  # 30% del capital para esta estrategia
        "min_volatility_atr": 0.3,  # 0.3% ATR mínimo
        "order_size_usd": 2.50,  # Tamaño fijo por nivel $2.50
    },
    "dca_intelligent": {
        "enabled": True,
        "buy_interval_hours": 4,  # Cada 4 horas
        "dip_threshold_pct": 0.03,  # REDUCIDO: Comprar extra si baja 3% (antes 5%)
        "allocation_pct": 0.40,  # 40% del capital
        "order_size_usd": 3.00,  # NUEVO: Tamaño fijo por compra DCA $3.00
    },
    "technical_rsi_macd": {
        "enabled": True,
        "rsi_oversold": 30,  # Industria estándar: 30 (más conservador)
        "rsi_overbought": 70,  # Industria estándar: 70 (más conservador)
        "macd_signal_threshold": 0,
        "allocation_pct": 0.30,  # 30% del capital
    },
}

# =============================================================================
# CONFIGURACIÓN DE NOTIFICACIONES (TELEGRAM)
# =============================================================================
TELEGRAM = {
    "enabled": True,
    "bot_token": os.getenv("TELEGRAM_BOT_TOKEN", ""),
    "chat_id": os.getenv("TELEGRAM_CHAT_ID", ""),
    "notifications": {
        "on_trade_open": True,
        "on_trade_close": True,
        "on_profit": True,
        "on_loss": True,
        "daily_summary": True,
        "on_error": True,
    }
}

# =============================================================================
# INTERVALOS DE TIEMPO
# =============================================================================
TIMEFRAMES = {
    "primary": "1h",      # Timeframe principal para análisis
    "secondary": "4h",    # Timeframe secundario
    "trend": "1d",        # Para detectar tendencia general
}

# =============================================================================
# BASE DE DATOS
# =============================================================================
DATABASE = {
    "type": "sqlite",
    "path": BASE_DIR / "data" / "trading_bot.db",
}

# =============================================================================
# LOGGING
# =============================================================================
LOGGING = {
    "level": "INFO",
    "file": BASE_DIR / "logs" / "bot.log",
    "format": "%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    "max_size_mb": 10,
    "backup_count": 5,
}

# =============================================================================
# MODO DE OPERACIÓN
# =============================================================================
OPERATION_MODE = {
    "mode": "paper",  # "paper" para simulación, "live" para real
    "paper_balance_usd": 75,  # Balance inicial en paper trading
}
