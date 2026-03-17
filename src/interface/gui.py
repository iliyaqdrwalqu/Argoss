"""
gui.py — Главный интерфейс ARGOS на CustomTkinter
================================================
Единый тёмный кибер-стиль:
  • Цветовая палитра: #060A1A фон, #00FFFF акцент, #00FF88 зелень
  • Шрифт: Consolas (монопространственный, HUD-стиль)
  • Вкладки: Консоль | Память | Система
  • Боковая панель: AI-режим, голос, быстрые команды, метрики ЦП/ОЗУ
  • Строка состояния: квантовое состояние, время, CPU/RAM
  • История команд: ↑ / ↓ в поле ввода
  • Анимация обработки: мигающие точки пока АРГОС думает
"""
from __future__ import annotations

import platform
import threading
import time
from collections import deque
from datetime import datetime

import customtkinter as ctk

# ══════════════════════════════════════════════════════════════════════════════
# ЦВЕТОВАЯ ТЕМА  (вся палитра в одном месте)
# ══════════════════════════════════════════════════════════════════════════════
_C = {
    # Фоны
    "bg":          "#060A1A",   # главный фон
    "sidebar":     "#080D20",   # боковая панель
    "card":        "#0D1628",   # карточки / фреймы
    "input_bg":    "#0A1020",   # поле ввода
    "statusbar":   "#050810",   # строка состояния
    # Акценты
    "cyan":        "#00FFFF",   # основной акцент
    "cyan_dim":    "#00AACC",   # приглушённый акцент
    "green":       "#00FF88",   # успех / голос
    "green_dim":   "#00AA55",   # приглушённый зелёный
    "red":         "#FF3333",   # ошибка / опасность
    "yellow":      "#FFFF00",   # предупреждение
    "blue":        "#3399FF",   # пользователь
    "blue_dim":    "#1A3A6A",   # фон кнопки пользователя
    # Текст
    "text":        "#C0D8FF",   # основной текст
    "text_dim":    "#445566",   # второстепенный текст
    "text_muted":  "#223344",   # разделители
    # Кнопки
    "btn":         "#0D2040",   # обычная кнопка фон
    "btn_hover":   "#1A3A6A",   # hover обычной кнопки
    "btn_border":  "#1A2A4A",   # рамка кнопки
    "btn_active":  "#003355",   # активная/нажатая
    # Голос
    "mic_idle":    "#0D2A0D",   # кнопка микрофона (ожидание)
    "mic_listen":  "#3A0D0D",   # кнопка микрофона (слушает)
    # Бары прогресса
    "bar_low":     "#00AAFF",   # нагрузка < 60%
    "bar_mid":     "#FFAA00",   # нагрузка 60-85%
    "bar_high":    "#FF3333",   # нагрузка > 85%
}

# Шрифты
_F = {
    "logo":    ("Consolas", 22, "bold"),
    "head":    ("Consolas", 13, "bold"),
    "label":   ("Consolas", 11),
    "small":   ("Consolas", 10),
    "chat":    ("Consolas", 13),
    "input":   ("Consolas", 13),
    "status":  ("Consolas", 10),
    "btn":     ("Consolas", 11),
    "btn_big": ("Consolas", 12, "bold"),
}


# ══════════════════════════════════════════════════════════════════════════════
# ВСПОМОГАТЕЛЬНЫЙ ВИДЖЕТ: метрика с баром
# ══════════════════════════════════════════════════════════════════════════════
class _MetricBar(ctk.CTkFrame):
    """Строка: «CPU  [████░░░] 42%»."""

    def __init__(self, master, label: str, **kw):
        super().__init__(master, fg_color="transparent", **kw)
        self.columnconfigure(0, weight=0)
        self.columnconfigure(1, weight=1)
        self.columnconfigure(2, weight=0)

        ctk.CTkLabel(self, text=label, font=_F["small"],
                     text_color=_C["text_dim"], width=36,
                     anchor="w").grid(row=0, column=0, sticky="w")

        self._bar = ctk.CTkProgressBar(self, height=6,
                                        progress_color=_C["bar_low"],
                                        fg_color=_C["card"])
        self._bar.set(0)
        self._bar.grid(row=0, column=1, sticky="ew", padx=(4, 4))

        self._val = ctk.CTkLabel(self, text="—  ", font=_F["small"],
                                  text_color=_C["cyan"], width=38, anchor="e")
        self._val.grid(row=0, column=2, sticky="e")

    def update(self, pct: float):
        v = max(0.0, min(1.0, pct / 100.0))
        self._bar.set(v)
        color = (_C["bar_high"] if pct > 85 else
                 _C["bar_mid"]  if pct > 60 else _C["bar_low"])
        self._bar.configure(progress_color=color)
        self._val.configure(text=f"{pct:.0f}%")


# ══════════════════════════════════════════════════════════════════════════════
# ГЛАВНОЕ ОКНО
# ══════════════════════════════════════════════════════════════════════════════
class ArgosGUI(ctk.CTk):
    """Главный интерфейс ARGOS.  Публичный API не изменён:
    ArgosGUI(core, admin, flasher, location)."""

    EMPTY_CORE_RESPONSE_TEXT = "❌ Пустой ответ от ядра."
    _THINK_FRAMES = ["⠋", "⠙", "⠹", "⠸", "⠼", "⠴", "⠦", "⠧", "⠇", "⠏"]
    _HISTORY_MAX  = 100

    def __init__(self, core, admin, flasher, location: str = ""):
        super().__init__()
        self.core     = core
        self.admin    = admin
        self.flasher  = flasher
        self._location = location

        self._listening  = False
        self._processing = False
        self._think_idx  = 0
        self._cmd_hist: deque[str] = deque(maxlen=self._HISTORY_MAX)
        self._hist_pos   = -1

        # ── Глобальные настройки CTk ──────────────────────────────────────
        ctk.set_appearance_mode("dark")
        ctk.set_default_color_theme("blue")
        self.configure(fg_color=_C["bg"])

        # ── Окно ─────────────────────────────────────────────────────────
        self.title("👁️  ARGOS UNIVERSAL OS")
        self.geometry("1280x780")
        self.minsize(900, 580)
        try:
            self.iconbitmap(default="")
        except Exception:
            pass

        # ── Сетка главного окна ──────────────────────────────────────────
        self.grid_columnconfigure(0, weight=0)   # sidebar фиксирован
        self.grid_columnconfigure(1, weight=1)   # основная область
        self.grid_rowconfigure(0, weight=1)      # контент
        self.grid_rowconfigure(1, weight=0)      # строка состояния

        self._build_sidebar()
        self._build_main()
        self._build_statusbar()

        # ── Горячие клавиши ───────────────────────────────────────────────
        self.bind("<Escape>", lambda _: self.entry.focus())
        self.entry.bind("<Return>",  lambda _: self._send_text(self.entry.get()))
        self.entry.bind("<Up>",      self._hist_prev)
        self.entry.bind("<Down>",    self._hist_next)
        self.entry.bind("<Control-l>", lambda _: self._clear_chat())

        # ── Фоновые таймеры ───────────────────────────────────────────────
        self._tick_status()
        self._tick_metrics()

    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    # СТРОИТЕЛЬСТВО UI
    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

    # ── Боковая панель ───────────────────────────────────────────────────
    def _build_sidebar(self):
        self.sidebar = ctk.CTkScrollableFrame(
            self, width=248, fg_color=_C["sidebar"],
            corner_radius=0, scrollbar_button_color=_C["btn_border"],
            scrollbar_button_hover_color=_C["cyan_dim"],
        )
        self.sidebar.grid(row=0, column=0, sticky="nsew", padx=0, pady=0)

        # ── Логотип ───────────────────────────────────────────────────────
        logo_frame = ctk.CTkFrame(self.sidebar, fg_color="transparent")
        logo_frame.pack(fill="x", padx=12, pady=(16, 4))
        ctk.CTkLabel(logo_frame, text="👁️", font=("Consolas", 28)).pack(side="left")
        ctk.CTkLabel(logo_frame, text=" ARGOS", font=_F["logo"],
                     text_color=_C["cyan"]).pack(side="left")

        ctk.CTkLabel(self.sidebar,
                     text=f"v{getattr(self.core, 'VERSION', '1.3')}  ·  {self._location}",
                     font=_F["small"], text_color=_C["text_dim"],
                     wraplength=220, justify="left").pack(padx=12, pady=(0, 8))

        self._sep()

        # ── Квантовое состояние ──────────────────────────────────────────
        self.q_label = ctk.CTkLabel(
            self.sidebar, text="⚛  Состояние: —",
            font=_F["label"], text_color=_C["green"])
        self.q_label.pack(padx=12, pady=(6, 2), anchor="w")

        self._sep()

        # ── Голос ─────────────────────────────────────────────────────────
        self._section("🔊  ГОЛОС")
        self.voice_label = ctk.CTkLabel(
            self.sidebar,
            text=f"Режим: {'ВКЛ' if self.core.voice_on else 'ВЫКЛ'}",
            font=_F["small"], text_color=_C["text_dim"])
        self.voice_label.pack(padx=12, pady=(0, 4), anchor="w")

        self.voice_toggle_btn = self._btn(
            "🔇 Отключить голос" if self.core.voice_on else "🔊 Включить голос",
            self._toggle_voice_mode,
        )
        self.voice_btn = self._btn(
            "🎙  Слушай меня", self._toggle_listen,
            fg_color=_C["mic_idle"], hover_color=_C["mic_listen"], height=38,
        )

        self._sep()

        # ── Модель ИИ ─────────────────────────────────────────────────────
        self._section("🤖  МОДЕЛЬ ИИ")
        self.ai_mode_var = ctk.StringVar(
            value=self._ai_mode_to_ui(self.core.ai_mode))
        ctk.CTkOptionMenu(
            self.sidebar,
            values=["Auto", "Gemini", "GigaChat", "YandexGPT", "Ollama"],
            variable=self.ai_mode_var,
            command=self._on_ai_mode_changed,
            fg_color=_C["btn"], button_color=_C["cyan_dim"],
            button_hover_color=_C["cyan"], text_color=_C["text"],
            font=_F["btn"],
        ).pack(fill="x", padx=12, pady=(0, 4))

        self.ai_mode_label = ctk.CTkLabel(
            self.sidebar,
            text=f"Активен: {self.core.ai_mode_label()}",
            font=_F["small"], text_color=_C["cyan_dim"])
        self.ai_mode_label.pack(padx=12, pady=(0, 4), anchor="w")

        self._sep()

        # ── Метрики ───────────────────────────────────────────────────────
        self._section("📊  РЕСУРСЫ")
        self.bar_cpu  = _MetricBar(self.sidebar, "CPU")
        self.bar_cpu.pack(fill="x", padx=12, pady=2)
        self.bar_ram  = _MetricBar(self.sidebar, "RAM")
        self.bar_ram.pack(fill="x", padx=12, pady=2)
        self.bar_disk = _MetricBar(self.sidebar, "Disk")
        self.bar_disk.pack(fill="x", padx=12, pady=(2, 8))

        self._sep()

        # ── Быстрые команды ───────────────────────────────────────────────
        _quick = [
            ("СИСТЕМА",  [
                ("📊 Статус системы",     "статус системы"),
                ("🔍 Диагностика ИИ",      "диагностика ии"),
                ("🧪 Проверь драйверы",    "проверь драйверы"),
                ("🧠 Сознание статус",     "сознание статус"),
                ("📋 Список функций",      "список функций аргоса"),
            ]),
            ("СЕТЬ",  [
                ("📡 Сканировать сеть",    "сканируй сеть"),
                ("🔍 Сканируй порты",      "сканируй порты"),
                ("🌐 Геолокация",          "геолокация"),
                ("🪙 Крипто",             "крипто"),
                ("📰 AI Дайджест",         "дайджест"),
            ]),
            ("IoT / ПРОШИВКИ",  [
                ("📡 IoT статус",          "iot статус"),
                ("🏭 IoT протоколы",       "iot протоколы"),
                ("🔌 RS TTL / UART",       "rs ttl"),
                ("🧩 Шаблоны шлюзов",      "шаблоны шлюзов"),
                ("💾 Создать копию",        "репликация"),
            ]),
        ]
        for section_name, items in _quick:
            self._section(f"⚡  {section_name}")
            for label, cmd in items:
                self._btn(label, lambda c=cmd: self._send_text(c))

        # Специальные диалоговые кнопки
        self._sep()
        self._btn("📟 Статус устройства", self._prompt_device_status)
        self._btn("🛠  Создай прошивку",  self._prompt_create_firmware)
        self._btn("🗑  Очистить чат",     self._clear_chat,
                  fg_color="#2A0A0A", hover_color="#4A1A1A")

    # ── Основная область ──────────────────────────────────────────────────
    def _build_main(self):
        main = ctk.CTkFrame(self, fg_color="transparent")
        main.grid(row=0, column=1, sticky="nsew", padx=(0, 10), pady=10)
        main.grid_rowconfigure(0, weight=1)
        main.grid_rowconfigure(1, weight=0)
        main.grid_columnconfigure(0, weight=1)

        # ── Вкладки ───────────────────────────────────────────────────────
        self.tabs = ctk.CTkTabview(
            main, fg_color=_C["card"],
            segmented_button_fg_color=_C["sidebar"],
            segmented_button_selected_color=_C["blue_dim"],
            segmented_button_selected_hover_color=_C["btn_hover"],
            segmented_button_unselected_color=_C["sidebar"],
            segmented_button_unselected_hover_color=_C["btn"],
            text_color=_C["text"], text_color_disabled=_C["text_dim"],
        )
        self.tabs.grid(row=0, column=0, sticky="nsew")

        for name in ("💬 Консоль", "🧠 Память", "⚙️ Система", "📦 Сборка"):
            self.tabs.add(name)

        self._build_tab_console()
        self._build_tab_memory()
        self._build_tab_system()
        self._build_tab_deploy()

        # ── Строка ввода ──────────────────────────────────────────────────
        inp_frame = ctk.CTkFrame(main, fg_color=_C["card"],
                                  corner_radius=10)
        inp_frame.grid(row=1, column=0, sticky="ew", pady=(6, 0))
        inp_frame.grid_columnconfigure(0, weight=1)

        self.entry = ctk.CTkEntry(
            inp_frame,
            placeholder_text="Директива для Аргоса... (↑↓ — история, Enter — отправить)",
            height=44, font=_F["input"],
            fg_color=_C["input_bg"], text_color=_C["text"],
            border_color=_C["btn_border"], border_width=1,
            placeholder_text_color=_C["text_dim"],
        )
        self.entry.grid(row=0, column=0, sticky="ew",
                        padx=(10, 6), pady=8)

        self._send_btn = ctk.CTkButton(
            inp_frame, text="▶ EXECUTE", width=120, height=44,
            font=_F["btn_big"],
            fg_color=_C["btn"], hover_color=_C["btn_hover"],
            border_color=_C["cyan_dim"], border_width=1,
            text_color=_C["cyan"],
            command=lambda: self._send_text(self.entry.get()),
        )
        self._send_btn.grid(row=0, column=1, padx=(0, 6), pady=8)

        self._think_lbl = ctk.CTkLabel(
            inp_frame, text="", font=_F["label"],
            text_color=_C["yellow"], width=24,
        )
        self._think_lbl.grid(row=0, column=2, padx=(0, 8))

    # ── Вкладка: Консоль ─────────────────────────────────────────────────
    def _build_tab_console(self):
        tab = self.tabs.tab("💬 Консоль")
        tab.grid_rowconfigure(0, weight=1)
        tab.grid_columnconfigure(0, weight=1)

        self.chat = ctk.CTkTextbox(
            tab, font=_F["chat"], wrap="word",
            fg_color=_C["bg"], text_color=_C["text"],
            border_width=0, corner_radius=0,
        )
        self.chat.grid(row=0, column=0, sticky="nsew", padx=4, pady=4)
        self.chat.configure(state="disabled")

        # Цветовые теги для разных типов сообщений
        self.chat.tag_config("user",   foreground=_C["blue"])
        self.chat.tag_config("argos",  foreground=_C["cyan"])
        self.chat.tag_config("system", foreground=_C["green"])
        self.chat.tag_config("error",  foreground=_C["red"])
        self.chat.tag_config("ts",     foreground=_C["text_dim"])
        self.chat.tag_config("sep",    foreground=_C["text_muted"])

        self._append_system(
            "👁️  АРГОС ИНИЦИАЛИЗИРОВАН\n"
            "═" * 52 + "\n"
            f"  Версия: {getattr(self.core, 'VERSION', '?')}\n"
            f"  ИИ:     {self.core.ai_mode_label()}\n"
            f"  Голос:  {'ВКЛ' if self.core.voice_on else 'ВЫКЛ'}\n"
            "═" * 52 + "\n"
        )

    # ── Вкладка: Память ──────────────────────────────────────────────────
    def _build_tab_memory(self):
        tab = self.tabs.tab("🧠 Память")
        tab.grid_rowconfigure(1, weight=1)
        tab.grid_columnconfigure(0, weight=1)

        btn_row = ctk.CTkFrame(tab, fg_color="transparent")
        btn_row.grid(row=0, column=0, sticky="ew", padx=8, pady=(8, 4))

        ctk.CTkButton(
            btn_row, text="🔄 Обновить", width=120, height=30,
            font=_F["btn"], fg_color=_C["btn"], hover_color=_C["btn_hover"],
            text_color=_C["cyan"],
            command=self._refresh_memory_tab,
        ).pack(side="left", padx=(0, 6))

        ctk.CTkButton(
            btn_row, text="📋 История диалога", width=160, height=30,
            font=_F["btn"], fg_color=_C["btn"], hover_color=_C["btn_hover"],
            text_color=_C["cyan"],
            command=self._show_dialogue_history,
        ).pack(side="left")

        self.mem_box = ctk.CTkTextbox(
            tab, font=("Consolas", 12), wrap="word",
            fg_color=_C["bg"], text_color=_C["text"], border_width=0,
        )
        self.mem_box.grid(row=1, column=0, sticky="nsew", padx=4, pady=(0, 4))
        self.mem_box.insert("end", "Нажмите «Обновить» для загрузки памяти.\n")
        self.mem_box.configure(state="disabled")

    # ── Вкладка: Система ─────────────────────────────────────────────────
    def _build_tab_system(self):
        tab = self.tabs.tab("⚙️ Система")
        tab.grid_rowconfigure(1, weight=1)
        tab.grid_columnconfigure(0, weight=1)

        btn_row = ctk.CTkFrame(tab, fg_color="transparent")
        btn_row.grid(row=0, column=0, sticky="ew", padx=8, pady=(8, 4))

        ctk.CTkButton(
            btn_row, text="🔄 Обновить", width=120, height=30,
            font=_F["btn"], fg_color=_C["btn"], hover_color=_C["btn_hover"],
            text_color=_C["cyan"],
            command=self._refresh_system_tab,
        ).pack(side="left", padx=(0, 6))

        ctk.CTkButton(
            btn_row, text="🛡 Диагностика", width=140, height=30,
            font=_F["btn"], fg_color=_C["btn"], hover_color=_C["btn_hover"],
            text_color=_C["cyan"],
            command=lambda: self._send_text("диагностика ии"),
        ).pack(side="left")

        self.sys_box = ctk.CTkTextbox(
            tab, font=("Consolas", 12), wrap="word",
            fg_color=_C["bg"], text_color=_C["text"], border_width=0,
        )
        self.sys_box.grid(row=1, column=0, sticky="nsew", padx=4, pady=(0, 4))
        self.sys_box.insert("end", "Нажмите «Обновить» для загрузки состояния.\n")
        self.sys_box.configure(state="disabled")

    # ── Вкладка: Сборка / Deploy ─────────────────────────────────────────
    def _build_tab_deploy(self):
        tab = self.tabs.tab("📦 Сборка")
        tab.grid_rowconfigure(1, weight=1)
        tab.grid_columnconfigure(0, weight=1)

        # ── Заголовок ─────────────────────────────────────────────────────
        hdr = ctk.CTkFrame(tab, fg_color="transparent")
        hdr.grid(row=0, column=0, sticky="ew", padx=8, pady=(10, 4))

        ctk.CTkLabel(
            hdr, text="⚙️  Сборка и развёртывание ARGOS",
            font=_F["head"], text_color=_C["cyan"],
        ).pack(side="left", padx=4)

        # ── Прокручиваемый контент ────────────────────────────────────────
        scroll = ctk.CTkScrollableFrame(
            tab, fg_color=_C["bg"], corner_radius=6,
        )
        scroll.grid(row=1, column=0, sticky="nsew", padx=4, pady=(0, 4))
        scroll.grid_columnconfigure(0, weight=1)

        def _card(parent, title: str, color: str = None) -> ctk.CTkFrame:
            c = ctk.CTkFrame(parent, fg_color=_C["card"], corner_radius=8,
                             border_width=1, border_color=color or _C["btn_border"])
            c.pack(fill="x", padx=6, pady=5)
            ctk.CTkLabel(c, text=title, font=_F["head"],
                         text_color=color or _C["cyan"]).pack(
                anchor="w", padx=12, pady=(10, 4))
            return c

        def _row(parent) -> ctk.CTkFrame:
            f = ctk.CTkFrame(parent, fg_color="transparent")
            f.pack(fill="x", padx=8, pady=(0, 8))
            return f

        def _action_btn(parent, text: str, cmd, color: str = None) -> ctk.CTkButton:
            b = ctk.CTkButton(
                parent, text=text, height=32, font=_F["btn"],
                fg_color=_C["btn"], hover_color=_C["btn_hover"],
                border_color=color or _C["btn_border"], border_width=1,
                text_color=color or _C["cyan"],
                command=cmd,
            )
            b.pack(side="left", padx=(0, 6))
            return b

        # ── Docker ────────────────────────────────────────────────────────
        card = _card(scroll, "🐳  Docker", _C["cyan"])
        _info = ctk.CTkLabel(card, text="Запуск headless-сервера ARGOS в контейнере",
                              font=_F["small"], text_color=_C["text_dim"])
        _info.pack(anchor="w", padx=12, pady=(0, 4))
        row = _row(card)
        _action_btn(row, "▶ docker-compose up",
                    lambda: self._run_build_cmd("docker-compose up -d"),
                    _C["cyan"])
        _action_btn(row, "⏹ docker-compose down",
                    lambda: self._run_build_cmd("docker-compose down"),
                    _C["red"])
        _action_btn(row, "🔨 docker build",
                    lambda: self._run_build_cmd("docker build -t argos-universal:latest ."),
                    _C["cyan_dim"])

        # ── EXE (Windows/Linux) ───────────────────────────────────────────
        card2 = _card(scroll, "🖥️  Сборка .exe / binary", _C["green"])
        ctk.CTkLabel(card2, text="PyInstaller → portable single-file executable",
                     font=_F["small"], text_color=_C["text_dim"]).pack(
            anchor="w", padx=12, pady=(0, 4))
        row2 = _row(card2)
        _action_btn(row2, "▶ build_exe.py",
                    lambda: self._run_build_cmd("python build_exe.py"),
                    _C["green"])
        _action_btn(row2, "▶ build_exe.py --onedir",
                    lambda: self._run_build_cmd("python build_exe.py --onedir"),
                    _C["green_dim"])
        _action_btn(row2, "▶ pyinstaller argos.spec",
                    lambda: self._run_build_cmd("pyinstaller argos.spec"),
                    _C["green_dim"])

        # ── APK (Android) ─────────────────────────────────────────────────
        card3 = _card(scroll, "📱  Android APK (Buildozer)", _C["yellow"])
        ctk.CTkLabel(card3,
                     text="Требуется: buildozer, openjdk-17, Android SDK/NDK",
                     font=_F["small"], text_color=_C["text_dim"]).pack(
            anchor="w", padx=12, pady=(0, 4))
        row3 = _row(card3)
        _action_btn(row3, "▶ buildozer debug",
                    lambda: self._run_build_cmd("buildozer android debug"),
                    _C["yellow"])
        _action_btn(row3, "▶ buildozer release",
                    lambda: self._run_build_cmd("buildozer android release"),
                    _C["yellow"])
        _action_btn(row3, "🔄 buildozer clean",
                    lambda: self._run_build_cmd("buildozer android clean"),
                    _C["text_dim"])

        # ── Google Colab ──────────────────────────────────────────────────
        card4 = _card(scroll, "☁️  Google Colab", _C["cyan_dim"])
        ctk.CTkLabel(card4,
                     text="Запуск ARGOS в браузере — без локальной установки",
                     font=_F["small"], text_color=_C["text_dim"]).pack(
            anchor="w", padx=12, pady=(0, 4))
        row4 = _row(card4)
        _action_btn(row4, "📋 Скопировать ссылку",
                    self._copy_colab_url, _C["cyan_dim"])
        _action_btn(row4, "📂 Открыть argos_colab.ipynb",
                    lambda: self._run_build_cmd("start argos_colab.ipynb"
                                                if platform.system() == "Windows"
                                                else "xdg-open argos_colab.ipynb"),
                    _C["cyan_dim"])

        # ── Лог сборки ────────────────────────────────────────────────────
        ctk.CTkLabel(scroll, text="📋  Лог сборки",
                     font=_F["head"], text_color=_C["text_dim"]).pack(
            anchor="w", padx=12, pady=(8, 2))
        self._deploy_log = ctk.CTkTextbox(
            scroll, height=140, font=("Consolas", 11),
            fg_color=_C["input_bg"], text_color=_C["green"],
            border_width=0, corner_radius=6,
        )
        self._deploy_log.pack(fill="x", padx=6, pady=(0, 8))
        self._deploy_log.insert("end", "Лог сборки появится здесь...\n")
        self._deploy_log.configure(state="disabled")

    def _run_build_cmd(self, cmd: str):
        """Запускает shell-команду сборки и стримит вывод в лог вкладки."""
        import subprocess, shlex

        def _run():
            self._deploy_log_append(f"\n$ {cmd}\n")
            try:
                use_shell = platform.system() == "Windows"
                proc = subprocess.Popen(
                    cmd if use_shell else shlex.split(cmd),
                    shell=use_shell,
                    stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                    text=True, bufsize=1,
                )
                for line in proc.stdout:
                    self._deploy_log_append(line)
                proc.wait()
                status = "✅ Готово" if proc.returncode == 0 else f"❌ Код: {proc.returncode}"
                self._deploy_log_append(f"{status}\n")
            except FileNotFoundError as exc:
                self._deploy_log_append(f"❌ Команда не найдена: {exc}\n")
            except Exception as exc:
                self._deploy_log_append(f"❌ Ошибка: {exc}\n")

        threading.Thread(target=_run, daemon=True).start()
        self.tabs.set("📦 Сборка")

    def _deploy_log_append(self, text: str):
        self.after(0, self._deploy_log_append_ui, text)

    def _deploy_log_append_ui(self, text: str):
        self._deploy_log.configure(state="normal")
        self._deploy_log.insert("end", text)
        self._deploy_log.see("end")
        self._deploy_log.configure(state="disabled")

    def _copy_colab_url(self):
        url = ("https://colab.research.google.com/github/"
               "labuaqlysnecy/Argoss/blob/main/argos_colab.ipynb")
        try:
            self.clipboard_clear()
            self.clipboard_append(url)
            self._deploy_log_append(f"📋 Ссылка скопирована: {url}\n")
        except Exception:
            self._deploy_log_append(f"Ссылка: {url}\n")

    # ── Строка состояния ──────────────────────────────────────────────────
    def _build_statusbar(self):
        bar = ctk.CTkFrame(self, height=24, fg_color=_C["statusbar"],
                            corner_radius=0)
        bar.grid(row=1, column=0, columnspan=2, sticky="ew")

        self._sb_state = ctk.CTkLabel(
            bar, text="⚛ —", font=_F["status"],
            text_color=_C["green_dim"])
        self._sb_state.pack(side="left", padx=(12, 0))

        _sep = ctk.CTkLabel(bar, text="│", font=_F["status"],
                             text_color=_C["text_muted"])
        _sep.pack(side="left", padx=8)

        self._sb_ai = ctk.CTkLabel(
            bar, text="🤖 —", font=_F["status"],
            text_color=_C["cyan_dim"])
        self._sb_ai.pack(side="left")

        self._sb_time = ctk.CTkLabel(
            bar, text="", font=_F["status"],
            text_color=_C["text_dim"])
        self._sb_time.pack(side="right", padx=12)

        self._sb_voice = ctk.CTkLabel(
            bar, text="🔊 —", font=_F["status"],
            text_color=_C["text_dim"])
        self._sb_voice.pack(side="right", padx=8)

    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    # ВСПОМОГАТЕЛЬНЫЕ СТРОИТЕЛЬНЫЕ МЕТОДЫ
    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

    def _sep(self):
        ctk.CTkLabel(self.sidebar, text="",
                     fg_color=_C["text_muted"], height=1).pack(
            fill="x", padx=12, pady=6)

    def _section(self, title: str):
        ctk.CTkLabel(self.sidebar, text=title, font=_F["small"],
                     text_color=_C["text_dim"]).pack(
            padx=12, pady=(8, 2), anchor="w")

    def _btn(self, text: str, cmd,
             fg_color=None, hover_color=None, height: int = 30) -> ctk.CTkButton:
        b = ctk.CTkButton(
            self.sidebar, text=text, height=height,
            font=_F["btn"], anchor="w",
            fg_color=fg_color or _C["btn"],
            hover_color=hover_color or _C["btn_hover"],
            border_color=_C["btn_border"], border_width=1,
            text_color=_C["text"],
            command=cmd,
        )
        b.pack(fill="x", padx=12, pady=2)
        return b

    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    # ЛОГИКА ОТПРАВКИ И ОБРАБОТКИ
    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

    def _send_text(self, text: str):
        if not text or not text.strip() or self._processing:
            return
        text = text.strip()
        self.entry.delete(0, "end")
        self._cmd_hist.appendleft(text)
        self._hist_pos = -1

        state = self.core.quantum.generate_state()["name"]
        ts = datetime.now().strftime("%H:%M:%S")
        self._append_tagged(f"[{ts}] ", "ts")
        self._append_tagged(f"[{state[:3].upper()}] ВЫ: {text}\n", "user")

        self._set_processing(True)
        threading.Thread(target=self._process, args=(text,), daemon=True).start()

    def _process(self, text: str):
        try:
            res = self.core.process_logic(text, self.admin, self.flasher)
        except Exception as e:
            res = {"state": "ERROR",
                   "answer": f"❌ Ошибка выполнения команды: {e}"}
        self.after(0, self._on_response, res)

    def _on_response(self, res: dict):
        self._set_processing(False)
        payload = res if res is not None else {}
        state = payload.get("state", "ERROR")
        answer = payload.get("answer", self.EMPTY_CORE_RESPONSE_TEXT)

        ts = datetime.now().strftime("%H:%M:%S")
        tag = "error" if state == "ERROR" else "argos"
        self._append_tagged(f"[{ts}] ", "ts")
        self._append_tagged(f"👁  АРГОС [{state}]:\n{answer}\n", tag)
        self._append_tagged("─" * 60 + "\n", "sep")

        self.q_label.configure(text=f"⚛  Состояние: {state}")
        self.ai_mode_label.configure(
            text=f"Активен: {self.core.ai_mode_label()}")
        voice_txt = "ВКЛ" if self.core.voice_on else "ВЫКЛ"
        self.voice_label.configure(text=f"Режим: {voice_txt}")
        self.voice_toggle_btn.configure(
            text=("🔇 Отключить голос" if self.core.voice_on
                  else "🔊 Включить голос"))
        self._update_statusbar()

    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    # ГОЛОС
    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

    def _toggle_listen(self):
        if self._listening or self._processing:
            return
        self._listening = True
        self.voice_btn.configure(text="🔴 Слушаю...",
                                  fg_color=_C["mic_listen"])
        self._append_system("🎙  Слушаю... говорите команду.\n")
        threading.Thread(target=self._listen_loop, daemon=True).start()

    def _listen_loop(self):
        text = self.core.listen()
        self.after(0, self._after_listen, text)

    def _after_listen(self, text: str):
        self._listening = False
        self.voice_btn.configure(text="🎙  Слушай меня",
                                  fg_color=_C["mic_idle"])
        if text:
            self._send_text(text)
        else:
            self._append_tagged("👂 Не распознано. Попробуй снова.\n", "error")

    def _toggle_voice_mode(self):
        self.core.voice_on = not self.core.voice_on
        v = "ВКЛ" if self.core.voice_on else "ВЫКЛ"
        self.voice_label.configure(text=f"Режим: {v}")
        self.voice_toggle_btn.configure(
            text=("🔇 Отключить голос" if self.core.voice_on
                  else "🔊 Включить голос"))
        self._append_system(f"🔈 Голосовой режим: {v}\n")

    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    # AI-РЕЖИМ
    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

    _AI_UI_MAP = {
        "gemini": "Gemini", "gigachat": "GigaChat",
        "yandexgpt": "YandexGPT", "ollama": "Ollama",
    }
    _UI_AI_MAP = {v: k for k, v in _AI_UI_MAP.items()}

    def _ai_mode_to_ui(self, mode: str) -> str:
        return self._AI_UI_MAP.get((mode or "auto").strip().lower(), "Auto")

    def _ui_to_ai_mode(self, mode: str) -> str:
        return self._UI_AI_MAP.get(mode, "auto")

    def _on_ai_mode_changed(self, selected: str):
        mode = self._ui_to_ai_mode(selected)
        msg  = self.core.set_ai_mode(mode)
        self.ai_mode_label.configure(
            text=f"Активен: {self.core.ai_mode_label()}")
        self._append_system(f"{msg}\n")

    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    # ДИАЛОГОВЫЕ КНОПКИ
    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

    def _prompt_device_status(self):
        dlg = ctk.CTkInputDialog(text="ID устройства:",
                                  title="Статус устройства")
        dev_id = (dlg.get_input() or "").strip()
        if dev_id:
            self._send_text(f"статус устройства {dev_id}")

    def _prompt_create_firmware(self):
        dlg = ctk.CTkInputDialog(
            text="Формат: id шаблон [порт]\nПример: gw1 esp32_lora /dev/ttyUSB0",
            title="Создать прошивку")
        args = (dlg.get_input() or "").strip()
        if args:
            self._send_text(f"создай прошивку {args}")

    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    # ВКЛАДКИ: ПАМЯТЬ / СИСТЕМА
    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

    def _refresh_memory_tab(self):
        self.mem_box.configure(state="normal")
        self.mem_box.delete("1.0", "end")
        if self.core.memory:
            txt = self.core.memory.format_memory()
        else:
            txt = "Модуль памяти не активирован."
        self.mem_box.insert("end", txt)
        self.mem_box.configure(state="disabled")

    def _show_dialogue_history(self):
        self.mem_box.configure(state="normal")
        self.mem_box.delete("1.0", "end")
        try:
            if self.core.db:
                hist = self.core.db.format_history(20)
            elif self.core.memory:
                hist = self.core.memory.format_memory()
            else:
                hist = "База данных не подключена."
        except Exception as e:
            hist = f"Ошибка чтения истории: {e}"
        self.mem_box.insert("end", hist)
        self.mem_box.configure(state="disabled")

    def _refresh_system_tab(self):
        self.sys_box.configure(state="normal")
        self.sys_box.delete("1.0", "end")
        lines = [
            f"  Версия ARGOS:  {getattr(self.core, 'VERSION', '?')}",
            f"  Режим ИИ:      {self.core.ai_mode_label()}",
            f"  Квантовое:     {self.core.quantum.generate_state()['name']}",
            f"  Голос:         {'ВКЛ' if self.core.voice_on else 'ВЫКЛ'}",
            "",
        ]
        try:
            import psutil
            lines += [
                f"  CPU:           {psutil.cpu_percent(interval=0.2):.1f}%",
                f"  RAM:           {psutil.virtual_memory().percent:.1f}%",
                f"  Disk:          {psutil.disk_usage('/').percent:.1f}%",
            ]
            bat = psutil.sensors_battery()
            if bat:
                plug = "🔌" if bat.power_plugged else "🔋"
                lines.append(f"  Батарея:       {plug} {bat.percent:.0f}%")
        except ImportError:
            lines.append("  psutil не установлен.")
        except Exception as e:
            lines.append(f"  Ошибка метрик: {e}")
        self.sys_box.insert("end", "\n".join(lines) + "\n")
        self.sys_box.configure(state="disabled")

    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    # ИСТОРИЯ КОМАНД (↑ / ↓)
    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

    def _hist_prev(self, _event=None):
        if not self._cmd_hist:
            return
        self._hist_pos = min(self._hist_pos + 1, len(self._cmd_hist) - 1)
        self._set_entry(list(self._cmd_hist)[self._hist_pos])

    def _hist_next(self, _event=None):
        if self._hist_pos <= 0:
            self._hist_pos = -1
            self._set_entry("")
            return
        self._hist_pos -= 1
        self._set_entry(list(self._cmd_hist)[self._hist_pos])

    def _set_entry(self, text: str):
        self.entry.delete(0, "end")
        self.entry.insert(0, text)

    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    # АНИМАЦИЯ "ДУМАЕТ..."
    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

    def _set_processing(self, on: bool):
        self._processing = on
        if on:
            self._send_btn.configure(state="disabled",
                                      text_color=_C["text_dim"])
            self._animate_think()
        else:
            self._think_lbl.configure(text="")
            self._send_btn.configure(state="normal",
                                      text_color=_C["cyan"])

    def _animate_think(self):
        if not self._processing:
            return
        frame = self._THINK_FRAMES[self._think_idx % len(self._THINK_FRAMES)]
        self._think_lbl.configure(text=frame)
        self._think_idx += 1
        self.after(80, self._animate_think)

    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    # ТИКИ (фоновые обновления)
    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

    def _tick_status(self):
        self._update_statusbar()
        self.after(2000, self._tick_status)

    def _tick_metrics(self):
        self._update_metrics()
        self.after(3000, self._tick_metrics)

    def _update_statusbar(self):
        state = self.core.quantum.generate_state()["name"]
        self._sb_state.configure(text=f"⚛  {state}")
        self._sb_ai.configure(
            text=f"🤖  {self.core.ai_mode_label()}")
        v = "ВКЛ" if self.core.voice_on else "ВЫКЛ"
        self._sb_voice.configure(text=f"🔊 {v}")
        self._sb_time.configure(
            text=datetime.now().strftime("%H:%M:%S"))

    def _update_metrics(self):
        try:
            import psutil
            self.bar_cpu.update(psutil.cpu_percent(interval=0.1))
            self.bar_ram.update(psutil.virtual_memory().percent)
            self.bar_disk.update(psutil.disk_usage("/").percent)
        except Exception:
            pass

    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    # ВЫВОД В ЧАТ
    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

    def _append_tagged(self, text: str, tag: str = ""):
        self.chat.configure(state="normal")
        if tag:
            self.chat.insert("end", text, tag)
        else:
            self.chat.insert("end", text)
        self.chat.see("end")
        self.chat.configure(state="disabled")

    def _append_system(self, text: str):
        self._append_tagged(text, "system")

    def _clear_chat(self):
        self.chat.configure(state="normal")
        self.chat.delete("1.0", "end")
        self.chat.configure(state="disabled")
        self._append_system("🗑  Чат очищен.\n")

    # ── Обратная совместимость с внешним кодом ────────────────────────────
    def _append(self, text: str, color: str = "#ffffff"):
        """Устаревший метод — оставлен для совместимости."""
        self._append_tagged(text)

