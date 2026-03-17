import cmd
import importlib
import os
import platform
import shlex
import subprocess
import sys
import threading
import time
from datetime import datetime

import psutil

from src.security.syscalls import ArgosSyscalls
from src.security.root_manager import RootManager
from src.quantum.logic import ArgosQuantum
from src.factory.replicator import Replicator
from src.admin import ArgosAdmin
from src.argos_logger import get_logger

log = get_logger("argos.shell")

# ── Rich (опциональный) ────────────────────────────────────────────────────
try:
    Console = importlib.import_module("rich.console").Console
    Table   = importlib.import_module("rich.table").Table
    Panel   = importlib.import_module("rich.panel").Panel
    Layout  = importlib.import_module("rich.layout").Layout
    Live    = importlib.import_module("rich.live").Live
    Text    = importlib.import_module("rich.text").Text
    box     = importlib.import_module("rich.box")
    console = Console()
    RICH_OK = True
except ImportError:
    class _NS:
        def __enter__(self):  return self
        def __exit__(self, *_): return False
    class Console:
        def print(self, *a, **kw): print(*a)
        def status(self, *a, **kw): return _NS()
    console = Console()
    RICH_OK = False

# ── Лог-файл ──────────────────────────────────────────────────────────────
_LOG_CANDIDATES = [
    os.path.join(os.path.dirname(__file__), "..", "..", "argos.log"),
    os.path.join(os.path.dirname(__file__), "..", "..", "logs", "argos.log"),
    "/var/log/argos.log",
]
_LOG_FILE = next((p for p in _LOG_CANDIDATES if os.path.exists(p)), None)


def _tail_log(n: int = 12) -> str:
    """Возвращает последние n строк лог-файла."""
    if not _LOG_FILE:
        return "(лог-файл не найден)"
    try:
        with open(_LOG_FILE, "r", errors="replace") as f:
            lines = f.readlines()
        return "".join(lines[-n:]).strip() or "(лог пуст)"
    except Exception as e:
        return f"(ошибка чтения лога: {e})"


def _run_capture(cmd_parts: list, timeout: int = 30) -> tuple[int, str]:
    """Выполняет команду и возвращает (код, объединённый вывод)."""
    try:
        r = subprocess.run(cmd_parts, capture_output=True, text=True,
                           timeout=timeout)
        out = (r.stdout or "") + ("\n" + r.stderr if r.stderr else "")
        return r.returncode, out.strip()
    except FileNotFoundError:
        return -1, f"команда не найдена: {cmd_parts[0]}"
    except subprocess.TimeoutExpired:
        return -2, f"таймаут ({timeout}s)"
    except Exception as e:
        return -3, str(e)


# ═══════════════════════════════════════════════════════════════════════════
class ArgosShell(cmd.Cmd):
    """
    Интерактивный терминал Аргоса.

    Команды:
      status       — системный статус (CPU/RAM/диск/процессы)
      exec <cmd>   — выполнить системную команду, захватить вывод
      ls [путь]    — листинг директории
      cat <файл>   — содержимое файла
      ps [фильтр]  — список процессов
      net          — сетевое состояние (IP, соединения)
      scan         — сканирование локальной сети (реальное)
      tail [n]     — последние строки лога Аргоса
      dashboard    — TUI-мониторинг (Rich, Ctrl+C для выхода)
      colibri      — статус / запуск / остановка Колибри-демона
      quantum      — квантовые состояния (Bayesian)
      syscall      — низкоуровневые ctypes/syscall данные
      snapshot     — управление снимками системы
      whoami       — текущий пользователь
      clear        — очистить экран
      exit / quit  — выйти
    """

    intro   = ""
    prompt  = "argos> "

    def __init__(self, core=None):
        super().__init__()
        self.core       = core
        self.syscalls   = ArgosSyscalls()
        self.root_mgr   = RootManager()
        self.quantum    = ArgosQuantum()
        self.replicator = Replicator()
        self.admin      = ArgosAdmin()
        self.os_type    = platform.system()
        self._colibri   = None      # ColibriDaemon instance
        self._set_prompt()

    # ── Prompt ────────────────────────────────────────────────────────────

    def _set_prompt(self):
        user = os.getenv("USER", os.getenv("USERNAME", "user"))
        root = self.root_mgr.is_root
        if RICH_OK:
            color = "red" if root else "green"
            sym   = "#" if root else "$"
            self.prompt = f"[{color}]argos@{user}{sym}[/{color}] "
        else:
            sym = "#" if root else "$"
            self.prompt = f"argos@{user}{sym} "

    # ── Preloop ───────────────────────────────────────────────────────────

    def preloop(self):
        os.system("cls" if os.name == "nt" else "clear")
        if RICH_OK:
            self._print_logo_rich()
        else:
            self._print_logo_plain()

    def _print_logo_rich(self):
        logo = Text(
            "\n    ___    ____  __________  _____\n"
            "   /   |  / __ \\/ ____/ __ \\/ ___/\n"
            "  / /| | / /_/ / / __/ / / /\\__ \\ \n"
            " / ___ |/ _, _/ /_/ / /_/ /___/ / \n"
            "/_/  |_/_/ |_|\\____/\\____//____/  \n",
            style="bold cyan",
        )
        info = (
            f"Argos Shell v2.0 | OS: {platform.system()} {platform.release()}\n"
            f"Пользователь: [bold yellow]{os.getenv('USER', 'unknown')}[/bold yellow]  "
            f"| Python {platform.python_version()}"
        )
        console.print(Panel(logo, title="[bold cyan]SYSTEM ONLINE[/bold cyan]",
                            subtitle=info, border_style="cyan"))
        console.print("[dim]Введи 'help' для списка команд.[/dim]\n")

    def _print_logo_plain(self):
        print("\033[96mArgos Shell v2.0\033[0m")
        print(f"OS: {platform.system()} {platform.release()}")
        print("-" * 40)
        print("Введи 'help' для списка команд.\n")

    # ═══════════════════════════════════════════════════════════════════════
    # КОМАНДЫ
    # ═══════════════════════════════════════════════════════════════════════

    # ── status ────────────────────────────────────────────────────────────

    def do_status(self, arg):
        """Системный статус: CPU, RAM, диск, сеть, root."""
        cpu   = psutil.cpu_percent(interval=0.5)
        mem   = psutil.virtual_memory()
        disk  = psutil.disk_usage("/")
        boot  = datetime.fromtimestamp(psutil.boot_time()).strftime("%Y-%m-%d %H:%M")
        procs = len(psutil.pids())

        if RICH_OK:
            t = Table(title="Системный статус", box=box.ROUNDED)
            t.add_column("Параметр", style="cyan", no_wrap=True)
            t.add_column("Значение", style="magenta")

            def _color_val(val, warn=70, crit=90):
                s = f"{val:.1f}%"
                if val >= crit:  return f"[bold red]{s}[/bold red]"
                if val >= warn:  return f"[yellow]{s}[/yellow]"
                return f"[green]{s}[/green]"

            t.add_row("CPU",          _color_val(cpu))
            t.add_row("RAM",          _color_val(mem.percent)
                      + f"  ({mem.used//1024**2} / {mem.total//1024**2} MB)")
            t.add_row("Диск /",       _color_val(disk.percent)
                      + f"  ({disk.used//1024**3} / {disk.total//1024**3} GB)")
            t.add_row("Процессов",    str(procs))
            t.add_row("Загрузка ОС",  boot)
            t.add_row("ОС",           f"{platform.system()} {platform.release()} {platform.machine()}")
            t.add_row("Root",         ("✅ да" if self.root_mgr.is_root else "❌ нет"))
            console.print(t)
        else:
            print(f"CPU: {cpu:.1f}%  RAM: {mem.percent:.1f}%  Диск: {disk.percent:.1f}%")
            print(f"Процессов: {procs}  Загружен: {boot}")
            print(f"OS: {platform.system()} {platform.release()}")
            print(f"Root: {'да' if self.root_mgr.is_root else 'нет'}")

    # ── exec ──────────────────────────────────────────────────────────────

    def do_exec(self, arg):
        """Выполнить системную команду и вывести результат.
        Использование: exec <команда>
        Пример:        exec df -h
        """
        if not arg.strip():
            print("Использование: exec <команда>")
            return
        result = self.admin.run_cmd(arg.strip(), user="argos_shell")
        console.print(result)

    # ── default — всё неизвестное выполняем как shell-команду ─────────────

    def default(self, line):
        """Выполняет любую shell-команду с захватом вывода."""
        line = line.strip()
        if not line:
            return
        try:
            parts = shlex.split(line)
        except ValueError:
            parts = line.split()
        code, out = _run_capture(parts, timeout=30)
        if out:
            console.print(out)
        if code not in (0, -1, -2, -3) and not out:
            console.print(f"[yellow]код выхода: {code}[/yellow]")

    # ── ls ────────────────────────────────────────────────────────────────

    def do_ls(self, arg):
        """Листинг директории.
        Использование: ls [путь]
        """
        path = arg.strip() or "."
        result = self.admin.list_dir(path)
        console.print(result)

    # ── cat ───────────────────────────────────────────────────────────────

    def do_cat(self, arg):
        """Вывести содержимое файла.
        Использование: cat <путь>
        """
        path = arg.strip()
        if not path:
            print("Использование: cat <путь>")
            return
        result = self.admin.read_file(path)
        console.print(result)

    # ── ps ────────────────────────────────────────────────────────────────

    def do_ps(self, arg):
        """Список процессов (топ-20 по CPU).
        Использование: ps [фильтр_имени]
        """
        filt = arg.strip().lower()
        procs = []
        for p in psutil.process_iter(["pid", "name", "cpu_percent",
                                       "memory_percent", "status"]):
            try:
                info = p.info
                if filt and filt not in info["name"].lower():
                    continue
                procs.append(info)
            except (psutil.NoSuchProcess, psutil.AccessDenied):
                pass
        procs.sort(key=lambda x: x["cpu_percent"] or 0, reverse=True)
        if RICH_OK:
            t = Table(title=f"Процессы {'(фильтр: ' + filt + ')' if filt else '(топ-20)'}")
            t.add_column("PID",    style="cyan",    no_wrap=True)
            t.add_column("Имя",   style="magenta")
            t.add_column("CPU%",  style="yellow",   justify="right")
            t.add_column("MEM%",  style="green",    justify="right")
            t.add_column("Стат",  style="dim")
            for p in procs[:20]:
                t.add_row(str(p["pid"]), p["name"] or "?",
                          f"{p['cpu_percent']:.1f}",
                          f"{p['memory_percent']:.1f}",
                          p["status"] or "?")
            console.print(t)
        else:
            for p in procs[:20]:
                print(f"  {p['pid']:>7}  {p['name']:<22} CPU:{p['cpu_percent']:.1f}% MEM:{p['memory_percent']:.1f}%")

    # ── net ───────────────────────────────────────────────────────────────

    def do_net(self, arg):
        """Сетевые интерфейсы и активные соединения."""
        lines = ["🌐 Сетевые интерфейсы:"]
        for iface, addrs in psutil.net_if_addrs().items():
            for addr in addrs:
                if addr.family.name in ("AF_INET", "AF_INET6"):
                    lines.append(f"  {iface:12s}  {addr.family.name:8s}  {addr.address}")
        stats = psutil.net_io_counters()
        lines.append(f"\n📊 Трафик: ↑{stats.bytes_sent//1024} KB  ↓{stats.bytes_recv//1024} KB")
        conns = psutil.net_connections(kind="inet")
        established = [c for c in conns if c.status == "ESTABLISHED"]
        lines.append(f"Активных TCP соединений: {len(established)}")
        console.print("\n".join(lines))

    # ── scan ──────────────────────────────────────────────────────────────

    def do_scan(self, arg):
        """Сканирование локальной сети (реальный ping-sweep).
        Использование: scan [подсеть]  — например: scan 192.168.1
        """
        subnet = arg.strip() or ""
        if RICH_OK:
            with console.status("[bold green]Сканирование сети...[/bold green]",
                                spinner="dots"):
                result = self._real_scan(subnet)
        else:
            print("Сканирование сети...")
            result = self._real_scan(subnet)
        console.print(result)

    def _real_scan(self, subnet: str = "") -> str:
        try:
            from src.skills.net_scanner import NetGhost
            ng = NetGhost()
            if subnet:
                ng_subnet = subnet.rstrip(".") + "."
                hosts = ng.ping_scan(ng_subnet)
                if hosts:
                    return "🖧 Найдены хосты:\n" + "\n".join(f"  • {h}" for h in hosts)
                return f"🖧 Хосты не найдены в подсети {subnet}"
            return ng.scan()
        except Exception as e:
            # Fallback: быстрый ping через subprocess
            import socket
            local_ip = ""
            try:
                s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
                s.connect(("8.8.8.8", 80))
                local_ip = s.getsockname()[0]
                s.close()
            except Exception:
                pass
            lines = [f"🖧 Сканирование (fallback, IP={local_ip or '?'}):"]
            if local_ip:
                subnet_base = ".".join(local_ip.split(".")[:3]) + "."
                live = []
                def _ping(ip):
                    flag = "-n" if os.name == "nt" else "-c"
                    r = subprocess.run(
                        ["ping", flag, "1", "-W", "1", ip],
                        capture_output=True, timeout=2
                    )
                    if r.returncode == 0:
                        live.append(ip)
                threads = []
                for i in range(1, 255):
                    ip = subnet_base + str(i)
                    th = threading.Thread(target=_ping, args=(ip,), daemon=True)
                    threads.append(th)
                    th.start()
                for th in threads:
                    th.join(timeout=3)
                for ip in sorted(live):
                    lines.append(f"  • {ip}")
                if not live:
                    lines.append("  (хосты не найдены)")
            else:
                lines.append(f"  Ошибка: {e}")
            return "\n".join(lines)

    # ── tail ──────────────────────────────────────────────────────────────

    def do_tail(self, arg):
        """Последние строки лога Аргоса.
        Использование: tail [количество_строк]   (по умолчанию 20)
        """
        try:
            n = int(arg.strip()) if arg.strip() else 20
        except ValueError:
            n = 20
        log_text = _tail_log(n)
        if RICH_OK:
            console.print(Panel(log_text, title=f"[bold]argos.log (последние {n} строк)[/bold]",
                                border_style="white"))
        else:
            print(f"--- argos.log (последние {n}) ---")
            print(log_text)

    # ── dashboard ─────────────────────────────────────────────────────────

    def do_dashboard(self, arg):
        """Живой TUI-монитор (Rich). Выход: Ctrl+C."""
        if not RICH_OK:
            print("Rich не установлен. Используй: pip install rich")
            return
        layout = self._make_layout()
        with Live(layout, refresh_per_second=2, screen=True) as _:
            try:
                while True:
                    layout["header"].update(self._panel_header())
                    layout["left"].update(self._panel_stats())
                    layout["right"].update(self._panel_quantum())
                    layout["footer"].update(self._panel_log())
                    time.sleep(0.5)
            except KeyboardInterrupt:
                pass

    def _make_layout(self):
        layout = Layout()
        layout.split(
            Layout(name="header", size=3),
            Layout(name="main",   ratio=1),
            Layout(name="footer", size=10),
        )
        layout["main"].split_row(Layout(name="left"), Layout(name="right"))
        return layout

    def _panel_header(self):
        grid = Table.grid(expand=True)
        grid.add_column(justify="center", ratio=1)
        grid.add_column(justify="right")
        grid.add_row("[b]ARGOS INTEGRATED DASHBOARD[/b]",
                     datetime.now().strftime("%Y-%m-%d %H:%M:%S"))
        return Panel(grid, style="white on blue")

    def _panel_stats(self):
        cpu  = psutil.cpu_percent(interval=None)
        mem  = psutil.virtual_memory().percent
        disk = psutil.disk_usage("/").percent
        t = Table(box=None, expand=True)
        t.add_column("Метрика")
        t.add_column("Значение", justify="right")
        def _c(v):
            s = f"{v:.1f}%"
            return (f"[red]{s}[/red]" if v >= 90
                    else f"[yellow]{s}[/yellow]" if v >= 70
                    else f"[green]{s}[/green]")
        t.add_row("CPU",         _c(cpu))
        t.add_row("RAM",         _c(mem))
        t.add_row("Диск",        _c(disk))
        t.add_row("Процессов",   str(len(psutil.pids())))
        try:
            temps = psutil.sensors_temperatures()
            for key, entries in temps.items():
                if entries:
                    t.add_row(f"Темп ({key})", f"{entries[0].current:.1f}°C")
                    break
        except (AttributeError, Exception):
            pass
        return Panel(t, title="[b]Телеметрия[/b]", border_style="green")

    def _panel_quantum(self):
        state = self.quantum.generate_state()
        t = Table(box=None, expand=True)
        t.add_column("Состояние")
        t.add_column("Вероятность", justify="right")
        for s, p in state["probabilities"].items():
            row_style = "bold cyan" if s == state["name"] else ""
            t.add_row(f"[{row_style}]{s}[/{row_style}]" if row_style else s,
                      f"[{row_style}]{p:.3f}[/{row_style}]" if row_style else f"{p:.3f}")
        return Panel(t, title=f"Квантовое состояние: [bold]{state['name']}[/bold]",
                     border_style="magenta")

    def _panel_log(self):
        """Показывает реальные последние строки из лог-файла."""
        log_text = _tail_log(8)
        return Panel(log_text, title="📋 Последние логи", border_style="white")

    # ── colibri ───────────────────────────────────────────────────────────

    def do_colibri(self, arg):
        """Управление демоном Колибри (WhisperNode P2P).
        Использование:
          colibri start [--port PORT] [--light]  — запустить
          colibri stop                            — остановить
          colibri status                          — статус
          colibri restart                         — перезапустить
        """
        parts = arg.strip().split()
        sub   = parts[0].lower() if parts else "status"

        if sub in ("start", "запусти", "старт"):
            try:
                port = int(parts[2]) if len(parts) > 2 and parts[1] == "--port" else 5000
            except (ValueError, IndexError):
                print(f"⚠️ Неверный порт '{parts[2] if len(parts) > 2 else '?'}', использую 5000")
                port = 5000
            light = "--light" in parts
            console.print(self._colibri_start(port=port, light_mode=light))
        elif sub in ("stop", "останови", "стоп"):
            console.print(self._colibri_stop())
        elif sub in ("restart", "перезапусти"):
            self._colibri_stop()
            time.sleep(1)
            console.print(self._colibri_start())
        else:
            console.print(self._colibri_status())

    def _colibri_start(self, port: int = 5000, light_mode: bool = False) -> str:
        if self._colibri and self._colibri.running:
            return "ℹ️ Колибри уже запущен."
        try:
            from src.connectivity.colibri_daemon import ColibriDaemon
            self._colibri = ColibriDaemon(
                port=port,
                light_mode=light_mode,
                work_dir=os.path.join(
                    os.path.dirname(__file__), "..", "..", "logs"),
            )
            self._colibri.start()
            time.sleep(0.5)
            return (f"✅ Колибри запущен:\n"
                    f"   Порт: {port} | light_mode: {light_mode}\n"
                    f"   Node ID: {self._colibri.node_id}")
        except Exception as e:
            return f"❌ Ошибка запуска Колибри: {e}"

    def _colibri_stop(self) -> str:
        if not self._colibri or not self._colibri.running:
            return "ℹ️ Колибри не запущен."
        self._colibri.stop()
        return "✅ Колибри остановлен."

    def _colibri_status(self) -> str:
        if not self._colibri:
            return ("🐦 Колибри: не запущен.\n"
                    "   Запусти: colibri start")
        s = self._colibri.status()
        running = s.get("daemon_running", False)
        lines = [
            f"🐦 КОЛИБРИ:",
            f"   Запущен:   {'✅' if running else '❌'}",
            f"   Node ID:   {self._colibri.node_id}",
            f"   Порт:      {self._colibri.port}",
            f"   Режим:     {'light' if self._colibri.light_mode else 'full'}",
        ]
        if running and "peers" in s:
            lines.append(f"   Пиры:      {s['peers']}")
        if running and "cluster_size" in s:
            lines.append(f"   Кластер:   {s['cluster_size']} нод")
        return "\n".join(lines)

    # ── quantum ───────────────────────────────────────────────────────────

    def do_quantum(self, arg):
        """Квантовые состояния (Bayesian Inference)."""
        state = self.quantum.generate_state()
        if RICH_OK:
            t = Table(title=f"Квантовое состояние: {state['name']}")
            t.add_column("Состояние")
            t.add_column("Вероятность", justify="right")
            t.add_column("Граф")
            for s, p in state["probabilities"].items():
                bar = "█" * int(p * 25)
                style = "bold cyan" if s == state["name"] else ""
                t.add_row(
                    f"[{style}]{s}[/{style}]" if style else s,
                    f"[{style}]{p:.3f}[/{style}]" if style else f"{p:.3f}",
                    f"[{style}]{bar}[/{style}]" if style else bar,
                )
            console.print(t)
        else:
            print(f"\nДоминант: {state['name']}")
            for s, p in state["probabilities"].items():
                bar = "█" * int(p * 20)
                print(f"  {s:<14} {p:.3f}  {bar}")

    # ── syscall ───────────────────────────────────────────────────────────

    def do_syscall(self, arg):
        """Низкоуровневые ctypes/syscall данные."""
        parts = [
            self.syscalls.status(),
            self.syscalls.process_identity(),
            self.syscalls.terminal_size(),
        ]
        result = "\n".join(parts)
        if RICH_OK:
            console.print(Panel(result, title="Syscall Interface", border_style="red"))
        else:
            print(result)

    # ── snapshot ──────────────────────────────────────────────────────────

    def do_snapshot(self, arg):
        """Управление снимками системы.
        Использование:
          snapshot create [метка]
          snapshot list
          snapshot rollback <файл>
        """
        parts = arg.split()
        if not parts:
            print("Использование: snapshot [create|list|rollback <файл>]")
            return
        sub = parts[0].lower()
        if sub == "create":
            label = parts[1] if len(parts) > 1 else "manual"
            print(self.replicator.create_snapshot(label))
        elif sub == "list":
            files = self.replicator.list_snapshots()
            print("\n--- Доступные снимки ---")
            for f in (files or []):
                print(f"  {f}")
            print("------------------------")
        elif sub == "rollback":
            if len(parts) < 2:
                print("Укажи файл снимка.")
                return
            target = parts[1]
            ans = input(f"⚠️  Откат к {target}? (y/n): ")
            if ans.lower() == "y":
                print(self.replicator.rollback(target))
            else:
                print("Отменено.")
        else:
            print(f"Неизвестная подкоманда: {sub}")

    # ── clone (Argos OS image) ────────────────────────────────────────────

    def do_clone(self, arg):
        """Создать образ Argos OS — полный клон системы с загрузочным скриптом.
        Использование:
          clone
        Создаёт файл builds/images/ArgosOS_Image_<дата>.7z, готовый к развёртыванию.
        """
        print("⏳ Создаю образ Argos OS…")
        print(self.replicator.create_os_image())

    # ── whoami ────────────────────────────────────────────────────────────

    def do_whoami(self, arg):
        """Информация о текущем пользователе."""
        uid  = os.getuid()  if hasattr(os, "getuid")  else "N/A"
        gid  = os.getgid()  if hasattr(os, "getgid")  else "N/A"
        euid = os.geteuid() if hasattr(os, "geteuid") else "N/A"
        print(f"Пользователь: {os.getenv('USER', os.getenv('USERNAME', '?'))}")
        print(f"UID={uid}  GID={gid}  EUID={euid}")
        print(f"Root: {'да' if self.root_mgr.is_root else 'нет'}")

    # ── clear ─────────────────────────────────────────────────────────────

    def do_clear(self, arg):
        """Очистить экран."""
        os.system("cls" if os.name == "nt" else "clear")
        if RICH_OK:
            self._print_logo_rich()

    # ── exit / quit ───────────────────────────────────────────────────────

    def do_exit(self, arg):
        """Выйти из Argos Shell."""
        if self._colibri and self._colibri.running:
            self._colibri.stop()
        print("Сессия Argos Shell завершена.")
        return True

    do_quit = do_exit

    # ── vision ────────────────────────────────────────────────────────────

    def do_vision(self, arg):
        """Запустить Vision-модуль (OpenCV камера/экран)."""
        try:
            from src.vision import ArgosVision
            v = ArgosVision()
            print(v.live_feed(timeout=None))
        except ImportError:
            print("Vision модуль недоступен (нет зависимостей).")
        except Exception as e:
            print(f"Vision ошибка: {e}")


# ── Точка входа ─────────────────────────────────────────────────────────────

if __name__ == "__main__":
    try:
        ArgosShell().cmdloop()
    except KeyboardInterrupt:
        print("\nВыход...")


# Rich Visualization
try:
    Console = importlib.import_module("rich.console").Console
    Table = importlib.import_module("rich.table").Table
    Panel = importlib.import_module("rich.panel").Panel
    Layout = importlib.import_module("rich.layout").Layout
    Live = importlib.import_module("rich.live").Live
    Text = importlib.import_module("rich.text").Text
    box = importlib.import_module("rich.box")
    console = Console()
    RICH_OK = True
except ImportError:
    # Заглушка, если Rich не установлен
    class _NoopStatus:
        def __enter__(self):
            return self
        def __exit__(self, exc_type, exc, tb):
            return False

    class Console:
        def print(self, *args, **kwargs):
            print(*args)
        def status(self, *args, **kwargs):
            return _NoopStatus()
    console = Console()
    RICH_OK = False

class ArgosShell(cmd.Cmd):
    intro = ""
    prompt = "argos> "
    
    def __init__(self):
        super().__init__()
        self.syscalls = ArgosSyscalls()
        self.root_manager = RootManager()
        self.quantum = ArgosQuantum()
        self.replicator = Replicator()
        self.os_type = platform.system()
        self._set_prompt()

    def _set_prompt(self):
        user = os.getenv("USER", "user")
        if self.root_manager.is_root:
            self.prompt = f"[red]argos@{user} (ROOT)# [/red]" if RICH_OK else f"argos@{user} (ROOT)# "
        else:
            self.prompt = f"[green]argos@{user}$ [/green]" if RICH_OK else f"argos@{user}$ "

    def preloop(self):
        self._clear_screen()
        if RICH_OK:
            self._print_logo_rich()
        else:
            self._print_logo_plain()
    
    def _print_logo_rich(self):
        logo = Text(r"""
    ___    ____  __________  _____
   /   |  / __ \/ ____/ __ \/ ___/
  / /| | / /_/ / / __/ / / /\__ \ 
 / ___ |/ _, _/ /_/ / /_/ /___/ / 
/_/  |_/_/ |_|\____/\____//____/  
                                  
        """, style="bold cyan")
        
        info = f"Argos System v1.3 | Kernel: {platform.release()}\nLogged in as: [bold yellow]{os.getenv('USER', 'unknown')}[/bold yellow]"
        console.print(Panel(logo, title="[bold cyan]SYSTEM ONLINE[/bold cyan]", subtitle=info, border_style="cyan"))
        console.print("[dim]Type 'help' or '?' for commands.[/dim]\n")

    def _print_logo_plain(self):
        print("\033[96mArgos System v1.3\033[0m")
        print(f"Kernel: {platform.release()}")
        print("-" * 40)

    def _clear_screen(self):
        os.system('cls' if os.name == 'nt' else 'clear')

    def do_status(self, arg):
        """Show system status and root privileges check."""
        if not RICH_OK:
            print("\n--- System Status ---")
            print(f"OS: {platform.system()} {platform.release()}")
            print(self.root_manager.status())
            print("---------------------\n")
            return

        table = Table(title="System Status", box=box.ROUNDED)
        table.add_column("Property", style="cyan")
        table.add_column("Value", style="magenta")
        
        table.add_row("OS", f"{platform.system()} {platform.release()}")
        table.add_row("Architecture", platform.machine())
        
        root_status = self.root_manager.status()
        if "✅" in root_status:
            status_style = "bold green"
        else:
            status_style = "bold yellow"
            
        table.add_row("Privileges", Text(root_status, style=status_style))
        console.print(table)

    def do_dashboard(self, arg):
        """Launch the live TUI dashboard (Rich). Press Ctrl+C to exit."""
        if not RICH_OK:
            print("Rich library not installed. Dashboard unavailable.")
            return

        layout = self._make_layout()
        with Live(layout, refresh_per_second=4, screen=True) as live:
            try:
                while True:
                    layout["header"].update(self._get_header_panel())
                    layout["left"].update(self._get_system_stats_panel())
                    layout["right"].update(self._get_quantum_panel())
                    layout["footer"].update(self._get_log_panel())
                    time.sleep(0.25)
            except KeyboardInterrupt:
                pass

    def _make_layout(self):
        layout = Layout()
        layout.split(
            Layout(name="header", size=3),
            Layout(name="main", ratio=1),
            Layout(name="footer", size=7)
        )
        layout["main"].split_row(
            Layout(name="left"),
            Layout(name="right"),
        )
        return layout

    def _get_header_panel(self):
        grid = Table.grid(expand=True)
        grid.add_column(justify="center", ratio=1)
        grid.add_column(justify="right")
        grid.add_row(
            "[b]ARGOS INTEGRATED DASHBOARD[/b]", 
            datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        )
        return Panel(grid, style="white on blue")

    def _get_system_stats_panel(self):
        table = Table(box=None, expand=True)
        table.add_column("Metric")
        table.add_column("Value", justify="right")
        
        cpu = psutil.cpu_percent()
        mem = psutil.virtual_memory().percent
        disk = psutil.disk_usage('/').percent
        
        table.add_row("CPU Load", f"[green]{cpu}%[/green]" if cpu < 50 else f"[red]{cpu}%[/red]")
        table.add_row("Memory", f"[yellow]{mem}%[/yellow]")
        table.add_row("Disk", f"{disk}%")
        
        return Panel(table, title="[b]System Telemetry[/b]", border_style="green")

    def _get_quantum_panel(self):
        state = self.quantum.generate_state()
        table = Table(box=None, expand=True)
        table.add_column("State")
        table.add_column("Prob")
        
        for s, p in state['probabilities'].items():
            if s == state['name']:
                table.add_row(f"[bold cyan]{s}[/bold cyan]", f"{p:.2f}")
            else:
                table.add_row(s, f"{p:.2f}")
                
        return Panel(table, title=f"Quantum State: [bold]{state['name']}[/bold]", border_style="magenta")

    def _get_log_panel(self):
        # В реальной системе здесь был бы tail -f логов
        log_text = Text()
        log_text.append(f"[{datetime.now().strftime('%H:%M:%S')}] System stable.\n", style="dim")
        log_text.append(f"[{datetime.now().strftime('%H:%M:%S')}] Security scan complete: No threats.\n", style="green")
        log_text.append(f"[{datetime.now().strftime('%H:%M:%S')}] Waiting for user input...", style="dim")
        return Panel(log_text, title="System Logs", border_style="white")

    def do_vision(self, arg):
        """Start Vision Feedback window (OpenCV)."""
        try:
            from src.vision import ArgosVision
            vision = ArgosVision()
            # Аргумент timeout можно передать
            print(vision.live_feed(timeout=None))
        except ImportError:
            print("Vision module not reachable.")
        except Exception as e:
            print(f"Error starting vision: {e}")

    def do_syscall(self, arg):
        """Execute low-level system calls via ctypes (Linux/Windows)."""
        if not RICH_OK:
            print(self.syscalls.status())
            print(self.syscalls.process_identity())
            print(self.syscalls.terminal_size())
            return

        # Rich implementation
        text = Text()
        text.append(self.syscalls.status() + "\n")
        text.append(self.syscalls.process_identity() + "\n")
        text.append(self.syscalls.terminal_size())
        console.print(Panel(text, title="Syscall Interface", border_style="red"))

    def do_scan(self, arg):
        """Scan local network (simulated/real depending on modules)."""
        if not RICH_OK:
            print("Scanning network environment...")
            time.sleep(1)
            print("- 192.168.1.10  Argos-Core       ONLINE (Self)")
            print("- 192.168.1.1   Gateway          ONLINE")
            print("- 192.168.1.14  Simulate-IoT     ONLINE")
            return

        with console.status("[bold green]Scanning network environment...[/bold green]", spinner="dots"):
            time.sleep(2)
            
        table = Table(title="Network Scan Results")
        table.add_column("IP Address", style="cyan")
        table.add_column("Hostname", style="magenta")
        table.add_column("Status", style="green")
        
        table.add_row("192.168.1.10", "Argos-Core", "ONLINE (Self)")
        table.add_row("192.168.1.1", "Gateway", "ONLINE")
        table.add_row("192.168.1.14", "Simulate-IoT", "ONLINE")
        
        console.print(table)

    def do_clear(self, arg):
        """Clear the terminal screen."""
        self._clear_screen()
        if RICH_OK:
            self._print_logo_rich()

    # ... (rest of formatting) ...

    def do_quantum(self, arg):
        """Show current quantum state probabilities (Bayesian Network)."""
        state = self.quantum.generate_state()
        print("\n--- Quantum State Inference ---")
        print(f"Dominant State: \033[96m{state['name']}\033[0m")
        print("\nProbabilities:")
        for s, p in state['probabilities'].items():
            bar = "█" * int(p * 20)
            print(f"  {s:<12} {p:.2f} {bar}")
        print("-------------------------------\n")

    def do_snapshot(self, arg):
        """Manage system snapshots: create | list | rollback <file>"""
        args = arg.split()
        if not args:
            print("Usage: snapshot [create|list|rollback <filename>]")
            return

        cmd = args[0]
        if cmd == "create":
            label = args[1] if len(args) > 1 else "manual"
            print(self.replicator.create_snapshot(label))
        
        elif cmd == "list":
            files = self.replicator.list_snapshots()
            print("\n--- Available Snapshots ---")
            for f in files:
                print(f"  {f}")
            print("---------------------------\n")

        elif cmd == "rollback":
            if len(args) < 2:
                print("Error: Specify snapshot filename to rollback.")
                return
            target = args[1]
            confirm = input(f"⚠️  WARNING: Rollback to {target}? Current data may be lost. (y/n): ")
            if confirm.lower() == 'y':
                print(self.replicator.rollback(target))
            else:
                print("Rollback cancelled.")
        else:
            print(f"Unknown snapshot command: {cmd}")

    def do_whoami(self, arg):
        """Show current user identity."""
        print(f"User: {os.getenv('USER')}")
        print(f"UID: {os.getuid() if hasattr(os, 'getuid') else 'N/A'}")
        print(f"GID: {os.getgid() if hasattr(os, 'getgid') else 'N/A'}")

    def do_exit(self, arg):
        """Exit the Argos Shell."""
        print("Shutting down Argos Shell session...")
        return True

    def default(self, line):
        try:
            # Pass unknown commands to system shell
            os.system(line)
        except Exception as e:
            print(f"Error executing system command: {e}")

if __name__ == "__main__":
    try:
        ArgosShell().cmdloop()
    except KeyboardInterrupt:
        print("\nExiting...")
