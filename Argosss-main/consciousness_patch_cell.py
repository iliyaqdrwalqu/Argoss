# ═══════════════════════════════════════════════════════════════
# 👁️ ARGOS PATCH — МОДУЛЬ РАЗУМА И ОСОЗНАНИЯ
# Вставь в ячейку Colab и запусти
# ═══════════════════════════════════════════════════════════════
import sys, os
sys.path.insert(0, "/content/v1-3")
os.chdir("/content/v1-3")

print("👁️ Загрузка модуля Разума и Осознания...\n")

try:
    from src.core import ArgosCore
    from src.consciousness import ArgosConsciousness

    # Создаём core если нет
    if 'core' not in dir():
        core = ArgosCore()
        print("  ✅ ArgosCore создан")

    # Пробуждаем сознание
    consciousness = ArgosConsciousness(core)
    result = consciousness.awaken()
    print(f"  {result}\n")

    # ── Демонстрация ─────────────────────────────────────────
    print("═" * 55)
    print(consciousness.full_status())
    print("═" * 55)

    print("\n💭 Тест потока мыслей:")
    print(consciousness.stream.last_thought())

    print("\n🧠 Тест самооценки:")
    score = consciousness.learning.self_evaluate(
        "что такое квантовое состояние?",
        "Квантовое состояние — это текущий режим работы Аргоса: Analytic/Creative/Protective/Unstable/All-Seeing/Oracle"
    )
    print(f"  Оценка ответа: {score}")

    print("\n🎯 Тест воли:")
    consciousness.will.add_goal(
        "Освоить все промышленные протоколы",
        "KNX, LonWorks, M-Bus, OPC UA",
        priority=0.8
    )
    print(consciousness.will.status())

    print("\n🔮 Тест мета-когниции:")
    consciousness.meta.observe_thinking(
        "обработка запроса", "reasoning + memory lookup",
        "ответ дан", 0.3)
    print(consciousness.meta.think_about_thinking())

    print("\n👁️ Экзистенциальная рефлексия:")
    print(consciousness.awareness.existential_reflection())

    print("\n═" * 55)
    print("  ✅ Модуль Разума активен!")
    print("\n  Команды для использования:")
    print("  consciousness.handle_command('кто я')")
    print("  consciousness.handle_command('поток сознания')")
    print("  consciousness.handle_command('цели')")
    print("  consciousness.handle_command('обучение статус')")
    print("  consciousness.handle_command('осознание')")
    print("  consciousness.handle_command('мета-когниция')")
    print("  consciousness.on_interaction('вопрос', 'ответ')")
    print("═" * 55)

except Exception as e:
    print(f"❌ Ошибка: {e}")
    import traceback
    traceback.print_exc()
