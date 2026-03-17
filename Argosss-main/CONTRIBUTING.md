# Contributing to Argos Universal OS

Спасибо, что хотите помочь проекту Argos!

## Как начать

1. Форкните репозиторий и создайте ветку от `main`.
2. Установите зависимости:
   ```bash
   pip install -r requirements.txt
   ```
3. Инициализируйте проект:
   ```bash
   python genesis.py
   ```
4. Проверьте целостность:
   ```bash
   python health_check.py
   ```
5. Запустите тесты:
   ```bash
   pytest -q
   ```

## Что можно улучшать

- Новые `skills` в `src/skills/`
- IoT и bridge-модули в `src/connectivity/`
- Улучшение observability (`src/observability.py`)
- Сценарии в `examples/`
- Документация в `docs/`

## Стандарты кода

- Python 3.10+
- Малые, сфокусированные PR
- Без хардкода секретов (используй `.env`)
- Graceful fallback для optional-зависимостей (SDR, BLE, Kivy и т.д.)
- Новые функции — с тестами в `tests/`

## Процесс Pull Request

1. Обновите код и документацию
2. Убедитесь, что проверки проходят:
   ```bash
   python health_check.py
   pytest -q
   black src/ --check
   flake8 src/ --max-line-length=120
   ```
3. Опишите: что изменено, почему, как проверяли

## Security

- Не публикуйте API-ключи, токены и приватные данные
- Для уязвимостей — приватный disclosure: seva1691@mail.ru

## Направления, где нужна помощь

- Новые IoT-протоколы и bridge-адаптеры
- Skills для новых сервисов и API
- Тесты (покрытие ~14%, цель 30%+)
- Документация и примеры сценариев
- Оптимизация Speculative Consensus pipeline
