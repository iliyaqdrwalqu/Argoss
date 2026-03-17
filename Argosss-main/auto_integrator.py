#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
auto_integrator.py — Автоматическая интеграция модулей Argos в веб-интерфейс.

Сканирует корневую директорию проекта, находит классы, реализующие IModule,
и строит динамическое FastAPI-приложение с вкладкой для каждого модуля.

Запуск:
  python auto_integrator.py               # на порту 8081
  python auto_integrator.py --port 9000

Интегрируется с main.py:
  python main.py --web    (основной интерфейс, порт 8080)
  python auto_integrator.py --port 8081   (модульный интерфейс)
"""

from __future__ import annotations

import importlib.util
import inspect
import logging
import os
import sys
from typing import Any, Dict, List, Optional, Type

log = logging.getLogger("argos.auto_integrator")

# ─────────────────────────────────────────────────────────────────────────────
# Базовый интерфейс модуля
# ─────────────────────────────────────────────────────────────────────────────

class IModule:
    """
    Базовый класс-интерфейс для модулей, автоматически интегрируемых
    в веб-интерфейс Argos.

    Каждый модуль должен реализовать:
      get_module_name()   → str      — отображаемое имя
      get_description()   → str      — краткое описание
      get_status()        → dict     — текущее состояние
      get_commands()      → list     — список доступных команд
      get_widget()        → str      — HTML-виджет
      execute_command()   → Any      — выполнение команды
    """

    @classmethod
    def get_module_name(cls) -> str:
        return cls.__name__

    @classmethod
    def get_description(cls) -> str:
        return ""

    @classmethod
    def get_status(cls) -> Dict[str, Any]:
        return {}

    @classmethod
    def get_commands(cls) -> List[Dict[str, str]]:
        return []

    @classmethod
    def get_widget(cls) -> str:
        return "<p>Модуль не предоставляет виджет.</p>"

    @classmethod
    def execute_command(cls, command: str, params: Optional[Dict] = None) -> Any:
        return {"error": f"Команда '{command}' не реализована"}


# ─────────────────────────────────────────────────────────────────────────────
# Сканер модулей
# ─────────────────────────────────────────────────────────────────────────────

class ModuleScanner:
    """
    Сканирует .py-файлы в заданной директории и ищет классы,
    реализующие IModule.
    """

    # Файлы, которые игнорируем при сканировании
    SKIP_PREFIXES = (
        "deepseek_", "ARGOS_RESTORE", "ARGOS_EMERGENCY",
        "deepseek_ini_",
    )
    SKIP_FILES = {
        "auto_integrator.py", "git_push.py", "pypi_publisher.py",
        "PATCH_core_model_pypi.py",
    }

    def __init__(self, base_path: Optional[str] = None) -> None:
        self.base_path = base_path or os.path.dirname(os.path.abspath(__file__))
        self.modules: Dict[str, Type[IModule]] = {}

    def scan(self) -> Dict[str, Type[IModule]]:
        """
        Обходит base_path и загружает все IModule-классы.

        Безопасность: сканируется только локальная директория проекта,
        указанная через base_path (по умолчанию — директория этого файла).
        Нежелательные файлы исключаются через SKIP_FILES и SKIP_PREFIXES.
        Не запускайте integrator с base_path, указывающим на недоверенные каталоги.
        """
        for fname in os.listdir(self.base_path):
            if not fname.endswith(".py"):
                continue
            if fname in self.SKIP_FILES:
                continue
            if any(fname.startswith(p) for p in self.SKIP_PREFIXES):
                continue

            fpath = os.path.join(self.base_path, fname)
            module_name = fname[:-3]
            try:
                spec = importlib.util.spec_from_file_location(module_name, fpath)
                if spec is None or spec.loader is None:
                    continue
                mod = importlib.util.module_from_spec(spec)
                spec.loader.exec_module(mod)  # type: ignore[union-attr]
                self._extract_imodules(mod)
            except Exception as exc:
                log.debug("Пропуск %s: %s", fname, exc)

        log.info("Найдено модулей IModule: %d → %s", len(self.modules), list(self.modules))
        return self.modules

    def _extract_imodules(self, mod) -> None:
        for _, obj in inspect.getmembers(mod, inspect.isclass):
            if (
                obj is not IModule
                and issubclass(obj, IModule)
                and not inspect.isabstract(obj)
            ):
                name = obj.get_module_name()
                if name not in self.modules:
                    self.modules[name] = obj
                    log.debug("Найден IModule: %s", name)


# ─────────────────────────────────────────────────────────────────────────────
# Построитель FastAPI-приложения
# ─────────────────────────────────────────────────────────────────────────────

# HTML-шаблоны (встроены, без Jinja2 для минимальных зависимостей)
_INDEX_TEMPLATE = """\
<!DOCTYPE html>
<html lang="ru">
<head>
  <meta charset="UTF-8">
  <title>Argos — модули</title>
  <style>
    body{{background:#000;color:#00FF41;font-family:monospace;margin:20px}}
    h1{{color:#00F2FF}}
    .grid{{display:flex;flex-wrap:wrap;gap:15px;margin-top:20px}}
    .card{{border:1px solid #00FF41;padding:15px;width:220px;border-radius:6px}}
    .card h3{{margin:0 0 8px;color:#00F2FF}}
    a{{color:#00FF41}}
    a:hover{{color:#00F2FF}}
  </style>
</head>
<body>
  <h1>👁️ ARGOS — Автоинтеграция модулей</h1>
  <div class="grid">
    {cards}
  </div>
</body>
</html>"""

_CARD_TEMPLATE = """\
<div class="card">
  <h3>{name}</h3>
  <p style="font-size:12px;color:#aaa">{desc}</p>
  <a href="/module/{name}">Открыть →</a>
</div>"""

_MODULE_TEMPLATE = """\
<!DOCTYPE html>
<html lang="ru">
<head>
  <meta charset="UTF-8">
  <title>{name} — Argos</title>
  <style>
    body{{background:#000;color:#00FF41;font-family:monospace;margin:20px}}
    h1,h2{{color:#00F2FF}}
    pre{{background:#001100;border:1px solid #00FF41;padding:10px;overflow:auto;max-height:300px}}
    .cmd{{background:#001100;border:1px solid #555;padding:6px 10px;margin:4px 0;
          cursor:pointer;border-radius:3px;display:inline-block}}
    .cmd:hover{{border-color:#00FF41}}
    #result{{margin-top:15px;border:1px solid #00FF41;padding:10px;min-height:40px;
             white-space:pre-wrap;word-break:break-word}}
    a{{color:#00FF41}}
  </style>
</head>
<body>
  <p><a href="/">← Назад</a></p>
  <h1>Модуль: {name}</h1>
  <p>{desc}</p>

  <h2>Текущее состояние</h2>
  <pre id="status">{status_json}</pre>

  <h2>Команды</h2>
  {cmd_buttons}

  <h2>Виджет</h2>
  <div>{widget}</div>

  <h2>Результат</h2>
  <div id="result">&gt; Нажмите команду...</div>

  <script>
    function exec(cmd) {{
      fetch('/api/module/{name}/execute', {{
        method: 'POST',
        headers: {{'Content-Type': 'application/json'}},
        body: JSON.stringify({{command: cmd, params: {{}}}}),
      }})
      .then(r => r.json())
      .then(d => document.getElementById('result').textContent = JSON.stringify(d, null, 2));
    }}
    // Авто-обновление статуса каждые 5с
    setInterval(() => {{
      fetch('/api/module/{name}/status')
        .then(r => r.json())
        .then(d => document.getElementById('status').textContent = JSON.stringify(d, null, 2));
    }}, 5000);
  </script>
</body>
</html>"""


def _build_fastapi_app(modules: Dict[str, Type[IModule]]):
    """Строит и возвращает FastAPI-приложение для найденных модулей."""
    try:
        from fastapi import FastAPI
        from fastapi.responses import HTMLResponse, JSONResponse
    except ImportError:
        raise ImportError("pip install fastapi uvicorn")

    import json as _json

    app = FastAPI(title="Argos Auto Integrator", version="1.33")

    @app.get("/", response_class=HTMLResponse)
    def index():
        cards = "".join(
            _CARD_TEMPLATE.format(name=name, desc=cls.get_description()[:80])
            for name, cls in modules.items()
        )
        return HTMLResponse(_INDEX_TEMPLATE.format(cards=cards or "<p>Модули не найдены</p>"))

    for _name, _cls in modules.items():
        # Закрытие через default-аргумент
        def _make_routes(name=_name, cls=_cls):
            @app.get(f"/module/{name}", response_class=HTMLResponse)
            def module_page():
                status = cls.get_status()
                commands = cls.get_commands()
                btns = "".join(
                    f'<div class="cmd" onclick="exec(\'{c["name"]}\')">'
                    f'{c["name"]} — {c.get("description","")}</div>'
                    for c in commands
                )
                html = _MODULE_TEMPLATE.format(
                    name=name,
                    desc=cls.get_description(),
                    status_json=_json.dumps(status, indent=2, ensure_ascii=False),
                    cmd_buttons=btns or "<p>Команды не определены</p>",
                    widget=cls.get_widget(),
                )
                return HTMLResponse(html)

            @app.get(f"/api/module/{name}/status")
            def module_status():
                return JSONResponse(cls.get_status())

            @app.post(f"/api/module/{name}/execute")
            async def module_execute(request):
                data = await request.json()
                cmd    = data.get("command", "")
                params = data.get("params", {})
                result = cls.execute_command(cmd, params)
                return JSONResponse({"result": result})

        _make_routes()

    return app


# ─────────────────────────────────────────────────────────────────────────────
# Публичный API (для main.py)
# ─────────────────────────────────────────────────────────────────────────────

def run_integrator(host: str = "0.0.0.0", port: int = 8081) -> None:
    """Запускает веб-интерфейс автоинтегратора."""
    try:
        import uvicorn
    except ImportError:
        print("❌ AUTO_INTEGRATOR: pip install fastapi uvicorn")
        return

    scanner = ModuleScanner()
    modules = scanner.scan()
    app = _build_fastapi_app(modules)
    print(f"🔌 AUTO_INTEGRATOR: http://{host}:{port}  (модулей: {len(modules)})")
    uvicorn.run(app, host=host, port=port, log_level="warning")


# ─────────────────────────────────────────────────────────────────────────────
# Точка входа
# ─────────────────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    import argparse

    logging.basicConfig(level=logging.INFO)
    p = argparse.ArgumentParser(description="Argos Auto Integrator")
    p.add_argument("--host", default="0.0.0.0")
    p.add_argument("--port", type=int, default=8081)
    args = p.parse_args()
    run_integrator(host=args.host, port=args.port)
