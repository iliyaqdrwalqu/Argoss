# ======================================================
# ᑧ ARGOS v1.33 - MODULE: KIVY_UI (SMOOTH GLASS)
# kivy_1gui.py — альтернативный упрощённый Kivy UI
# Оригинал от Всеволода; интегрирован в src/interface/
# ======================================================
try:
    from kivy.app import App
    from kivy.uix.floatlayout import FloatLayout
    from kivy.lang import Builder
    from kivy.clock import Clock
    from kivy.graphics import Color, Rectangle, Line
    from kivy.core.window import Window
    KIVY_OK = True
except ImportError:
    KIVY_OK = False

if KIVY_OK:
    Builder.load_string('''
<ArgosRoot1>:
    canvas.before:
        # Фон Матрицы
        Color:
            rgba: 0, 0.02, 0.04, 1
        Rectangle:
            size: self.size
            pos: self.pos

    # Тактильные Кнопки "Sovereign Emerald"
    GridLayout:
        cols: 2
        spacing: "15dp"
        padding: "20dp"
        size_hint: (0.9, 0.4)
        pos_hint: {'center_x': .5, 'top': 0.9}

        Button:
            text: "🛡️ ROOT"
            background_color: (0, 0.5, 0.4, 0.3)
            on_press: app.execute("root")
        Button:
            text: "📡 NFC"
            background_color: (0, 0.5, 0.4, 0.3)
            on_press: app.execute("nfc")
        Button:
            text: "🔵 BLUETOOTH"
            background_color: (0, 0.5, 0.4, 0.3)
            on_press: app.execute("bt")
        Button:
            text: "🌐 AETHER"
            background_color: (0, 0.5, 0.4, 0.3)
            on_press: app.execute("shell ping -c 1 8.8.8.8")

    # Световая консоль Ghost Terminal
    Label:
        id: console
        text: "> Initializing v1.33...\\n> All systems operational."
        size_hint: (0.9, 0.4)
        pos_hint: {'center_x': .5, 'y': 0.05}
        halign: 'left'
        valign: 'bottom'
        color: 0, 1, 0.4, 1
        font_size: '14sp'
        text_size: self.width, None
''')

    class ArgosRoot1(FloatLayout):
        pass

    class ArgosGUI1(App):
        """Упрощённый Kivy UI ARGOS v1.33 (Smooth Glass / Sovereign Emerald)."""

        def __init__(self, core=None, **kwargs):
            super().__init__(**kwargs)
            self.core = core
            self.core_callback = None

        def build(self):
            self.root_node = ArgosRoot1()
            return self.root_node

        def execute(self, cmd: str):
            """Исполнить команду через core или core_callback."""
            if self.core_callback:
                result = self.core_callback(cmd)
            elif self.core and hasattr(self.core, "process"):
                r = self.core.process(cmd)
                result = r.get("answer", str(r)) if isinstance(r, dict) else str(r)
            else:
                result = f"Local: {cmd}"
            self.log(result[:200] if result else cmd)

        def log(self, text: str):
            try:
                self.root_node.ids.console.text += "\n" + str(text)
            except Exception:
                pass

        def run(self):
            super().run()

else:
    class ArgosRoot1:
        pass

    class ArgosGUI1:
        """Заглушка если Kivy не установлен."""

        def __init__(self, core=None, **kwargs):
            self.core = core
            self.core_callback = None

        def execute(self, cmd: str):
            print(f"[kivy_1gui] {cmd}")

        def log(self, text: str):
            print(f"[kivy_1gui] {text}")

        def run(self):
            print("⚠️  kivy_1gui: Kivy не установлен. pip install kivy")
