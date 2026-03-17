# ======================================================
# ᑧ ARGOS v1.33 - MODULE: KIVY_UI (SMOOTH GLASS)
# ======================================================
from kivy.app import App
from kivy.uix.floatlayout import FloatLayout
from kivy.lang import Builder
from kivy.clock import Clock
from kivy.graphics import Color, Rectangle, Line
from kivy.core.window import Window

Builder.load_string('''
<ArgosRoot>:
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

class ArgosRoot(FloatLayout): pass

class ArgosGUI(App):
    def build(self):
        self.root_node = ArgosRoot()
        return self.root_node

    def execute(self, cmd):
        # Эта функция будет перехвачена главным ядром main.py
        if hasattr(self, 'core_callback'):
            self.core_callback(cmd)
        else:
            self.root_node.ids.console.text += "\\n" + cmd + ": Local Execute"

    def log(self, text):
        self.root_node.ids.console.text += "\\n" + str(text)