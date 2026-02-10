"""
Script de Configuración Inicial
================================
Ejecuta este script para configurar el bot por primera vez
"""

import os
import sys
import shutil
from pathlib import Path


def create_directories():
    """Crea los directorios necesarios."""
    dirs = [
        "logs",
        "data",
        "backups",
    ]
    
    for dir_name in dirs:
        Path(dir_name).mkdir(exist_ok=True)
        print(f"✅ Directorio creado: {dir_name}/")


def create_env_file():
    """Crea el archivo .env si no existe."""
    env_file = Path(".env")
    env_example = Path(".env.example")
    
    if env_file.exists():
        print("ℹ️  .env ya existe, saltando...")
        return
    
    if env_example.exists():
        shutil.copy(env_example, env_file)
        print("✅ Archivo .env creado desde .env.example")
        print("⚠️  IMPORTANTE: Edita .env con tus credenciales reales")
    else:
        print("❌ No se encontró .env.example")


def check_python_version():
    """Verifica la versión de Python."""
    version = sys.version_info
    if version.major < 3 or (version.major == 3 and version.minor < 10):
        print(f"❌ Python 3.10+ requerido. Versión actual: {version.major}.{version.minor}")
        return False
    print(f"✅ Python {version.major}.{version.minor} detectado")
    return True


def install_dependencies():
    """Instala las dependencias."""
    print("\n📦 Instalando dependencias...")
    os.system(f"{sys.executable} -m pip install -r requirements.txt")
    print("✅ Dependencias instaladas")


def test_imports():
    """Prueba que los imports funcionen."""
    print("\n🧪 Probando imports...")
    try:
        import ccxt
        print("  ✅ ccxt")
    except ImportError:
        print("  ❌ ccxt - ejecuta: pip install ccxt")
    
    try:
        import pandas
        print("  ✅ pandas")
    except ImportError:
        print("  ❌ pandas")
    
    try:
        import pandas_ta
        print("  ✅ pandas_ta")
    except ImportError:
        print("  ❌ pandas_ta")
    
    try:
        from loguru import logger
        print("  ✅ loguru")
    except ImportError:
        print("  ❌ loguru")


def show_next_steps():
    """Muestra los siguientes pasos."""
    print("\n" + "=" * 50)
    print("🎉 CONFIGURACIÓN COMPLETADA")
    print("=" * 50)
    print("""
PRÓXIMOS PASOS:

1. 📝 Edita el archivo .env con tus credenciales:
   - BINANCE_API_KEY
   - BINANCE_API_SECRET
   - TELEGRAM_BOT_TOKEN (opcional)
   - TELEGRAM_CHAT_ID (opcional)

2. 🔑 Crea API Keys en Binance:
   https://www.binance.com/en/my/settings/api-management
   ⚠️ SOLO habilita permisos de "Spot Trading" y "Read"
   ⚠️ NUNCA habilites permisos de retiro

3. 🤖 Crea un bot de Telegram (opcional):
   - Habla con @BotFather
   - Envía /newbot
   - Copia el token

4. 🧪 Prueba el bot en modo PAPER (simulación):
   python main.py --mode paper

5. 🚀 Cuando estés listo para trading real:
   - Cambia OPERATION_MODE["mode"] a "live" en config/settings.py
   - O ejecuta: python main.py --mode live
""")


def main():
    print("=" * 50)
    print("🤖 SETUP - BOT DE TRADING AUTOMATIZADO")
    print("=" * 50)
    print()
    
    if not check_python_version():
        return
    
    create_directories()
    create_env_file()
    install_dependencies()
    test_imports()
    show_next_steps()


if __name__ == "__main__":
    main()
