#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
grist_git_sync.py — двусторонняя синхронизация между Grist и Git.
Позволяет версионировать конфигурации, метаданные узлов и журналы.
"""

from __future__ import annotations

import csv
import io
import os
import re
import subprocess
import threading
import time
from datetime import datetime
from typing import Dict, Optional

import requests


class GristGitSync:
    """
    Синхронизирует таблицы Grist с Git-репозиторием.
    - Выгружает таблицы в CSV и коммитит их.
    - При обнаружении изменений в Git (новый коммит) обновляет Grist.
    """

    def __init__(
        self,
        grist_api_key: str,
        grist_doc_id: str,
        grist_server: str = "https://docs.getgrist.com",
        git_repo_path: str = ".",
        git_branch: str = "main",
        sync_interval: int = 60,
    ):
        self.grist_api_key = grist_api_key
        self.grist_doc_id = grist_doc_id
        self.grist_server = grist_server.rstrip("/")
        self.git_repo_path = os.path.abspath(git_repo_path)
        self.git_branch = git_branch
        self.sync_interval = max(1, int(sync_interval))
        self.last_commit_hash = self._get_current_commit()
        self.running = True
        self.thread: Optional[threading.Thread] = None

    # ------------------------------------------------------------------
    # Grist API методы
    # ------------------------------------------------------------------
    def _grist_request(self, method: str, endpoint: str, data=None):
        """Базовый запрос к Grist API."""
        url = f"{self.grist_server}/api/docs/{self.grist_doc_id}/{endpoint.lstrip('/')}"
        headers = {
            "Authorization": f"Bearer {self.grist_api_key}",
            "Content-Type": "application/json",
        }
        response = requests.request(method, url, headers=headers, json=data, timeout=30)
        response.raise_for_status()
        return response.json()

    def list_tables(self):
        """Возвращает список таблиц в документе."""
        return self._grist_request("GET", "tables")

    def export_table_csv(self, table_id: str) -> str:
        """Экспортирует таблицу в CSV (через API)."""
        url = f"{self.grist_server}/api/docs/{self.grist_doc_id}/tables/{table_id}/data"
        headers = {"Authorization": f"Bearer {self.grist_api_key}"}
        response = requests.get(url, headers=headers, timeout=30)
        response.raise_for_status()
        data = response.json()

        records = data.get("records", []) if isinstance(data, dict) else []
        if not records:
            return ""

        output = io.StringIO()
        writer = csv.writer(output)
        headers_row = list(records[0].get("fields", {}).keys())
        writer.writerow(headers_row)
        for record in records:
            fields = record.get("fields", {})
            writer.writerow([fields.get(col, "") for col in headers_row])
        return output.getvalue()

    def import_table_csv(self, table_id: str, csv_content: str):
        """Импортирует CSV в таблицу (заменяет данные)."""
        url = f"{self.grist_server}/api/docs/{self.grist_doc_id}/tables/{table_id}/data"
        headers = {"Authorization": f"Bearer {self.grist_api_key}", "Content-Type": "text/csv"}
        response = requests.post(url, headers=headers, data=csv_content.encode("utf-8"), timeout=30)
        response.raise_for_status()
        return response.json()

    # ------------------------------------------------------------------
    # Git методы
    # ------------------------------------------------------------------
    def _git_command(self, *args: str) -> str:
        """Выполняет Git-команду в репозитории."""
        result = subprocess.run(
            ["git", *args],
            cwd=self.git_repo_path,
            capture_output=True,
            text=True,
            check=False,
            timeout=30,
        )
        if result.returncode != 0:
            raise RuntimeError(f"Git error: {(result.stderr or result.stdout).strip()}")
        return result.stdout.strip()

    def _get_current_commit(self):
        """Возвращает хеш текущего коммита."""
        try:
            return self._git_command("rev-parse", "HEAD")
        except Exception:
            return None

    @staticmethod
    def _safe_table_name(table_name: str) -> str:
        """Безопасное имя файла для CSV-слепка."""
        base = (table_name or "").strip() or "table"
        return re.sub(r"[^A-Za-z0-9._-]+", "_", base)

    def commit_csvs(self, tables_data: Dict[str, str], message: Optional[str] = None):
        """
        Сохраняет CSV-представления таблиц в файлы и коммитит их.
        tables_data: dict {table_name: csv_content}
        """
        snapshots_dir = os.path.join(self.git_repo_path, "grist_snapshots")
        os.makedirs(snapshots_dir, exist_ok=True)

        for table_name, csv_content in tables_data.items():
            safe_name = self._safe_table_name(table_name)
            file_path = os.path.join(snapshots_dir, f"{safe_name}.csv")
            with open(file_path, "w", encoding="utf-8", newline="") as f:
                f.write(csv_content)
            rel_path = os.path.relpath(file_path, self.git_repo_path)
            self._git_command("add", "--", rel_path)

        if not message:
            message = f"Grist snapshot {datetime.now().isoformat()}"

        diff_cached = subprocess.run(
            ["git", "diff", "--cached", "--quiet"],
            cwd=self.git_repo_path,
            capture_output=True,
            text=True,
            check=False,
            timeout=30,
        )
        if diff_cached.returncode == 0:
            return "No changes to commit."

        self._git_command("commit", "-m", message)
        self.last_commit_hash = self._get_current_commit()
        return f"Committed: {message}"

    def get_changed_tables(self, from_commit: Optional[str] = None, to_commit: Optional[str] = None):
        """
        Определяет, какие таблицы изменились между коммитами.
        Возвращает список имён таблиц.
        """
        if not from_commit:
            from_commit = self.last_commit_hash
        if not to_commit:
            to_commit = "HEAD"
        if not from_commit:
            return []

        diff = self._git_command("diff", "--name-only", from_commit, to_commit, "--", "grist_snapshots/")
        files = [x for x in diff.splitlines() if x.strip()]
        tables = []
        for file_name in files:
            if file_name.endswith(".csv"):
                tables.append(os.path.basename(file_name)[:-4])
        return tables

    def load_csv_from_git(self, table_name: str, commit_hash: Optional[str] = None):
        """Загружает CSV-слепок таблицы из Git."""
        if not commit_hash:
            commit_hash = "HEAD"
        safe_name = self._safe_table_name(table_name)
        file_path = f"grist_snapshots/{safe_name}.csv"
        try:
            return self._git_command("show", f"{commit_hash}:{file_path}")
        except Exception:
            return None

    # ------------------------------------------------------------------
    # Цикл синхронизации
    # ------------------------------------------------------------------
    def sync_grist_to_git(self):
        """Выгружает все таблицы из Grist в Git."""
        tables = self.list_tables()
        tables_data = {}
        for table in tables.get("tables", []):
            table_id = table["id"]
            csv_content = self.export_table_csv(table_id)
            tables_data[table_id] = csv_content
        if tables_data:
            self.commit_csvs(tables_data, "Auto-sync from Grist")

    def sync_git_to_grist(self):
        """Если в Git есть новые коммиты, обновляет изменённые таблицы в Grist."""
        current_commit = self._get_current_commit()
        if current_commit and current_commit != self.last_commit_hash:
            changed_tables = self.get_changed_tables(self.last_commit_hash, current_commit)
            for table_name in changed_tables:
                csv_content = self.load_csv_from_git(table_name, current_commit)
                if csv_content:
                    self.import_table_csv(table_name, csv_content)
            self.last_commit_hash = current_commit

    def sync_loop(self):
        """Бесконечный цикл синхронизации (для фонового потока)."""
        while self.running:
            try:
                self.sync_grist_to_git()
                self.sync_git_to_grist()
            except Exception:
                pass
            time.sleep(self.sync_interval)

    def start(self):
        if self.thread and self.thread.is_alive():
            return
        self.thread = threading.Thread(target=self.sync_loop, daemon=True)
        self.thread.start()

    def stop(self):
        self.running = False


if __name__ == "__main__":
    # Параметры (в реальности берутся из .env)
    grist_api_key = os.getenv("GRIST_API_KEY", "your_key")
    grist_doc_id = os.getenv("GRIST_DOC_ID", "your_doc_id")

    sync = GristGitSync(grist_api_key, grist_doc_id, git_repo_path=".")
    sync.start()
    try:
        time.sleep(300)
    finally:
        sync.stop()
