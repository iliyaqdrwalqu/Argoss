import os
import subprocess
import tempfile
import unittest
from unittest.mock import MagicMock, patch

from src.knowledge.grist_git_sync import GristGitSync


class TestGristGitSync(unittest.TestCase):
    def _init_repo(self, path: str):
        subprocess.run(["git", "init"], cwd=path, check=True, capture_output=True, text=True)
        subprocess.run(["git", "config", "user.email", "test@example.com"], cwd=path, check=True)
        subprocess.run(["git", "config", "user.name", "Test User"], cwd=path, check=True)
        with open(os.path.join(path, "README.md"), "w", encoding="utf-8") as f:
            f.write("init\n")
        subprocess.run(["git", "add", "README.md"], cwd=path, check=True)
        subprocess.run(["git", "commit", "-m", "init"], cwd=path, check=True, capture_output=True, text=True)

    def test_export_table_csv(self):
        sync = GristGitSync("k", "d")
        mock_resp = MagicMock()
        mock_resp.json.return_value = {
            "records": [
                {"fields": {"temperature": 22.5, "humidity": 60}},
                {"fields": {"temperature": 23.0, "humidity": 58}},
            ]
        }
        mock_resp.raise_for_status.return_value = None

        with patch("src.knowledge.grist_git_sync.requests.get", return_value=mock_resp):
            csv_text = sync.export_table_csv("SensorData")

        self.assertIn("temperature,humidity", csv_text)
        self.assertIn("22.5,60", csv_text)

    def test_commit_and_load_csv_from_git(self):
        with tempfile.TemporaryDirectory() as repo:
            self._init_repo(repo)
            sync = GristGitSync("k", "d", git_repo_path=repo)

            msg = sync.commit_csvs({"sensor/table": "a,b\n1,2\n"}, message="snapshot")
            self.assertIn("Committed:", msg)

            loaded = sync.load_csv_from_git("sensor/table")
            self.assertEqual(loaded.strip(), "a,b\n1,2")

    def test_get_changed_tables_between_commits(self):
        with tempfile.TemporaryDirectory() as repo:
            self._init_repo(repo)
            sync = GristGitSync("k", "d", git_repo_path=repo)

            sync.commit_csvs({"table_one": "x\n1\n"}, message="snap1")
            first = sync.last_commit_hash
            sync.commit_csvs({"table_one": "x\n2\n", "table_two": "y\n3\n"}, message="snap2")
            second = sync.last_commit_hash

            changed = sync.get_changed_tables(first, second)
            self.assertIn("table_one", changed)
            self.assertIn("table_two", changed)

