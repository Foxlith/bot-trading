import os
import sqlite3
import pandas as pd
import matplotlib.pyplot as plt
import seaborn as sns
from datetime import datetime
from loguru import logger
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from config.settings import DATABASE

class ChartGenerator:
    """Generador de gráficos estadísticos del bot."""
    
    def __init__(self):
        self.db_path = DATABASE["path"]
        self.output_dir = "results/charts"
        os.makedirs(self.output_dir, exist_ok=True)
        
        # Configurar estilo Dark Mode para Seaborn
        plt.style.use('dark_background')
        sns.set_theme(style="darkgrid", rc={
            "axes.facecolor": "#1e1e1e",
            "figure.facecolor": "#121212",
            "axes.edgecolor": "#333333",
            "grid.color": "#2c2c2c",
            "text.color": "#e0e0e0",
            "axes.labelcolor": "#e0e0e0",
            "xtick.color": "#e0e0e0",
            "ytick.color": "#e0e0e0"
        })

    def generate_daily_performance_chart(self) -> str:
        """
        Genera un panel con 2 gráficos:
        1. Curva de ganancias acumuladas en el tiempo.
        2. Beneficio neto por moneda.
        
        Retorna la ruta absoluta de la imagen generada.
        """
        try:
            with sqlite3.connect(self.db_path) as conn:
                # Obtener solo trades cerrados (ventas)
                query = "SELECT closed_at, symbol, profit FROM trade_history WHERE side = 'sell' AND closed_at IS NOT NULL ORDER BY closed_at ASC"
                df = pd.read_sql_query(query, conn)
                
            if df.empty:
                logger.warning("No hay trades para generar el gráfico.")
                return ""
            
            # Convertir fechas
            df['closed_at'] = pd.to_datetime(df['closed_at'])
            
            # --- Gráfico 1: Curva de PnL Acumulado ---
            df_time = df.sort_values('closed_at')
            df_time['cumulative_profit'] = df_time['profit'].cumsum()
            
            # --- Gráfico 2: Profit por Símbolo ---
            df_symbol = df.groupby('symbol')['profit'].sum().reset_index()
            df_symbol = df_symbol.sort_values('profit', ascending=False)
            
            # Crear figura con 2 subplots
            fig, (ax1, ax2) = plt.subplots(2, 1, figsize=(10, 10), dpi=150)
            fig.patch.set_facecolor('#121212')
            
            # Dibujar Curva PnL
            sns.lineplot(data=df_time, x='closed_at', y='cumulative_profit', ax=ax1, color='#00ff9d', linewidth=2.5)
            ax1.fill_between(df_time['closed_at'], df_time['cumulative_profit'], alpha=0.2, color='#00ff9d')
            ax1.set_title("Crecimiento de Capital (P&L Acumulado)", fontsize=14, pad=15, color='white', weight='bold')
            ax1.set_ylabel("Ganancia Neta (USDT)", fontsize=11)
            ax1.set_xlabel("")
            
            # Formatear el eje X para que no se superpongan las fechas
            fig.autofmt_xdate()
            
            # Dibujar Barras por Símbolo
            colors = ['#00ff9d' if x >= 0 else '#ff4d4d' for x in df_symbol['profit']]
            sns.barplot(data=df_symbol, x='symbol', y='profit', ax=ax2, palette=colors)
            ax2.set_title("Rendimiento por Criptomoneda", fontsize=14, pad=15, color='white', weight='bold')
            ax2.set_ylabel("Profit (USDT)", fontsize=11)
            ax2.set_xlabel("")
            ax2.tick_params(axis='x', rotation=45)
            
            # Ajustar layout
            plt.tight_layout(pad=3.0)
            
            # Guardar
            filename = f"daily_report_{datetime.now().strftime('%Y%m%d')}.png"
            filepath = os.path.join(self.output_dir, filename)
            absolute_path = os.path.abspath(filepath)
            
            plt.savefig(absolute_path, bbox_inches='tight', facecolor=fig.get_facecolor())
            plt.close()
            
            logger.info(f"📊 Gráfico generado correctamente en {absolute_path}")
            return absolute_path
            
        except Exception as e:
            logger.error(f"❌ Error generando gráficos: {e}")
            import traceback
            logger.error(traceback.format_exc())
            return ""

def get_chart_generator():
    return ChartGenerator()
