"""
Optimizador de Estrategia Technical
====================================
Ejecuta múltiples backtests con diferentes parámetros
para encontrar la configuración más rentable.
"""

import itertools
import sys
import os

# Añadir el directorio actual al path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from backtest import (
    download_binance_data, add_indicators, 
    TechnicalSimulator, PORTFOLIO_ALLOC, FEE_RATE
)

import pandas as pd
import numpy as np
from datetime import datetime


def run_tech_backtest(df_dict: dict, config: dict, capital: float = 60.0) -> dict:
    """Ejecuta un backtest SOLO de Technical con los parámetros dados."""
    tech = TechnicalSimulator(capital, config)
    
    # Alinear datos
    common_ts = None
    for symbol, df in df_dict.items():
        ts_set = set(df["timestamp"])
        if common_ts is None:
            common_ts = ts_set
        else:
            common_ts = common_ts.intersection(ts_set)
    common_ts = sorted(common_ts)
    
    indexed = {s: df.set_index("timestamp") for s, df in df_dict.items()}
    
    peak = capital
    max_dd = 0
    
    for ts in common_ts:
        prices = {}
        for symbol in df_dict.keys():
            if ts not in indexed[symbol].index:
                continue
            row = indexed[symbol].loc[ts]
            prices[symbol] = row["close"]
            
            ema_200 = row.get("ema_200", 0)
            can_buy = ema_200 <= 0 or row["close"] >= ema_200
            tech.process_tick(symbol, row, can_buy, ts)
        
        equity = tech.get_equity(prices)
        if equity > peak:
            peak = equity
        dd = (peak - equity) / peak if peak > 0 else 0
        if dd > max_dd:
            max_dd = dd
    
    # Resultados
    final_prices = {s: df["close"].iloc[-1] for s, df in df_dict.items()}
    final_equity = tech.get_equity(final_prices)
    
    sells = [t for t in tech.trades if t["side"] == "sell"]
    buys = [t for t in tech.trades if t["side"] == "buy"]
    wins = [t for t in sells if t.get("profit", 0) > 0]
    total_profit = sum(t.get("profit", 0) for t in sells)
    total_fees = sum(t.get("fee", 0) for t in tech.trades)
    win_rate = len(wins) / len(sells) * 100 if sells else 0
    
    return {
        "config": config,
        "final_equity": final_equity,
        "return_pct": (final_equity / capital - 1) * 100,
        "max_drawdown": max_dd * 100,
        "total_trades": len(sells),
        "win_rate": win_rate,
        "total_profit": total_profit,
        "total_fees": total_fees,
        "wins": len(wins),
        "losses": len(sells) - len(wins),
    }


def main():
    print("\n" + "=" * 70)
    print("  🔬 OPTIMIZADOR DE ESTRATEGIA TECHNICAL")
    print("=" * 70)
    
    # Descargar datos (3 meses)
    symbols = list(PORTFOLIO_ALLOC.keys())
    df_dict = {}
    for symbol in symbols:
        df = download_binance_data(symbol, "1h", 3)
        df = add_indicators(df)
        df_dict[symbol] = df
    
    # Parámetros a probar
    param_grid = {
        "rsi_oversold":     [25, 30, 35],
        "rsi_overbought":   [65, 70, 75],
        "stop_loss_pct":    [0.03, 0.05, 0.07],
        "take_profit_pct":  [0.04, 0.06, 0.08, 0.10],
        "trailing_stop_pct": [0.015, 0.02, 0.03],
    }
    
    # Generar todas las combinaciones
    keys = list(param_grid.keys())
    values = list(param_grid.values())
    combinations = list(itertools.product(*values))
    
    print(f"\n  📊 Probando {len(combinations)} combinaciones de parámetros...")
    print(f"  📅 Datos: 3 meses, BTC/USDT + ETH/USDT")
    print()
    
    results = []
    best_result = None
    
    for i, combo in enumerate(combinations):
        config = dict(zip(keys, combo))
        config["allocation_pct"] = 0.30
        
        result = run_tech_backtest(df_dict, config)
        results.append(result)
        
        # Track best
        if best_result is None or result["return_pct"] > best_result["return_pct"]:
            best_result = result
        
        # Progreso cada 20 combinaciones
        if (i + 1) % 50 == 0 or i == len(combinations) - 1:
            print(f"  ⏳ {i+1}/{len(combinations)} | Mejor hasta ahora: {best_result['return_pct']:+.2f}% (WR: {best_result['win_rate']:.0f}%)")
    
    # Ordenar por retorno
    results.sort(key=lambda x: x["return_pct"], reverse=True)
    
    # ===== REPORTE =====
    print("\n" + "=" * 70)
    print("  📊 TOP 10 CONFIGURACIONES")
    print("=" * 70)
    print(f"{'#':>3} {'Return':>8} {'WinRate':>8} {'Trades':>7} {'DD':>6} {'Profit':>9} | RSI_OS RSI_OB  SL    TP   Trail")
    print("-" * 90)
    
    for i, r in enumerate(results[:10]):
        c = r["config"]
        print(f"{i+1:>3} {r['return_pct']:>+7.2f}% {r['win_rate']:>7.1f}% {r['total_trades']:>6}  {r['max_drawdown']:>5.1f}% ${r['total_profit']:>7.2f} |"
              f"  {c['rsi_oversold']:>4}  {c['rsi_overbought']:>5}  {c['stop_loss_pct']*100:.0f}%  {c['take_profit_pct']*100:.0f}%  {c['trailing_stop_pct']*100:.1f}%")
    
    # Peores
    print(f"\n  ❌ PEORES 3:")
    for i, r in enumerate(results[-3:]):
        c = r["config"]
        print(f"     {r['return_pct']:>+7.2f}% WR:{r['win_rate']:>5.1f}% | RSI {c['rsi_oversold']}/{c['rsi_overbought']} SL:{c['stop_loss_pct']*100:.0f}% TP:{c['take_profit_pct']*100:.0f}%")
    
    # MEJOR configuración
    best = results[0]
    bc = best["config"]
    print(f"\n  {'═' * 66}")
    print(f"  🏆 MEJOR CONFIGURACIÓN ENCONTRADA:")
    print(f"  {'═' * 66}")
    print(f"     RSI Oversold:     {bc['rsi_oversold']}")
    print(f"     RSI Overbought:   {bc['rsi_overbought']}")
    print(f"     Stop Loss:        {bc['stop_loss_pct']*100:.0f}%")
    print(f"     Take Profit:      {bc['take_profit_pct']*100:.0f}%")
    print(f"     Trailing Stop:    {bc['trailing_stop_pct']*100:.1f}%")
    print(f"     Return:           {best['return_pct']:+.2f}%")
    print(f"     Win Rate:         {best['win_rate']:.1f}%")
    print(f"     Max Drawdown:     {best['max_drawdown']:.1f}%")
    print(f"     Trades:           {best['total_trades']} ({best['wins']}W / {best['losses']}L)")
    print(f"     Profit:           ${best['total_profit']:.2f}")
    print(f"  {'═' * 66}")
    
    # Guardar resultados
    with open("optimize_result.txt", "w", encoding="utf-8") as f:
        f.write("=== TECHNICAL STRATEGY OPTIMIZATION ===\n\n")
        f.write("TOP 10 CONFIGURATIONS:\n")
        for i, r in enumerate(results[:10]):
            c = r["config"]
            f.write(f"#{i+1}: Return={r['return_pct']:+.2f}% WR={r['win_rate']:.1f}% "
                    f"Trades={r['total_trades']} DD={r['max_drawdown']:.1f}% "
                    f"Profit=${r['total_profit']:.2f} | "
                    f"RSI={c['rsi_oversold']}/{c['rsi_overbought']} "
                    f"SL={c['stop_loss_pct']*100:.0f}% TP={c['take_profit_pct']*100:.0f}% "
                    f"Trail={c['trailing_stop_pct']*100:.1f}%\n")
        
        f.write(f"\nBEST CONFIG:\n")
        for k, v in bc.items():
            f.write(f"  {k}: {v}\n")
        f.write(f"\nBest Return: {best['return_pct']:+.2f}%\n")
        f.write(f"Best Win Rate: {best['win_rate']:.1f}%\n")
    
    print("\n  [Resultados guardados en optimize_result.txt]")


if __name__ == "__main__":
    main()
