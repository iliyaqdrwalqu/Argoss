"""
tool_calling.py — model-driven Tool Calling для Argos.

Идея: вместо жёстких цепочек модель получает JSON-схемы инструментов,
сама планирует вызовы и возвращает итоговый ответ.
"""

from __future__ import annotations

import json
import logging
import os
from typing import Any, Callable

import psutil
import requests

MAX_PREVIOUS_OUTPUTS = 5
MAX_PREVIOUS_RESULT_CHARS = 800
log = logging.getLogger(__name__)


class ArgosToolCallingEngine:
    def __init__(self, core):
        self.core = core
        try:
            configured_rounds = int(os.getenv("ARGOS_TOOL_CALLING_MAX_ROUNDS", "3"))
        except (TypeError, ValueError):
            log.warning(
                "Invalid ARGOS_TOOL_CALLING_MAX_ROUNDS=%r, fallback to 3",
                os.getenv("ARGOS_TOOL_CALLING_MAX_ROUNDS"),
            )
            configured_rounds = 3
        self.max_rounds = max(1, min(configured_rounds, 5))

    def tool_schemas(self) -> list[dict[str, Any]]:
        return [
            {
                "name": "get_system_stats",
                "description": "Получить краткий статус системы: CPU, RAM, диск, ОС.",
                "parameters": {
                    "type": "object",
                    "properties": {},
                    "additionalProperties": False,
                },
            },
            {
                "name": "get_disk_usage",
                "description": "Получить детальный статус диска: свободно/занято в GB и процентах.",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "path": {"type": "string", "description": "Точка монтирования, по умолчанию '/'"}
                    },
                    "required": [],
                    "additionalProperties": False,
                },
            },
            {
                "name": "get_health_report",
                "description": "Получить health-отчёт сенсоров (температура, сеть, питание, storage).",
                "parameters": {
                    "type": "object",
                    "properties": {},
                    "additionalProperties": False,
                },
            },
            {
                "name": "get_weather",
                "description": "Получить информацию о погоде через weather skill (если доступен).",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "query": {"type": "string", "description": "Город или уточнение, например 'Москва'"}
                    },
                    "required": [],
                    "additionalProperties": False,
                },
            },
            {
                "name": "list_files",
                "description": "Показать содержимое директории.",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "path": {"type": "string", "description": "Путь до каталога, по умолчанию '.'"}
                    },
                    "required": [],
                    "additionalProperties": False,
                },
            },
            {
                "name": "read_file_preview",
                "description": "Прочитать начало файла (ограниченный предпросмотр).",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "path": {"type": "string", "description": "Путь к файлу"},
                        "max_chars": {"type": "integer", "minimum": 100, "maximum": 6000},
                    },
                    "required": ["path"],
                    "additionalProperties": False,
                },
            },
            {
                "name": "network_status",
                "description": "Получить статус P2P сети (если P2P запущен).",
                "parameters": {
                    "type": "object",
                    "properties": {},
                    "additionalProperties": False,
                },
            },
            {
                "name": "start_p2p",
                "description": "Запустить P2P мост Аргоса.",
                "parameters": {
                    "type": "object",
                    "properties": {},
                    "additionalProperties": False,
                },
            },
            {
                "name": "route_p2p_query",
                "description": "Отправить запрос на вычислительно лучшую ноду P2P сети.",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "prompt": {"type": "string", "description": "Текст запроса"}
                    },
                    "required": ["prompt"],
                    "additionalProperties": False,
                },
            },
        ]

    def try_handle(self, user_text: str, admin, flasher) -> str | None:
        outputs = []
        context_text = ""
        if getattr(self.core, "context", None):
            try:
                context_text = self.core.context.get_prompt_context(user_text) or ""
            except Exception:
                context_text = ""
        seen_calls = set()

        for _ in range(self.max_rounds):
            plan = self._plan_calls(user_text, context_text=context_text, previous_outputs=outputs)
            if not plan:
                return None if not outputs else self._synthesize_answer(user_text, outputs)

            calls = plan.get("tool_calls") or []
            confidence = float(plan.get("confidence", 0) or 0)
            final_answer = (plan.get("final_answer") or "").strip()

            if not calls:
                if final_answer and confidence >= 0.65:
                    return final_answer
                break

            any_new_calls = False
            for call in calls[:3]:
                name = call.get("name")
                if not isinstance(name, str) or not name.strip():
                    log.warning("Tool-calling planner returned invalid tool name: %r", name)
                    continue
                arguments = call.get("arguments") or {}
                signature = self._call_signature(name, arguments)
                if signature in seen_calls:
                    continue
                seen_calls.add(signature)
                any_new_calls = True
                result = self._execute_tool(name, arguments, admin=admin, flasher=flasher)
                outputs.append({"tool": name, "arguments": arguments, "result": result})

            if not any_new_calls:
                break

        if outputs:
            return self._synthesize_answer(user_text, outputs)
        return None

    def _call_signature(self, name: str, arguments: Any) -> str:
        normalized = self._normalize_signature_payload(arguments)
        try:
            payload = json.dumps(normalized, ensure_ascii=False, sort_keys=True, default=str)
        except Exception as exc:
            log.warning("Tool-call signature JSON serialization failed for %r: %s", name, exc)
            payload = str(normalized)
        return f"{name}:{payload}"

    def _normalize_signature_payload(self, value: Any) -> Any:
        if isinstance(value, dict):
            return {k: self._normalize_signature_payload(v) for k, v in sorted(value.items())}
        if isinstance(value, (list, tuple)):
            return [self._normalize_signature_payload(v) for v in value]
        return value

    def _execute_tool(self, name: str, arguments: dict[str, Any], admin, flasher) -> str:
        tools: dict[str, Callable[[dict[str, Any]], str]] = {
            "get_system_stats": lambda args: admin.get_stats(),
            "get_disk_usage": self._tool_get_disk_usage,
            "get_health_report": lambda args: self.core.sensors.get_full_report(),
            "get_weather": lambda args: self._tool_get_weather(args.get("query", "")),
            "list_files": lambda args: admin.list_dir(args.get("path", ".")),
            "read_file_preview": self._tool_read_file_preview,
            "network_status": lambda args: self.core.p2p.network_status() if self.core.p2p else "P2P не запущен.",
            "start_p2p": lambda args: self.core.start_p2p(),
            "route_p2p_query": lambda args: self.core.p2p.route_query(args.get("prompt", "")) if self.core.p2p else "P2P не запущен.",
        }

        fn = tools.get(name)
        if not fn:
            return f"❌ Неизвестный инструмент: {name}"

        try:
            return fn(arguments)
        except Exception as exc:
            return f"❌ Ошибка инструмента {name}: {exc}"

    def _tool_get_disk_usage(self, arguments: dict[str, Any]) -> str:
        path = arguments.get("path") or "/"
        try:
            usage = psutil.disk_usage(path)
            total_gb = usage.total / (1024 ** 3)
            free_gb = usage.free / (1024 ** 3)
            used_gb = usage.used / (1024 ** 3)
            return (
                f"Диск {path}: занято {used_gb:.1f} GB ({usage.percent}%), "
                f"свободно {free_gb:.1f} GB из {total_gb:.1f} GB"
            )
        except Exception as exc:
            return f"Ошибка чтения диска {path}: {exc}"

    def _tool_get_weather(self, query: str) -> str:
        if self.core.skill_loader:
            text = f"weather {query}".strip()
            result = self.core.skill_loader.dispatch(text, core=self.core)
            if result:
                return result
        return "Навык погоды не дал ответ. Проверь загрузку weather skill."

    def _tool_read_file_preview(self, arguments: dict[str, Any]) -> str:
        path = arguments.get("path", "")
        if not path:
            return "❌ read_file_preview: требуется path"

        max_chars = int(arguments.get("max_chars", 2000) or 2000)
        max_chars = max(100, min(max_chars, 6000))

        safe_path = os.path.normpath(path)
        if safe_path.startswith(".."):
            return "❌ Доступ к path вне workspace запрещён."

        try:
            with open(safe_path, "r", encoding="utf-8") as f:
                content = f.read(max_chars)
            suffix = "..." if len(content) == max_chars else ""
            return f"📄 {safe_path}:\n{content}{suffix}"
        except Exception as exc:
            return f"Ошибка чтения файла: {exc}"

    def _plan_calls(
        self,
        user_text: str,
        context_text: str = "",
        previous_outputs: list[dict[str, Any]] | None = None,
    ) -> dict[str, Any] | None:
        prev_text = ""
        if previous_outputs:
            compact_outputs = []
            for item in previous_outputs[-MAX_PREVIOUS_OUTPUTS:]:
                result_text = item.get("result", "")
                if not isinstance(result_text, str):
                    result_text = str(result_text)
                if len(result_text) > MAX_PREVIOUS_RESULT_CHARS:
                    result_text = result_text[:MAX_PREVIOUS_RESULT_CHARS] + "..."
                compact_outputs.append({
                    "tool": item.get("tool"),
                    "arguments": item.get("arguments"),
                    "result": result_text,
                })
            prev_text = f"\n\nРезультаты предыдущих шагов: {json.dumps(compact_outputs, ensure_ascii=False)}"
        prompt = (
            "Ты planner для Tool Calling. Тебе даны инструменты и JSON-схемы. "
            "Выбери до 3 вызовов инструментов, если они действительно нужны для ответа.\n\n"
            "Верни СТРОГО JSON без markdown:\n"
            "{\n"
            "  \"confidence\": 0.0,\n"
            "  \"tool_calls\": [{\"name\": \"...\", \"arguments\": {...}}],\n"
            "  \"final_answer\": \"...\"\n"
            "}\n\n"
            "Правила:\n"
            "- Если инструменты не нужны, верни пустой tool_calls и ответ в final_answer.\n"
            "- Аргументы должны строго соответствовать схеме.\n"
            "- Не выдумывай инструменты.\n"
            "- Если на предыдущих шагах уже есть данные, не повторяй те же вызовы без причины.\n"
            "- Отвечай на русском.\n\n"
            f"Инструменты: {json.dumps(self.tool_schemas(), ensure_ascii=False)}\n\n"
            f"Контекст диалога: {context_text or 'нет'}\n"
            f"Запрос пользователя: {user_text}"
            f"{prev_text}"
        )

        text = self._ask_model_text(prompt)
        if not text:
            return None
        return self._extract_json(text)

    def _synthesize_answer(self, user_text: str, outputs: list[dict[str, Any]]) -> str:
        prompt = (
            "Сформируй короткий итоговый ответ пользователю на русском. "
            "Используй только данные из результатов инструментов, без выдумок.\n\n"
            f"Запрос: {user_text}\n"
            f"Результаты инструментов: {json.dumps(outputs, ensure_ascii=False)}"
        )
        text = self._ask_model_text(prompt)
        if text:
            return text.strip()

        lines = ["Итог по инструментам:"]
        for item in outputs:
            lines.append(f"- {item['tool']}: {item['result']}")
        return "\n".join(lines)

    def _ask_model_text(self, prompt: str) -> str | None:
        answer = self.core._ask_gemini("Ты planner/синтезатор ответов Аргоса. Отвечай строго по задаче.", prompt)
        if answer:
            return answer

        answer = self.core._ask_gigachat("Ты planner/синтезатор ответов Аргоса. Отвечай строго по задаче.", prompt)
        if answer:
            return answer

        answer = self.core._ask_yandexgpt("Ты planner/синтезатор ответов Аргоса. Отвечай строго по задаче.", prompt)
        if answer:
            return answer

        try:
            self.core._ensure_ollama_running()
            response = requests.post(
                self.core.ollama_url,
                json={
                    "model": os.getenv("OLLAMA_MODEL", "llama3.2:1b"),
                    "prompt": prompt,
                    "stream": False,
                    "format": "json",
                },
                timeout=int(os.getenv("OLLAMA_TIMEOUT", "600")),
            )
            if not response.ok:
                return None
            return response.json().get("response")
        except Exception:
            return None

    def _extract_json(self, text: str) -> dict[str, Any] | None:
        candidate = text.strip()
        if candidate.startswith("```"):
            candidate = candidate.strip("`")
            candidate = candidate.replace("json", "", 1).strip()

        # Попытка 1: как есть
        try:
            obj = json.loads(candidate)
            if isinstance(obj, dict):
                return obj
        except Exception:
            pass

        # Попытка 2: вырезать крупнейший JSON-объект
        left = candidate.find("{")
        right = candidate.rfind("}")
        if left >= 0 and right > left:
            chunk = candidate[left:right + 1]
            try:
                obj = json.loads(chunk)
                if isinstance(obj, dict):
                    return obj
            except Exception:
                return None
        return None
