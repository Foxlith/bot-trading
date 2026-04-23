"""
Transaction ID Generator and Notifier
======================================
Generates unique transaction IDs for each trade and ensures delivery to Telegram
"""
import uuid
import hashlib
from datetime import datetime
from typing import Optional
import json

class TransactionManager:
    """
    Manages unique transaction IDs for all trades.
    Ensures every buy/sell has a traceable ID for sync with external systems.
    """
    
    @staticmethod
    def generate_tx_id(symbol: str, side: str, strategy: str) -> str:
        """
        Generate a unique transaction ID.
        Format: TX-{STRATEGY}-{SYMBOL}-{TIMESTAMP}-{HASH}
        Example: TX-DCA-BTC-20260126-a1b2c3
        """
        timestamp = datetime.now().strftime("%Y%m%d%H%M%S")
        unique_part = uuid.uuid4().hex[:6].upper()
        symbol_short = symbol.replace("/USDT", "").replace("/", "")
        strategy_short = strategy[:3].upper()
        
        tx_id = f"TX-{strategy_short}-{symbol_short}-{timestamp}-{unique_part}"
        return tx_id
    
    @staticmethod
    def create_trade_payload(
        tx_id: str,
        symbol: str,
        side: str,
        price: float,
        amount: float,
        strategy: str,
        profit: Optional[float] = None
    ) -> dict:
        """
        Create standardized trade payload for notifications.
        This payload should be sent to both Telegram and Bubble.
        """
        return {
            "tx_id": tx_id,
            "timestamp": datetime.now().isoformat(),
            "symbol": symbol,
            "side": side,  # "buy" or "sell"
            "price": price,
            "amount": amount,
            "value_usd": price * amount,
            "strategy": strategy,
            "profit": profit,
            "status": "executed"
        }
    
    @staticmethod
    def format_telegram_message(payload: dict) -> str:
        """
        Format trade payload for Telegram notification.
        """
        emoji = "🟢" if payload["side"] == "buy" else "🔴"
        profit_text = ""
        if payload.get("profit") is not None:
            p = payload["profit"]
            profit_emoji = "✅" if p >= 0 else "❌"
            profit_text = f"\n{profit_emoji} <b>Profit:</b> ${p:+.4f}"
        
        fee_text = ""
        net_invest_text = ""
        
        if payload.get("fee_paid") is not None:
            fee_text = f"\n💸 <b>Comisión:</b> ${payload['fee_paid']:.4f}"
            
        # Calcular inversión neta (Valor - Fees)
        if payload.get("value_usd") is not None:
            from decimal import Decimal
            import math
            def safe_d(v, d='0'):
                try:
                    if v is None or v == '' or (isinstance(v, float) and (math.isnan(v) or math.isinf(v))):
                        return Decimal(d)
                    return Decimal(str(v))
                except: return Decimal(d)
            net_val = safe_d(payload['value_usd'])
            if payload.get("fee_paid") is not None:
                d_fee = safe_d(payload['fee_paid'])
                if payload["side"] == "buy":
                    net_val += d_fee # Costo total
                else:
                    net_val -= d_fee # Recibido neto
            net_invest_text = f"\n💵 <b>Inversión Neta:</b> ${float(net_val):.4f}"

        # Razón del cierre (Trailing Stop, Take Profit, etc.)
        reason_text = ""
        if payload.get("reason"):
            reason_text = f"\n📋 <b>Razón:</b> {payload['reason']}"

        msg = f"""
{emoji} <b>TRADE EJECUTADO</b>

🔖 <b>ID Operación:</b> <code>{payload['tx_id']}</code>
📊 <b>Par:</b> {payload['symbol']}
📌 <b>Tipo:</b> {payload['side'].upper()}
💰 <b>Precio:</b> ${float(payload['price']):,.2f}
📦 <b>Cantidad:</b> {float(payload['amount']):.8f}
{fee_text}{net_invest_text}
🎯 <b>Estrategia:</b> {payload['strategy']}{profit_text}{reason_text}

⏰ {payload.get('timestamp', datetime.now().strftime('%Y-%m-%d %H:%M:%S'))}
"""
        return msg.strip()


# Example usage for integration into existing strategies
def example_integration():
    """
    How to integrate TransactionManager into existing code:
    
    In DCAStrategy, GridStrategy, or TechnicalStrategy:
    
    1. Import: from src.utils.transaction_manager import TransactionManager
    
    2. On Buy:
        tx_id = TransactionManager.generate_tx_id(symbol, "buy", "DCA")
        payload = TransactionManager.create_trade_payload(
            tx_id=tx_id,
            symbol=symbol,
            side="buy",
            price=price,
            amount=amount,
            strategy="DCA Intelligent"
        )
        # Send to Telegram
        telegram_msg = TransactionManager.format_telegram_message(payload)
        await notifier.send_message(telegram_msg)
        
        # Send to Bubble (if integrated)
        # await bubble_client.create_trade(payload)
        
        # Store tx_id in local DB for reference
        # Add tx_id to trade_history table
    
    3. On Sell:
        tx_id = TransactionManager.generate_tx_id(symbol, "sell", "Grid")
        payload = TransactionManager.create_trade_payload(
            tx_id=tx_id,
            symbol=symbol,
            side="sell",
            price=price,
            amount=amount,
            strategy="Grid Trading",
            profit=profit
        )
        # Same notification flow as above
    """
    
    # Demo
    tx_id = TransactionManager.generate_tx_id("BTC/USDT", "buy", "DCA")
    payload = TransactionManager.create_trade_payload(
        tx_id=tx_id,
        symbol="BTC/USDT",
        side="buy",
        price=90000,
        amount=0.0001,
        strategy="DCA Intelligent"
    )
    
    print("Generated TX ID:", tx_id)
    print("\nPayload (for Bubble API):")
    print(json.dumps(payload, indent=2, default=str))
    print("\nTelegram Message:")
    print(TransactionManager.format_telegram_message(payload))


if __name__ == "__main__":
    example_integration()
