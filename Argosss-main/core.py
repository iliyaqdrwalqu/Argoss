import datetime

class ArgosAbsolute:
    def __init__(self):
        self.version = '1.31.0'
        self.start_time = datetime.datetime.now()
        print(f'>>> Kernel {self.version} initialized.')

    def execute(self, cmd):
        cmd = cmd.lower().strip()
        if cmd == 'status':
            return f'OS: Argos v{self.version} | Status: ACTIVE | Uptime: {datetime.datetime.now() - self.start_time}'
        if cmd == 'root':
            return '🛡️ ROOT: ACCESS GRANTED'
        return f'[AI] Received: {cmd}'