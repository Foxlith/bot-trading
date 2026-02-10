"""
Test Notification Format
========================
Simulates a trade and prints the formatted Telegram message.
"""
import sys
import json
sys.path.insert(0, ".") # Add current dir to path

from src.utils.transaction_manager import TransactionManager

def test_notification():
    print("=" * 60)
    print("TESTING TELEGRAM NOTIFICATION FORMAT")
    print("=" * 60)
    
    # 1. Simulate Buy
    print("\n--- SIMULATION: BUY SOL ---")
    tx_id = TransactionManager.generate_tx_id("SOL/USDT", "buy", "DCA")
    
    buy_payload = TransactionManager.create_trade_payload(
        tx_id=tx_id,
        symbol="SOL/USDT",
        side="buy",
        price=124.18,
        amount=0.02417207,
        strategy="DCA Intelligent"
    )
    # Add fee manually as it would happen in strategy
    buy_payload["fee_paid"] = 0.003  # $3 * 0.1%
    
    msg_buy = TransactionManager.format_telegram_message(buy_payload)
    print(msg_buy)
    
    # 2. Simulate Sell (Profit)
    print("\n\n--- SIMULATION: SELL BTC (Take Profit) ---")
    tx_id_sell = TransactionManager.generate_tx_id("BTC/USDT", "sell", "Grid")
    
    sell_payload = TransactionManager.create_trade_payload(
        tx_id=tx_id_sell,
        symbol="BTC/USDT",
        side="sell",
        price=91500.00,
        amount=0.0005,
        strategy="Grid Trading"
    )
    sell_payload["fee_paid"] = 0.045  # Approx fees
    sell_payload["profit"] = 1.25     # Net profit
    
    msg_sell = TransactionManager.format_telegram_message(sell_payload)
    print(msg_sell)

if __name__ == "__main__":
    test_notification()
