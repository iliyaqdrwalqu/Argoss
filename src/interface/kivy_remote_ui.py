# ======================================================
# ARGOS v1.4.0 — Android Remote Control UI (Kivy)
# kivy_remote_ui.py — Full remote control client for ARGOS API
#
# Tabs:
#   ① Settings  — Server URL + Token (persisted via JSONStore)
#   ② Dashboard — /api/health polling
#   ③ Events    — /api/events polling
#   ④ Console   — /api/command execution
#
# Network calls run off the UI thread via threading.
# ======================================================
import threading
import time

try:
    import requests as _req_lib
    REQUESTS_OK = True
except ImportError:
    REQUESTS_OK = False

try:
    from kivy.app import App
    from kivy.uix.boxlayout import BoxLayout
    from kivy.uix.tabbedpanel import TabbedPanel, TabbedPanelItem
    from kivy.uix.label import Label
    from kivy.uix.textinput import TextInput
    from kivy.uix.button import Button
    from kivy.uix.scrollview import ScrollView
    from kivy.uix.gridlayout import GridLayout
    from kivy.clock import Clock
    from kivy.storage.jsonstore import JsonStore
    KIVY_OK = True
except ImportError:
    KIVY_OK = False


# ── Цветовая схема ────────────────────────────────────────────────────────────
_BG   = (0.04, 0.05, 0.10, 1)
_CARD = (0.08, 0.11, 0.21, 1)
_CYAN = (0, 1, 0.8, 1)
_GREEN = (0, 1, 0.4, 1)
_RED  = (1, 0.3, 0.3, 1)
_GRAY = (0.5, 0.6, 0.7, 1)

_DEFAULT_URL   = "http://localhost:8080"
_POLL_INTERVAL = 5  # seconds


def _do_request(method: str, url: str, token: str, **kwargs):
    """Синхронный HTTP-запрос с Bearer-токеном. Возвращает (dict|None, error_str|None)."""
    if not REQUESTS_OK:
        return None, "requests not installed"
    headers = {}
    if token:
        headers["Authorization"] = f"Bearer {token}"
    try:
        resp = _req_lib.request(method, url, headers=headers, timeout=8, **kwargs)
        try:
            return resp.json(), None
        except Exception:
            return {"_text": resp.text}, None
    except Exception as exc:
        return None, str(exc)


if KIVY_OK:
    # ─────────────────────────────────────────────────────────────────────────
    # Settings screen widget
    # ─────────────────────────────────────────────────────────────────────────
    class SettingsPanel(BoxLayout):
        def __init__(self, store: "JsonStore", **kwargs):
            super().__init__(orientation="vertical", padding=16, spacing=10, **kwargs)
            self._store = store

            saved_url   = store.get("cfg", {}).get("url",   _DEFAULT_URL)   if store.exists("cfg") else _DEFAULT_URL
            saved_token = store.get("cfg", {}).get("token", "")             if store.exists("cfg") else ""

            self.add_widget(Label(text="[b]Настройки подключения[/b]",
                                  markup=True, color=_CYAN,
                                  size_hint_y=None, height=36))

            self.add_widget(Label(text="Server URL:", color=_GRAY,
                                  size_hint_y=None, height=28, halign="left",
                                  text_size=(None, None)))
            self.url_input = TextInput(text=saved_url, multiline=False,
                                       size_hint_y=None, height=40,
                                       background_color=_CARD)
            self.add_widget(self.url_input)

            self.add_widget(Label(text="Bearer Token (ARGOS_REMOTE_TOKEN):", color=_GRAY,
                                  size_hint_y=None, height=28, halign="left",
                                  text_size=(None, None)))
            self.token_input = TextInput(text=saved_token, multiline=False,
                                          password=True,
                                          size_hint_y=None, height=40,
                                          background_color=_CARD)
            self.add_widget(self.token_input)

            btn = Button(text="💾 Сохранить", size_hint_y=None, height=44,
                         background_color=(0.1, 0.4, 0.8, 1))
            btn.bind(on_press=self._save)
            self.add_widget(btn)

            self._status = Label(text="", color=_GREEN, size_hint_y=None, height=28)
            self.add_widget(self._status)

            # Spacer
            self.add_widget(BoxLayout())

        def _save(self, *_):
            url   = self.url_input.text.strip().rstrip("/")
            token = self.token_input.text.strip()
            self._store.put("cfg", url=url, token=token)
            self._status.text = "✅ Сохранено"
            Clock.schedule_once(lambda *_: setattr(self._status, "text", ""), 2)

        @property
        def server_url(self) -> str:
            return self.url_input.text.strip().rstrip("/")

        @property
        def token(self) -> str:
            return self.token_input.text.strip()

    # ─────────────────────────────────────────────────────────────────────────
    # Dashboard (health) panel
    # ─────────────────────────────────────────────────────────────────────────
    class DashboardPanel(BoxLayout):
        def __init__(self, settings: SettingsPanel, **kwargs):
            super().__init__(orientation="vertical", padding=16, spacing=10, **kwargs)
            self._settings = settings
            self._polling  = False
            self._poll_ev  = None

            self.add_widget(Label(text="[b]Dashboard[/b]", markup=True,
                                  color=_CYAN, size_hint_y=None, height=36))

            self._info = Label(text="Нажмите «Обновить» для проверки API.",
                               color=_GRAY, halign="left", valign="top",
                               text_size=(None, None))
            self.add_widget(self._info)

            row = BoxLayout(size_hint_y=None, height=44, spacing=8)
            btn_refresh = Button(text="🔄 Обновить", background_color=(0.1, 0.4, 0.8, 1))
            btn_refresh.bind(on_press=lambda *_: self._fetch())
            btn_poll = Button(text="▶ Авто-опрос", background_color=(0.1, 0.5, 0.3, 1))
            btn_poll.bind(on_press=self._toggle_poll)
            self._btn_poll = btn_poll
            row.add_widget(btn_refresh)
            row.add_widget(btn_poll)
            self.add_widget(row)
            self.add_widget(BoxLayout())

        def _toggle_poll(self, *_):
            self._polling = not self._polling
            if self._polling:
                self._btn_poll.text = "⏹ Стоп"
                self._poll_ev = Clock.schedule_interval(
                    lambda *_: self._fetch(), _POLL_INTERVAL
                )
                self._fetch()
            else:
                self._btn_poll.text = "▶ Авто-опрос"
                if self._poll_ev:
                    self._poll_ev.cancel()
                    self._poll_ev = None

        def _fetch(self):
            url   = self._settings.server_url
            token = self._settings.token
            if not url:
                self._set_info("⚠️ Server URL не задан. Заполните Настройки.", _RED)
                return
            threading.Thread(target=self._do_fetch, args=(url, token), daemon=True).start()

        def _do_fetch(self, url: str, token: str):
            data, err = _do_request("GET", f"{url}/api/health", token)
            if err:
                Clock.schedule_once(
                    lambda *_: self._set_info(f"❌ Ошибка: {err}", _RED)
                )
                return
            status  = data.get("status", "?")
            version = data.get("version", "?")
            uptime  = data.get("uptime_seconds", "?")
            text    = (
                f"✅ ARGOS API\n"
                f"   Статус:  {status}\n"
                f"   Версия:  {version}\n"
                f"   Uptime:  {uptime}s\n"
                f"   URL:     {url}"
            )
            Clock.schedule_once(lambda *_: self._set_info(text, _GREEN))

        def _set_info(self, text: str, color):
            self._info.color = color
            self._info.text  = text

    # ─────────────────────────────────────────────────────────────────────────
    # Events feed panel
    # ─────────────────────────────────────────────────────────────────────────
    class EventsPanel(BoxLayout):
        def __init__(self, settings: SettingsPanel, **kwargs):
            super().__init__(orientation="vertical", padding=16, spacing=8, **kwargs)
            self._settings = settings
            self._polling  = False
            self._poll_ev  = None

            self.add_widget(Label(text="[b]События[/b]", markup=True,
                                  color=_CYAN, size_hint_y=None, height=36))

            sv = ScrollView()
            self._log = Label(text="Нет данных", color=_GREEN, halign="left",
                              valign="top", size_hint_y=None)
            self._log.bind(texture_size=lambda *_: setattr(
                self._log, "height", max(self._log.texture_size[1], 100)))
            sv.add_widget(self._log)
            self.add_widget(sv)

            row = BoxLayout(size_hint_y=None, height=44, spacing=8)
            btn_fetch = Button(text="🔄 Обновить", background_color=(0.1, 0.4, 0.8, 1))
            btn_fetch.bind(on_press=lambda *_: self._fetch())
            btn_poll = Button(text="▶ Авто-опрос", background_color=(0.1, 0.5, 0.3, 1))
            btn_poll.bind(on_press=self._toggle_poll)
            self._btn_poll = btn_poll
            row.add_widget(btn_fetch)
            row.add_widget(btn_poll)
            self.add_widget(row)

        def _toggle_poll(self, *_):
            self._polling = not self._polling
            if self._polling:
                self._btn_poll.text = "⏹ Стоп"
                self._poll_ev = Clock.schedule_interval(
                    lambda *_: self._fetch(), _POLL_INTERVAL
                )
                self._fetch()
            else:
                self._btn_poll.text = "▶ Авто-опрос"
                if self._poll_ev:
                    self._poll_ev.cancel()
                    self._poll_ev = None

        def _fetch(self):
            url   = self._settings.server_url
            token = self._settings.token
            if not url:
                Clock.schedule_once(lambda *_: setattr(
                    self._log, "text", "⚠️ Server URL не задан."))
                return
            threading.Thread(target=self._do_fetch, args=(url, token), daemon=True).start()

        def _do_fetch(self, url: str, token: str):
            data, err = _do_request("GET", f"{url}/api/events?limit=30", token)
            if err:
                Clock.schedule_once(
                    lambda *_: setattr(self._log, "text", f"❌ {err}")
                )
                return
            events = data.get("events", [])
            if not events:
                lines = "📭 Нет событий."
            else:
                lines_list = []
                for ev in reversed(events):
                    ts_str = time.strftime("%H:%M:%S", time.localtime(ev.get("ts", 0)))
                    ev_type = ev.get("type", "?")
                    src     = ev.get("source", "?")
                    payload = str(ev.get("payload", ""))[:60]
                    lines_list.append(f"[{ts_str}] {ev_type} ← {src}  {payload}")
                lines = "\n".join(lines_list)
            Clock.schedule_once(lambda *_: setattr(self._log, "text", lines))

    # ─────────────────────────────────────────────────────────────────────────
    # Command console panel
    # ─────────────────────────────────────────────────────────────────────────
    class ConsolePanel(BoxLayout):
        def __init__(self, settings: SettingsPanel, **kwargs):
            super().__init__(orientation="vertical", padding=16, spacing=8, **kwargs)
            self._settings = settings
            self._history  = []

            self.add_widget(Label(text="[b]Консоль команд[/b]", markup=True,
                                  color=_CYAN, size_hint_y=None, height=36))

            sv = ScrollView()
            self._output = Label(
                text="> ARGOS Remote Console ready.\n> Введите команду и нажмите «Выполнить».",
                color=_GREEN, halign="left", valign="top", size_hint_y=None,
            )
            self._output.bind(texture_size=lambda *_: setattr(
                self._output, "height", max(self._output.texture_size[1], 200)))
            sv.add_widget(self._output)
            self.add_widget(sv)

            inp_row = BoxLayout(size_hint_y=None, height=44, spacing=8)
            self._cmd_input = TextInput(
                hint_text="Введите команду...", multiline=False,
                background_color=_CARD, size_hint_x=0.75,
            )
            self._cmd_input.bind(on_text_validate=self._send)
            btn = Button(text="▶ Выполнить", size_hint_x=0.25,
                         background_color=(0.1, 0.4, 0.8, 1))
            btn.bind(on_press=self._send)
            inp_row.add_widget(self._cmd_input)
            inp_row.add_widget(btn)
            self.add_widget(inp_row)

        def _send(self, *_):
            cmd = self._cmd_input.text.strip()
            if not cmd:
                return
            url   = self._settings.server_url
            token = self._settings.token
            if not url:
                self._append("⚠️ Server URL не задан. Заполните Настройки.", error=True)
                return
            if not token:
                self._append("⚠️ Token не задан. Заполните Настройки.", error=True)
                return
            self._cmd_input.text = ""
            self._append(f"\n> {cmd}")
            self._history.append(cmd)
            threading.Thread(
                target=self._do_send, args=(url, token, cmd), daemon=True
            ).start()

        def _do_send(self, url: str, token: str, cmd: str):
            data, err = _do_request(
                "POST", f"{url}/api/command", token,
                json={"cmd": cmd},
            )
            if err:
                Clock.schedule_once(
                    lambda *_: self._append(f"❌ {err}", error=True)
                )
                return
            answer = data.get("answer", str(data)) if data else "—"
            Clock.schedule_once(lambda *_: self._append(f"  {answer}"))

        def _append(self, text: str, error: bool = False):
            self._output.color = _RED if error else _GREEN
            self._output.text += f"\n{text}"

    # ─────────────────────────────────────────────────────────────────────────
    # Main App
    # ─────────────────────────────────────────────────────────────────────────
    class ArgosRemoteApp(App):
        """ARGOS Remote Control — Android APK клиент для управления ARGOS по API."""

        def build(self):
            from kivy.core.window import Window
            Window.clearcolor = _BG

            store = JsonStore("argos_remote.json")

            root = BoxLayout(orientation="vertical")

            tp = TabbedPanel(do_default_tab=False)

            # 1. Settings
            tab_settings = TabbedPanelItem(text="⚙️ Настройки")
            self._settings = SettingsPanel(store)
            tab_settings.add_widget(self._settings)
            tp.add_widget(tab_settings)

            # 2. Dashboard
            tab_dash = TabbedPanelItem(text="📊 Dashboard")
            tab_dash.add_widget(DashboardPanel(self._settings))
            tp.add_widget(tab_dash)

            # 3. Events
            tab_events = TabbedPanelItem(text="📡 События")
            tab_events.add_widget(EventsPanel(self._settings))
            tp.add_widget(tab_events)

            # 4. Console
            tab_console = TabbedPanelItem(text="🖥 Консоль")
            tab_console.add_widget(ConsolePanel(self._settings))
            tp.add_widget(tab_console)

            root.add_widget(tp)
            return root

else:
    # ── Заглушка для не-Android окружений ────────────────────────────────────
    class ArgosRemoteApp:
        """Stub when Kivy is not installed."""

        def run(self):
            print("⚠️  kivy_remote_ui: Kivy не установлен. pip install kivy")
