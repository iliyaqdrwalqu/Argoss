from src.modules.base import BaseModule


class SystemMonitorModule(BaseModule):
    module_id = "system_monitor"
    title = "System Monitor"

    def can_handle(self, text: str, lowered: str) -> bool:
        keys = ["статус системы", "чек-ап", "состояние здоровья", "список процессов", "убей процесс", "завершить процесс"]
        return any(k in lowered for k in keys)

    def handle(self, text: str, lowered: str, admin=None, flasher=None) -> str | None:
        if not self.core or not admin:
            return None

        if any(k in lowered for k in ["статус системы", "чек-ап", "состояние здоровья"]):
            return f"{admin.get_stats()}\n{self.core.sensors.get_full_report()}"

        if "список процессов" in lowered:
            return admin.list_processes()

        if any(k in lowered for k in ["убей процесс", "завершить процесс"]):
            return admin.kill_process(text.split()[-1])

        return None
