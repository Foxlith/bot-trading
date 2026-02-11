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
    "initial_cop": 800_000,  # Total invertido en pesos colombianos (300k + 500k)
    "monthly_contribution_cop": 300_000,
    "usd_cop_rate": 3_652,  # TRM actual COP/USD
    "initial_usd": 211.92,  # $75 + $136.92 (500k COP)
    "monthly_contribution_usd": 82,
}

# =============================================================================
# PORTAFOLIO - DISTRIBUCIÓN RECOMENDADA
# =============================================================================
PORTFOLIO = {
    "BTC/USDT": {
        "allocation": 0.45,  # 45% del capital (concentrado para mejor sizing)
        "min_order_usd": 5,
        "description": "Bitcoin - Base sólida, menor volatilidad"
    },
    "ETH/USDT": {
        "allocation": 0.55,  # 55% del capital (mejor rendimiento en Grid)
        "min_order_usd": 5,
        "description": "Ethereum - Mayor volatilidad, mejor para Grid"
    },
    "SOL/USDT": {
        "allocation": 0.0,   # SELL-ONLY: No comprar más, solo vender posiciones existentes
        "min_order_usd": 5,
        "sell_only": True,    # Marcador para que las estrategias solo vendan
        "description": "Solana - Solo vender posiciones existentes"
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
    "trailing_stop_pct": 0.03,  # 3% (optimizado, antes 2%)
    
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
        "grid_levels": 5,           # REDUCIDO: 5 niveles (antes 10) = menos exposición
        "grid_spacing_pct": 0.02,   # SUBIDO: 2% entre niveles (antes 0.5%) = grid cubre 10% de rango
        "take_profit_pct": 0.03,    # 3% profit target = mayor margen neto después de fees
        "allocation_pct": 0.30,     # 30% del capital para esta estrategia
        "min_volatility_atr": 0.3,  # 0.3% ATR mínimo
        "order_size_usd": 2.50,     # Tamaño fijo por nivel $2.50
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
        "rsi_overbought": 65,  # Optimizado: 65 (antes 70) - Vender antes
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
