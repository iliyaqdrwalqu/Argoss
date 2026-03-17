"""
agent.py — Режим автономного агента Аргоса
  Разбивает сложную задачу на шаги и выполняет цепочку команд.
  "сканируй сеть → найди новые устройства → запиши в файл → отправь в Telegram"
"""
import re
import time
from src.argos_logger import get_logger

log = get_logger("argos.agent")

STEP_SEPARATORS = [" затем ", " потом ", " после этого ", " → ", "->", " и затем ", " далее "]


class ArgosAgent:
    def __init__(self, core):
        self.core    = core
        self._running = False
        self._results = []

    def execute_plan(self, plan: str, admin, flasher) -> str:
        """Разбирает план на шаги и выполняет последовательно."""
        steps = self._parse_steps(plan)
        if len(steps) <= 1:
            return None  # Не агентная задача — обычная команда

        log.info("Агент: %d шагов", len(steps))
        self._results = []
        self._running = True

        results = [f"🤖 АГЕНТ АКТИВИРОВАН — {len(steps)} шагов:\n"]

        for i, step in enumerate(steps, 1):
            if not self._running:
                results.append(f"\n⛔ Выполнение прервано на шаге {i}.")
                break

            step = step.strip()
            if not step:
                continue

            results.append(f"\n📍 Шаг {i}/{len(steps)}: {step}")
            log.info("Шаг %d: %s", i, step)

            try:
                res = self.core.process_logic(step, admin, flasher)
                answer = res.get("answer", "")[:300]
                results.append(f"   ✅ {answer}")
                self._results.append({"step": step, "result": answer, "ok": True})
            except Exception as e:
                err = str(e)
                results.append(f"   ❌ Ошибка: {err}")
                self._results.append({"step": step, "result": err, "ok": False})
                log.error("Шаг %d ошибка: %s", i, err)

            # Небольшая пауза между шагами
            time.sleep(0.5)

        self._running = False
        ok_count   = sum(1 for r in self._results if r["ok"])
        fail_count = len(self._results) - ok_count

        results.append(f"\n━━━━━━━━━━━━━━━━━━━━━━━━━━")
        results.append(f"🤖 ПЛАН ВЫПОЛНЕН: ✅ {ok_count} / ❌ {fail_count}")

        return "\n".join(results)

    def _parse_steps(self, text: str) -> list:
        """Разбивает текст на шаги по разделителям."""
        result = [text]
        for sep in STEP_SEPARATORS:
            new_result = []
            for part in result:
                new_result.extend(part.split(sep))
            result = new_result
        # Дополнительно по нумерованным пунктам "1. ... 2. ..."
        numbered = re.split(r'\d+\.\s+', text)
        if len(numbered) > 2:
            return [s.strip() for s in numbered if s.strip()]
        return [s.strip() for s in result if s.strip()]

    def stop(self):
        self._running = False
        return "⛔ Агент остановлен."

    def last_report(self) -> str:
        if not self._results:
            return "📭 Агент ещё не запускался."
        lines = ["📋 ПОСЛЕДНИЙ ОТЧЁТ АГЕНТА:"]
        for i, r in enumerate(self._results, 1):
            icon = "✅" if r["ok"] else "❌"
            lines.append(f"  {icon} Шаг {i}: {r['step'][:50]}")
            lines.append(f"      → {r['result'][:100]}")
        return "\n".join(lines)
