#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
auto_integrator.py — Автоматический интегратор модулей Аргоса.

Сканирует пакеты в src/, находит все классы, реализующие интерфейс IModule,
и строит динамическое FastAPI-приложение с вкладкой для каждого модуля.

Запуск:
    python -m src.interface.auto_integrator
    # или
    from src.interface.auto_integrator import run_integrator
    run_integrator(host="0.0.0.0", port=8080)
"""
from __future__ import annotations

import importlib
import inspect
import os
import sys
from typing import Any, Dict, List, Type

from src.argos_logger import get_logger

_log = get_logger("argos.auto_integrator")

# ─────────────────────────────────────────────────
# Интерфейс IModule
# ─────────────────────────────────────────────────
class IModule:
    """
    Базовый интерфейс для автоинтегрируемых модулей Аргоса.

    Каждый класс, унаследовавшийся от IModule и реализовавший его методы,
    автоматически получает вкладку в веб-интерфейсе.
    """

    @classmethod
    def get_module_name(cls) -> str:
        """Отображаемое имя модуля."""
        return cls.__name__

    @classmethod
    def get_description(cls) -> str:
        """Краткое описание модуля."""
        return getattr(cls, "__doc__", "") or ""

    @classmethod
    def get_status(cls) -> Dict[str, Any]:
        """Текущее состояние модуля (для отображения в карточке)."""
        return {}

    @classmethod
    def get_commands(cls) -> List[Dict[str, str]]:
        """
        Список команд, которые модуль принимает.
        Каждая команда — dict с ключами "name" и "description".
        """
        return []

    @classmethod
    def get_widget(cls) -> str:
        """HTML-код виджета для вкладки модуля (опционально)."""
        return "<p>Модуль не предоставляет виджет.</p>"

    @classmethod
    def execute_command(cls, command: str, params: Dict | None = None) -> Any:
        """Выполняет команду модуля и возвращает результат."""
        return None


# ─────────────────────────────────────────────────
# Сканер модулей
# ─────────────────────────────────────────────────
class ModuleScanner:
    """Обходит src/ и собирает все подклассы IModule."""

    def __init__(self, base_path: str | None = None):
        self.base_path = base_path or os.path.join(
            os.path.dirname(__file__), "..", ".."
        )
        self.src_path = os.path.join(self.base_path, "src")
        sys.path.insert(0, self.base_path)
        self.modules: Dict[str, Type[IModule]] = {}

    def scan(self) -> Dict[str, Type[IModule]]:
        """Сканирует src/ и возвращает словарь name → class."""
        for root, dirs, files in os.walk(self.src_path):
            # Пропускаем кеш Python
            dirs[:] = [d for d in dirs if d != "__pycache__"]
            for file in files:
                if not file.endswith(".py") or file.startswith("__"):
                    continue
                rel = os.path.relpath(os.path.join(root, file), self.base_path)
                mod_name = rel.replace(os.sep, ".")[:-3]  # убираем .py
                try:
                    module = importlib.import_module(mod_name)
                    self._extract(module)
                except Exception:
                    pass   # некоторые модули могут требовать внешних зависимостей
        return self.modules

    def _extract(self, module) -> None:
        for _, obj in inspect.getmembers(module, inspect.isclass):
            if (
                obj is not IModule
                and issubclass(obj, IModule)
                and not inspect.isabstract(obj)
                and obj.__module__ == module.__name__
            ):
                name = obj.get_module_name()
                self.modules[name] = obj


# ─────────────────────────────────────────────────
# HTML-шаблоны (встроенные, без файловой системы)
# ─────────────────────────────────────────────────
_INDEX_HTML = """<!DOCTYPE html>
<html lang="ru">
<head>
  <meta charset="UTF-8">
  <title>Argos — модули</title>
  <style>
    body {{ font-family: Arial, sans-serif; margin: 20px; background: #1a1a2e; color: #e0e0e0; }}
    h1 {{ color: #e94560; }}
    .grid {{ display: flex; flex-wrap: wrap; gap: 20px; margin-top: 20px; }}
    .card {{ background: #16213e; border: 1px solid #0f3460; padding: 20px;
             width: 240px; border-radius: 10px; }}
    .card h3 {{ margin-top: 0; color: #e94560; }}
    a {{ color: #53d8fb; text-decoration: none; }}
    a:hover {{ text-decoration: underline; }}
  </style>
</head>
<body>
  <h1>👁️ Argos — автоинтеграция модулей</h1>
  <div class="grid">
    {cards}
  </div>
</body>
</html>"""

_CARD_HTML = """<div class="card">
  <h3>{name}</h3>
  <p>{description}</p>
  <a href="/module/{name}">Открыть →</a>
</div>"""

_MODULE_HTML = """<!DOCTYPE html>
<html lang="ru">
<head>
  <meta charset="UTF-8">
  <title>{name} — Argos</title>
  <style>
    body {{ font-family: Arial; margin: 20px; background: #1a1a2e; color: #e0e0e0; }}
    h1,h2 {{ color: #e94560; }}
    pre {{ background: #0f3460; padding: 12px; border-radius: 6px; overflow-x: auto; }}
    .cmd {{ background: #16213e; border: 1px solid #0f3460; padding: 8px 14px;
            margin: 6px 0; cursor: pointer; border-radius: 4px; display: inline-block; }}
    .cmd:hover {{ background: #0f3460; }}
    a {{ color: #53d8fb; }}
    #result {{ margin-top: 12px; padding: 10px; background: #0f3460; border-radius: 5px;
               display: none; }}
  </style>
</head>
<body>
  <a href="/">← Назад</a>
  <h1>Модуль: {name}</h1>
  <p>{description}</p>
  <h2>Состояние</h2>
  <pre>{status_json}</pre>
  <h2>Команды</h2>
  <div>{command_buttons}</div>
  <div id="result"></div>
  <h2>Виджет</h2>
  <div>{widget}</div>
  <script>
    function exec(cmd) {{
      fetch('/api/module/{name}/execute', {{
        method: 'POST',
        headers: {{'Content-Type': 'application/json'}},
        body: JSON.stringify({{command: cmd}})
      }}).then(r => r.json()).then(data => {{
        var el = document.getElementById('result');
        el.style.display = 'block';
        el.textContent = JSON.stringify(data.result, null, 2);
      }});
    }}
  </script>
</body>
</html>"""


# ─────────────────────────────────────────────────
# FastAPI-приложение
# ─────────────────────────────────────────────────
def build_app(modules: Dict[str, Type[IModule]]):
    """Строит и возвращает FastAPI-приложение."""
    try:
        from fastapi import FastAPI, Request
        from fastapi.responses import HTMLResponse, JSONResponse
    except ImportError as e:
        raise ImportError("Установи fastapi: pip install fastapi uvicorn") from e

    import json

    app = FastAPI(title="Argos Auto Integration", version="1.3")

    @app.get("/", response_class=HTMLResponse)
    async def index():
        cards = "\n".join(
            _CARD_HTML.format(
                name=name,
                description=(cls.get_description() or "")[:120],
            )
            for name, cls in modules.items()
        )
        return _INDEX_HTML.format(cards=cards)

    for _name, _cls in modules.items():

        def _make_routes(name: str, cls: Type[IModule]):
            @app.get(f"/module/{name}", response_class=HTMLResponse)
            async def module_page(name=name, cls=cls):
                status  = cls.get_status()
                commands = cls.get_commands()
                widget  = cls.get_widget()
                buttons = "\n".join(
                    f'<div class="cmd" onclick="exec(\'{c["name"]}\')">'
                    f'{c["name"]} — {c.get("description","")}</div>'
                    for c in commands
                )
                return _MODULE_HTML.format(
                    name=name,
                    description=cls.get_description() or "",
                    status_json=json.dumps(status, indent=2, ensure_ascii=False),
                    command_buttons=buttons,
                    widget=widget,
                )

            @app.post(f"/api/module/{name}/execute")
            async def execute_command(request: Request, name=name, cls=cls):
                body    = await request.json()
                command = body.get("command")
                params  = body.get("params", {})
                result  = cls.execute_command(command, params)
                return {"result": result}

        _make_routes(_name, _cls)

    return app


# ─────────────────────────────────────────────────
# Публичный API
# ─────────────────────────────────────────────────
def run_integrator(host: str = "0.0.0.0", port: int = 8080) -> None:
    """Сканирует модули и запускает веб-интегратор."""
    try:
        import uvicorn
    except ImportError as e:
        raise ImportError("Установи uvicorn: pip install uvicorn") from e

    scanner = ModuleScanner()
    modules = scanner.scan()
    _log.info("AutoIntegrator: найдено модулей: %d", len(modules))
    for name in modules:
        _log.info("   • %s", name)

    app = build_app(modules)
    _log.info("Запуск на http://%s:%d", host, port)
    uvicorn.run(app, host=host, port=port)


if __name__ == "__main__":
    run_integrator()
