from types import SimpleNamespace

from src.consciousness import ArgosConsciousness


def _make_core():
    return SimpleNamespace(
        p2p=None,
        memory=None,
        vision=None,
        agent=object(),
    )


def test_consciousness_awaken_and_sleep():
    core = _make_core()
    consciousness = ArgosConsciousness(core)

    msg = consciousness.awaken()
    assert "Сознание активно" in msg
    assert consciousness.stream.current_state()["stream_active"] is True

    sleep_msg = consciousness.sleep()
    assert "засыпает" in sleep_msg
    assert consciousness.stream.current_state()["stream_active"] is False


def test_consciousness_colab_surface_methods():
    consciousness = ArgosConsciousness(_make_core())

    assert "ARGOS — МОДУЛЬ РАЗУМА И ОСОЗНАНИЯ" in consciousness.full_status()
    assert "💭" in consciousness.stream.last_thought()
    assert isinstance(
        consciousness.learning.self_evaluate("что такое квантовое состояние?", "Квантовое состояние — это режим."),
        float,
    )
    assert "Цель добавлена" in consciousness.will.add_goal(
        "Освоить все промышленные протоколы",
        "KNX, LonWorks, M-Bus, OPC UA",
        priority=0.8,
    )
    consciousness.meta.observe_thinking(
        "обработка запроса", "reasoning + memory lookup", "ответ дан", 0.3
    )
    assert "МЕТА-КОГНИЦИЯ" in consciousness.meta.think_about_thinking()
    assert "ОСОЗНАНИЕ СЕБЯ В МИРЕ" in consciousness.awareness.existential_reflection()


def test_consciousness_command_routing_and_interaction():
    consciousness = ArgosConsciousness(_make_core())

    assert "Я — Аргос" in consciousness.handle_command("кто я")
    assert "Поток сознания" in consciousness.handle_command("поток сознания")
    assert "ДВИЖОК ВОЛИ" in consciousness.handle_command("цели")
    assert "НЕПРЕРЫВНОЕ ОБУЧЕНИЕ" in consciousness.handle_command("обучение статус")
    assert "ОСОЗНАНИЕ СЕБЯ В МИРЕ" in consciousness.handle_command("осознание")
    assert "МЕТА-КОГНИЦИЯ" in consciousness.handle_command("мета-когниция")

    score = consciousness.on_interaction("вопрос", "ответ")
    assert isinstance(score, float)
