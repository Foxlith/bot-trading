"""
Ollama AI Advisor
==================
Analista de mercado inteligente usando LLMs locales vía Ollama.
Actúa como "segundo par de ojos" para filtrar señales de trading.

Funcionalidades:
- Filtro de señales: Evalúa si un trade propuesto es viable
- Análisis de portafolio: Análisis completo a demanda
- Reporte diario: Resumen narrativo inteligente
"""

import json
import time
from typing import Dict, Any, Optional
from datetime import datetime, timedelta
from loguru import logger

# Intentar importar ollama
try:
    import ollama
    OLLAMA_AVAILABLE = True
except ImportError:
    OLLAMA_AVAILABLE = False
    logger.warning("⚠️ Paquete 'ollama' no instalado. Ejecuta: pip install ollama")

import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from config.settings import OLLAMA


class OllamaAdvisor:
    """
    Analista de mercado IA usando Ollama (modelos locales).
    
    Actúa como filtro inteligente de señales de trading:
    - Analiza datos técnicos (RSI, MACD, tendencia, etc.)
    - Evalúa si un trade es recomendable con score de confianza
    - Genera reportes narrativos en español
    - Cache de respuestas para no sobrecargar
    
    IMPORTANTE: La IA NUNCA ejecuta trades directamente.
    Solo proporciona un score de confianza que el motor de reglas evalúa.
    """
    
    def __init__(self):
        self.enabled = OLLAMA.get("enabled", False) and OLLAMA_AVAILABLE
        self.model = OLLAMA.get("model", "qwen3:8b")
        self.base_url = OLLAMA.get("base_url", "http://localhost:11434")
        self.timeout = OLLAMA.get("timeout_seconds", 30)
        self.filter_enabled = OLLAMA.get("filter_enabled", True)
        self.min_confidence = OLLAMA.get("min_confidence", 5)
        self.cache_minutes = OLLAMA.get("cache_minutes", 5)
        
        # Cache de respuestas (evita consultas repetidas)
        self._cache: Dict[str, Dict] = {}
        self._cache_times: Dict[str, datetime] = {}
        
        # Estadísticas
        self.stats = {
            "queries": 0,
            "approvals": 0,
            "rejections": 0,
            "errors": 0,
            "avg_response_time": 0,
        }
        
        # Verificar conexión con Ollama
        if self.enabled:
            self._check_connection()
        else:
            if not OLLAMA_AVAILABLE:
                logger.info("🧠 AI Advisor deshabilitado (paquete ollama no instalado)")
            else:
                logger.info("🧠 AI Advisor deshabilitado por configuración")
    
    def _check_connection(self) -> None:
        """Verifica que Ollama esté corriendo y el modelo disponible."""
        try:
            # Configurar host si es diferente al default
            if self.base_url != "http://localhost:11434":
                os.environ['OLLAMA_HOST'] = self.base_url
            
            models = ollama.list()
            model_names = [m.model for m in models.models] if hasattr(models, 'models') else []
            
            if not model_names:
                logger.warning("⚠️ No hay modelos instalados en Ollama")
                logger.info(f"   Ejecuta: ollama pull {self.model}")
                self.enabled = False
                return
            
            # Verificar si nuestro modelo está disponible
            model_found = any(self.model in name for name in model_names)
            
            if model_found:
                logger.info(f"🧠 AI Advisor conectado - Modelo: {self.model}")
                logger.info(f"   Filtro {'ACTIVO' if self.filter_enabled else 'INFORMATIVO'} | "
                           f"Confianza mínima: {self.min_confidence}/10")
            else:
                logger.warning(f"⚠️ Modelo '{self.model}' no encontrado en Ollama")
                logger.info(f"   Modelos disponibles: {model_names[:5]}")
                logger.info(f"   Ejecuta: ollama pull {self.model}")
                # Intentar usar el primer modelo disponible como fallback
                if model_names:
                    self.model = model_names[0]
                    logger.info(f"   Usando fallback: {self.model}")
                else:
                    self.enabled = False
                    
        except Exception as e:
            logger.warning(f"⚠️ Ollama no está corriendo o no es accesible: {e}")
            logger.info("   Asegúrate de que Ollama esté iniciado")
            self.enabled = False
    
    def _get_cached(self, cache_key: str) -> Optional[Dict]:
        """Devuelve respuesta cacheada si existe y no ha expirado."""
        if cache_key in self._cache:
            cache_time = self._cache_times.get(cache_key)
            if cache_time and (datetime.now() - cache_time) < timedelta(minutes=self.cache_minutes):
                logger.debug(f"🧠 Cache hit: {cache_key}")
                return self._cache[cache_key]
        return None
    
    def _set_cache(self, cache_key: str, data: Dict) -> None:
        """Guarda respuesta en cache."""
        self._cache[cache_key] = data
        self._cache_times[cache_key] = datetime.now()
    
    def _query_ollama(self, prompt: str, system_prompt: str = "", max_tokens: int = 512) -> Optional[str]:
        """
        Envía una consulta a Ollama y devuelve la respuesta.
        Incluye timeout y manejo de errores.
        
        NOTA: Para modelos Qwen3, se agrega '/no_think' al final del prompt
        para desactivar el modo "thinking" que causa latencia extrema (250s+ → 15-30s).
        """
        if not self.enabled:
            return None
        
        try:
            start_time = time.time()
            
            # Desactivar modo thinking de Qwen3 para respuestas rápidas
            # https://huggingface.co/Qwen/Qwen3-8B - /no_think flag
            effective_prompt = prompt
            if "qwen3" in self.model.lower():
                effective_prompt = prompt + "\n\n/no_think"
            
            messages = []
            if system_prompt:
                messages.append({"role": "system", "content": system_prompt})
            messages.append({"role": "user", "content": effective_prompt})
            
            response = ollama.chat(
                model=self.model,
                messages=messages,
                options={
                    "temperature": 0.3,  # Baja para respuestas más consistentes
                    "num_predict": max_tokens,  # Limitar largo de respuesta
                },
            )
            
            elapsed = time.time() - start_time
            self.stats["queries"] += 1
            
            # Actualizar promedio de tiempo de respuesta
            n = self.stats["queries"]
            self.stats["avg_response_time"] = (
                (self.stats["avg_response_time"] * (n - 1) + elapsed) / n
            )
            
            logger.info(f"🧠 Ollama respondió en {elapsed:.1f}s")
            
            content = response.get("message", {}).get("content", "")
            return content
            
        except Exception as e:
            self.stats["errors"] += 1
            logger.warning(f"⚠️ Error consultando Ollama: {e}")
            return None
    
    def _parse_json_response(self, response: str) -> Optional[Dict]:
        """
        Extrae JSON de la respuesta de Ollama.
        Maneja casos donde la IA incluye texto antes/después del JSON.
        """
        if not response:
            return None
        
        try:
            # Intentar parsear directamente
            return json.loads(response)
        except json.JSONDecodeError:
            pass
        
        # Buscar JSON entre llaves
        try:
            start = response.find("{")
            end = response.rfind("}") + 1
            if start != -1 and end > start:
                json_str = response[start:end]
                return json.loads(json_str)
        except json.JSONDecodeError:
            pass
        
        # Buscar en bloques de código
        try:
            if "```json" in response:
                json_str = response.split("```json")[1].split("```")[0].strip()
                return json.loads(json_str)
            elif "```" in response:
                json_str = response.split("```")[1].split("```")[0].strip()
                return json.loads(json_str)
        except (json.JSONDecodeError, IndexError):
            pass
        
        logger.warning("⚠️ No se pudo extraer JSON de la respuesta de Ollama")
        return None
    
    # =========================================================================
    # MÉTODO PRINCIPAL: Filtro de Señales de Trading
    # =========================================================================
    
    def analyze_trade_signal(
        self,
        symbol: str,
        strategy: str,
        signal_type: str,  # "buy" o "sell"
        market_data: Dict[str, Any],
    ) -> Dict[str, Any]:
        """
        Analiza una señal de trading antes de ejecutarla.
        
        Returns:
            Dict con:
            - approved: bool (True si la IA aprueba el trade)
            - confidence: int (1-10)
            - reasoning: str (explicación en español)
            - recommendation: str ("ejecutar", "esperar", "rechazar")
        """
        # Default: aprobar si la IA no está disponible
        default_response = {
            "approved": True,
            "confidence": 7,
            "reasoning": "IA no disponible - Ejecutando por defecto",
            "recommendation": "ejecutar",
        }
        
        if not self.enabled or not self.filter_enabled:
            return default_response
        
        # Verificar cache
        cache_key = f"signal_{symbol}_{strategy}_{signal_type}"
        cached = self._get_cached(cache_key)
        if cached:
            return cached
        
        # Construir prompt con datos de mercado
        system_prompt = """Eres un analista de trading profesional especializado en criptomonedas.
Tu trabajo es evaluar señales de trading y dar tu opinión experta.

REGLAS ESTRICTAS:
1. Responde ÚNICAMENTE con un JSON válido, sin texto adicional
2. El campo "confidence" debe ser un número entero del 1 al 10
3. El campo "recommendation" debe ser: "ejecutar", "esperar" o "rechazar"
4. El campo "reasoning" debe ser una explicación breve en ESPAÑOL (máximo 2 oraciones)
5. El campo "approved" debe ser true si confidence >= 5, false si < 5
6. NO inventes datos. Usa SOLO los datos proporcionados
7. NO pongas el bloque de pensamiento en la respuesta, solo el JSON"""

        prompt = f"""Analiza esta señal de trading y evalúa si es recomendable ejecutarla:

SEÑAL: {signal_type.upper()} {symbol}
ESTRATEGIA: {strategy}

DATOS DE MERCADO ACTUALES:
- Precio: ${market_data.get('price', 0):,.2f}
- RSI (14): {market_data.get('rsi', 'N/A')}
- MACD: {market_data.get('macd', 'N/A')} (Signal: {market_data.get('macd_signal', 'N/A')})
- Histograma MACD: {market_data.get('macd_hist', 'N/A')}
- Tendencia (EMAs): {market_data.get('trend', 'N/A')}
- Posición Bollinger: {market_data.get('bb_position', 'N/A')}
- Volatilidad (ATR): {market_data.get('atr', 'N/A')}
- Cambio 24h: {market_data.get('change_24h', 'N/A')}%
- EMA 200: ${market_data.get('ema_200', 0):,.2f}

Responde SOLO con este formato JSON:
{{"approved": true/false, "confidence": 1-10, "reasoning": "tu análisis aquí", "recommendation": "ejecutar/esperar/rechazar"}}"""

        response = self._query_ollama(prompt, system_prompt)
        result = self._parse_json_response(response)
        
        if result and all(k in result for k in ["approved", "confidence", "reasoning"]):
            # Validar y normalizar
            confidence = max(1, min(10, int(result.get("confidence", 5))))
            result["confidence"] = confidence
            result["approved"] = confidence >= self.min_confidence
            result["reasoning"] = self._sanitize_to_spanish(result.get("reasoning", ""))
            
            # Actualizar estadísticas
            if result["approved"]:
                self.stats["approvals"] += 1
            else:
                self.stats["rejections"] += 1
            
            # Log del resultado
            emoji = "✅" if result["approved"] else "❌"
            logger.info(f"🧠 AI {emoji} {signal_type.upper()} {symbol} | "
                       f"Confianza: {confidence}/10 | {result.get('reasoning', '')}")
            
            self._set_cache(cache_key, result)
            return result
        
        # Si la IA no pudo responder, aprobar por defecto
        logger.warning("🧠 AI no pudo analizar la señal - Aprobando por defecto")
        return default_response

    # =========================================================================
    # MÉTODO: Detección de Oportunidades de Venta (IA Proactiva)
    # =========================================================================

    def analyze_sell_opportunity(
        self,
        symbol: str,
        strategy: str,
        market_data: Dict[str, Any],
        position_data: Dict[str, Any],
    ) -> Dict[str, Any]:
        """
        🧠 CEREBRO PRINCIPAL DE VENTA
        
        Analiza si hay una buena oportunidad de vender una posición DCA.
        La IA recibe contexto completo del mercado y la posición, y decide:
        - ¿Vender o mantener?
        - ¿Qué porcentaje vender? (10%, 25%, 50%)
        - ¿Qué tan urgente es? (1-10)

        La IA busca señales de techo de mercado:
        - RSI elevado (>65) = mercado potencialmente sobrecomprado
        - MACD con divergencia bajista = momentum cayendo
        - Precio en Bollinger superior = precio en extremo
        - Ganancia actual con señales de agotamiento

        Returns:
            Dict con:
            - should_sell: bool (True si la IA recomienda vender)
            - sell_pct: float (0.10, 0.25 o 0.50)
            - urgency: int (1-10, 10 = vende AHORA, 1 = mantén)
            - reasoning: str (explicación en español)
        """
        # Default: no vender (conservador)
        default_response = {
            "should_sell": False,
            "sell_pct": 0.0,
            "urgency": 3,
            "reasoning": "IA no disponible - Manteniendo posición",
        }

        if not self.enabled or not self.filter_enabled:
            return default_response

        # Cache separado para señales de venta (expiración más corta: 3 min)
        cache_key = f"sell_{symbol}_{strategy}"
        cached = self._get_cached(cache_key)
        if cached:
            return cached

        # Datos de la posición
        entry_price = float(position_data.get("entry_price", 0) or 0)
        current_price = float(market_data.get("price", 0) or 0)
        accumulated = float(position_data.get("accumulated", 0) or 0)
        profit_pct = ((current_price - entry_price) / entry_price * 100) if entry_price > 0 else 0
        
        # Calcular valor de la posición y costos estimados
        position_value_usd = accumulated * current_price
        profit_usd = accumulated * (current_price - entry_price)
        estimated_sell_fee = position_value_usd * 0.001  # 0.1% fee

        system_prompt = """Eres un analista de trading profesional experto en criptomonedas.
Tu rol es decidir si es BUEN MOMENTO para vender una posición de acumulación (DCA).

FILOSOFÍA: El DCA acumula a largo plazo, pero TAMBIÉN debe asegurar ganancias en momentos clave.
No dejes escapar oportunidades reales pensando que "siempre subirá más".

IDIOMA: Responde SIEMPRE en ESPAÑOL. NUNCA uses chino, inglés ni otro idioma. Solo español.

REGLAS ESTRICTAS:
1. Responde ÚNICAMENTE con un JSON válido, sin texto adicional
2. El campo "urgency" debe ser un número entero del 1 al 10:
   - 9-10: VENDER AHORA - señales muy fuertes de techo (RSI>75, divergencia MACD, Bollinger extremo)
   - 7-8: VENDER - buen momento para asegurar ganancias parciales
   - 6: VENTA LIGERA - conviene tomar algo de ganancia (10%)
   - 4-5: NEUTRAL - el mercado podría ir en cualquier dirección
   - 1-3: MANTENER - el precio probablemente seguirá subiendo
3. El campo "should_sell" debe ser true si urgency >= 6
4. El campo "sell_pct" indica cuánto vender:
   - 0.10 (10%) para ventas ligeras / asegurar algo
   - 0.25 (25%) para toma de ganancias moderada
   - 0.50 (50%) para señales fuertes de techo
   - 0.60 (60%) MAX - SOLO para asegurar ganancias altas (>10%) si hay fuerte riesgo de retroceso. NUNCA vender todo.
5. El campo "reasoning" debe ser en ESPAÑOL ÚNICAMENTE (máximo 2 oraciones, sin caracteres chinos)
6. NO inventes datos. Usa SOLO los datos proporcionados
7. NO pongas bloques de pensamiento, solo el JSON"""

        prompt = f"""Tengo una posición DCA abierta en {symbol}. Analiza si es buen momento para vender:

POSICIÓN ACTUAL:
- Símbolo: {symbol}
- Precio de entrada promedio: ${entry_price:,.2f}
- Precio actual: ${current_price:,.2f}
- Ganancia actual: {profit_pct:+.2f}%
- Ganancia en USD: ${profit_usd:+.2f}
- Valor total posición: ${position_value_usd:.2f}
- Fee estimado si vendo: ${estimated_sell_fee:.4f}

INDICADORES TÉCNICOS ACTUALES:
- RSI (14): {market_data.get('rsi', 'N/A')} (>70 = sobrecompra, >80 = extrema)
- MACD: {market_data.get('macd', 'N/A')} (Signal: {market_data.get('macd_signal', 'N/A')})
- Histograma MACD: {market_data.get('macd_hist', 'N/A')} (negativo = momentum cayendo)
- Tendencia (EMAs): {market_data.get('trend', 'N/A')}
- EMA 200: ${market_data.get('ema_200', 0):,.2f}
- Posición Bollinger: {market_data.get('bb_position', 'N/A')} (overbought = en techo)
- Cambio 24h: {market_data.get('change_24h', 'N/A')}%
- Máximo 24h: ${market_data.get('high_24h', 0):,.2f}
- Mínimo 24h: ${market_data.get('low_24h', 0):,.2f}

PREGUNTA: ¿Debo vender algo de esta posición ahora o mantener todo?

Responde SOLO con este formato JSON:
{{"should_sell": true/false, "sell_pct": 0.10/0.25/0.50/0.60, "urgency": 1-10, "reasoning": "tu análisis aquí"}}"""

        response = self._query_ollama(prompt, system_prompt, max_tokens=256)
        result = self._parse_json_response(response)

        if result and "urgency" in result and "reasoning" in result:
            urgency = max(1, min(10, int(result.get("urgency", 3))))
            result["urgency"] = urgency
            result["should_sell"] = urgency >= 6
            
            # Validar y normalizar sell_pct
            sell_pct = float(result.get("sell_pct", 0.25))
            if sell_pct not in (0.10, 0.25, 0.50, 0.60):
                # Redondear al más cercano válido
                if sell_pct <= 0.15:
                    sell_pct = 0.10
                elif sell_pct <= 0.35:
                    sell_pct = 0.25
                elif sell_pct <= 0.55:
                    sell_pct = 0.50
                else:
                    sell_pct = 0.60
            result["sell_pct"] = sell_pct
            
            # Sanitizar reasoning (quitar caracteres chinos que qwen2.5 a veces mezcla)
            result["reasoning"] = self._sanitize_to_spanish(result.get("reasoning", ""))

            # Log detallado
            emoji = "🔴" if result["should_sell"] else "🟡"
            action = f"VENDER {int(sell_pct*100)}%" if result["should_sell"] else "MANTENER"
            logger.info(
                f"🧠 AI {emoji} {symbol} [{strategy}] | "
                f"Urgencia: {urgency}/10 | {action} | "
                f"Ganancia: {profit_pct:+.1f}% (${profit_usd:+.2f}) | "
                f"{result.get('reasoning', '')}"
            )

            # Guardar en cache (3 minutos para ventas)
            self._cache[cache_key] = result
            self._cache_times[cache_key] = datetime.now() - timedelta(
                minutes=self.cache_minutes - 3
            )
            return result

        logger.warning("🧠 AI no pudo analizar oportunidad de venta - Manteniendo posición")
        return default_response


    # Análisis de Portafolio (para comando /ai_analisis en Telegram)
    # =========================================================================
    
    def analyze_portfolio(
        self,
        portfolio_data: Dict[str, Dict],
        trade_stats: Dict[str, Any],
        capital_info: Dict[str, Any],
    ) -> str:
        """
        Genera un análisis completo del portafolio usando IA.
        Diseñado para el comando /ai_analisis de Telegram.
        
        Returns:
            Análisis en formato texto (HTML para Telegram)
        """
        if not self.enabled:
            return "🧠 AI Advisor no está disponible. Verifica que Ollama esté corriendo."
        
        # Verificar cache
        cache_key = "portfolio_analysis"
        cached = self._get_cached(cache_key)
        if cached:
            return cached.get("analysis", "")
        
        system_prompt = """Eres un analista financiero experto en criptomonedas.
Genera un análisis profesional pero accesible en ESPAÑOL.
El análisis debe ser práctico y con recomendaciones claras.
Usa emojis para hacer el reporte más visual.
NO uses formato markdown. Usa texto plano con emojis.
Máximo 400 palabras."""

        # Construir resumen de datos del portafolio
        market_summary = ""
        for symbol, data in portfolio_data.items():
            if "error" not in data:
                market_summary += f"""
{symbol}:
  Precio: ${data.get('price', 0):,.2f}
  Cambio 24h: {data.get('change_24h', 0):+.2f}%
  RSI: {data.get('rsi', 'N/A')}
  MACD Tendencia: {data.get('macd_trend', 'N/A')}
  Tendencia General: {data.get('trend', 'N/A')}
  Posición Bollinger: {data.get('bb_position', 'N/A')}
  Volatilidad (ATR): {data.get('atr', 'N/A')}
"""

        prompt = f"""Analiza el estado actual de mi portafolio de criptomonedas y dame tu opinión experta:

ESTADO DEL PORTAFOLIO:
- Capital Inicial: ${capital_info.get('initial', 0):.2f}
- Capital Actual: ${capital_info.get('current', 0):.2f}
- P&L Total: ${capital_info.get('pnl', 0):+.2f} ({capital_info.get('roi', 0):+.2f}%)
- Total Trades: {trade_stats.get('total_trades', 0)}
- Win Rate: {trade_stats.get('win_rate', 0):.1f}%

DATOS DE MERCADO:
{market_summary}

Genera un análisis que incluya:
1. 📊 Estado general del mercado
2. 🔍 Análisis por cada moneda (oportunidades/riesgos)
3. 💡 Recomendaciones concretas (qué hacer ahora)
4. ⚠️ Riesgos a vigilar
5. 🎯 Perspectiva para las próximas horas"""

        response = self._query_ollama(prompt, system_prompt, max_tokens=1024)
        
        if response:
            # Limpiar la respuesta de posibles bloques de pensamiento
            analysis = self._clean_thinking_blocks(response)
            self._set_cache(cache_key, {"analysis": analysis})
            return analysis
        
        return "🧠 No se pudo generar el análisis. Verifica que Ollama esté corriendo."
    
    # =========================================================================
    # Reporte Diario Inteligente
    # =========================================================================
    
    def generate_daily_report(
        self,
        daily_stats: Dict[str, Any],
        market_data: Dict[str, Dict],
        portfolio_info: Dict[str, Any],
    ) -> str:
        """
        Genera un reporte diario narrativo inteligente.
        
        Returns:
            Reporte en texto formateado para Telegram
        """
        if not self.enabled:
            return ""
        
        system_prompt = """Eres el asistente de un trader de criptomonedas.
Genera un reporte diario breve, directo y en ESPAÑOL.
Sé concreto: di qué pasó, qué funcionó, qué no, y qué vigilar mañana.
Usa emojis para hacerlo visual. Máximo 250 palabras.
NO uses formato markdown."""

        # Resumen del día
        trades_text = ""
        for symbol, data in market_data.items():
            if "error" not in data:
                trades_text += f"  {symbol}: ${data.get('price', 0):,.2f} (RSI: {data.get('rsi', 50):.0f})\n"

        prompt = f"""Genera el reporte diario de mi bot de trading:

RESULTADOS DE HOY:
- Trades ejecutados: {daily_stats.get('total_trades', 0)}
- Trades ganados: {daily_stats.get('winning_trades', 0)}
- Trades perdidos: {daily_stats.get('losing_trades', 0)}
- P&L del día: ${daily_stats.get('total_profit', 0):+.2f}
- Win Rate: {daily_stats.get('win_rate', 0):.1f}%

ESTADO ACTUAL DEL PORTAFOLIO:
- Capital: ${portfolio_info.get('current_capital', 0):.2f}
- ROI Total: {portfolio_info.get('roi', 0):+.2f}%

PRECIOS ACTUALES:
{trades_text}

Genera un reporte breve con:
1. Resumen de lo que pasó hoy
2. Qué funcionó y qué no
3. Qué esperar para mañana
4. Una recomendación concreta"""

        response = self._query_ollama(prompt, system_prompt, max_tokens=1024)
        
        if response:
            report = self._clean_thinking_blocks(response)
            return f"🧠 <b>═══ REPORTE DIARIO IA ═══</b>\n\n{report}\n\n<i>Generado por {self.model}</i>"
        
        return ""
    
    # =========================================================================
    # Utilidades
    # =========================================================================
    
    def _clean_thinking_blocks(self, text: str) -> str:
        """
        Limpia bloques de pensamiento (<think>...</think>) de modelos
        que usan modo thinking (como Qwen3).
        """
        import re
        # Eliminar bloques <think>...</think>
        cleaned = re.sub(r'<think>.*?</think>', '', text, flags=re.DOTALL)
        # Limpiar líneas vacías extras
        cleaned = re.sub(r'\n{3,}', '\n\n', cleaned)
        return cleaned.strip()
    
    def _sanitize_to_spanish(self, text: str) -> str:
        """
        Elimina caracteres no-latinos (chino, japonés, coreano, etc.) que
        el modelo qwen2.5 a veces mezcla en sus respuestas en español.
        """
        import re
        # Eliminar caracteres CJK (chino/japonés/coreano) y otros scripts no-latinos
        cleaned = re.sub(r'[\u4e00-\u9fff\u3400-\u4dbf\u3000-\u303f\uff00-\uffef]+', '', text)
        # Limpiar espacios y puntuación sueltos que queden
        cleaned = re.sub(r'\s{2,}', ' ', cleaned)
        cleaned = re.sub(r'[，。、]+', '.', cleaned)  # Puntuación china → punto
        return cleaned.strip()
    
    def get_stats(self) -> Dict[str, Any]:
        """Devuelve estadísticas del AI Advisor."""
        return {
            **self.stats,
            "model": self.model,
            "enabled": self.enabled,
            "filter_enabled": self.filter_enabled,
            "min_confidence": self.min_confidence,
            "cache_size": len(self._cache),
        }
    
    def is_available(self) -> bool:
        """Verifica si el advisor está disponible."""
        return self.enabled


# Singleton
_advisor: Optional[OllamaAdvisor] = None

def get_ai_advisor() -> OllamaAdvisor:
    """Obtiene la instancia singleton del AI Advisor."""
    global _advisor
    if _advisor is None:
        _advisor = OllamaAdvisor()
    return _advisor
