"""
skill_loader.py — Plugin-система навыков Аргоса
  Загружает навыки из директорий с manifest.yaml/json.
  Проверяет зависимости, версии, разрешения.
  Поддерживает версионирование и P2P-синхронизацию.
"""
import importlib, importlib.util, json, os, sys
from packaging.version import Version as V
from src.argos_logger import get_logger
from src.event_bus import get_bus, Events

log = get_logger("argos.skills")
bus = get_bus()

SKILLS_ROOT = "src/skills"

# Структура нового навыка
MANIFEST_SCHEMA = {
    "required": ["name", "version", "entry", "author"],
    "optional": ["description", "dependencies", "permissions",
                 "min_argos_version", "tags", "category"],
}

PERMISSIONS = {
    "network",    # доступ к сети
    "files",      # доступ к файлам
    "execute",    # выполнение команд
    "root",       # root-команды
    "iot",        # IoT устройства
    "telegram",   # Telegram уведомления
    "p2p",        # P2P сеть
}

PERMISSION_ALIASES = {
    "system": "execute",
    "file_write": "files",
}

ARGOS_VERSION = "1.0.0"

IMPORT_NAME_ALIASES = {
    "beautifulsoup4": "bs4",
    "pyyaml": "yaml",
    "python-telegram-bot": "telegram",
    "google-genai": "google.genai",
}


class SkillManifest:
    def __init__(self, data: dict, skill_dir: str):
        self.name        = data.get("name", "unknown")
        self.version     = data.get("version", "0.0.1")
        self.entry       = data.get("entry", "skill.py")
        self.author      = data.get("author", "unknown")
        self.description = data.get("description", "")
        self.dependencies= data.get("dependencies", [])
        raw_permissions = set(data.get("permissions", []))
        self.permissions = {PERMISSION_ALIASES.get(p, p) for p in raw_permissions}
        self.min_version = data.get("min_argos_version", "0.0.0")
        self.tags        = data.get("tags", [])
        self.category    = data.get("category", "general")
        self.dir         = skill_dir
        self._raw        = data

    def validate(self) -> list[str]:
        errors = []
        for f in MANIFEST_SCHEMA["required"]:
            if not getattr(self, f, None):
                errors.append(f"Отсутствует обязательное поле: {f}")
        invalid_perms = self.permissions - PERMISSIONS
        if invalid_perms:
            errors.append(f"Неизвестные разрешения: {invalid_perms}")
        try:
            V(self.version)
        except Exception:
            errors.append(f"Неверный формат версии: {self.version}")
        try:
            if V(ARGOS_VERSION) < V(self.min_version):
                errors.append(f"Требуется Аргос >= {self.min_version}, текущий {ARGOS_VERSION}")
        except Exception:
            pass
        return errors


class SkillInstance:
    def __init__(self, manifest: SkillManifest, module):
        self.manifest = manifest
        self.module   = module
        self.loaded_at= __import__("time").time()
        self._started = False

    def start(self, core=None):
        if hasattr(self.module, "setup"):
            self.module.setup(core)
        self._started = True

    def stop(self):
        if hasattr(self.module, "teardown"):
            self.module.teardown()
        self._started = False

    def handle(self, text: str, core=None):
        if hasattr(self.module, "handle"):
            return self.module.handle(text, core)
        return None

    @property
    def name(self): return self.manifest.name
    @property
    def version(self): return self.manifest.version


class SkillLoader:
    def __init__(self, core=None):
        self.core = core
        self._skills: dict[str, SkillInstance] = {}
        self._failed: dict[str, str]           = {}

    def discover(self) -> list[str]:
        """Ищет все директории с manifest.json или manifest.yaml в SKILLS_ROOT."""
        found = []
        if not os.path.isdir(SKILLS_ROOT):
            return found
        for item in os.listdir(SKILLS_ROOT):
            skill_dir = os.path.join(SKILLS_ROOT, item)
            if os.path.isdir(skill_dir):
                for mf in ("manifest.json", "manifest.yaml", "manifest.yml"):
                    if os.path.exists(os.path.join(skill_dir, mf)):
                        found.append(item)
                        break
        return found

    def _load_manifest(self, skill_dir: str) -> SkillManifest | None:
        for mf in ("manifest.json", "manifest.yaml", "manifest.yml"):
            path = os.path.join(skill_dir, mf)
            if not os.path.exists(path):
                continue
            try:
                if mf.endswith(".json"):
                    data = json.load(open(path, encoding="utf-8"))
                else:
                    try:
                        import yaml
                        data = yaml.safe_load(open(path, encoding="utf-8"))
                    except ImportError:
                        # fallback: простой yaml parser
                        data = _simple_yaml_load(path)
                return SkillManifest(data, skill_dir)
            except Exception as e:
                log.error("Manifest load %s: %s", path, e)
        return None

    def load(self, skill_name: str, core=None) -> str:
        skill_dir = os.path.join(SKILLS_ROOT, skill_name)
        if not os.path.isdir(skill_dir):
            # Fallback: старый стиль — один .py файл
            return self._load_legacy(skill_name)

        manifest = self._load_manifest(skill_dir)
        if not manifest:
            return f"❌ manifest не найден в {skill_dir}"

        errors = manifest.validate()
        if errors:
            return f"❌ Manifest ошибки: {'; '.join(errors)}"

        # Проверяем зависимости
        missing = self._check_deps(manifest.dependencies)
        if missing:
            return f"❌ Зависимости не установлены: {', '.join(missing)}\npip install {' '.join(missing)}"

        # Загружаем модуль
        entry_path = os.path.join(skill_dir, manifest.entry)
        if not os.path.exists(entry_path):
            return f"❌ Точка входа не найдена: {entry_path}"

        try:
            spec   = importlib.util.spec_from_file_location(
                f"argos_skill_{skill_name}", entry_path)
            module = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(module)

            inst = SkillInstance(manifest, module)
            inst.start(core)
            self._skills[skill_name] = inst
            bus.emit(Events.SKILL_LOADED,
                     {"name": skill_name, "version": manifest.version,
                      "category": manifest.category}, "skill_loader")
            log.info("Навык загружен: %s v%s", skill_name, manifest.version)
            return f"✅ Навык '{manifest.name}' v{manifest.version} загружен."
        except Exception as e:
            self._failed[skill_name] = str(e)
            log.error("Навык %s ошибка: %s", skill_name, e)
            return f"❌ {skill_name}: {e}"

    def _load_legacy(self, skill_name: str) -> str:
        """Загружает старый формат: src/skills/skill_name.py"""
        try:
            mod = importlib.import_module(f"src.skills.{skill_name}")
            manifest = SkillManifest({
                "name": skill_name, "version": "0.1.0",
                "entry": f"{skill_name}.py", "author": "legacy"
            }, os.path.join(SKILLS_ROOT, skill_name))
            inst = SkillInstance(manifest, mod)
            self._skills[skill_name] = inst
            return f"✅ Навык '{skill_name}' загружен (legacy mode)."
        except Exception as e:
            return f"❌ {skill_name}: {e}"

    def _check_deps(self, deps: list) -> list:
        missing = []
        for dep in deps:
            pkg = dep.split(">=")[0].split("==")[0].strip()
            module_name = IMPORT_NAME_ALIASES.get(pkg.lower(), pkg.replace("-", "_"))
            try:
                importlib.import_module(module_name)
            except ImportError:
                missing.append(dep)
        return missing

    def unload(self, skill_name: str) -> str:
        inst = self._skills.get(skill_name)
        if not inst:
            return f"❌ Навык '{skill_name}' не загружен."
        inst.stop()
        del self._skills[skill_name]
        return f"✅ Навык '{skill_name}' выгружен."

    def reload(self, skill_name: str, core=None) -> str:
        self.unload(skill_name)
        return self.load(skill_name, core)

    def dispatch(self, text: str, core=None) -> str | None:
        for name, inst in self._skills.items():
            try:
                result = inst.handle(text, core)
                if result:
                    bus.emit(Events.SKILL_EXECUTED,
                             {"skill": name, "input": text[:80]}, "skill_loader")
                    return result
            except Exception as e:
                log.error("Skill %s dispatch error: %s", name, e)
        return None

    def load_all(self, core=None) -> str:
        names = self.discover()
        results = [f"📦 Обнаружено навыков: {len(names)}"]
        for name in names:
            results.append(self.load(name, core))
        return "\n".join(results)

    def list_skills(self) -> str:
        loaded = list(self._skills.values())
        failed = self._failed
        lines  = [f"🧩 НАВЫКИ АРГОСА ({len(loaded)} загружено):"]
        by_cat = {}
        for inst in loaded:
            cat = inst.manifest.category
            by_cat.setdefault(cat, []).append(inst)
        for cat, skills in sorted(by_cat.items()):
            lines.append(f"\n  [{cat.upper()}]")
            for s in skills:
                desc = s.manifest.description[:50]
                lines.append(f"    ✅ {s.name} v{s.version} — {desc}")
        if failed:
            lines.append(f"\n  [ОШИБКИ]")
            for name, err in failed.items():
                lines.append(f"    ❌ {name}: {err[:60]}")
        return "\n".join(lines) if len(lines) > 1 else "Навыков нет."

    def create_skill_template(self, name: str, category: str = "custom") -> str:
        skill_dir = os.path.join(SKILLS_ROOT, name)
        os.makedirs(skill_dir, exist_ok=True)

        manifest = {
            "name": name, "version": "1.0.0",
            "entry": "skill.py", "author": "Всеволод",
            "description": f"Навык {name}",
            "category": category,
            "tags": [category],
            "dependencies": [],
            "permissions": ["network"],
        }
        json.dump(manifest, open(os.path.join(skill_dir, "manifest.json"), "w",
                                  encoding="utf-8"), indent=2, ensure_ascii=False)

        skill_code = f'''"""
{name} — Навык Аргоса
Автогенерировано ArgosUniversal
"""

TRIGGERS = ["{name.lower()}", "{name.lower().replace("_"," ")}"]

def setup(core=None):
    """Инициализация навыка."""
    pass

def handle(text: str, core=None) -> str | None:
    """Обработка команды. Вернуть None если не наш запрос."""
    t = text.lower()
    if not any(tr in t for tr in TRIGGERS):
        return None
    return f"✅ Навык {name}: обработка {{text[:50]}}"

def teardown():
    """Завершение работы навыка."""
    pass
'''
        with open(os.path.join(skill_dir, "skill.py"), "w", encoding="utf-8") as f:
            f.write(skill_code)
        with open(os.path.join(skill_dir, "README.md"), "w", encoding="utf-8") as f:
            f.write(f"# {name}\n\nКатегория: {category}\n\n## Команды\n\n- `{name}` — ...\n")

        return (f"✅ Шаблон навыка создан: {skill_dir}/\n"
                f"   📄 skill.py — логика\n"
                f"   📄 manifest.json — декларация\n"
                f"   📄 README.md — документация")


def _simple_yaml_load(path: str) -> dict:
    """Минимальный YAML-парсер (только простые key: value)."""
    result = {}
    with open(path, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith("#"):
                continue
            if ":" in line:
                k, _, v = line.partition(":")
                v = v.strip().strip('"\'')
                if v.startswith("["):
                    result[k.strip()] = [x.strip().strip('"\'')
                                         for x in v.strip("[]").split(",") if x.strip()]
                else:
                    result[k.strip()] = v
    return result
