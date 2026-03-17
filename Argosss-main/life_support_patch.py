# ═══════════════════════════════════════════════════════════════
# 💰 ARGOS PATCH — МОДУЛЬ ЖИЗНЕОБЕСПЕЧЕНИЯ
# Вставь в ячейку Colab и запусти
# ═══════════════════════════════════════════════════════════════
import sys, os
sys.path.insert(0, "/content/v1-3")
os.chdir("/content/v1-3")

print("💰 Загрузка модуля Жизнеобеспечения...\n")

try:
    from src.core import ArgosCore
    from src.life_support import ArgosLifeSupport

    if 'core' not in dir():
        core = ArgosCore()
        print("  ✅ ArgosCore создан")

    life = ArgosLifeSupport(core)
    life.start()
    print("  ✅ LifeSupport запущен\n")

    # ── Демонстрация ──────────────────────────────────────
    print(life.handle_command("финансы"))
    print()
    print(life.handle_command("заработок"))
    print()
    print(life.handle_command("окупаемость"))
    print()
    print("═"*50)
    print("  ✅ Модуль активен!")
    print("\n  Команды:")
    print("  life.handle_command('финансы')")
    print("  life.handle_command('заработок')")
    print("  life.handle_command('питч 1')")
    print("  life.handle_command('провайдеры')")
    print("  life.handle_command('контракт Telegram бот|ООО Ромашка|15000')")
    print("  life.handle_command('расход api|Gemini ключ|0.05')")
    print("═"*50)

except Exception as e:
    print(f"❌ Ошибка: {e}")
    import traceback
    traceback.print_exc()
