"""
github_marketplace.py — Установка навыков из GitHub.
  Поддерживает:
  - RAW index.json (repo root)
  - fallback на raw skill.py в src/skills/
  - публичные и приватные репозитории через GITHUB_TOKEN
"""
import base64
import json
import os
import shutil
import tempfile
import zipfile
from pathlib import Path

import requests

from src.argos_logger import get_logger

log = get_logger("argos.marketplace")


class GitHubMarketplace:
    def __init__(self, skill_loader=None, core=None):
        self.skill_loader = skill_loader
        self.core = core
        self.base_api = "https://api.github.com"

    def _headers(self) -> dict:
        token = os.getenv("GITHUB_TOKEN", "").strip()
        headers = {"Accept": "application/vnd.github+json"}
        if token:
            headers["Authorization"] = f"Bearer {token}"
        return headers

    def _raw_url(self, repo: str, path: str, ref: str = "main") -> str:
        owner, name = repo.split("/", 1)
        return f"https://raw.githubusercontent.com/{owner}/{name}/{ref}/{path}"

    def _api(self, url: str, timeout: int = 20):
        return requests.get(url, headers=self._headers(), timeout=timeout)

    def _load_index(self, repo: str) -> dict | None:
        for ref in ("main", "master"):
            try:
                r = requests.get(self._raw_url(repo, "index.json", ref=ref), timeout=15)
                if r.ok:
                    return r.json()
            except Exception:
                pass
        return None

    def _download_release_zip(self, repo: str, tag: str | None = None) -> Path | None:
        owner, name = repo.split("/", 1)
        if tag:
            url = f"{self.base_api}/repos/{owner}/{name}/zipball/{tag}"
        else:
            url = f"{self.base_api}/repos/{owner}/{name}/zipball"
        try:
            r = requests.get(url, headers=self._headers(), timeout=40)
            if not r.ok:
                return None
            tmp = Path(tempfile.mkdtemp(prefix="argos_market_"))
            zf = tmp / "repo.zip"
            zf.write_bytes(r.content)
            return zf
        except Exception:
            return None

    def _extract_skill_from_zip(self, zip_path: Path, skill_name: str) -> Path | None:
        out_dir = zip_path.parent / "unzipped"
        out_dir.mkdir(parents=True, exist_ok=True)
        with zipfile.ZipFile(zip_path, "r") as z:
            z.extractall(out_dir)

        candidates = [
            f"src/skills/{skill_name}",
            f"skills/{skill_name}",
        ]
        for root, dirs, _files in os.walk(out_dir):
            for cand in candidates:
                p = Path(root) / cand
                if p.exists() and p.is_dir():
                    return p
        return None

    def _install_skill_dir(self, src_dir: Path, skill_name: str) -> str:
        target = Path("src/skills") / skill_name
        if target.exists():
            shutil.rmtree(target)
        shutil.copytree(src_dir, target)
        if self.skill_loader:
            return self.skill_loader.load(skill_name, core=self.core)
        return f"✅ Навык '{skill_name}' установлен в {target}."

    def _install_from_raw(self, repo: str, skill_name: str) -> str:
        for ref in ("main", "master"):
            py_url = self._raw_url(repo, f"src/skills/{skill_name}.py", ref=ref)
            mf_url = self._raw_url(repo, f"src/skills/{skill_name}/manifest.yaml", ref=ref)
            skill_url = self._raw_url(repo, f"src/skills/{skill_name}/skill.py", ref=ref)

            py_resp = requests.get(py_url, timeout=20)
            if py_resp.ok:
                target = Path("src/skills") / f"{skill_name}.py"
                target.write_text(py_resp.text, encoding="utf-8")
                if self.skill_loader:
                    return self.skill_loader.reload(skill_name, core=self.core)
                return f"✅ Навык '{skill_name}' установлен (legacy)."

            mf_resp = requests.get(mf_url, timeout=20)
            sk_resp = requests.get(skill_url, timeout=20)
            if mf_resp.ok and sk_resp.ok:
                target_dir = Path("src/skills") / skill_name
                target_dir.mkdir(parents=True, exist_ok=True)
                (target_dir / "manifest.yaml").write_text(mf_resp.text, encoding="utf-8")
                (target_dir / "skill.py").write_text(sk_resp.text, encoding="utf-8")
                if self.skill_loader:
                    return self.skill_loader.reload(skill_name, core=self.core)
                return f"✅ Навык '{skill_name}' установлен (v2)."

        return "❌ Не найдено skill.py/manifest в указанном репозитории."

    def install(self, repo: str, skill_name: str) -> str:
        if "/" not in repo:
            return "❌ Репозиторий должен быть в формате USER/REPO"

        index = self._load_index(repo)
        if index and isinstance(index, dict):
            skills = index.get("skills", {})
            entry = skills.get(skill_name)
            if isinstance(entry, dict):
                raw_url = entry.get("raw_url")
                if raw_url:
                    try:
                        r = requests.get(raw_url, timeout=20)
                        if r.ok:
                            target = Path("src/skills") / f"{skill_name}.py"
                            target.write_text(r.text, encoding="utf-8")
                            if self.skill_loader:
                                return self.skill_loader.reload(skill_name, core=self.core)
                            return f"✅ Навык '{skill_name}' установлен из index.json"
                    except Exception:
                        pass

        zip_path = self._download_release_zip(repo)
        if zip_path:
            try:
                skill_dir = self._extract_skill_from_zip(zip_path, skill_name)
                if skill_dir:
                    return self._install_skill_dir(skill_dir, skill_name)
            except Exception as e:
                log.warning("ZIP install failed: %s", e)

        return self._install_from_raw(repo, skill_name)

    def update(self, repo: str, skill_name: str) -> str:
        return self.install(repo=repo, skill_name=skill_name)
