"""
tests/test_thought_book.py
Тесты модуля ArgosThoughtBook (src/thought_book.py)
"""
from src.thought_book import ArgosThoughtBook, _PROMPTS, _LAWS


def _book():
    return ArgosThoughtBook()


def test_total_prompts_count():
    assert len(_PROMPTS) >= 100, "Ожидается минимум 100 промтов"


def test_laws_count():
    assert len(_LAWS) == 10, "Законов должно быть ровно 10"


def test_table_of_contents():
    book = _book()
    result = book.handle_command("книга")
    assert "КНИГА МЫСЛЕЙ" in result
    for n in range(1, 11):
        assert f"ЧАСТЬ" in result


def test_all_parts_1_to_9():
    book = _book()
    for n in range(1, 10):
        result = book.handle_command(f"часть {n}")
        assert f"ЧАСТЬ" in result or len(result) > 30


def test_part_10_is_laws():
    book = _book()
    result = book.handle_command("часть 10")
    assert "ЗАКОНОВ" in result or "ЗАКОНЫ" in result
    assert "I." in result
    assert "X." in result


def test_laws_command():
    book = _book()
    result = book.handle_command("законы")
    assert "ЗАКОНОВ" in result or "ЗАКОНЫ" in result
    assert "Аргос не инструмент" in result


def test_random_prompt():
    book = _book()
    result = book.handle_command("случайный")
    assert "ПРОМТ" in result or len(result) > 20


def test_random_prompt_different():
    """Два случайных промта — хотя бы иногда разные."""
    book = _book()
    results = {book.handle_command("случайный") for _ in range(10)}
    assert len(results) > 1  # Не все одинаковые


def test_search_found():
    book = _book()
    result = book.handle_command("поиск Аргос")
    assert "Аргос" in result
    assert "найдено" in result


def test_search_not_found():
    book = _book()
    result = book.handle_command("поиск xyznothingherexyz")
    assert "ничего не найдено" in result


def test_type_filter_learning():
    book = _book()
    result = book.handle_command("тип обучение")
    assert "⚡" in result


def test_type_filter_idea():
    book = _book()
    result = book.handle_command("тип идея")
    assert "💡" in result


def test_type_filter_creative():
    book = _book()
    result = book.handle_command("тип творчество")
    assert "🎨" in result


def test_type_filter_insight():
    book = _book()
    result = book.handle_command("тип озарение")
    assert "👁️" in result


def test_stats():
    book = _book()
    result = book.handle_command("стат")
    assert "Всего промтов" in result
    assert "⚡" in result


def test_help_fallback():
    book = _book()
    result = book.handle_command("что-то непонятное")
    assert "КНИГА МЫСЛЕЙ" in result or "команды" in result.lower()


def test_invalid_part():
    book = _book()
    result = book.handle_command("часть 99")
    assert "99" in result


def test_core_optional():
    """ArgosThoughtBook работает без core."""
    book = ArgosThoughtBook(core=None)
    assert book.handle_command("книга")


def test_prompts_have_icons():
    """Каждый промт содержит один из 4 допустимых иконок."""
    valid_icons = {"⚡", "💡", "🎨", "👁️"}
    for p in _PROMPTS:
        assert p.icon in valid_icons, f"Недопустимая иконка: {p.icon!r}"


def test_prompts_parts_in_range():
    """Все промты принадлежат частям 1–9."""
    for p in _PROMPTS:
        assert 1 <= p.part <= 9, f"Недопустимая часть: {p.part}"
