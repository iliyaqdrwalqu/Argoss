# Developer Guide: Как писать новые навыки (плагины)

ARGOS поддерживает два формата навыков:

1) Legacy: `src/skills/<name>.py`
2) Plugin v2: `src/skills/<name>/manifest.json` + `skill.py`

Рекомендуется использовать Plugin v2.

## Структура навыка v2

```text
src/skills/my_skill/
  manifest.json
  skill.py
  README.md
```

Пример `manifest.json`:

```json
{
  "name": "my_skill",
  "version": "1.0.0",
  "entry": "skill.py",
  "author": "you",
  "description": "Мой навык",
  "category": "custom",
  "dependencies": [],
  "permissions": ["network"]
}
```

Пример `skill.py`:

```python
TRIGGERS = ["мой навык", "my skill"]

def setup(core=None):
    pass

def handle(text: str, core=None) -> str | None:
    t = text.lower()
    if not any(tr in t for tr in TRIGGERS):
        return None
    return "✅ Навык сработал"

def teardown():
    pass
```

## Подключение навыка

- Автозагрузка: через `SkillLoader` при старте.
- Ручное управление:
  - `загрузи навык my_skill`
  - `перезагрузи навык my_skill`
  - `выгрузи навык my_skill`

## Рекомендации

- Возвращай `None`, если команда не относится к навыку.
- Не выполняй опасные действия без явного подтверждения пользователя.
- Держи логику навыка независимой и тестируемой.
