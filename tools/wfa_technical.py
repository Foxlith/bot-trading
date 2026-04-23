"""
Walk-Forward Analysis (WFA) para Estrategia Technical
=====================================================
El WFA minimiza el OVERFITTING evaluando si los parámetros encontrados en
datos pasados resuenan en un período "no visto" inmediatamente posterior.

Divide el histórico en ventanas MÓVILES.
- Ventana 1: Optimiza en Meses 1-3 -> Prueba en Mes 4
- Ventana 2: Optimiza en Meses 2-4 -> Prueba en Mes 5
- Ventana 3: Optimiza en Meses 3-5 -> Prueba en Mes 6

Si los parámetros ganadores del período de Entrenamiento ganan 
en el período de Prueba, la estrategia es robusta para el mundo real.
"""

import itertools
import sys
import os
import pandas as pd

# Añadimos la ruta raíz para importar módulos core
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from backtest import download_binance_data, add_indicators, PORTFOLIO_ALLOC
from optimize_technical import run_tech_backtest

def run_wfa():
    print("\n" + "=" * 70)
    print("  🔬 WALK-FORWARD ANALYSIS - TECHNICAL STRATEGY")
    print("=" * 70)

    symbols = list(PORTFOLIO_ALLOC.keys())
    df_dict = {}
    
    # Descargar 6 meses de datos para tener suficiente histórico
    print("  📥 Descargando 6 meses de datos históricos para WFA...")
    for symbol in symbols:
        df = download_binance_data(symbol, "1h", 6)
        df = add_indicators(df)
        df_dict[symbol] = df

    # Definir la parrilla de parámetros a buscar en In-Sample
    # Acotada ligeramente para evitar simulaciones infinitas en WFA
    param_grid = {
        "rsi_oversold":     [20, 25, 30],
        "rsi_overbought":   [70, 75, 80],
        "stop_loss_pct":    [0.03, 0.05, 0.07],
        "take_profit_pct":  [0.04, 0.06, 0.08],
        "trailing_stop_pct": [0.015, 0.02, 0.03],
    }
    
    keys = list(param_grid.keys())
    values = list(param_grid.values())
    combinations = list(itertools.product(*values))

    # Obtener el timestamp inicial general para anclar las ventanas
    start_ts = min([df['timestamp'].min() for df in df_dict.values()])
    
    # Crear las ventanas (Windows) a lo largo de 6 meses
    # Cada mes se define en promedios de 30 días
    train_days_len = 90  # 3 meses In-Sample
    test_days_len = 30   # 1 mes Out-Of-Sample
    step_days = 30       # Avanzar la ventana 1 mes por iteración
    
    windows = []
    for i in range(3):
        train_start = start_ts + pd.Timedelta(days=i * step_days)
        train_end = train_start + pd.Timedelta(days=train_days_len)
        test_end = train_end + pd.Timedelta(days=test_days_len)
        
        windows.append({
            "name": f"W{i+1}",
            "train_start": train_start,
            "train_end": train_end,
            "test_start": train_end,
            "test_end": test_end
        })

    print(f"\n  📊 Iniciando simulación sobre {len(combinations)} combinaciones por cada una de {len(windows)} ventanas...\n")

    wfa_results = []

    # Iterar cada ventana deslizante
    for w in windows:
        print(f"\n  ▶️ Procesando Ventana {w['name']}:")
        print(f"     Entrenamiento (IS):  {w['train_start'].date()} -> {w['train_end'].date()}")
        print(f"     Prueba OOS  (OOS): {w['test_start'].date()} -> {w['test_end'].date()}")
        
        # 1. Preparar Diccionario Train
        train_dict = {}
        for s, df in df_dict.items():
            mask = (df['timestamp'] >= w['train_start']) & (df['timestamp'] < w['train_end'])
            train_dict[s] = df.loc[mask].copy()

        # Encontrar el mejor set de parámetros en Entrenamiento
        best_train_result = None
        
        for combo in combinations:
            config = dict(zip(keys, combo))
            config["allocation_pct"] = 0.30
            
            res = run_tech_backtest(train_dict, config)
            if best_train_result is None or res["return_pct"] > best_train_result["return_pct"]:
                best_train_result = res
                
        best_cfg = best_train_result["config"]
        print(f"     🏆 Ganador IS: ROI {best_train_result['return_pct']:+.2f}%")
        print(f"        -> [RSI:{best_cfg['rsi_oversold']}/{best_cfg['rsi_overbought']} SL:{best_cfg['stop_loss_pct']*100:.0f}% TP:{best_cfg['take_profit_pct']*100:.0f}%]")
        
        # 2. Someter a la Prueba de Fuego (Out-Of-Sample) con datos no vistos
        test_dict = {}
        empty_test = False
        for s, df in df_dict.items():
            mask = (df['timestamp'] >= w['test_start']) & (df['timestamp'] < w['test_end'])
            subset = df.loc[mask].copy()
            if subset.empty:
                empty_test = True
            test_dict[s] = subset
            
        if empty_test:
            print("     ⚠️ Advertencia: No hay suficientes datos para el test. Saltando ventana.")
            continue
            
        test_res = run_tech_backtest(test_dict, best_cfg)
        print(f"     📊 Resultado OOS: ROI {test_res['return_pct']:+.2f}%, WR: {test_res['win_rate']:.1f}%")
        
        wfa_results.append({
            "window": w['name'],
            "train_roi": best_train_result['return_pct'],
            "test_roi": test_res['return_pct'],
            "config": best_cfg
        })

    # Imprimir Reporte Final Consolidado
    print("\n\n" + "=" * 70)
    print("  ✅ RESUMEN WALK-FORWARD ANALYSIS")
    print("=" * 70)
    
    total_test_roi = 0
    passed_windows = 0
    
    for r in wfa_results:
        # Se considera "PASS" si en el mercado real (OOS) mantuvimos rendimientos positivos
        status = "🟢 PASS" if r['test_roi'] > 0 else "🔴 FAIL"
        if r['test_roi'] > 0:
            passed_windows += 1
        total_test_roi += r['test_roi']
        
        c = r['config']
        print(f"  {r['window']:>4} | Train (Pasado): {r['train_roi']:>+7.2f}% | Test (Futuro): {r['test_roi']:>+7.2f}% {status}")
        print(f"         -> Parámetros: RSI {c['rsi_oversold']}/{c['rsi_overbought']}, SL {c['stop_loss_pct']*100:.0f}%, TP {c['take_profit_pct']*100:.0f}%")
    
    if len(wfa_results) > 0:
        avg_test_roi = total_test_roi / len(wfa_results)
        efficiency = passed_windows / len(wfa_results) * 100
        
        print("\n  🎯 MÉTRICAS DE ROBUSTEZ FINAL:")
        print(f"     Eficiencia OOS (Victorias en pruebas no vistas): {efficiency:.0f}%")
        print(f"     ROI Promedio Mensual Out-of-Sample:              {avg_test_roi:+.2f}%")
        
        if efficiency >= 66 and avg_test_roi > 0:
            print("\n  🌟 CONCLUSIÓN: La estrategia TÉCNICA es ROBUSTA. Minimiza el overfitting de parámetros.")
            print("                 Es segura para desplegarse o considerarse un setup estructural válido.")
        else:
            print("\n  ⚠️ CONCLUSIÓN: La estrategia sufre de OVERFITTING. Los parámetros rinden bien")
            print("                 viéndolos al pasado, pero fallan consistentemente en datos nuevos.")
    
    print("=" * 70 + "\n")

if __name__ == "__main__":
    run_wfa()
