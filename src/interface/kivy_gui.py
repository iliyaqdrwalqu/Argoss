"""
kivy_gui.py — ARGOS v1.3 Kivy UI (Smooth Glass / Sovereign Emerald)
Запуск: python main.py --mobile
"""
try:
    from kivy.app import App
    from kivy.uix.floatlayout import FloatLayout
    from kivy.uix.boxlayout import BoxLayout
    from kivy.uix.label import Label
    from kivy.uix.button import Button
    from kivy.uix.textinput import TextInput
    from kivy.uix.scrollview import ScrollView
    from kivy.uix.gridlayout import GridLayout
    from kivy.lang import Builder
    from kivy.clock import Clock
    from kivy.graphics import Color, Rectangle
    from kivy.core.window import Window
    KIVY_OK = True
except ImportError:
    KIVY_OK = False

if KIVY_OK:
    Builder.load_string('''
<ArgosRoot>:
    canvas.before:
        Color:
            rgba: 0, 0.02, 0.04, 1
        Rectangle:
            size: self.size
            pos: self.pos

    orientation: "vertical"
    padding: "12dp"
    spacing: "8dp"

    # Заголовок
    Label:
        text: "🔱  ARGOS SOVEREIGN v1.33"
        size_hint_y: None
        height: "48dp"
        font_size: "20sp"
        bold: True
        color: 0, 1, 0.4, 1

    # Быстрые кнопки
    GridLayout:
        cols: 3
        spacing: "8dp"
        size_hint_y: None
        height: "110dp"

        Button:
            text: "🛡️ ROOT"
            background_color: 0, 0.5, 0.35, 0.4
            on_press: app.quick_cmd("root статус")
        Button:
            text: "📡 NFC"
            background_color: 0, 0.5, 0.35, 0.4
            on_press: app.quick_cmd("nfc статус")
        Button:
            text: "🔵 BT"
            background_color: 0, 0.5, 0.35, 0.4
            on_press: app.quick_cmd("bt статус")
        Button:
            text: "📊 STATUS"
            background_color: 0, 0.45, 0.6, 0.4
            on_press: app.quick_cmd("статус системы")
        Button:
            text: "🌐 AETHER"
            background_color: 0, 0.45, 0.6, 0.4
            on_press: app.quick_cmd("shell ping -c 1 8.8.8.8")
        Button:
            text: "⚛️ QUANTUM"
            background_color: 0.3, 0, 0.6, 0.4
            on_press: app.quick_cmd("квантовое состояние")

    # Лог / консоль
    ScrollView:
        size_hint_y: 0.45
        Label:
            id: console
            text: "> Initializing v1.33...\n> All systems operational."
            size_hint_y: None
            height: self.texture_size[1]
            halign: "left"
            valign: "top"
            color: 0, 1, 0.4, 1
            font_size: "13sp"
            text_size: self.width, None
            markup: True

    # Ввод команд
    BoxLayout:
        size_hint_y: None
        height: "48dp"
        spacing: "8dp"

        TextInput:
            id: cmd_input
            hint_text: "Команда Аргосу..."
            background_color: 0, 0.1, 0.1, 1
            foreground_color: 0, 1, 0.4, 1
            cursor_color: 0, 1, 0.4, 1
            font_size: "14sp"
            multiline: False
            on_text_validate: app.send_cmd()

        Button:
            text: "▶"
            size_hint_x: None
            width: "60dp"
            background_color: 0, 0.5, 0.35, 1
            on_press: app.send_cmd()
''')

    class ArgosRoot(BoxLayout):
        pass

    class ArgosGUI(App):
        def __init__(self, core=None, **kwargs):
            super().__init__(**kwargs)
            self.core = core
            self._history = []
            self.core_callback = None

        def build(self):
            Window.clearcolor = (0, 0.02, 0.04, 1)
            self.root_node = ArgosRoot()
            # Запускаем авто-обновление состояния
            Clock.schedule_interval(self._tick, 5)
            return self.root_node

        def _console(self):
            try:
                return self.root_node.ids.console
            except Exception:
                return None

        def log(self, text: str):
            c = self._console()
            if c:
                c.text += "\n[color=00ff66]>[/color] " + str(text)

        def quick_cmd(self, cmd: str):
            self.log(f"[color=aaffcc]{cmd}[/color]")
            self._execute(cmd)

        def send_cmd(self):
            try:
                inp = self.root_node.ids.cmd_input
                cmd = inp.text.strip()
                if not cmd:
                    return
                inp.text = ""
                self._history.append(cmd)
                self.log(f"[color=00ffff]▶ {cmd}[/color]")
                self._execute(cmd)
            except Exception as e:
                self.log(f"[color=ff4444]Ошибка ввода: {e}[/color]")

        def _execute(self, cmd: str):
            import threading
            def _run():
                try:
                    if self.core_callback is not None:
                        answer = self.core_callback(cmd)
                    elif self.core:
                        r = self.core.process(cmd)
                        answer = r.get("answer", str(r)) if isinstance(r, dict) else str(r)
                    else:
                        answer = f"{cmd}: Local Execute"
                    Clock.schedule_once(lambda dt: self.log(answer[:300]), 0)
                except Exception as e:
                    Clock.schedule_once(lambda dt, err=e: self.log(f"[color=ff4444]❌ {err}[/color]"), 0)
            threading.Thread(target=_run, daemon=True).start()

        def execute(self, cmd: str):
            """Public command entrypoint for external callbacks/UI bindings."""
            self._execute(cmd)

        def _tick(self, dt):
            """Авто-обновление состояния каждые 5 сек."""
            if self.core and hasattr(self.core, "quantum"):
                try:
                    state = self.core.quantum.state
                    self.log(f"[color=888888]⚛ {state}[/color]")
                except Exception:
                    pass

        def run(self):
            super().run()

    # Alias for compatibility with mobile_ui.py
    ArgosKivyApp = ArgosGUI

else:
    # Заглушка если Kivy не установлен
    class ArgosGUI:
        def __init__(self, core=None, **kwargs):
            self.core = core
            self.core_callback = None

        def run(self):
            print("⚠️  Kivy не установлен. Запусти: pip install kivy")
            print("    Используй --no-gui режим.")

        def log(self, text):
            print(f"[GUI] {text}")

        def execute(self, cmd: str):
            if self.core_callback:
                return self.core_callback(cmd)
            self.log(f"{cmd}: Local Execute")

    # Alias for compatibility with mobile_ui.py
    ArgosKivyApp = ArgosGUI
