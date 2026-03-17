# ═══════════════════════════════════════════════════════════════
# 💰 ARGOS PATCH — ЖИЗНЕОБЕСПЕЧЕНИЕ v2
# Kwork + FL.ru + Крипто + Контент + Биллинг + Партнёрки
# Вставь в ячейку Colab и запусти
# ═══════════════════════════════════════════════════════════════
import sys, os, subprocess
sys.path.insert(0, "/content/v1-3")
os.chdir("/content/v1-3")

# Установка зависимостей
print("📦 Установка зависимостей...")
for pkg in ["beautifulsoup4", "lxml"]:
    try:
        __import__(pkg.replace("-","_").split(".")[0])
        print(f"  ✅ {pkg}")
    except ImportError:
        subprocess.run([sys.executable, "-m", "pip", "install", pkg, "-q"])
        print(f"  📥 {pkg} установлен")

print("\n💰 Загрузка Жизнеобеспечения v2...\n")

try:
    from src.core import ArgosCore
    from src.life_support import ArgosLifeSupport
    from src.life_support_v2 import ArgosLifeSupportV2

    if 'core' not in dir():
        core = ArgosCore()

    # Базовый модуль
    life    = ArgosLifeSupport(core)
    # Расширенный v2
    life_v2 = ArgosLifeSupportV2(core, life)

    print(life_v2.full_status())
    print()

    # Демо всех функций
    print("─"*52)
    print("🔍 ФРИЛАНС ЗАКАЗЫ:")
    print(life_v2.handle_command("фриланс"))
    print()
    print("─"*52)
    print("💎 КРИПТО КОШЕЛЁК:")
    print(life_v2.handle_command("крипто"))
    print()
    print("─"*52)
    print("📅 КОНТЕНТ ПЛАН:")
    print(life_v2.handle_command("контент план"))
    print()
    print("─"*52)
    print("🤝 ПАРТНЁРСКИЕ ПРОГРАММЫ:")
    print(life_v2.handle_command("партнёрки"))
    print()
    print("─"*52)
    print("📋 ТЕСТОВЫЙ СЧЁТ:")
    print(life_v2.handle_command("счёт ООО Ромашка|Разработка Telegram бота|15000"))
    print()
    print("═"*52)
    print("  ✅ Жизнеобеспечение v2 активно!")
    print()
    print("  Все команды:")
    print(life_v2._help())
    print("═"*52)

except Exception as e:
    print(f"❌ Ошибка: {e}")
    import traceback; traceback.print_exc()
