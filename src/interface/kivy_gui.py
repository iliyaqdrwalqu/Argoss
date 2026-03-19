"""
kivy_gui.py — ARGOS v1.4.0 Kivy UI (Sovereign Emerald)
Запуск: python main.py --mobile

ПАТЧ [FIX-KV-INDENT]:
  Исправлен многострочный text: в KV-строке.
  Kivy-парсер не поддерживает реальные переносы строк внутри text: значений.
  Заменено на экранированный \\n.
"""
try:
    from kivy.app import App
    from kivy.uix.boxlayout import BoxLayout
    from kivy.lang import Builder
    from kivy.clock import Clock
    from kivy.core.window import Window
    KIVY_OK = True
except ImportError:
    KIVY_OK = False

if KIVY_OK:
    Builder.load_string(r'''
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

    Label:
        text: "\u0422\u0435\u043a\u0441\u0442: ARGOS SOVEREIGN v1.4.0"
        size_hint_y: None
        height: "48dp"
        font_size: "20sp"
        bold: True
        color: 0, 1, 0.4, 1

    GridLayout:
        cols: 3
        spacing: "8dp"
        size_hint_y: None
        height: "110dp"

        Button:
            text: "ROOT"
            background_color: 0, 0.5, 0.35, 0.4
            on_press: app.quick_cmd("root статус")
        Button:
            text: "NFC"
            background_color: 0, 0.5, 0.35, 0.4
            on_press: app.quick_cmd("nfc статус")
        Button:
            text: "BT"
            background_color: 0, 0.5, 0.35, 0.4
            on_press: app.quick_cmd("bt статус")
        Button:
            text: "STATUS"
            background_color: 0, 0.45, 0.6, 0.4
            on_press: app.quick_cmd("статус системы")
        Button:
            text: "AETHER"
            background_color: 0, 0.45, 0.6, 0.4
            on_press: app.quick_cmd("shell ping -c 1 8.8.8.8")
        Button:
            text: "QUANTUM"
            background_color: 0.3, 0, 0.6, 0.4
            on_press: app.quick_cmd("квантовое состояние")

    ScrollView:
        size_hint_y: 0.45
        Label:
            id: console
            text: "> Initializing v1.4.0...\\n> All systems operational."
            size_hint_y: None
            height: self.texture_size[1]
            halign: "left"
            valign: "top"
            color: 0, 1, 0.4, 1
            font_size: "13sp"
            text_size: self.width, None
            markup: True

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
            text: ">"
            size_hint_x: None
            width: "60dp"
            background_color: 0, 0.5, 0.35, 1
            on_press: app.send_cmd()
''')

    class ArgosRoot(BoxLayout):
        pass

    class ArgosGUI(App):
        def __init__(self, core=None, admin=None, flasher=None,
                     location: str = "", **kwargs):
            super().__init__(**kwargs)
            self.core     = core
            self.admin    = admin
            self.flasher  = flasher
            self._location = location
            self._history: list[str] = []
            self.core_callback = None

        def build(self):
            Window.clearcolor = (0, 0.02, 0.04, 1)
            self.root_node = ArgosRoot()
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

        def _append(self, text: str, color: str = ""):
            """Совместимость с boot_desktop()."""
            self.log(text)

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
                self.log(f"[color=00ffff]> {cmd}[/color]")
                self._execute(cmd)
            except Exception as e:
                self.log(f"[color=ff4444]Ошибка: {e}[/color]")

        def _execute(self, cmd: str):
            import threading

            def _run():
                try:
                    if self.core_callback is not None:
                        answer = self.core_callback(cmd)
                    elif self.core:
                        r = self.core.process(cmd)
                        answer = (r.get("answer", str(r))
                                  if isinstance(r, dict) else str(r))
                    else:
                        answer = f"{cmd}: Local Execute"
                    Clock.schedule_once(
                        lambda dt: self.log(str(answer)[:400]), 0
                    )
                except Exception as e:
                    Clock.schedule_once(
                        lambda dt, err=e: self.log(
                            f"[color=ff4444]ERR: {err}[/color]"
                        ), 0,
                    )

            threading.Thread(target=_run, daemon=True).start()

        def execute(self, cmd: str):
            self._execute(cmd)

        def _tick(self, dt):
            if self.core and hasattr(self.core, "quantum"):
                try:
                    state = self.core.quantum.state
                    self.log(f"[color=888888]Q:{state}[/color]")
                except Exception:
                    pass

        def mainloop(self):
            """Алиас для совместимости с boot_desktop()."""
            self.run()

    # Алиас для mobile_ui.py
    ArgosKivyApp = ArgosGUI

else:
    # Заглушка если Kivy не установлен
    class ArgosGUI:
        def __init__(self, core=None, admin=None, flasher=None,
                     location: str = "", **kwargs):
            self.core    = core
            self.admin   = admin
            self.flasher = flasher
            self.core_callback = None

        def run(self):
            print("Kivy не установлен: pip install kivy")
            print("Используй: python main.py --no-gui")

        def mainloop(self):
            self.run()

        def log(self, text: str):
            print(f"[GUI] {text}")

        def _append(self, text: str, color: str = ""):
            print(text)

        def execute(self, cmd: str):
            if self.core_callback:
                return self.core_callback(cmd)
            self.log(f"{cmd}: Local Execute")

    ArgosKivyApp = ArgosGUI
