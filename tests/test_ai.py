"""Test rápido del AI Advisor con llama3.1"""
import time
import sys
sys.path.insert(0, ".")

from src.ai.ollama_advisor import OllamaAdvisor

advisor = OllamaAdvisor()

fake_market = {
    "price": 82500, "rsi": 42, "macd": -150, "macd_signal": -120,
    "macd_hist": -30, "trend": "downtrend", "bb_position": "lower_half",
    "atr": 1200, "change_24h": -2.5, "ema_200": 85000,
}

print("Consultando a la IA (llama3.1)...")
t = time.time()
result = advisor.analyze_trade_signal("BTC/USDT", "DCA", "buy", fake_market)
elapsed = time.time() - t

print(f"\n=== RESULTADO ===")
print(f"Tiempo: {elapsed:.1f}s")
print(f"Aprobado: {result['approved']}")
print(f"Confianza: {result['confidence']}/10")
print(f"Razon: {result['reasoning']}")
print(f"Recomendacion: {result['recommendation']}")
print(f"\n[TEST COMPLETADO]")
