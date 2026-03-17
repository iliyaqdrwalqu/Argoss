"""
scheduler.py — Планировщик задач Аргоса
  "аргос, напомни в 09:00 сделать бэкап"
  "аргос, каждый час сканируй сеть"
  "аргос, покажи расписание"
"""
import threading
import time
import json
import os
import re
from src.argos_logger import get_logger

log = get_logger("argos.scheduler")
TASKS_FILE = "config/scheduled_tasks.json"


class ArgosScheduler:
    def __init__(self, core=None):
        self.core    = core
        self.tasks   = self._load()
        self._running = False

    def _load(self) -> list:
        if os.path.exists(TASKS_FILE):
            try:
                return json.load(open(TASKS_FILE, encoding="utf-8"))
            except Exception:
                pass
        return []

    def _save(self):
        os.makedirs("config", exist_ok=True)
        json.dump(self.tasks, open(TASKS_FILE, "w", encoding="utf-8"), indent=2, ensure_ascii=False)

    def start(self) -> str:
        self._running = True
        threading.Thread(target=self._loop, daemon=True).start()
        log.info("Scheduler запущен. Задач: %d", len(self.tasks))
        return f"⏰ Планировщик запущен. Активных задач: {len(self.tasks)}"

    def stop(self):
        self._running = False

    def _loop(self):
        while self._running:
            now = time.localtime()
            for task in list(self.tasks):
                if self._should_run(task, now):
                    self._execute(task)
                    if task.get("repeat") == "once":
                        self.tasks.remove(task)
                        self._save()
            time.sleep(30)  # проверка каждые 30 секунд

    def _should_run(self, task: dict, now) -> bool:
        t_type = task.get("type")
        last   = task.get("last_run", 0)
        now_ts = time.time()

        if t_type == "daily":
            h, m = task.get("hour", 9), task.get("minute", 0)
            if now.tm_hour == h and now.tm_min == m:
                if now_ts - last > 60:  # не дублировать в ту же минуту
                    return True

        elif t_type == "interval":
            interval = task.get("interval_sec", 3600)
            if now_ts - last >= interval:
                return True

        elif t_type == "once":
            run_at = task.get("run_at", 0)
            if now_ts >= run_at and last == 0:
                return True

        return False

    def _execute(self, task: dict):
        cmd     = task.get("command", "")
        task_id = task.get("id", "?")
        log.info("Выполняю задачу #%s: %s", task_id, cmd)
        task["last_run"] = time.time()
        self._save()

        if self.core:
            # Эмулируем ввод пользователя
            try:
                from src.admin import ArgosAdmin
                from src.factory.flasher import AirFlasher
                admin   = ArgosAdmin()
                flasher = AirFlasher()
                res = self.core.process_logic(cmd, admin, flasher)
                log.info("Задача #%s завершена: %s", task_id, res.get("answer","")[:100])
            except Exception as e:
                log.error("Задача #%s ошибка: %s", task_id, e)
        else:
            print(f"[SCHEDULER] Задача: {cmd}")

    def add_daily(self, command: str, hour: int, minute: int = 0) -> str:
        task = {
            "id":       len(self.tasks) + 1,
            "type":     "daily",
            "command":  command,
            "hour":     hour,
            "minute":   minute,
            "last_run": 0,
        }
        self.tasks.append(task)
        self._save()
        return f"✅ Задача #{task['id']} добавлена: '{command}' каждый день в {hour:02d}:{minute:02d}"

    def add_interval(self, command: str, interval_sec: int) -> str:
        task = {
            "id":           len(self.tasks) + 1,
            "type":         "interval",
            "command":      command,
            "interval_sec": interval_sec,
            "last_run":     0,
        }
        self.tasks.append(task)
        self._save()
        mins = interval_sec // 60
        return f"✅ Задача #{task['id']}: '{command}' каждые {mins} мин."

    def add_once(self, command: str, delay_sec: int) -> str:
        task = {
            "id":       len(self.tasks) + 1,
            "type":     "once",
            "repeat":   "once",
            "command":  command,
            "run_at":   time.time() + delay_sec,
            "last_run": 0,
        }
        self.tasks.append(task)
        self._save()
        return f"✅ Задача #{task['id']}: '{command}' через {delay_sec//60} мин."

    def remove(self, task_id: int) -> str:
        before = len(self.tasks)
        self.tasks = [t for t in self.tasks if t.get("id") != task_id]
        if len(self.tasks) < before:
            self._save()
            return f"✅ Задача #{task_id} удалена."
        return f"❌ Задача #{task_id} не найдена."

    def list_tasks(self) -> str:
        if not self.tasks:
            return "📭 Расписание пустое."
        lines = ["⏰ РАСПИСАНИЕ АРГОСА:"]
        for t in self.tasks:
            if t["type"] == "daily":
                when = f"каждый день {t['hour']:02d}:{t['minute']:02d}"
            elif t["type"] == "interval":
                when = f"каждые {t['interval_sec']//60} мин"
            else:
                import datetime
                when = f"однажды в {datetime.datetime.fromtimestamp(t['run_at']).strftime('%H:%M')}"
            lines.append(f"  #{t['id']} [{t['type']}] {when}: {t['command'][:50]}")
        return "\n".join(lines)

    def parse_and_add(self, text: str) -> str:
        """Парсит натуральный язык: 'напомни в 9 утра сделать бэкап'"""
        t = text.lower()

        # Интервалы
        m = re.search(r"каждые?\s+(\d+)\s*(час|мин|секунд)", t)
        if m:
            n, unit = int(m.group(1)), m.group(2)
            secs = n * (3600 if "час" in unit else 60 if "мин" in unit else 1)
            cmd  = re.sub(r"каждые?\s+\d+\s*\w+\s*(запуск|делай|выполняй)?", "", t).strip()
            return self.add_interval(cmd or text, secs)

        # Ежедневно в HH:MM
        m = re.search(r"в\s+(\d{1,2})(?::(\d{2}))?\s*(утра|вечера|ночи)?", t)
        if m:
            h = int(m.group(1))
            mins = int(m.group(2)) if m.group(2) else 0
            if m.group(3) in ("вечера",) and h < 12: h += 12
            cmd = re.sub(r"напомни|ежедневно|каждый день|в\s+\d+.*", "", t).strip()
            return self.add_daily(cmd or text, h, mins)

        # Через N минут
        m = re.search(r"через\s+(\d+)\s*(мин|час)", t)
        if m:
            n, unit = int(m.group(1)), m.group(2)
            secs = n * (3600 if "час" in unit else 60)
            cmd  = re.sub(r"через\s+\d+\s*\w+\s*", "", t).strip()
            return self.add_once(cmd or text, secs)

        return "❓ Не понял расписание. Примеры:\n  'каждый час сканируй сеть'\n  'в 09:00 дайджест'\n  'через 30 мин статус системы'"
