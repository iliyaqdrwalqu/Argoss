"""
core.py — ArgosCore FINAL v2.0
    Все подсистемы интегрированы:
    ИИ + Контекст + Голос + Wake Word + Память + Планировщик +
    Алерты + Агент + Vision + P2P + Загрузчик + 50+ команд
"""
import os, threading, requests, asyncio, tempfile, importlib.util, re
import json
import time
import base64
import uuid
import subprocess
from collections import deque

# ── Graceful imports ──────────────────────────────────────
try:
    from google import genai as genai_sdk; GEMINI_OK = True
except ImportError:
    genai_sdk = None; GEMINI_OK = False

try:
    import pyttsx3; PYTTSX3_OK = True
except ImportError:
    pyttsx3 = None; PYTTSX3_OK = False

try:
    import speech_recognition as sr; SR_OK = True
except ImportError:
    sr = None; SR_OK = False

from src.quantum.logic               import ArgosQuantum
from src.skills.web_scrapper         import ArgosScrapper
from src.factory.replicator          import Replicator
from src.connectivity.sensor_bridge  import ArgosSensorBridge
from src.connectivity.p2p_bridge     import ArgosBridge, p2p_protocol_roadmap
from src.skill_loader                import SkillLoader
from src.dag_agent                   import DAGManager
from src.github_marketplace          import GitHubMarketplace
from src.modules                     import ModuleLoader
from src.context_manager             import DialogContext
from src.agent                       import ArgosAgent
from src.argos_logger                import get_logger
from dotenv import load_dotenv
load_dotenv()

log = get_logger("argos.core")

_DEFAULT_PROVIDER_COOLDOWN_SECONDS = 600
_MIN_PROVIDER_COOLDOWN_SECONDS = 60
_MAX_PROVIDER_COOLDOWN_SECONDS = 3600

_PLACEHOLDER_SECRET_VALUES = {"", "your_key_here", "your_token_here", "none", "null", "changeme"}


def _read_secret_env(name: str) -> str:
    value = (os.getenv(name, "") or "").strip()
    if value.lower() in _PLACEHOLDER_SECRET_VALUES:
        return ""
    return value


# Маркеры смешаны (RU/EN), потому что ошибки приходят как от наших русских
# reason-строк, так и от англоязычных API/SSL исключений.
_PERMANENT_PROVIDER_ERROR_MARKERS = (
    "некорректный/просроченный api ключ",
    "ошибка авторизации http",
    "ssl сертификат не прошёл проверку",
    "api key expired",
    "invalid api key",
    "api_key_invalid",
    "certificate verify failed",
)


class _SlidingWindowRateLimiter:
    def __init__(self, max_calls: int, window_seconds: int):
        self.max_calls = max_calls
        self.window_seconds = window_seconds
        self._hits = deque()
        self._lock = threading.Lock()

    def allow(self) -> bool:
        now = time.time()
        with self._lock:
            while self._hits and (now - self._hits[0]) >= self.window_seconds:
                self._hits.popleft()
            if len(self._hits) >= self.max_calls:
                return False
            self._hits.append(now)
            return True


class _GeminiResponse:
    def __init__(self, text: str = ""):
        self.text = text or ""


class _GeminiCompatClient:
    """Лёгкий адаптер google.genai под старый интерфейс generate_content()."""
    def __init__(self, api_key: str, model_name: str = "gemini-2.0-flash"):
        self.client = genai_sdk.Client(api_key=api_key)
        self.model_name = self._resolve_model_name(model_name)

    def _resolve_model_name(self, requested: str) -> str:
        env_model = os.getenv("GEMINI_MODEL", "").strip()
        if env_model:
            requested = env_model

        candidates = [
            requested,
            "gemini-2.0-flash",
            "gemini-2.0-flash-lite",
            "gemini-1.5-flash",
            "gemini-1.5-pro",
        ]

        try:
            available = []
            for model in self.client.models.list():
                name = getattr(model, "name", "") or ""
                if name:
                    available.append(name)

            if not available:
                return requested

            for cand in candidates:
                if cand in available:
                    return cand
                if f"models/{cand}" in available:
                    return f"models/{cand}"

            # Берём первую flash-модель, если есть
            for name in available:
                if "flash" in name.lower():
                    return name
            return available[0]
        except Exception:
            return requested

    def generate_content(self, contents):
        if isinstance(contents, list):
            prompt = "\n\n".join(str(x) for x in contents if isinstance(x, str) and x.strip())
        else:
            prompt = str(contents)
        try:
            resp = self.client.models.generate_content(model=self.model_name, contents=prompt)
        except Exception as first_error:
            # Попытка один раз переключиться на доступную модель (404/NOT_FOUND и совместимость API)
            new_model = self._resolve_model_name("gemini-2.0-flash")
            if new_model != self.model_name:
                self.model_name = new_model
                resp = self.client.models.generate_content(model=self.model_name, contents=prompt)
            else:
                raise first_error

        text = getattr(resp, "text", "") or ""
        return _GeminiResponse(text=text)


class ArgosCore:
    VERSION = "1.3.0"

    def __init__(self):
        self.quantum    = ArgosQuantum()
        self.scrapper   = ArgosScrapper()
        self.replicator = Replicator()
        self.sensors    = ArgosSensorBridge()
        self.context    = DialogContext(max_turns=10)
        self.agent      = ArgosAgent(self)
        self.ollama_url = os.getenv("OLLAMA_HOST", "http://localhost:11434").rstrip("/") + "/api/generate"
        self.ai_mode    = self._normalize_ai_mode(os.getenv("ARGOS_AI_MODE", "auto"))
        self.voice_on   = os.getenv("ARGOS_VOICE_DEFAULT", "off").strip().lower() in (
            "1", "true", "on", "yes", "да", "вкл"
        )
        self.p2p        = None
        self.db         = None
        self.memory     = None
        self.scheduler  = None
        self.alerts     = None
        self.vision     = None
        self._boot      = None
        self._dashboard = None
        self._wake      = None
        self._tts_engine = None
        self._tts_lock = threading.Lock()
        self._whisper_model = None
        self.skill_loader = None
        self.dag_manager  = None
        self.marketplace  = None
        self.iot_bridge   = None
        self.iot_emulator = None
        self.mesh_net     = None
        self.smart_sys    = None
        self.gateway_mgr  = None
        self.industrial   = None
        self.platform_admin = None
        self.smart_profiles = {}
        self._smart_create_wizard = None
        self.operator_mode = False
        self.module_loader = None
        self.ha = None
        self.tool_calling = None
        self.git_ops = None
        self.otg = None
        self.grist = None
        self.cloud_object_storage = None
        self.gemini_rpm_limit = 15
        self._gemini_limiter = _SlidingWindowRateLimiter(max_calls=self.gemini_rpm_limit, window_seconds=60)
        self._last_gemini_rate_limited = False
        self._gigachat_access_token = _read_secret_env("GIGACHAT_ACCESS_TOKEN") or None
        self._gigachat_token_expires_at = 0.0
        cooldown_raw = os.getenv("ARGOS_PROVIDER_FAILURE_COOLDOWN", str(_DEFAULT_PROVIDER_COOLDOWN_SECONDS))
        try:
            cooldown_seconds = int(cooldown_raw)
        except ValueError:
            cooldown_seconds = _DEFAULT_PROVIDER_COOLDOWN_SECONDS
            log.warning(
                "ARGOS_PROVIDER_FAILURE_COOLDOWN=%r некорректен, используется значение по умолчанию %s сек",
                cooldown_raw,
                _DEFAULT_PROVIDER_COOLDOWN_SECONDS,
            )
        # Ограничиваем окно на разумный диапазон: 1 минута .. 1 час.
        self.provider_failure_cooldown_seconds = max(
            _MIN_PROVIDER_COOLDOWN_SECONDS,
            min(cooldown_seconds, _MAX_PROVIDER_COOLDOWN_SECONDS),
        )
        self._provider_disabled_until: dict[str, float] = {}
        self._provider_disable_reason: dict[str, str] = {}
        self._provider_disabled_permanent: dict[str, str] = {}
        self.auto_collab_enabled = os.getenv("ARGOS_AUTO_COLLAB", "on").strip().lower() not in {"0", "false", "off", "no", "нет"}
        self.auto_collab_max_models = max(2, min(int(os.getenv("ARGOS_AUTO_COLLAB_MAX_MODELS", "4") or "4"), 4))
        self.homeostasis = None
        self.curiosity = None
        self._homeostasis_block_heavy = False

        self._init_voice()
        self._setup_ai()
        self._init_memory()
        self._init_homeostasis()
        self._init_curiosity()
        self._init_scheduler()
        self._init_alerts()
        self._init_vision()
        self._init_skills()
        self._init_dags()
        self._init_marketplace()
        self._init_iot()
        self._init_industrial()
        self._init_platform_admin()
        self._init_smart_systems()
        self._init_home_assistant()
        self._init_modules()
        self._init_tool_calling()
        self._init_git_ops()
        self._init_otg()
        self._init_grist()
        self._init_cloud_object_storage()
        self._init_own_model()
        log.info("ArgosCore FINAL v2.0 инициализирован.")

    # ═══════════════════════════════════════════════════════
    # ИНИЦИАЛИЗАЦИЯ ПОДСИСТЕМ
    # ═══════════════════════════════════════════════════════
    def _init_memory(self):
        try:
            from src.memory import ArgosMemory
            self.memory = ArgosMemory()
            self.context.memory_ref = self.memory
            log.info("Память: OK")
        except Exception as e:
            log.warning("Память недоступна: %s", e)

    def _init_cloud_object_storage(self):
        try:
            from src.connectivity.cloud_object_storage import IBMCloudObjectStorage
            self.cloud_object_storage = IBMCloudObjectStorage.from_env()
            log.info(self.cloud_object_storage.status())
        except Exception as e:
            log.warning("IBM Cloud Object Storage недоступен: %s", e)

    def _init_scheduler(self):
        try:
            from src.skills.scheduler import ArgosScheduler
            self.scheduler = ArgosScheduler(core=self)
            self.scheduler.start()
            log.info("Планировщик: OK")
        except Exception as e:
            log.warning("Планировщик: %s", e)

    def _init_homeostasis(self):
        try:
            from src.hardware_guard import HardwareHomeostasisGuard
            self.homeostasis = HardwareHomeostasisGuard(core=self)
            if os.getenv("ARGOS_HOMEOSTASIS", "on").strip().lower() not in {"0", "off", "false", "no", "нет"}:
                self.homeostasis.start()
            log.info("Homeostasis: OK")
        except Exception as e:
            log.warning("Homeostasis: %s", e)

    def _init_curiosity(self):
        try:
            from src.curiosity import ArgosCuriosity
            self.curiosity = ArgosCuriosity(core=self)
            if os.getenv("ARGOS_CURIOSITY", "on").strip().lower() not in {"0", "off", "false", "no", "нет"}:
                self.curiosity.start()
            log.info("Curiosity: OK")
        except Exception as e:
            log.warning("Curiosity: %s", e)

    def _init_alerts(self):
        try:
            from src.connectivity.alert_system import AlertSystem
            self.alerts = AlertSystem(on_alert=self._on_alert)
            self.alerts.start(interval_sec=30)
            log.info("Алерты: OK")
        except Exception as e:
            log.warning("Алерты: %s", e)

    def _init_vision(self):
        try:
            from src.vision import ArgosVision
            self.vision = ArgosVision()
            log.info("Vision: OK")
        except Exception as e:
            log.warning("Vision: %s", e)

    def _init_skills(self):
        try:
            self.skill_loader = SkillLoader()
            report = self.skill_loader.load_all(core=self)
            log.info("SkillLoader: OK")
            log.info(report.replace("\n", " | "))
        except Exception as e:
            log.warning("SkillLoader: %s", e)

    def _init_dags(self):
        try:
            self.dag_manager = DAGManager(core=self)
            log.info("DAG Manager: OK")
        except Exception as e:
            log.warning("DAG Manager: %s", e)

    def _init_marketplace(self):
        try:
            self.marketplace = GitHubMarketplace(skill_loader=self.skill_loader, core=self)
            log.info("GitHub Marketplace: OK")
        except Exception as e:
            log.warning("GitHub Marketplace: %s", e)

    def _init_iot(self):
        """IoT Bridge + Mesh Network + Gateway Manager + IoT Emulators."""
        try:
            from src.connectivity.iot_bridge import IoTBridge
            self.iot_bridge = IoTBridge()
            log.info("IoT Bridge: OK (%d устройств)", len(self.iot_bridge.registry.all()))
        except Exception as e:
            log.warning("IoT Bridge: %s", e)

        try:
            from src.connectivity.iot_emulator import IotEmulatorManager
            mqtt_host = os.getenv("MQTT_HOST", "localhost")
            mqtt_port = int(os.getenv("MQTT_PORT", "1883"))
            self.iot_emulator = IotEmulatorManager(mqtt_host=mqtt_host, mqtt_port=mqtt_port)
            log.info("IoT Emulator Manager: OK")
        except Exception as e:
            log.warning("IoT Emulator Manager: %s", e)

        try:
            from src.connectivity.mesh_network import MeshNetwork
            self.mesh_net = MeshNetwork()
            log.info("Mesh Network: OK (%d устройств)", len(self.mesh_net.devices))
        except Exception as e:
            log.warning("Mesh Network: %s", e)

        try:
            from src.connectivity.gateway_manager import GatewayManager
            self.gateway_mgr = GatewayManager(iot_bridge=self.iot_bridge)
            log.info("Gateway Manager: OK")
        except Exception as e:
            log.warning("Gateway Manager: %s", e)

    def _init_industrial(self):
        """Industrial Protocols Manager — KNX / LonWorks / M-Bus / OPC-UA."""
        try:
            from industrial_protocols import IndustrialProtocolsManager
            self.industrial = IndustrialProtocolsManager(core=self)
            log.info("Industrial Protocols: OK (KNX/LON/M-Bus/OPC-UA)")
        except Exception as e:
            log.warning("Industrial Protocols: %s", e)

    def _init_platform_admin(self):
        """Platform Admin — Linux / Windows / Android управление."""
        try:
            from src.platform_admin import PlatformAdmin
            self.platform_admin = PlatformAdmin(core=self)
            log.info("PlatformAdmin: OK (os=%s)", self.platform_admin.os)
        except Exception as e:
            log.warning("PlatformAdmin: %s", e)

    def _init_smart_systems(self):
        """Smart Systems Manager — умные среды."""
        try:
            from src.smart_systems import SmartSystemsManager, SYSTEM_PROFILES
            self.smart_sys = SmartSystemsManager(on_alert=self._on_alert)
            self.smart_profiles = SYSTEM_PROFILES
            log.info("Smart Systems: OK (%d систем)", len(self.smart_sys.systems))
        except Exception as e:
            log.warning("Smart Systems: %s", e)

    def _init_modules(self):
        """Dynamic modules (src/modules/*_module.py)."""
        try:
            self.module_loader = ModuleLoader()
            report = self.module_loader.load_all(core=self)
            log.info(report.replace("\n", " | "))
        except Exception as e:
            log.warning("Modules: %s", e)

    def _init_home_assistant(self):
        try:
            from src.connectivity.home_assistant import HomeAssistantBridge
            self.ha = HomeAssistantBridge()
            log.info("Home Assistant bridge: %s", "ON" if self.ha.enabled else "OFF")
        except Exception as e:
            log.warning("Home Assistant bridge: %s", e)

    def _init_tool_calling(self):
        try:
            from src.tool_calling import ArgosToolCallingEngine
            self.tool_calling = ArgosToolCallingEngine(core=self)
            log.info("Tool Calling: OK")
        except Exception as e:
            log.warning("Tool Calling: %s", e)

    def _init_git_ops(self):
        try:
            from src.git_ops import ArgosGitOps
            self.git_ops = ArgosGitOps(repo_path=".")
            log.info("GitOps: OK")
        except Exception as e:
            log.warning("GitOps: %s", e)

    def _init_otg(self):
        try:
            from src.connectivity.otg_manager import OTGManager
            self.otg = OTGManager()
            log.info("OTG Manager: OK")
        except Exception as e:
            self.otg = None
            log.warning("OTG Manager: %s", e)

    def _init_grist(self):
        try:
            from src.knowledge.grist_storage import GristStorage
            self.grist = GristStorage()
            if self.memory and hasattr(self.memory, "attach_grist"):
                self.memory.attach_grist(self.grist)
            log.info("Grist Storage: OK (настроен=%s)", self.grist._configured)
        except Exception as e:
            self.grist = None
            log.warning("Grist Storage: %s", e)

    def _init_own_model(self):
        try:
            from src.argos_model import ArgosOwnModel
            self.own_model = ArgosOwnModel()
            log.info("OwnModel: OK")
        except Exception as e:
            self.own_model = None
            log.warning("OwnModel: %s", e)

    def process(self, user_text: str, admin=None, flasher=None) -> dict:
        """Обёртка над process_logic с дефолтными значениями admin/flasher."""
        return self.process_logic(user_text, admin, flasher)

    def _on_alert(self, msg: str):
        log.warning("ALERT: %s", msg)
        self.say(msg)

    def _remember_dialog_turn(self, user_text: str, answer: str, state: str):
        if not self.memory:
            return
        try:
            self.memory.log_dialogue("user", user_text, state=state)
            self.memory.log_dialogue("argos", answer, state=state)
        except Exception as e:
            log.warning("Memory dialogue index: %s", e)

    # ═══════════════════════════════════════════════════════
    # P2P / DASHBOARD / WAKE WORD
    # ═══════════════════════════════════════════════════════
    def start_p2p(self) -> str:
        self.p2p = ArgosBridge(core=self)
        result = self.p2p.start()
        log.info("P2P: %s", result.split('\n')[0])
        return result

    def start_dashboard(self, admin, flasher, port: int = 8080) -> str:
        try:
            from src.interface.fastapi_dashboard import FastAPIDashboard
            self._dashboard = FastAPIDashboard(self, admin, flasher, port)
            result = self._dashboard.start()
            if isinstance(result, str) and not result.startswith("❌"):
                return result
        except Exception:
            pass

        try:
            from src.interface.web_dashboard import WebDashboard
            self._dashboard = WebDashboard(self, admin, flasher, port)
            return self._dashboard.start()
        except Exception as e:
            return f"❌ Dashboard: {e}"

    def start_wake_word(self, admin, flasher) -> str:
        try:
            from src.connectivity.wake_word import WakeWordListener
            self._wake = WakeWordListener(self, admin, flasher)
            return self._wake.start()
        except Exception as e:
            return f"❌ Wake Word: {e}"

    # ═══════════════════════════════════════════════════════
    # ГОЛОС
    # ═══════════════════════════════════════════════════════
    def _init_voice(self):
        if not PYTTSX3_OK:
            log.warning("pyttsx3 не установлен: pip install pyttsx3")
            return
        try:
            self._tts_engine = pyttsx3.init()
            for v in self._tts_engine.getProperty('voices'):
                if "Russian" in v.name or "ru" in v.id:
                    self._tts_engine.setProperty('voice', v.id)
                    break
            self._tts_engine.setProperty('rate', 175)
            log.info("TTS: OK")
        except Exception as e:
            self._tts_engine = None
            log.warning("TTS недоступен: %s", e)

    def say(self, text: str):
        if not self.voice_on or not self._tts_engine:
            return
        def _speak():
            try:
                with self._tts_lock:
                    self._tts_engine.say(text[:300])
                    self._tts_engine.runAndWait()
            except Exception as e:
                log.warning("TTS runtime error: %s", e)
        threading.Thread(target=_speak, daemon=True).start()

    def listen(self) -> str:
        if SR_OK:
            try:
                rec = sr.Recognizer()
                with sr.Microphone() as src:
                    log.info("Слушаю...")
                    rec.adjust_for_ambient_noise(src, duration=0.5)
                    audio = rec.listen(src, timeout=7, phrase_time_limit=15)
                    try:
                        text = rec.recognize_google(audio, language="ru-RU")
                        log.info("Распознано (google): %s", text)
                        return text.lower()
                    except Exception:
                        text = self._transcribe_with_whisper(audio)
                        if text:
                            log.info("Распознано (whisper): %s", text)
                            return text.lower()
            except Exception as e:
                log.error("STT: %s", e)

        log.warning("STT недоступен (SpeechRecognition/Whisper)")
        return ""

    def _transcribe_with_whisper(self, audio_data) -> str:
        try:
            if self._whisper_model is None:
                from faster_whisper import WhisperModel
                model_size = os.getenv("WHISPER_MODEL", "small")
                device = os.getenv("WHISPER_DEVICE", "cpu")
                compute = os.getenv("WHISPER_COMPUTE_TYPE", "int8")
                self._whisper_model = WhisperModel(model_size, device=device, compute_type=compute)

            with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as tmp:
                tmp.write(audio_data.get_wav_data())
                wav_path = tmp.name

            segments, _ = self._whisper_model.transcribe(wav_path, language="ru", vad_filter=True)
            text = " ".join(seg.text.strip() for seg in segments if seg.text and seg.text.strip())
            try:
                os.remove(wav_path)
            except Exception:
                pass
            return text
        except Exception as e:
            log.warning("Whisper STT fallback: %s", e)
            return ""

    def transcribe_audio_path(self, audio_path: str) -> str:
        """Транскрибация аудиофайла (ogg/mp3/wav) через faster-whisper."""
        if not audio_path or not os.path.exists(audio_path):
            return ""
        try:
            if self._whisper_model is None:
                from faster_whisper import WhisperModel
                model_size = os.getenv("WHISPER_MODEL", "small")
                device = os.getenv("WHISPER_DEVICE", "cpu")
                compute = os.getenv("WHISPER_COMPUTE_TYPE", "int8")
                self._whisper_model = WhisperModel(model_size, device=device, compute_type=compute)

            segments, _ = self._whisper_model.transcribe(audio_path, language="ru", vad_filter=True)
            text = " ".join(seg.text.strip() for seg in segments if seg.text and seg.text.strip())
            return text.strip()
        except Exception as e:
            log.warning("Whisper file STT: %s", e)
            return ""

    def voice_services_report(self) -> str:
        tts_ready = bool(PYTTSX3_OK and self._tts_engine)
        stt_live_ready = bool(SR_OK)
        stt_file_ready = bool(importlib.util.find_spec("faster_whisper"))
        voice_mode = "ВКЛ" if self.voice_on else "ВЫКЛ"
        return (
            "🎙 Проверка голосовых служб:\n"
            f"• Голосовой вывод (TTS): {'✅ готов' if tts_ready else '❌ недоступен'}\n"
            f"• Голосовой ввод (микрофон): {'✅ готов' if stt_live_ready else '❌ недоступен'}\n"
            f"• Голосовой ввод (аудиофайлы): {'✅ готов' if stt_file_ready else '❌ недоступен'}\n"
            f"• Текущий голосовой режим: {voice_mode}"
        )

    # ═══════════════════════════════════════════════════════
    # ИИ
    # ═══════════════════════════════════════════════════════
    def _normalize_ai_mode(self, mode: str) -> str:
        value = (mode or "auto").strip().lower()
        if value in {"gemini", "google", "g"}:
            return "gemini"
        if value in {"gigachat", "giga", "sber", "gc"}:
            return "gigachat"
        if value in {"yandexgpt", "yandex", "ya", "yg"}:
            return "yandexgpt"
        if value in {"ollama", "local", "o"}:
            return "ollama"
        return "auto"

    def set_ai_mode(self, mode: str) -> str:
        self.ai_mode = self._normalize_ai_mode(mode)
        return f"🤖 Режим ИИ: {self.ai_mode_label()}"

    def ai_mode_label(self) -> str:
        if self.ai_mode == "gemini":
            return "Gemini"
        if self.ai_mode == "gigachat":
            return "GigaChat"
        if self.ai_mode == "yandexgpt":
            return "YandexGPT"
        if self.ai_mode == "ollama":
            return "Ollama"
        return "Auto"

    def _setup_ai(self):
        key = _read_secret_env("GEMINI_API_KEY")
        if GEMINI_OK and key:
            self.model = _GeminiCompatClient(api_key=key, model_name="gemini-2.0-flash")
            log.info("Gemini: OK")
        else:
            self.model = None
            log.info("Gemini недоступен — используется Ollama")

        # Always start Ollama so it is ready as a fallback even when a cloud
        # provider (e.g. Gemini) is configured but later turns out to have an
        # expired or invalid API key.
        ollama_ok = self._ensure_ollama_running()
        if ollama_ok:
            log.info("Ollama: ✅ доступна (резервный провайдер готов)")
        else:
            log.warning("Ollama: ❌ недоступна — резервный локальный провайдер не запущен")

        if self._has_gigachat_config():
            log.info("GigaChat: конфигурация обнаружена")
        else:
            log.info("GigaChat недоступен — нет credentials")

        if self._has_yandexgpt_config():
            log.info("YandexGPT: конфигурация обнаружена")
        else:
            log.info("YandexGPT недоступен — нет IAM/FOLDER")

    def _gemini_rate_limit_text(self) -> str:
        return f"Gemini: превышен лимит {self.gemini_rpm_limit} запросов в минуту. Повтори чуть позже или переключи режим ИИ."

    @staticmethod
    def _is_host_reachable(host: str, port: int = 443, timeout: float = 2.0) -> bool:
        """Быстрая проверка TCP-доступности хоста перед HTTP-запросом.

        Возвращает False если DNS не резолвится или соединение недоступно.
        Позволяет избежать лишних ошибок в лог при работе в офлайн/CI среде.
        """
        import socket as _socket
        try:
            with _socket.create_connection((host, port), timeout=timeout):
                return True
        except OSError:
            return False

    def _has_gigachat_config(self) -> bool:
        if self._gigachat_access_token:
            return True
        client_id = _read_secret_env("GIGACHAT_CLIENT_ID")
        client_secret = _read_secret_env("GIGACHAT_CLIENT_SECRET")
        return bool(client_id and client_secret)

    def _has_yandexgpt_config(self) -> bool:
        iam = _read_secret_env("YANDEX_IAM_TOKEN")
        folder = _read_secret_env("YANDEX_FOLDER_ID")
        return bool(iam and folder)

    def _is_provider_temporarily_disabled(self, provider_name: str) -> bool:
        if provider_name in self._provider_disabled_permanent:
            return True
        until = float(self._provider_disabled_until.get(provider_name, 0.0))
        if until <= time.time():
            self._provider_disabled_until.pop(provider_name, None)
            self._provider_disable_reason.pop(provider_name, None)
            return False
        return True

    def _disable_provider_temporarily(self, provider_name: str, reason: str) -> None:
        reason_lower = reason.lower() if isinstance(reason, str) else ""
        if any(x in reason_lower for x in _PERMANENT_PROVIDER_ERROR_MARKERS):
            if provider_name not in self._provider_disabled_permanent:
                self._provider_disabled_permanent[provider_name] = reason
                log.warning("%s отключен до перезапуска: %s", provider_name, reason)
            return
        was_already_disabled = self._is_provider_temporarily_disabled(provider_name)
        self._provider_disabled_until[provider_name] = time.time() + self.provider_failure_cooldown_seconds
        self._provider_disable_reason[provider_name] = reason
        if not was_already_disabled:
            log.warning(
                "%s временно отключен на %s сек: %s",
                provider_name,
                self.provider_failure_cooldown_seconds,
                reason,
            )

    def _get_gigachat_token(self) -> str | None:
        if self._gigachat_access_token and self._gigachat_token_expires_at <= 0:
            return self._gigachat_access_token

        if self._gigachat_access_token and time.time() < self._gigachat_token_expires_at - 30:
            return self._gigachat_access_token

        client_id = _read_secret_env("GIGACHAT_CLIENT_ID")
        client_secret = _read_secret_env("GIGACHAT_CLIENT_SECRET")
        if not (client_id and client_secret):
            return self._gigachat_access_token

        if not self._is_host_reachable("ngw.devices.sberbank.ru", 9443):
            log.debug("GigaChat: ngw.devices.sberbank.ru недоступен — пропуск")
            return None

        try:
            basic = base64.b64encode(f"{client_id}:{client_secret}".encode("utf-8")).decode("utf-8")
            headers = {
                "Authorization": f"Basic {basic}",
                "RqUID": str(uuid.uuid4()),
                "Content-Type": "application/x-www-form-urlencoded",
                "Accept": "application/json",
            }
            response = requests.post(
                "https://ngw.devices.sberbank.ru:9443/api/v2/oauth",
                headers=headers,
                data={"scope": "GIGACHAT_API_PERS"},
                timeout=20,
            )
            if not response.ok:
                log.error("GigaChat auth: HTTP %s %s", response.status_code, response.text[:400])
                return None

            payload = response.json()
            token = (payload.get("access_token") or "").strip()
            if not token:
                return None

            expires_at_ms = payload.get("expires_at")
            if isinstance(expires_at_ms, (int, float)):
                self._gigachat_token_expires_at = float(expires_at_ms) / 1000.0
            else:
                self._gigachat_token_expires_at = time.time() + 1800

            self._gigachat_access_token = token
            return token
        except Exception as e:
            log.error("GigaChat auth error: %s", e)
            return None

    def _ask_gemini(self, context: str, user_text: str) -> str | None:
        self._last_gemini_rate_limited = False
        if self._is_provider_temporarily_disabled("Gemini"):
            return None
        if not self.model:
            return None
        if not self._gemini_limiter.allow():
            self._last_gemini_rate_limited = True
            log.warning(self._gemini_rate_limit_text())
            return None
        try:
            hist = self.context.get_prompt_context()
            payload = f"{context}\n\n{hist}\n\nUser: {user_text}\nArgos:"
            res = self.model.generate_content(payload)
            return res.text
        except Exception as e:
            err_text = str(e).lower()
            if any(x in err_text for x in ("api_key_invalid", "api key expired", "invalid api key")):
                self._disable_provider_temporarily("Gemini", "некорректный/просроченный API ключ")
            log.error("Gemini: %s", e)
            return None

    def _ask_gigachat(self, context: str, user_text: str) -> str | None:
        if self._is_provider_temporarily_disabled("GigaChat"):
            return None
        token = self._get_gigachat_token()
        if not token:
            return None
        if not self._is_host_reachable("gigachat.devices.sberbank.ru"):
            log.debug("GigaChat: хост недоступен — пропуск")
            return None
        try:
            hist = self.context.get_prompt_context()
            payload = {
                "model": (os.getenv("GIGACHAT_MODEL", "GigaChat-2") or "GigaChat-2").strip(),
                "messages": [
                    {"role": "system", "content": context},
                    {"role": "user", "content": f"{hist}\n\n{user_text}"},
                ],
                "temperature": 0.4,
                "max_tokens": 1200,
            }
            response = requests.post(
                "https://gigachat.devices.sberbank.ru/api/v1/chat/completions",
                headers={
                    "Authorization": f"Bearer {token}",
                    "Content-Type": "application/json",
                    "Accept": "application/json",
                },
                json=payload,
                timeout=25,
            )
            if not response.ok:
                if response.status_code in (401, 403):
                    self._disable_provider_temporarily("GigaChat", f"ошибка авторизации HTTP {response.status_code}")
                log.error("GigaChat: HTTP %s %s", response.status_code, response.text[:400])
                return None

            data = response.json()
            choices = data.get("choices") or []
            if not choices:
                return None
            message = choices[0].get("message") or {}
            content = message.get("content")
            if isinstance(content, str):
                return content.strip()
            return None
        except Exception as e:
            if isinstance(e, requests.exceptions.SSLError):
                self._disable_provider_temporarily("GigaChat", "SSL сертификат не прошёл проверку")
            log.error("GigaChat: %s", e)
            return None

    def _ask_yandexgpt(self, context: str, user_text: str) -> str | None:
        if self._is_provider_temporarily_disabled("YandexGPT"):
            return None
        iam = _read_secret_env("YANDEX_IAM_TOKEN")
        folder = _read_secret_env("YANDEX_FOLDER_ID")
        if not (iam and folder):
            return None

        if not self._is_host_reachable("llm.api.cloud.yandex.net"):
            log.debug("YandexGPT: хост недоступен — пропуск")
            return None

        model_uri = (os.getenv("YANDEXGPT_MODEL_URI", "") or "").strip()
        if not model_uri:
            model_uri = f"gpt://{folder}/yandexgpt-lite/latest"

        try:
            hist = self.context.get_prompt_context()
            payload = {
                "modelUri": model_uri,
                "completionOptions": {
                    "stream": False,
                    "temperature": 0.4,
                    "maxTokens": "1200",
                },
                "messages": [
                    {"role": "system", "text": context},
                    {"role": "user", "text": f"{hist}\n\n{user_text}"},
                ],
            }
            response = requests.post(
                "https://llm.api.cloud.yandex.net/foundationModels/v1/completion",
                headers={
                    "Authorization": f"Bearer {iam}",
                    "x-folder-id": folder,
                    "Content-Type": "application/json",
                },
                json=payload,
                timeout=25,
            )
            if not response.ok:
                if response.status_code in (401, 403):
                    self._disable_provider_temporarily("YandexGPT", f"ошибка авторизации HTTP {response.status_code}")
                log.error("YandexGPT: HTTP %s %s", response.status_code, response.text[:400])
                return None

            data = response.json()
            result = data.get("result") or {}
            alternatives = result.get("alternatives") or []
            if not alternatives:
                return None
            message = alternatives[0].get("message") or {}
            text = message.get("text")
            if isinstance(text, str):
                return text.strip()
            return None
        except Exception as e:
            log.error("YandexGPT: %s", e)
            return None

    # ───────────────────────────────────────────────────────
    # OLLAMA AUTO-START
    # ───────────────────────────────────────────────────────
    _ollama_start_lock = threading.Lock()
    _ollama_proc: "subprocess.Popen | None" = None

    def _ensure_ollama_running(self) -> bool:
        """Жёсткий авто-старт Ollama: поднимает сервис если он не отвечает.

        Работает на Windows 10/11, Linux и macOS.
        На Windows Ollama устанавливается как системный процесс, но если он
        не запущен — метод запускает его явно через subprocess.

        Returns:
            True  — Ollama доступна (уже работала или успешно запущена).
            False — не удалось запустить.
        """
        import platform as _platform
        base_url = self.ollama_url.replace("/api/generate", "")
        ping_url = base_url.rstrip("/") + "/api/tags"

        log.info("[Ollama] Проверяю доступность: %s", ping_url)

        # Быстрая проверка — уже работает?
        try:
            requests.get(ping_url, timeout=3)
            log.info("[Ollama] ✅ Уже запущен (%s)", ping_url)
            return True
        except Exception as _e:
            log.info("[Ollama] Не отвечает при быстрой проверке: %s", _e)

        with ArgosCore._ollama_start_lock:
            # Повторная проверка под локом
            try:
                requests.get(ping_url, timeout=3)
                log.info("[Ollama] ✅ Уже запущен (подтверждено под локом)")
                return True
            except Exception:
                pass

            log.warning("[Ollama] Сервис не отвечает — запускаю автоматически…")

            # На Windows: ищем ollama.exe в стандартных путях установки
            is_windows = _platform.system() == "Windows"
            if is_windows:
                import shutil
                ollama_cmd = shutil.which("ollama") or r"C:\Users\Public\ollama\ollama.exe"
                popen_kwargs: dict = {
                    "stdout": subprocess.DEVNULL,
                    "stderr": subprocess.DEVNULL,
                    "creationflags": subprocess.CREATE_NO_WINDOW,  # не показывает консоль
                }
            else:
                ollama_cmd = "ollama"
                popen_kwargs = {
                    "stdout": subprocess.DEVNULL,
                    "stderr": subprocess.DEVNULL,
                }

            log.info("[Ollama] Команда запуска: %s serve", ollama_cmd)

            try:
                ArgosCore._ollama_proc = subprocess.Popen(
                    [ollama_cmd, "serve"],
                    **popen_kwargs,
                )
                log.info("[Ollama] Процесс запущен (PID %s), жду готовности…", ArgosCore._ollama_proc.pid)
            except FileNotFoundError:
                log.error(
                    "[Ollama] Исполняемый файл ollama не найден (путь: %s). "
                    "Скачай с https://ollama.com и установи.",
                    ollama_cmd,
                )
                return False
            except Exception as exc:
                log.error("[Ollama] Не удалось запустить: %s", exc)
                return False

            # Ждём готовности — до 30 секунд
            deadline = time.time() + 30
            _last_progress_log = time.time()
            while time.time() < deadline:
                time.sleep(1)
                try:
                    requests.get(ping_url, timeout=2)
                    log.info("[Ollama] ✅ Сервис запущен успешно (PID %s)", ArgosCore._ollama_proc.pid)
                    return True
                except Exception:
                    pass
                # Логируем прогресс каждые 5 секунд
                if time.time() - _last_progress_log >= 5:
                    remaining = max(0, int(deadline - time.time()))
                    log.info("[Ollama] Жду запуска… осталось ~%d сек", remaining)
                    _last_progress_log = time.time()

            log.error("[Ollama] ❌ Сервис не поднялся за 30 секунд (PID %s)", ArgosCore._ollama_proc.pid)
            return False

    def _ensure_ollama_model(self, model: str) -> bool:
        """Проверяет наличие модели в Ollama и скачивает её при отсутствии.

        Returns:
            True  — модель доступна (уже была или успешно скачана).
            False — не удалось скачать.
        """
        base_url = self.ollama_url.replace("/api/generate", "")
        tags_url = base_url.rstrip("/") + "/api/tags"
        try:
            tags_res = requests.get(tags_url, timeout=5)
            tags_res.raise_for_status()
            available = [m.get("name", "") for m in tags_res.json().get("models", [])]
            # Ollama хранит теги как «model:tag», поэтому сравниваем по базовому имени
            if any(m == model or m.startswith(model + ":") for m in available):
                return True
        except Exception as exc:
            log.warning("[Ollama] Не удалось получить список моделей: %s", exc)

        log.warning("[Ollama] Модель '%s' не найдена — пытаюсь скачать…", model)
        try:
            result = subprocess.run(
                ["ollama", "pull", model],
                timeout=300,
                capture_output=True,
                text=True,
            )
            if result.returncode == 0:
                log.info("[Ollama] ✅ Модель '%s' успешно скачана", model)
                return True
            log.error("[Ollama] Не удалось скачать модель '%s': %s", model, result.stderr.strip())
        except FileNotFoundError:
            log.error("[Ollama] Исполняемый файл ollama не найден — скачать модель невозможно")
        except subprocess.TimeoutExpired:
            log.error("[Ollama] Таймаут при скачивании модели '%s'", model)
        except Exception as exc:
            log.error("[Ollama] Ошибка при скачивании модели '%s': %s", model, exc)
        return False

    def _ask_ollama(self, context: str, user_text: str) -> str | None:
        if not self._ensure_ollama_running():
            log.error("[Ollama] _ask_ollama: сервис недоступен, запрос отменён")
            return None
        try:
            # Добавляем историю в промпт
            hist = self.context.get_prompt_context()
            full_prompt = f"{context}\n\n{hist}\n\nUser: {user_text}\nArgos:"
            model = os.getenv("OLLAMA_MODEL", "llama3.2:1b")
            ollama_timeout = int(os.getenv("OLLAMA_TIMEOUT", "600"))
            log.info("[Ollama] Отправляю запрос → %s | модель: %s", self.ollama_url, model)
            res = requests.post(
                self.ollama_url,
                json={"model": model, "prompt": full_prompt, "stream": False},
                timeout=ollama_timeout
            )
            if res.status_code == 404:
                log.warning("[Ollama] Модель '%s' не найдена (HTTP 404) — пробую скачать и повторить", model)
                if self._ensure_ollama_model(model):
                    res = requests.post(
                        self.ollama_url,
                        json={"model": model, "prompt": full_prompt, "stream": False},
                        timeout=ollama_timeout,
                    )
                else:
                    log.error("[Ollama] Не удалось получить модель '%s' — запрос отменён", model)
                    return None
            response_text = res.json().get('response') if res.ok else None
            if response_text:
                log.info("[Ollama] ✅ Ответ получен (%d симв.)", len(response_text))
            else:
                log.warning("[Ollama] Пустой ответ от модели %s (HTTP %s)", model, res.status_code)
            return response_text
        except Exception as e:
            log.error("[Ollama] Ошибка запроса к %s: %s", self.ollama_url, e)
            return None

    def _auto_providers(self) -> list[tuple[str, callable]]:
        providers = []
        if self.model and not self._is_provider_temporarily_disabled("Gemini"):
            providers.append(("Gemini", self._ask_gemini))
        if self._has_gigachat_config() and not self._is_provider_temporarily_disabled("GigaChat"):
            providers.append(("GigaChat", self._ask_gigachat))
        if self._has_yandexgpt_config() and not self._is_provider_temporarily_disabled("YandexGPT"):
            providers.append(("YandexGPT", self._ask_yandexgpt))
        providers.append(("Ollama", self._ask_ollama))
        return providers[:self.auto_collab_max_models]

    def _ask_auto_consensus(self, context: str, user_text: str) -> tuple[str | None, str | None]:
        providers = self._auto_providers()
        if not providers:
            return None, None

        if not self.auto_collab_enabled:
            for provider_name, fn in providers:
                answer = fn(context, user_text)
                if answer:
                    return answer, provider_name
            return None, None

        collected: list[tuple[str, str]] = []
        for provider_name, fn in providers:
            peer_block = ""
            if collected:
                peer_opinions = "\n".join(
                    f"- {name}: {text}" for name, text in collected
                )
                peer_block = (
                    "\n\nНиже ответы других ИИ-моделей. Учти их, исправь слабые места, "
                    "но не повторяй дословно и не упоминай названия моделей в финальном тексте:\n"
                    f"{peer_opinions}"
                )
            answer = fn(context + peer_block, user_text)
            if answer and answer.strip():
                collected.append((provider_name, answer.strip()))

        if not collected:
            return None, None
        if len(collected) == 1:
            return collected[0][1], collected[0][0]

        synthesis_prompt = (
            "Сделай единый, согласованный ответ пользователю на русском.\n"
            "Правила: по делу, без воды, без упоминания моделей, устранить противоречия, "
            "если есть неопределённость — явно это обозначить.\n\n"
            f"Запрос пользователя: {user_text}\n\n"
            "Черновики разных моделей:\n"
            + "\n".join(f"- {name}: {text}" for name, text in collected)
        )

        for provider_name, fn in providers:
            final_answer = fn(context, synthesis_prompt)
            if final_answer and final_answer.strip():
                used = "+".join(name for name, _ in collected)
                return final_answer.strip(), f"Auto-Consensus:{used}→{provider_name}"

        used = "+".join(name for name, _ in collected)
        merged = "\n\n".join(f"{name}: {text}" for name, text in collected)
        return merged, f"Auto-Consensus:{used}"

    # ═══════════════════════════════════════════════════════
    # ОСНОВНАЯ ЛОГИКА
    # ═══════════════════════════════════════════════════════
    def process_logic(self, user_text: str, admin, flasher) -> dict:
        q_data = self.quantum.generate_state()
        if self.context:
            self.context.set_quantum_state(q_data["name"])
        if self.curiosity:
            self.curiosity.touch_activity(user_text)
        t = user_text.lower()

        # Проверяем напоминания
        if self.memory:
            for r in self.memory.check_reminders():
                self.say(r)

        # Tool Calling — модель сама выбирает инструменты по JSON-схемам
        if self.tool_calling:
            tool_answer = self.tool_calling.try_handle(user_text, admin, flasher)
            if tool_answer:
                self.context.add("user", user_text)
                self.context.add("argos", tool_answer)
                self._remember_dialog_turn(user_text, tool_answer, "ToolCalling")
                if self.db:
                    self.db.log_chat("user", user_text)
                    self.db.log_chat("argos", tool_answer, "ToolCalling")
                self.say(tool_answer)
                return {"answer": tool_answer, "state": "ToolCalling"}

        # Агентный режим — цепочка задач
        agent_result = self.agent.execute_plan(user_text, admin, flasher)
        if agent_result:
            self.context.add("user", user_text)
            self.context.add("argos", agent_result)
            self._remember_dialog_turn(user_text, agent_result, "Agent")
            if self.db:
                self.db.log_chat("user", user_text)
                self.db.log_chat("argos", agent_result, "Agent")
            self.say("Агент выполнил задание.")
            return {"answer": agent_result, "state": "Agent"}

        # Одиночная команда
        intent = self.execute_intent(user_text, admin, flasher)
        if intent:
            self.context.add("user", user_text)
            self.context.add("argos", intent)
            self._remember_dialog_turn(user_text, intent, "System")
            if self.db:
                self.db.log_chat("user", user_text)
                self.db.log_chat("argos", intent, "System")
            self.say(intent)
            return {"answer": intent, "state": "System"}

        # Плагины SkillLoader v2
        if self.skill_loader:
            skill_answer = self.skill_loader.dispatch(user_text, core=self)
            if skill_answer:
                self.context.add("user", user_text)
                self.context.add("argos", skill_answer)
                self._remember_dialog_turn(user_text, skill_answer, "Skill")
                if self.db:
                    self.db.log_chat("user", user_text)
                    self.db.log_chat("argos", skill_answer, "Skill")
                self.say(skill_answer)
                return {"answer": skill_answer, "state": "Skill"}

        # Веб-поиск при необходимости
        if any(w in t for w in ["найди", "новости", "кто такой", "что такое"]):
            web = self.scrapper.quick_search(user_text)
            user_text = f"Данные из сети: {web}\nЗапрос: {user_text}"

        # Контекст + память для ИИ
        context = (
            f"Ты Аргос — всевидящий ИИ-ассистент. Квантовое состояние: {q_data['name']}. "
            f"Создатель: Всеволод. Год: 2026. Отвечай по-русски, кратко и по делу."
        )
        if self.memory:
            mc = self.memory.get_context()
            if mc:
                context += f"\n\n{mc}"
            rag_ctx = self.memory.get_rag_context(user_text, top_k=4)
            if rag_ctx:
                context += f"\n\n{rag_ctx}"

        answer = None
        engine = q_data['name']

        if self.ai_mode == "gemini":
            answer = self._ask_gemini(context, user_text)
            engine = f"{q_data['name']} (Gemini)"
        elif self.ai_mode == "gigachat":
            answer = self._ask_gigachat(context, user_text)
            engine = f"{q_data['name']} (GigaChat)"
        elif self.ai_mode == "yandexgpt":
            answer = self._ask_yandexgpt(context, user_text)
            engine = f"{q_data['name']} (YandexGPT)"
        elif self.ai_mode == "ollama":
            answer = self._ask_ollama(context, user_text)
            engine = f"{q_data['name']} (Ollama)"
        else:
            answer, auto_engine = self._ask_auto_consensus(context, user_text)
            if auto_engine:
                engine = f"{q_data['name']} ({auto_engine})"

        if not answer:
            if self.ai_mode == "gemini":
                if self._last_gemini_rate_limited:
                    answer = self._gemini_rate_limit_text()
                else:
                    answer = "Gemini недоступен в текущем режиме. Переключите режим ИИ на Auto, GigaChat, YandexGPT или Ollama."
            elif self.ai_mode == "gigachat":
                answer = "GigaChat недоступен в текущем режиме. Проверьте токен/credentials или переключите режим ИИ."
            elif self.ai_mode == "yandexgpt":
                answer = "YandexGPT недоступен в текущем режиме. Проверьте IAM_TOKEN/FOLDER_ID или переключите режим ИИ."
            elif self.ai_mode == "ollama":
                answer = "Ollama недоступен в текущем режиме. Проверьте локальный сервер Ollama или переключите режим ИИ."
            else:
                answer = "Связь с ядрами ИИ разорвана. Режим оффлайн."
            engine = "Offline"

        # Сохраняем в контекст и БД
        self.context.add("user", user_text)
        self.context.add("argos", answer)
        self._remember_dialog_turn(user_text, answer, engine)
        if self.db:
            self.db.log_chat("user", user_text)
            self.db.log_chat("argos", answer, engine)

        self.say(answer)
        return {"answer": answer, "state": engine}

    async def process_logic_async(self, user_text: str, admin, flasher) -> dict:
        """Неблокирующий async-вход для UI/ботов.
        Вся синхронная логика выполняется в thread executor.
        """
        return await asyncio.to_thread(self.process_logic, user_text, admin, flasher)

    # ═══════════════════════════════════════════════════════
    # ДИСПЕТЧЕР КОМАНД — 50+ интентов
    # ═══════════════════════════════════════════════════════
    def execute_intent(self, text: str, admin, flasher) -> str | None:
        t = text.lower()

        if any(k in t for k in [
            "проверь работу ии системы",
            "проверь работу ai системы",
            "проверь работу ии",
            "режимов эволюции и обучения",
            "режымов иволюции и обучения",
            "познание любопытство диолог",
            "познание любопытство диалог",
        ]):
            return self._ai_modes_diagnostic()

        if self._homeostasis_block_heavy and any(k in t for k in [
            "посмотри на экран", "что на экране", "посмотри в камеру", "анализ фото",
            "проанализируй изображение", "компиля", "compile", "создай прошивку", "прошей шлюз", "прошей gateway"
        ]):
            return "🔥 Гомеостаз: тяжёлая операция временно заблокирована (режим Protective/Unstable)."

        if self.homeostasis and any(k in t for k in ["гомеостаз статус", "статус гомеостаза", "homeostasis status"]):
            return self.homeostasis.status()
        if self.homeostasis and any(k in t for k in ["гомеостаз вкл", "включи гомеостаз", "homeostasis on"]):
            return self.homeostasis.start()
        if self.homeostasis and any(k in t for k in ["гомеостаз выкл", "выключи гомеостаз", "homeostasis off"]):
            return self.homeostasis.stop()

        if self.curiosity and any(k in t for k in ["любопытство статус", "статус любопытства", "curiosity status"]):
            return self.curiosity.status()
        if self.curiosity and any(k in t for k in ["любопытство вкл", "включи любопытство", "curiosity on"]):
            return self.curiosity.start()
        if self.curiosity and any(k in t for k in ["любопытство выкл", "выключи любопытство", "curiosity off"]):
            return self.curiosity.stop()
        if self.curiosity and any(k in t for k in ["любопытство сейчас", "curiosity now"]):
            return self.curiosity.ask_now()

        if self.git_ops and any(k in t for k in ["git статус", "гит статус", "git status"]):
            return self.git_ops.status()
        if self.git_ops and any(k in t for k in ["git пуш", "гит пуш", "git push"]):
            return self.git_ops.push()
        if self.git_ops and any(k in t for k in ["git автокоммит и пуш", "гит автокоммит и пуш", "git auto push", "git commit and push"]):
            msg = text
            for marker in ["git автокоммит и пуш", "гит автокоммит и пуш", "git auto push", "git commit and push"]:
                if marker in msg.lower():
                    idx = msg.lower().find(marker)
                    msg = msg[idx + len(marker):].strip()
                    break
            if not msg:
                msg = "chore: argos autonomous update"
            return self.git_ops.commit_and_push(msg)
        if self.git_ops and (t.startswith("git коммит ") or t.startswith("гит коммит ") or t.startswith("git commit ")):
            msg = text
            for marker in ["git коммит", "гит коммит", "git commit"]:
                if marker in msg.lower():
                    idx = msg.lower().find(marker)
                    msg = msg[idx + len(marker):].strip()
                    break
            return self.git_ops.commit(msg)

        if hasattr(admin, "set_alert_callback"):
            admin.set_alert_callback(self._on_alert)

        if hasattr(admin, "set_role") and any(k in t for k in ["роль доступа", "установи роль", "режим доступа"]):
            if "статус" in t and hasattr(admin, "security_status"):
                return admin.security_status()
            role = text.split()[-1].strip().lower()
            return admin.set_role(role)

        if hasattr(admin, "security_status") and any(k in t for k in ["статус безопасности", "security status", "audit status"]):
            return admin.security_status()

        if any(k in t for k in ["оператор режим вкл", "включи операторский режим"]):
            self.operator_mode = True
            return "🎛️ Операторский режим включён. Доступны сценарии: оператор инцидент / оператор диагностика / оператор восстановление"
        if any(k in t for k in ["оператор режим выкл", "выключи операторский режим"]):
            self.operator_mode = False
            return "🎛️ Операторский режим выключен."
        if any(k in t for k in ["оператор инцидент", "сценарий инцидент"]):
            return self._operator_incident(admin)
        if any(k in t for k in ["оператор диагностика", "сценарий диагностика"]):
            return self._operator_diagnostics(admin)
        if any(k in t for k in ["оператор восстановление", "сценарий восстановление"]):
            return self._operator_recovery()

        if self.module_loader and any(k in t for k in ["модули", "список модулей", "modules"]):
            return self.module_loader.list_modules()

        if self.tool_calling and any(k in t for k in ["схемы инструментов", "tool schema", "tool calling schema", "json схемы инструментов"]):
            return json.dumps(self.tool_calling.tool_schemas(), ensure_ascii=False, indent=2)

        # ── Мастер создания умной системы (пошаговый) ─────
        if self._smart_create_wizard is not None:
            if any(k in t.strip() for k in ["отмена", "cancel", "стоп"]):
                self._smart_create_wizard = None
                return "🛑 Мастер создания отменён."
            return self._continue_smart_create_wizard(text)

        # ── Dynamic modules dispatcher ────────────────────
        if self.module_loader:
            mod_answer = self.module_loader.dispatch(text, admin=admin, flasher=flasher)
            if mod_answer:
                return mod_answer

        # ── Home Assistant ────────────────────────────────
        if self.ha:
            if any(k in t for k in ["ha статус", "home assistant статус", "статус home assistant"]):
                return self.ha.health()
            if any(k in t for k in ["ha состояния", "home assistant состояния"]):
                return self.ha.list_states()
            if t.startswith("ha сервис "):
                # ha сервис light turn_on entity_id=light.kitchen brightness=180
                parts = text.split()
                if len(parts) < 4:
                    return "Формат: ha сервис [domain] [service] [key=value ...]"
                domain = parts[2]
                service = parts[3]
                data = {}
                for item in parts[4:]:
                    if "=" in item:
                        key, val = item.split("=", 1)
                        data[key] = val
                return self.ha.call_service(domain, service, data)
            if t.startswith("ha mqtt "):
                # ha mqtt home/livingroom/light/set state=ON brightness=180
                parts = text.split()
                if len(parts) < 3:
                    return "Формат: ha mqtt [topic] [key=value ...]"
                topic = parts[2]
                payload = {}
                for item in parts[3:]:
                    if "=" in item:
                        key, val = item.split("=", 1)
                        payload[key] = val
                if not payload:
                    payload = {"msg": "on"}
                return self.ha.publish_mqtt(topic, payload)

        # ── Мониторинг ────────────────────────────────────
        if any(k in t for k in ["статус системы", "чек-ап", "состояние здоровья"]):
            if admin:
                stats = admin.get_stats()
            else:
                import psutil as _ps
                c = _ps.cpu_percent(interval=0.5)
                r = _ps.virtual_memory().percent
                disk = _ps.disk_usage('/')
                stats = f"CPU: {c}% | RAM: {r}% | Диск: {disk.free // (2**30)}GB свободно"
            return f"{stats}\n{self.sensors.get_full_report()}"
        if "список процессов" in t:
            return admin.list_processes()
        if "выключи систему" in t:
            return admin.manage_power("shutdown")
        if any(k in t for k in ["убей процесс", "завершить процесс"]):
            return admin.kill_process(text.split()[-1])

        # ── Файлы ─────────────────────────────────────────
        if any(k in t for k in ["покажи файлы", "список файлов"]) or t.startswith("файлы "):
            path = text.replace("аргос","").replace("покажи файлы","").replace("список файлов","").replace("файлы","").strip()
            return admin.list_dir(path or ".")
        if "прочитай файл" in t:
            path = text.replace("аргос","").replace("прочитай файл","").strip()
            return admin.read_file(path)
        if any(k in t for k in ["создай файл", "напиши файл"]):
            parts = text.replace("создай файл","").replace("напиши файл","").strip().split(maxsplit=1)
            return admin.create_file(parts[0] if parts else "note.txt", parts[1] if len(parts)>1 else "")
        if any(k in t for k in ["удали файл", "удали папку"]):
            return admin.delete_item(text.replace("аргос","").replace("удали файл","").replace("удали папку","").strip())
        if any(k in t for k in ["добавь в файл", "дополни файл", "допиши в файл"]):
            for marker in ("добавь в файл", "дополни файл", "допиши в файл"):
                if marker in t:
                    tail = text.split(marker, 1)[-1].strip()
                    break
            parts = tail.split(maxsplit=1)
            if len(parts) >= 2:
                return admin.append_file(parts[0], parts[1])
            return "Формат: добавь в файл [путь] [текст]"
        if any(k in t for k in ["отредактируй файл", "измени файл", "замени в файле"]):
            for marker in ("отредактируй файл", "измени файл", "замени в файле"):
                if marker in t:
                    tail = text.split(marker, 1)[-1].strip()
                    break
            parts = tail.split("→", 1) if "→" in tail else tail.split("->", 1)
            if len(parts) == 2:
                path_and_old = parts[0].strip().split(maxsplit=1)
                if len(path_and_old) == 2:
                    return admin.edit_file(path_and_old[0], path_and_old[1], parts[1].strip())
            return "Формат: отредактируй файл [путь] [старый текст] → [новый текст]"
        if any(k in t for k in ["переименуй файл", "переименуй папку"]):
            for marker in ("переименуй файл", "переименуй папку"):
                if marker in t:
                    tail = text.split(marker, 1)[-1].strip()
                    break
            parts = tail.split(maxsplit=1)
            if len(parts) == 2:
                return admin.rename_file(parts[0], parts[1])
            return "Формат: переименуй файл [старый_путь] [новый_путь]"
        if any(k in t for k in ["скопируй файл", "скопируй папку"]):
            for marker in ("скопируй файл", "скопируй папку"):
                if marker in t:
                    tail = text.split(marker, 1)[-1].strip()
                    break
            parts = tail.split(maxsplit=1)
            if len(parts) == 2:
                return admin.copy_file(parts[0], parts[1])
            return "Формат: скопируй файл [источник] [назначение]"

        # ── Терминал ──────────────────────────────────────
        if any(k in t for k in ["консоль", "терминал"]):
            if not self.context.allow_root:
                return "⛔ Команды терминала ограничены текущим квантовым профилем (без root-допуска)."
            cmd = text.split("консоль",1)[-1].strip() if "консоль" in t else text.split("терминал",1)[-1].strip()
            return admin.run_cmd(cmd, user="argos")

        # ── Vision ────────────────────────────────────────
        if self.vision:
            if any(k in t for k in ["посмотри на экран", "что на экране", "скриншот"]):
                question = text.replace("аргос","").replace("посмотри на экран","").replace("что на экране","").replace("скриншот","").strip()
                return self.vision.look_at_screen(question or "Что происходит на экране?")
            if any(k in t for k in ["посмотри в камеру", "что видит камера", "включи камеру"]):
                question = text.replace("аргос","").replace("посмотри в камеру","").replace("что видит камера","").strip()
                return self.vision.look_through_camera(question or "Что ты видишь?")
            if "проанализируй изображение" in t or "анализ фото" in t:
                path = text.split()[-1]
                return self.vision.analyze_file(path)

        # ── Агент ─────────────────────────────────────────
        if "отчёт агента" in t or "последний план" in t:
            return self.agent.last_report()
        if "останови агента" in t:
            return self.agent.stop()

        # ── Контекст диалога ──────────────────────────────
        if any(k in t for k in ["сброс контекста", "забудь разговор", "новый диалог"]):
            return self.context.clear()
        if "контекст диалога" in t:
            return self.context.summary()

        # ── Репликация + IoT ──────────────────────────────
        if any(k in t for k in [
            "создай образ", "создай os образ", "клонируй себя",
            "образ argos", "argos os образ", "argos os клон",
            "создай клон os", "создай клон себя",
        ]):
            return self.replicator.create_os_image()

        # ── Адаптивный сборщик под устройство ────────────────
        if any(k in t for k in [
            "создай образ для устройства", "создай образ под устройство",
            "адаптивный образ", "образ под это устройство",
            "собери образ для этого устройства",
        ]):
            try:
                from src.device_scanner import AdaptiveImageBuilder
                return AdaptiveImageBuilder().build_for_this_device()
            except Exception as e:
                return f"❌ AdaptiveImageBuilder: {e}"

        if any(k in t for k in [
            "скан устройства", "сканировать устройство",
            "профиль устройства", "device scan", "device profile",
            "проверь железо", "какое железо", "железо инфо",
            "железо информация", "аппаратное обеспечение",
            "характеристики устройства", "инфо об устройстве",
            "диагностика железа", "хардвер", "железо статус",
        ]):
            try:
                from src.device_scanner import DeviceScanner
                return DeviceScanner().report()
            except Exception as e:
                return f"❌ DeviceScanner: {e}"

        if "создай образ для" in t:
            try:
                target = t.replace("создай образ для", "").strip().split()[0]
                from src.device_scanner import AdaptiveImageBuilder
                return AdaptiveImageBuilder().build_for_target(target)
            except Exception as e:
                return f"❌ {e}"

        if any(k in t for k in ["создай копию", "репликация"]):
            return self.replicator.create_replica()
        if "сканируй порты" in t:
            return f"Порты: {flasher.scan_ports()}"
        if any(k in t for k in [
            "argos os для android",
            "аргос ос для android",
            "argos os android",
            "аргос ос android",
            "argos os для телефона",
            "argos os для планшета",
            "argos os для tv",
        ]):
            if hasattr(flasher, "android_argos_os_plan"):
                profile = "phone"
                if "планшет" in t or "tablet" in t:
                    profile = "tablet"
                elif "tv" in t or "телевиз" in t:
                    profile = "tv"
                return flasher.android_argos_os_plan(profile=profile, preserve_features=True)
            return "❌ Модуль android_argos_os_plan недоступен в текущем flasher."
        if any(k in t for k in [
            "модификации прошивок носимых устройств аргос ос",
            "модификации прошивок носимых устройств argos os",
            "модификация прошивки носимого",
            "модифицируй прошивку носимого",
        ]):
            if hasattr(flasher, "wearable_firmware_mod"):
                port_match = re.search(r"(/dev/\S+|\bCOM\d+\b)", text, flags=re.IGNORECASE)
                port = port_match.group(1) if port_match else ""
                include_4pda = "4pda" in t
                device = re.sub(
                    r"(?i)(модификации прошивок носимых устройств аргос ос|"
                    r"модификации прошивок носимых устройств argos os|"
                    r"модификация прошивки носимого|модифицируй прошивку носимого)",
                    "",
                    text,
                )
                device = re.sub(r"(?i)\b4pda\b", "", device)
                if port:
                    device = device.replace(port, "")
                device = " ".join(device.split()) or "argos os wearable"
                return flasher.wearable_firmware_mod(
                    device=device,
                    port=port,
                    avatar="sigtrip",
                    include_4pda=include_4pda,
                )
            return "❌ Модуль wearable_firmware_mod недоступен в текущем flasher."
        if any(k in t for k in ["найди usb чипы", "usb чипы", "смарт прошивка usb", "smart flasher usb"]):
            if hasattr(flasher, "detect_usb_chips_report"):
                return flasher.detect_usb_chips_report()
            return "❌ Smart Flasher недоступен в текущем flasher-модуле."
        if any(k in t for k in ["умная прошивка", "smart flash", "смарт прошивка"]):
            if hasattr(flasher, "smart_flash"):
                parts = text.split()
                port = None
                for p in parts:
                    if p.startswith("/dev/") or p.upper().startswith("COM"):
                        port = p
                        break
                return flasher.smart_flash(port=port)

        # ── OTG (USB Host) ────────────────────────────────
        if any(k in t for k in ["otg статус", "otg status", "отг статус"]):
            return self.otg.status() if self.otg else "❌ OTG Manager не инициализирован."
        if any(k in t for k in ["otg скан", "otg scan", "otg устройства", "отг скан"]):
            return self.otg.scan_report() if self.otg else "❌ OTG Manager не инициализирован."
        if any(k in t for k in ["otg подключи", "otg connect", "отг подключи"]):
            if self.otg:
                parts = text.split()
                idx = next((i for i, p in enumerate(parts)
                            if p.lower() in ("подключи", "connect", "подключи")), -1)
                device_id = parts[idx + 1] if idx >= 0 and idx + 1 < len(parts) else ""
                baud = 115200
                for p in parts:
                    if p.isdigit() and int(p) in (9600, 19200, 38400, 57600, 115200, 230400, 460800):
                        baud = int(p)
                return self.otg.connect_serial(device_id, baud) if device_id else "❌ OTG: укажи ID или порт устройства."
            return "❌ OTG Manager не инициализирован."
        if any(k in t for k in ["otg отправь", "otg send", "отг отправь"]):
            if self.otg:
                parts = text.split(maxsplit=3)
                if len(parts) >= 3:
                    device_id = parts[2]
                    data = parts[3] if len(parts) > 3 else ""
                    return self.otg.send_data(device_id, data)
            return "❌ OTG Manager не инициализирован."
        if any(k in t for k in ["otg отключи", "otg disconnect", "отг отключи"]):
            if self.otg:
                parts = text.split()
                device_id = parts[-1] if len(parts) > 1 else ""
                return self.otg.disconnect(device_id) if device_id else "❌ OTG: укажи ID устройства."
            return "❌ OTG Manager не инициализирован."
        if any(k in t for k in ["otg мониторинг", "otg monitor", "отг мониторинг"]):
            return self.otg.start_monitor() if self.otg else "❌ OTG Manager не инициализирован."
        if any(k in t for k in ["rs ttl", "uart ttl", "ttl uart", "rs-ttl", "uart-ttl", "ttl-uart"]):
            return self._rs_ttl_help()
        if any(k in t for k in [
            "проверь драйверы", "драйверы android", "драйверы gui",
            "низкоуровневые драйверы", "driver check",
        ]):
            return self._low_level_drivers_report()

        # ── ГОСТ Криптография ─────────────────────────────
        if any(k in t for k in ["гост статус", "gost статус", "гост инфо"]):
            try:
                from src.security.gost_cipher import gost_status
                return gost_status()
            except Exception as e:
                return f"❌ ГОСТ: {e}"
        if any(k in t for k in ["гост хеш", "gost hash", "стрибог"]):
            payload = text.split(maxsplit=2)[-1] if len(text.split()) > 2 else ""
            if not payload:
                return "❌ ГОСТ хеш: укажи текст. Пример: гост хеш привет"
            try:
                from src.security.gost_cipher import gost_hash
                h = gost_hash(payload, bits=256).hex()
                return f"🔐 Стрибог-256:\n   {payload!r}\n   → {h}"
            except Exception as e:
                return f"❌ ГОСТ хеш: {e}"
        if any(k in t for k in ["гост p2p статус", "gost p2p"]):
            try:
                from src.connectivity.gost_p2p import get_gost_p2p
                return get_gost_p2p().status()
            except Exception as e:
                return f"❌ ГОСТ P2P: {e}"

        # ── Grist P2P Хранилище ───────────────────────────
        if any(k in t for k in ["grist статус", "грист статус", "grist status"]):
            return self.grist.status() if self.grist else "❌ Grist не инициализирован."
        if any(k in t for k in ["grist таблицы", "grist tables"]):
            return self.grist.list_tables() if self.grist else "❌ Grist не инициализирован."
        if any(k in t for k in ["grist список", "grist list", "grist ключи"]):
            return self.grist.list_keys() if self.grist else "❌ Grist не инициализирован."
        if any(k in t for k in ["grist ноды", "grist nodes", "grist p2p"]):
            return self.grist.get_nodes() if self.grist else "❌ Grist не инициализирован."
        if any(k in t for k in ["grist синк", "grist sync", "grist синхронизация"]):
            if self.grist:
                return self.grist.sync_node()
            return "❌ Grist не инициализирован."
        if any(k in t for k in ["grist сохрани", "grist save", "grist запиши"]):
            if self.grist:
                # Формат: "grist сохрани <ключ> <значение>"
                # parts[0]=grist, parts[1]=сохрани, parts[2]=ключ, parts[3]=значение
                parts = text.split(maxsplit=3)
                key   = parts[2] if len(parts) > 2 else ""
                val   = parts[3] if len(parts) > 3 else ""
                if not key:
                    return "❌ Grist сохрани: укажи ключ и значение.\n   Пример: grist сохрани моя_переменная значение"
                return self.grist.save(key, val)
            return "❌ Grist не инициализирован."
        if any(k in t for k in ["grist получи", "grist get", "grist читай"]):
            if self.grist:
                # Формат: "grist получи <ключ>"
                # parts[0]=grist, parts[1]=получи, parts[2]=ключ
                parts = text.split(maxsplit=2)
                key   = parts[2] if len(parts) > 2 else ""
                if not key:
                    return "❌ Grist получи: укажи ключ. Пример: grist получи моя_переменная"
                return self.grist.get(key)
            return "❌ Grist не инициализирован."

        # ── Голос ─────────────────────────────────────────
        if any(k in t for k in [
            "проверь работу голосовых служб",
            "проверь голосовые службы",
            "статус голосовых служб",
            "голосовых служб ввода и вывода",
            "голосовых служб вода и вывода",
            "voice services check",
        ]):
            return self.voice_services_report()
        if any(k in t for k in ["голос вкл", "включи голос"]):
            self.voice_on = True; return "🔊 Голосовой модуль активирован."
        if any(k in t for k in ["голос выкл", "выключи голос"]):
            self.voice_on = False; return "🔇 Голосовой модуль отключён."
        if any(k in t for k in ["режим ии авто", "модель авто", "ai mode auto"]):
            return self.set_ai_mode("auto")
        if any(k in t for k in ["режим ии gemini", "модель gemini", "ai mode gemini"]):
            return self.set_ai_mode("gemini")
        if any(k in t for k in ["режим ии gigachat", "модель gigachat", "ai mode gigachat", "режим ии гигачат"]):
            return self.set_ai_mode("gigachat")
        if any(k in t for k in ["режим ии yandexgpt", "модель yandexgpt", "ai mode yandexgpt", "режим ии яндекс"]):
            return self.set_ai_mode("yandexgpt")
        if any(k in t for k in ["режим ии ollama", "модель ollama", "ai mode ollama"]):
            return self.set_ai_mode("ollama")
        if any(k in t for k in ["текущий режим ии", "какая модель", "ai mode"]):
            return f"🤖 Текущий режим ИИ: {self.ai_mode_label()}"
        if any(k in t for k in ["включи wake word", "wake word вкл"]):
            return self.start_wake_word(admin, flasher)

        # ── Навыки ────────────────────────────────────────
        if self.skill_loader and any(k in t for k in ["навыки v2", "skills v2", "skillloader"]):
            return self.skill_loader.list_skills()
        if self.skill_loader and t.startswith("загрузи навык "):
            name = text.split("загрузи навык ", 1)[-1].strip()
            return self.skill_loader.load(name, core=self)
        if self.skill_loader and t.startswith("выгрузи навык "):
            name = text.split("выгрузи навык ", 1)[-1].strip()
            return self.skill_loader.unload(name)
        if self.skill_loader and t.startswith("перезагрузи навык "):
            name = text.split("перезагрузи навык ", 1)[-1].strip()
            return self.skill_loader.reload(name, core=self)

        if "дайджест" in t:
            from src.skills.content_gen import ContentGen
            return ContentGen().generate_digest()
        if "опубликуй" in t:
            from src.skills.content_gen import ContentGen
            return ContentGen().publish()
        if any(k in t for k in ["крипто", "биткоин", "bitcoin", "ethereum"]):
            from src.skills.crypto_monitor import CryptoSentinel
            return CryptoSentinel().report()
        if any(k in t for k in ["сканируй сеть", "сетевой призрак"]):
            from src.skills.net_scanner import NetGhost
            return NetGhost().scan()
        if any(k in t for k in ["список навыков", "навыки аргоса"]):
            if self.skill_loader:
                return self.skill_loader.list_skills()
            from src.skills.evolution import ArgosEvolution
            return ArgosEvolution().list_skills()
        if any(k in t for k in ["напиши навык", "создай навык"]):
            from src.skills.evolution import ArgosEvolution
            desc = text.replace("напиши навык","").replace("создай навык","").strip()
            return ArgosEvolution(ai_core=self).generate_skill(desc)

        # ── Память ────────────────────────────────────────
        if self.memory:
            if "запомни" in t:
                return self.memory.parse_and_remember(text.replace("аргос","").replace("запомни","").strip())
            if any(k in t for k in ["что ты знаешь", "моя память", "покажи память"]):
                return self.memory.format_memory()
            if any(k in t for k in ["поиск по памяти", "найди в памяти", "rag память"]):
                q = text
                for pref in ["поиск по памяти", "найди в памяти", "rag память", "аргос"]:
                    q = q.replace(pref, "")
                q = q.strip()
                if not q:
                    return "Формат: найди в памяти [запрос]"
                rag = self.memory.get_rag_context(q, top_k=5)
                return rag or "Ничего релевантного в векторной памяти не найдено."
            if any(k in t for k in ["граф знаний", "связи памяти", "мои связи"]):
                return self.memory.graph_report()
            if "забудь" in t and "разговор" not in t:
                return self.memory.forget(text.replace("аргос","").replace("забудь","").strip())
            if any(k in t for k in ["запиши заметку", "новая заметка"]):
                parts = text.replace("запиши заметку","").replace("новая заметка","").strip().split(":",1)
                return self.memory.add_note(parts[0].strip(), parts[1].strip() if len(parts)>1 else parts[0])
            if any(k in t for k in ["мои заметки", "список заметок"]):
                return self.memory.get_notes()
            if "прочитай заметку" in t:
                try: return self.memory.read_note(int(text.split()[-1]))
                except: return "Укажи номер: прочитай заметку 1"
            if "удали заметку" in t:
                try: return self.memory.delete_note(int(text.split()[-1]))
                except: return "Укажи номер: удали заметку 1"

        # ── Планировщик ───────────────────────────────────
        if self.scheduler:
            if any(k in t for k in ["расписание", "список задач"]):
                return self.scheduler.list_tasks()
            if any(k in t for k in ["каждые", "напомни", "ежедневно"]) or "через" in t or (t.strip().startswith("в ") and ":" in t):
                return self.scheduler.parse_and_add(text)
            if "удали задачу" in t:
                try: return self.scheduler.remove(int(text.split()[-1]))
                except: return "Укажи номер: удали задачу 1"

        # ── Алерты ────────────────────────────────────────
        if self.alerts:
            if any(k in t for k in ["статус алертов", "алерты"]):
                return self.alerts.status()
            if "установи порог" in t:
                try:
                    parts = text.split()
                    return self.alerts.set_threshold(parts[-2], float(parts[-1].replace("%","")))
                except: return "Формат: установи порог cpu 85"

        # ── Веб-панель ────────────────────────────────────
        if any(k in t for k in ["веб-панель", "веб панель", "dashboard", "открой панель"]):
            return self.start_dashboard(admin, flasher)

        # ── Геолокация ────────────────────────────────────
        if any(k in t for k in ["геолокация", "мой ip", "где я", "мой адрес"]):
            from src.connectivity.spatial import SpatialAwareness
            return SpatialAwareness(db=self.db).get_full_report()

        # ── Загрузчик ─────────────────────────────────────
        if any(k in t for k in ["загрузчик", "boot info"]):
            from src.security.bootloader_manager import BootloaderManager
            if not self._boot: self._boot = BootloaderManager()
            return self._boot.full_report()
        if "ARGOS-BOOT-CONFIRM" in t.upper():
            from src.security.bootloader_manager import BootloaderManager
            if not self._boot: self._boot = BootloaderManager()
            return self._boot.confirm("ARGOS-BOOT-CONFIRM")
        if any(k in t for k in ["установи persistence", "персистенс"]):
            from src.security.bootloader_manager import BootloaderManager
            if not self._boot: self._boot = BootloaderManager()
            return self._boot.install_persistence()
        if "обнови grub" in t:
            from src.security.bootloader_manager import BootloaderManager
            if not self._boot: self._boot = BootloaderManager()
            return self._boot.linux_update_grub()

        # ══════════════════════════════════════════════════
        # ПЛАТФОРМЕННОЕ АДМИНИСТРИРОВАНИЕ (Linux / Windows / Android)
        # ══════════════════════════════════════════════════
        if self.platform_admin:
            _platform_keywords = [
                # Статус
                "платформа статус", "platform status", "os статус",
                # Linux
                "apt установи", "apt удали", "apt обновить", "apt поиск", "apt список",
                "apt обновление", "linux установи пакет", "linux удали пакет",
                "linux обновить пакеты", "linux поиск пакета", "установленные пакеты linux",
                "snap установи", "snap список", "snap list",
                "сервис запусти", "сервис стоп", "сервис останови",
                "сервис перезапуск", "сервис статус", "сервис включи", "сервис отключи",
                "список сервисов", "все сервисы", "сервисы linux",
                "systemctl start", "systemctl stop", "systemctl restart",
                "systemctl status", "systemctl enable", "systemctl disable",
                "логи системы", "logи ", "journalctl",
                "диск linux", "диск использование",
                "размер папки", "df",
                "пользователь linux", "whoami linux", "linux кто я",
                "список пользователей linux", "пользователи linux",
                "добавь пользователя", "удали пользователя",
                "сеть linux", "ip адреса", "сетевые интерфейсы",
                "открытые порты", "порты linux", "ss linux", "netstat linux",
                "фаервол linux", "ufw статус", "firewall linux",
                "система linux", "linux инфо", "linux информация",
                "процессор linux", "cpu linux", "lscpu",
                "процессы linux", "top linux", "ps linux",
                # Windows
                "winget установи", "winget удали", "winget обновить", "winget поиск",
                "winget список", "winget upgrade", "windows установи", "windows удали",
                "windows обновить пакеты", "установленные пакеты windows",
                "windows сервис запусти", "windows сервис стоп",
                "windows сервис статус", "windows сервисы",
                "sc start", "sc stop", "sc query",
                "список сервисов windows",
                "реестр запрос",
                "задачи windows", "процессы windows", "tasklist",
                "убей задачу", "taskkill",
                "сеть windows", "ipconfig", "windows сеть",
                "фаервол windows", "windows firewall",
                "обновления windows", "windows update", "windows обновления",
                "ошибки windows", "event log windows", "windows логи",
                "диск windows", "windows диск",
                "система windows", "windows инфо", "systeminfo",
                "defender статус", "windows defender",
                "defender сканировать", "defender scan",
                "пользователи windows", "windows пользователи",
                "windows кто я", "whoami windows",
                # Android
                "adb устройства", "adb devices",
                "adb подключи", "adb отключи",
                "android приложения", "pm list packages", "список приложений android",
                "android системные приложения",
                "android установи", "pm install",
                "android удали", "pm uninstall",
                "android запусти", "android останови", "android очисти",
                "pkg установи", "pkg удали", "pkg обновить", "pkg поиск", "pkg список",
                "termux установи", "termux удали", "termux обновить",
                "termux поиск", "termux пакеты", "termux list",
                "android батарея", "battery status", "батарея",
                "android хранилище", "android диск", "android storage",
                "android инфо", "android информация", "android sys",
                "android wifi", "android сеть", "wifi android",
                "android процессы", "android top",
                "android настройки",
                "android скриншот", "adb screenshot",
                "adb logcat", "adb push", "adb pull",
                "android перезагрузка", "adb reboot",
                "android recovery", "android fastboot",
            ]
            if any(k in t for k in _platform_keywords):
                return self.platform_admin.handle_command(t)

        # ── Автозапуск ────────────────────────────────────
        if "установи автозапуск" in t:
            from src.security.autostart import ArgosAutostart
            return ArgosAutostart().install()
        if "статус автозапуска" in t:
            from src.security.autostart import ArgosAutostart
            return ArgosAutostart().status()
        if "удали автозапуск" in t:
            from src.security.autostart import ArgosAutostart
            return ArgosAutostart().uninstall()

        # ── P2P ───────────────────────────────────────────
        if any(k in t for k in ["статус сети", "p2p статус", "сеть нод"]):
            return self.p2p.network_status() if self.p2p else "P2P не запущен. Команда: запусти p2p"
        if any(k in t for k in ["протокол p2p", "p2p протокол", "libp2p", "zkp"]):
            return p2p_protocol_roadmap()
        if "запусти p2p" in t:
            return self.start_p2p()
        if "синхронизируй навыки" in t:
            return self.p2p.sync_skills_from_network() if self.p2p else "P2P не запущен."
        if "подключись к " in t:
            ip = text.split("подключись к ")[-1].strip().split()[0]
            return self.p2p.connect_to(ip) if self.p2p else "P2P не запущен."
        if any(k in t for k in ["распредели задачу", "общая мощность"]):
            if self.p2p:
                q = text.replace("распредели задачу","").replace("общая мощность","").strip()
                route_type = "heavy" if any(k in q.lower() for k in ["vision", "камер", "компиля", "compile", "прошив"]) else None
                return self.p2p.route_query(q or "Статус сети Аргоса.", task_type=route_type)
            return "P2P не запущен."

        # ── DAG ───────────────────────────────────────────
        if self.dag_manager and any(k in t for k in ["список dag", "dag список", "доступные dag"]):
            return self.dag_manager.list_dags()
        if self.dag_manager and ("запусти_dag" in t or "запусти dag" in t):
            name = text.replace("запусти_dag", "").replace("запусти dag", "").strip()
            name = name.replace(".json", "")
            name = name.split("/")[-1]
            if not name:
                return "Формат: запусти_dag имя_графа"
            return self.dag_manager.run(name)
        if self.dag_manager and ("создай_dag" in t or "создай dag" in t):
            desc = text.replace("создай_dag", "").replace("создай dag", "").strip()
            if not desc:
                return "Формат: создай_dag описание шагов"
            return self.dag_manager.create_from_text(desc)
        if self.dag_manager and any(k in t for k in ["синхронизируй dag", "dag sync"]):
            return self.dag_manager.sync_to_p2p()

        # ── GitHub Marketplace ────────────────────────────
        if self.marketplace and "установи навык из github" in t:
            spec = text.split("установи навык из github", 1)[-1].strip().split()
            if len(spec) < 2:
                return "Формат: установи навык из github USER/REPO SKILL"
            return self.marketplace.install(repo=spec[0], skill_name=spec[1])
        if self.marketplace and "обнови из github" in t:
            spec = text.split("обнови из github", 1)[-1].strip().split()
            if len(spec) < 2:
                return "Формат: обнови из github USER/REPO SKILL"
            return self.marketplace.update(repo=spec[0], skill_name=spec[1])
        if self.marketplace and "оцени навык" in t:
            spec = text.split("оцени навык", 1)[-1].strip().split()
            if len(spec) < 2:
                return "Формат: оцени навык SKILL [1-5]"
            return self.marketplace.rate(spec[0], spec[1])
        if self.marketplace and any(k in t for k in ["рейтинг навыков", "оценки навыков"]):
            return self.marketplace.ratings_report()

        # ── История ───────────────────────────────────────
        if any(k in t for k in ["история", "предыдущие разговоры"]):
            return self.db.format_history(10) if self.db else "БД не подключена."

        # ══════════════════════════════════════════════════
        # УМНЫЕ СИСТЕМЫ (дом, теплица, гараж, погреб, инкубатор, аквариум, террариум)
        # ══════════════════════════════════════════════════
        if self.smart_sys:
            if any(k in t for k in ["создай умную систему", "добавь умную систему", "мастер умной системы"]):
                return self._start_smart_create_wizard()
            if any(k in t for k in ["умные системы", "статус систем", "мои системы", "умный дом"]):
                return self.smart_sys.full_status()
            if any(k in t for k in ["типы систем", "доступные системы"]):
                return self.smart_sys.available_types()
            if "добавь систему" in t or "создай систему" in t:
                parts = text.replace("добавь систему","").replace("создай систему","").strip().split()
                if not parts:
                    return self.smart_sys.available_types()
                sys_type = parts[0]
                sys_id   = parts[1] if len(parts) > 1 else None
                return self.smart_sys.add_system(sys_type, sys_id)
            if "обнови сенсор" in t or "сенсор" in t and "=" in t:
                # Формат: обнови сенсор [система] [сенсор] [значение]
                parts = text.replace("обнови сенсор","").strip().split()
                if len(parts) >= 3:
                    return self.smart_sys.update(parts[0], parts[1], parts[2])
                return "Формат: обнови сенсор [id_системы] [сенсор] [значение]"
            if any(k in t for k in ["включи", "выключи", "установи"]) and self.smart_sys.systems:
                # включи полив greenhouse / выключи обогрев home
                for action_w, state in [("включи","on"),("выключи","off"),("установи","set")]:
                    if action_w in t:
                        rest = text.split(action_w, 1)[-1].strip().split()
                        if len(rest) >= 2:
                            actuator = rest[0]
                            sys_id   = rest[1]
                            if sys_id in self.smart_sys.systems:
                                return self.smart_sys.command(sys_id, actuator, state)
                        break
            if "добавь правило" in t:
                # добавь правило [система] если [условие] то [действие]
                rest = text.split("добавь правило", 1)[-1].strip()
                parts = rest.split(maxsplit=1)
                if len(parts) >= 2 and parts[0] in self.smart_sys.systems:
                    rule_text = parts[1]
                    if "если" in rule_text and "то" in rule_text:
                        cond = rule_text.split("если")[1].split("то")[0].strip()
                        act  = rule_text.split("то")[1].strip()
                        return self.smart_sys.systems[parts[0]].add_rule(cond, act)
                return "Формат: добавь правило [система] если [условие] то [действие]"

        # ══════════════════════════════════════════════════
        # IoT МОСТ (устройства, протоколы)
        # ══════════════════════════════════════════════════
        if self.iot_bridge:
            if any(k in t for k in ["iot статус", "iot устройства", "устройства iot"]):
                return self.iot_bridge.status()
            if any(k in t for k in ["iot протоколы", "протоколы iot", "пром протоколы", "какие протоколы"]):
                return self._iot_protocols_help()
            if "зарегистрируй устройство" in t or "добавь устройство" in t:
                # добавь устройство [id] [тип] [протокол] [адрес] [имя]
                parts = text.split("устройство", 1)[-1].strip().split()
                if len(parts) >= 3:
                    dev_id, dtype, proto = parts[0], parts[1], parts[2]
                    addr = parts[3] if len(parts) > 3 else ""
                    name = parts[4] if len(parts) > 4 else dev_id
                    return self.iot_bridge.register_device(dev_id, dtype, proto, addr, name)
                return "Формат: добавь устройство [id] [тип] [протокол] [адрес] [имя]"
            if "статус устройства" in t or "мониторинг устройства" in t:
                parts = text.split("устройства" if "устройства" in t else "устройство")[-1].strip().split()
                if parts:
                    return self.iot_bridge.device_status(parts[0])
                return "Формат: статус устройства [id]"
            if "подключи zigbee" in t:
                parts = text.split("подключи zigbee")[-1].strip().split()
                host = parts[0] if parts else "localhost"
                port = int(parts[1]) if len(parts) > 1 else 1883
                return self.iot_bridge.connect_zigbee(host, port)
            if "подключи lora" in t:
                parts = text.split("подключи lora")[-1].strip().split()
                port = parts[0] if parts else "/dev/ttyUSB0"
                baud = int(parts[1]) if len(parts) > 1 else 9600
                return self.iot_bridge.connect_lora(port, baud)
            if "запусти mesh" in t or "mesh старт" in t:
                return self.iot_bridge.start_mesh()
            if "подключи mqtt" in t:
                parts = text.split("подключи mqtt")[-1].strip().split()
                host = parts[0] if parts else "localhost"
                port = int(parts[1]) if len(parts) > 1 else 1883
                return self.iot_bridge.connect_mqtt(host, port)
            if any(k in t for k in ["команда устройству", "отправь команду"]):
                parts = text.split("устройству" if "устройству" in t else "команду")[-1].strip().split()
                if len(parts) >= 2:
                    return self.iot_bridge.send_command(parts[0], parts[1],
                                                       parts[2] if len(parts) > 2 else None)
                return "Формат: команда устройству [id] [команда] [значение]"

        # ══════════════════════════════════════════════════
        # ПРОМЫШЛЕННЫЕ ПРОТОКОЛЫ (KNX, LonWorks, M-Bus, OPC-UA)
        # ══════════════════════════════════════════════════
        if self.industrial:
            if any(k in t for k in [
                "industrial статус", "промышленные протоколы",
                "industrial discovery", "industrial поиск",
                "industrial устройства",
                "knx подключи", "opcua подключи",
                "mbus serial", "mbus tcp",
                "opcua browse", "opcua читай", "opcua пиши",
                "knx читай", "knx пиши",
                "lonworks читай", "lonworks пиши",
            ]):
                return self.industrial.handle_command(t)

        # ══════════════════════════════════════════════════
        # MESH-СЕТЬ (Zigbee, LoRa, WiFi Mesh)
        # ══════════════════════════════════════════════════
        if self.mesh_net:
            if any(k in t for k in ["статус mesh", "mesh статус", "mesh сеть", "mesh-сеть"]):
                return self.mesh_net.status_report()
            if "запусти zigbee" in t:
                parts = text.split("запусти zigbee")[-1].strip().split()
                port = parts[0] if parts else "/dev/ttyUSB0"
                baud = int(parts[1]) if len(parts) > 1 else 115200
                return self.mesh_net.start_zigbee(port, baud)
            if "запусти lora" in t:
                parts = text.split("запусти lora")[-1].strip().split()
                port = parts[0] if parts else "/dev/ttyUSB1"
                baud = int(parts[1]) if len(parts) > 1 else 9600
                return self.mesh_net.start_lora(port, baud)
            if "запусти wifi mesh" in t:
                ssid = text.split("запусти wifi mesh")[-1].strip() or "ArgosNet"
                return self.mesh_net.start_wifi_mesh(ssid)
            if "добавь mesh устройство" in t:
                parts = text.split("mesh устройство")[-1].strip().split()
                if len(parts) >= 3:
                    return self.mesh_net.add_device(parts[0], parts[1], parts[2],
                                                    parts[3] if len(parts) > 3 else "",
                                                    parts[4] if len(parts) > 4 else "")
                return "Формат: добавь mesh устройство [id] [протокол] [адрес] [имя] [комната]"
            if "mesh broadcast" in t or "mesh рассылка" in t:
                parts = text.split("broadcast" if "broadcast" in t else "рассылка")[-1].strip().split(maxsplit=1)
                if len(parts) >= 2:
                    return self.mesh_net.broadcast(parts[0], parts[1])
                return "Формат: mesh broadcast [протокол] [команда]"
            if "прошей gateway" in t:
                parts = text.split("gateway")[-1].strip().split()
                if len(parts) >= 1:
                    port = parts[0]
                    fw   = parts[1] if len(parts) > 1 else "zigbee_gateway"
                    return self.mesh_net.flash_gateway(port, fw)
                return "Формат: прошей gateway [порт] [прошивка]"

        # ══════════════════════════════════════════════════
        # IoT ШЛЮЗЫ (создание, конфиг, прошивка)
        # ══════════════════════════════════════════════════
        if self.gateway_mgr:
            if any(k in t for k in ["список шлюзов", "шлюзы", "gateways"]):
                return self.gateway_mgr.list_gateways()
            if any(k in t for k in ["шаблоны шлюзов", "типы шлюзов"]):
                return self.gateway_mgr.list_templates()
            if any(k in t for k in ["изучи протокол", "выучи протокол", "научи протокол"]):
                tail = text
                for marker in ("изучи протокол", "выучи протокол", "научи протокол"):
                    if marker in t:
                        tail = text.split(marker, 1)[-1].strip()
                        break
                parts = tail.split()
                if len(parts) >= 2:
                    template = parts[0]
                    protocol = parts[1]
                    firmware = parts[2] if len(parts) > 2 else ""
                    description = " ".join(parts[3:]) if len(parts) > 3 else f"Автошаблон для {protocol}"
                    return self.gateway_mgr.register_template(
                        name=template,
                        description=description,
                        protocol=protocol,
                        firmware=firmware,
                    )
                return ("Формат: изучи протокол [шаблон] [протокол] [прошивка?] [описание?]\n"
                        "Пример: изучи протокол bt_gateway bluetooth custom_bridge BLE шлюз")
            if any(k in t for k in ["изучи устройство", "выучи устройство", "изучи устроц", "выучи устроц"]):
                tail = text
                for marker in ("изучи устройство", "выучи устройство", "изучи устроц", "выучи устроц"):
                    if marker in t:
                        tail = text.split(marker, 1)[-1].strip()
                        break
                parts = tail.split()
                if len(parts) >= 2:
                    template = parts[0]
                    protocol = parts[1]
                    hardware = " ".join(parts[2:]) if len(parts) > 2 else "Generic gateway"
                    return self.gateway_mgr.register_template(
                        name=template,
                        description=f"Шаблон устройства: {hardware}",
                        protocol=protocol,
                        hardware=hardware,
                    )
                return ("Формат: изучи устройство [шаблон] [протокол] [hardware?]\n"
                        "Пример: изучи устройство rtu_bridge modbus USB-RS485 адаптер")
            if "создай прошивку" in t or "собери прошивку" in t:
                # создай прошивку [id] [шаблон] [порт?]
                tail = text.split("прошивку", 1)[-1].strip().split()
                if len(tail) >= 2:
                    gw_id = tail[0]
                    template = tail[1]
                    port = tail[2] if len(tail) > 2 else None
                    return self.gateway_mgr.prepare_firmware(gw_id, template, port)
                return f"Формат: создай прошивку [id] [шаблон] [порт]\n{self.gateway_mgr.list_templates()}"
            if "создай шлюз" in t or "создай gateway" in t:
                parts = text.split("шлюз" if "шлюз" in t else "gateway")[-1].strip().split()
                if len(parts) >= 2:
                    return self.gateway_mgr.create_gateway(parts[0], parts[1])
                return f"Формат: создай шлюз [id] [шаблон]\n{self.gateway_mgr.list_templates()}"
            if "прошей шлюз" in t or "flash gateway" in t:
                parts = text.split("шлюз" if "шлюз" in t else "gateway")[-1].strip().split()
                if parts:
                    port = parts[1] if len(parts) > 1 else None
                    return self.gateway_mgr.flash_gateway(parts[0], port)
                return "Формат: прошей шлюз [id] [порт]"
            if any(k in t for k in ["здоровье шлюзов", "health шлюзов", "проверь шлюзы"]):
                parts = text.split()
                gw_id = parts[-1] if len(parts) >= 3 and parts[-1] not in {"шлюзов", "шлюзы"} else None
                return self.gateway_mgr.health_check(gw_id)
            if "откат прошивки" in t:
                parts = text.split("откат прошивки", 1)[-1].strip().split()
                if not parts:
                    return "Формат: откат прошивки [id] [шагов?]"
                steps = 1
                if len(parts) > 1:
                    try:
                        steps = max(1, int(parts[1]))
                    except Exception:
                        steps = 1
                return self.gateway_mgr.rollback_firmware(parts[0], steps)
            if "конфиг шлюза" in t:
                gw_id = text.split("конфиг шлюза")[-1].strip().split()[0] if text.split("конфиг шлюза")[-1].strip() else ""
                if gw_id:
                    return self.gateway_mgr.get_config(gw_id)
                return "Формат: конфиг шлюза [id]"

        # ── Квантовый оракул ──────────────────────────────
        if any(k in t for k in ["оракул статус", "oracle status", "quantum oracle"]):
            try:
                from src.quantum.oracle import QuantumOracle
                return QuantumOracle().status()
            except Exception as e:
                return f"QuantumOracle: {e}"
        if any(k in t for k in ["оракул семя", "oracle seed", "quantum seed"]):
            try:
                from src.quantum.oracle import QuantumOracle
                seed = QuantumOracle().generate_seed(256)
                return f"🔮 Квантовое семя ({len(seed)*8} бит): {seed.hex()[:32]}…"
            except Exception as e:
                return f"QuantumOracle семя: {e}"
        if any(k in t for k in ["оракул режим", "oracle mode", "режим oracle", "оракул состояние"]):
            try:
                from src.quantum.logic import QuantumEngine, STATES
                q = QuantumEngine()
                return f"🔮 Oracle режим | Состояние: {q.state} — {STATES.get(q.state, '')}"
            except Exception as e:
                return f"Oracle режим: {e}"

        # ── Колибри ───────────────────────────────────────
        if any(k in t for k in ["колибри статус", "колибри", "colibri"]):
            try:
                from src.connectivity.colibri_daemon import ColibriDaemon
                return "🐦 Колибри: модуль доступен. Для запуска: 'запусти колибри'."
            except Exception:
                return "🐦 Колибри: не запущен. Установи зависимости и запусти вручную."

        # ── Функции АргосКоре ──────────────────────────────
        if any(k in t for k in [
            "функции аргоскоре", "аргоскоре функции", "функции ядра",
            "проверь аргоскоре", "аргоскоре проверь", "возможности аргоскоре",
            "аргоскоре возможности", "что умеет аргоскоре", "argoscore функции",
            "argoscore возможности", "список функций аргоса", "функции argos",
            "функции аргоса", "список функций",
        ]):
            return self._argoscore_functions()

        # ── Помощь ────────────────────────────────────────
        if t.strip() in ("помощь", "команды", "что умеешь", "help", "?"):
            return self._help()

        return None

    def _operator_incident(self, admin) -> str:
        lines = ["🚨 ОПЕРАТОР: ИНЦИДЕНТ"]
        lines.append(admin.get_stats())
        if self.alerts:
            lines.append(self.alerts.status())
        if self.gateway_mgr:
            lines.append(self.gateway_mgr.health_check())
        lines.append("Рекомендация: запусти 'оператор диагностика' для детального анализа.")
        return "\n\n".join(lines)

    def _operator_diagnostics(self, admin) -> str:
        lines = ["🩺 ОПЕРАТОР: ДИАГНОСТИКА"]
        lines.append(admin.get_stats())
        lines.append(self.sensors.get_full_report())
        if self.iot_bridge:
            lines.append(self.iot_bridge.status())
        if self.industrial:
            lines.append(self.industrial.status())
        if self.platform_admin:
            lines.append(self.platform_admin.status())
        if self.mesh_net:
            lines.append(self.mesh_net.status_report())
        if self.gateway_mgr:
            lines.append(self.gateway_mgr.health_check())
        return "\n\n".join(lines)

    def _operator_recovery(self) -> str:
        lines = ["🛠️ ОПЕРАТОР: ВОССТАНОВЛЕНИЕ"]
        if self.gateway_mgr:
            lines.append(self.gateway_mgr.health_check())
        lines.append("Чек-лист:\n  1) Проверить порты/сеть\n  2) Переподготовить прошивку\n  3) Выполнить откат прошивки при деградации")
        return "\n\n".join(lines)

    def _ai_modes_diagnostic(self) -> str:
        ai_mode = self.ai_mode_label() if hasattr(self, "ai_mode_label") else str(getattr(self, "ai_mode", "unknown"))
        try:
            from src.skills.evolution import ArgosEvolution  # noqa: F401
            evo_ready = "✅"
        except Exception:
            evo_ready = "⚠️"
        learning = self.own_model.status() if getattr(self, "own_model", None) else "⚠️ Модуль обучения недоступен."
        grist_sync = "✅" if getattr(getattr(self, "grist", None), "_configured", False) else "⚠️"
        cognition = "✅" if getattr(self, "memory", None) else "⚠️"
        curiosity = self.curiosity.status() if getattr(self, "curiosity", None) else "⚠️"
        dialog_ctx = "✅" if getattr(self, "context", None) else "⚠️"
        return (
            "🧪 ДИАГНОСТИКА ИИ/ЭВОЛЮЦИИ/ОБУЧЕНИЯ:\n"
            f"  • Режим ИИ: {ai_mode}\n"
            f"  • Эволюция навыков: {evo_ready}\n"
            f"  • Обучение модели: {learning}\n"
            f"  • Синхронизация знаний (ГОСТ P2P Grist): {grist_sync}\n"
            f"  • Познание (память): {cognition}\n"
            f"  • Любопытство: {curiosity}\n"
            f"  • Диалоговый контекст: {dialog_ctx}"
        )

    def _help(self) -> str:
        return """👁️ АРГОС UNIVERSAL OS — КОМАНДЫ:

📊 МОНИТОРИНГ
  статус системы · чек-ап · список процессов
  алерты · установи порог [метрика] [%] · геолокация

📁 ФАЙЛЫ  
  файлы [путь] · прочитай файл [путь]
  создай файл [имя] [текст] · удали файл [путь]

⚙️ СИСТЕМА
  консоль [команда] · убей процесс [имя]
  репликация · загрузчик · обнови grub
  установи автозапуск · веб-панель
    гомеостаз статус · гомеостаз вкл/выкл
    любопытство статус · любопытство вкл/выкл · любопытство сейчас
        git статус · git коммит [msg] · git пуш · git автокоммит и пуш [msg]

👁️ VISION (нужен Gemini API)
  посмотри на экран · что на экране
  посмотри в камеру · анализ фото [путь]

🤖 АГЕНТ (цепочки задач)
  статус → затем крипто → потом дайджест
  отчёт агента · останови агента

🧠 ПАМЯТЬ
  запомни [ключ]: [значение] · что ты знаешь
    найди в памяти [запрос] · поиск по памяти [запрос]
    граф знаний · связи памяти
  запиши заметку [название]: [текст]
  мои заметки · прочитай заметку [№]

⏰ РАСПИСАНИЕ
  каждые 2 часа [задача] · в 09:00 [задача]
  через 30 мин [задача] · расписание

🌐 P2P СЕТЬ
  статус сети · синхронизируй навыки
  подключись к [IP] · распредели задачу [вопрос]
    p2p протокол · libp2p · zkp

🧠 TOOL CALLING
    схемы инструментов · json схемы инструментов

� УМНЫЕ СИСТЕМЫ
  умные системы · типы систем
  добавь систему [тип] [id]
  обнови сенсор [система] [сенсор] [значение]
  включи/выключи [актуатор] [система]
  добавь правило [система] если [условие] то [действие]
  Типы: home, greenhouse, garage, cellar, incubator, aquarium, terrarium

📡 IoT / MESH-СЕТЬ
  iot статус · добавь устройство [id] [тип] [протокол]
    статус устройства [id] · iot протоколы
  подключи zigbee/lora/mqtt · запусти mesh
  статус mesh · запусти zigbee/lora [порт]
  запусти wifi mesh [SSID]
  добавь mesh устройство [id] [протокол] [адрес]
  mesh broadcast [протокол] [команда]
    найди usb чипы · умная прошивка [порт]
    Протоколы: BACnet, Modbus RTU/ASCII/TCP, KNX, LonWorks, M-Bus, OPC UA, MQTT
    Сети: Zigbee mesh, LoRa (SX1276), WiFi mesh

🔌 OTG (USB HOST)
  otg статус                           — состояние OTG-менеджера
  otg скан                             — список USB-устройств через OTG
  otg подключи [id/порт] [baudrate]    — подключиться к USB-Serial
  otg отправь [id] [данные]            — отправить данные в устройство
  otg отключи [id]                     — закрыть OTG-соединение
  otg мониторинг                       — авто-мониторинг подключений
  rs ttl / uart ttl                    — справка по UART TTL и конвертерам
  проверь драйверы android gui         — низкоуровневые драйверы Android/GUI

🔐 ГОСТ КРИПТОГРАФИЯ (ГОСТ Р 34.12-2015 + Р 34.11-2012)
  гост статус                          — состояние ГОСТ-модуля (Кузнечик/Магма/Стрибог)
  гост хеш [текст]                     — хеш Стрибог-256 (ГОСТ Р 34.11-2012)
  гост p2p статус                      — ГОСТ-защита P2P (HMAC-Стрибог + CTR-Кузнечик)

🗄 GRIST P2P ХРАНИЛИЩЕ
  grist статус                         — состояние подключения к Grist
  grist таблицы                        — список таблиц документа
  grist сохрани [ключ] [значение]      — сохранить запись (ГОСТ-шифрование)
  grist получи [ключ]                  — получить запись
  grist список                         — все записи ноды
  grist ноды                           — реестр P2P-нод в Grist
  grist синк                           — зарегистрировать ноду в Grist

🔧 IoT ШЛЮЗЫ
  список шлюзов · шаблоны шлюзов
  создай шлюз [id] [шаблон]
    создай прошивку [id] [шаблон] [порт]
    изучи протокол [шаблон] [протокол] [прошивка] [описание]
    изучи устройство [шаблон] [протокол] [hardware]
  прошей шлюз [id] [порт] · прошей gateway [порт] [прошивка]
  конфиг шлюза [id]
    MCU: STM32H503, ESP8266, RP2040

🏠 HOME ASSISTANT
    ha статус · ha состояния
    ha сервис [domain] [service] [key=value]
    ha mqtt [topic] [key=value]

🧩 МОДУЛИ
    список модулей

🐦 КОЛИБРИ (P2P mesh-агент)
  колибри статус · запусти колибри

🔮 КВАНТОВЫЙ ОРАКУЛ
  оракул статус · оракул семя · оракул режим

🎤 ГОЛОС
  голос вкл/выкл · включи wake word

💬 ДИАЛОГ
  контекст диалога · сброс контекста
  история · помощь"""

    def _argoscore_functions(self) -> str:
        """Возвращает структурированный отчёт о функциях и подсистемах ArgosCore."""
        lines = [f"🧠 ArgosCore v{self.VERSION} — ФУНКЦИИ И ПОДСИСТЕМЫ:\n"]

        # Подсистемы и их статус
        subsystems = [
            ("🧮 Квантовый модуль (quantum)",    self.quantum),
            ("🧠 Память (memory)",               self.memory),
            ("🎯 Агент (agent)",                 self.agent),
            ("📡 Сенсоры (sensors)",             self.sensors),
            ("📚 Навыки (skill_loader)",         self.skill_loader),
            ("🔮 Любопытство (curiosity)",       self.curiosity),
            ("❤️ Гомеостаз (homeostasis)",      self.homeostasis),
            ("🛠 Tool Calling",                   self.tool_calling),
            ("📆 Планировщик (scheduler)",       self.scheduler),
            ("🔔 Алерты (alerts)",               self.alerts),
            ("👁 Зрение (vision)",               self.vision),
            ("🌐 P2P сеть",                      self.p2p),
            ("🤖 IoT-мост (iot_bridge)",         self.iot_bridge),
            ("🏭 Промышленные протоколы",        self.industrial),
            ("🖥 Платформенный администратор",   self.platform_admin),
            ("🏠 Умные системы (smart_sys)",     self.smart_sys),
            ("🏡 Home Assistant (ha)",            self.ha),
            ("🔗 Git операции (git_ops)",        self.git_ops),
            ("📦 Модули (module_loader)",        self.module_loader),
            ("🗄 Grist P2P хранилище",           self.grist),
            ("☁️ Облачное хранилище",           self.cloud_object_storage),
            ("🔌 OTG (USB HOST)",                self.otg),
            ("🧪 Собственная модель (own_model)", getattr(self, "own_model", None)),
        ]

        lines.append("📦 ПОДСИСТЕМЫ:")
        for name, obj in subsystems:
            status = "✅ активна" if obj is not None else "⚠️ не загружена"
            lines.append(f"  {name}: {status}")

        # Публичные методы API
        lines.append("\n🔧 ПУБЛИЧНЫЕ МЕТОДЫ:")
        public_api = [
            ("process(user_text)",              "Главная точка входа: обработка команды/запроса"),
            ("execute_intent(text, admin)",     "Маршрутизация намерения к нужному обработчику"),
            ("say(text)",                       "TTS: озвучить текст"),
            ("listen()",                        "STT: прослушать речь с микрофона"),
            ("transcribe_audio_path(path)",     "STT: транскрибировать аудиофайл"),
            ("set_ai_mode(mode)",               "Переключить AI-провайдера (auto/gemini/ollama/…)"),
            ("ai_mode_label()",                 "Получить текущий AI-режим"),
            ("voice_services_report()",         "Отчёт о голосовых службах"),
            ("start_p2p()",                     "Запустить P2P-сеть"),
            ("start_dashboard(admin, flasher)", "Запустить веб-панель"),
            ("start_wake_word(admin, flasher)", "Запустить wake-word слушатель"),
            ("load_skill(name)",                "Загрузить навык по имени"),
        ]
        for method, desc in public_api:
            lines.append(f"  • {method} — {desc}")

        # AI-режим
        try:
            ai_lbl = self.ai_mode_label()
        except Exception:
            ai_lbl = str(getattr(self, "ai_mode", "unknown"))
        lines.append(f"\n🤖 ТЕКУЩИЙ AI-РЕЖИМ: {ai_lbl}")
        lines.append(f"📌 Версия ядра: {self.VERSION}")
        lines.append("\nℹ️ Для полного списка команд введи: помощь")

        return "\n".join(lines)

    def _iot_protocols_help(self) -> str:
        return """🏭 ПОДДЕРЖИВАЕМЫЕ IoT/ПРОМ ПРОТОКОЛЫ:

    • BACnet (Building Automation and Control Networks)
    • Modbus RTU / ASCII / TCP
    • KNX
    • LonWorks (Local Operating Network)
    • M-Bus (Meter-Bus)
    • OPC UA (Open Platform Communications Unified Architecture)
    • MQTT
    • RS TTL / UART TTL (TX, RX, GND; 3.3V/5V логика)

📡 Mesh и радио:
    • Zigbee mesh
    • LoRa mesh (включая SX1276)
    • WiFi mesh / gateway bridge

🔧 Прошивка устройств:
    • STM32H503, ESP8266, RP2040
    • Команды: создай прошивку [id] [шаблон] [порт]
                изучи протокол [шаблон] [протокол] [прошивка] [описание]
                изучи устройство [шаблон] [протокол] [hardware]

🔌 UART TTL / RS TTL:
    • Линии: TX, RX, GND
    • Уровни: 0/3.3V или 0/5V (безопасно только в пределах TTL)
    • TTL ↔ RS-232: MAX232
    • TTL ↔ RS-485: MAX485
    • TTL ↔ USB: FT232RL / CH340"""

    def _rs_ttl_help(self) -> str:
        return """🔌 RS TTL / UART TTL — справка:

  • Тип связи: последовательная асинхронная (UART), без общего тактового сигнала
  • Линии: TX, RX, GND
  • Логические уровни:
      - HIGH: обычно 3.3V или 5V
      - LOW: около 0V
  • Дистанция: обычно до нескольких метров (низкая помехоустойчивость)

⚠️ Нельзя подключать TTL напрямую к RS-232/RS-485:
  • TTL ↔ RS-232: используйте MAX232
  • TTL ↔ RS-485: используйте MAX485
  • TTL ↔ USB: используйте FT232RL / CH340

Для работы в терминале:
  • otg скан
  • otg подключи [id/порт] [baudrate]
  • otg отправь [id] [данные]
  • otg отключи [id]"""

    def _low_level_drivers_report(self) -> str:
        def _module_ok(name: str) -> bool:
            try:
                import importlib.util
                return importlib.util.find_spec(name) is not None
            except Exception:
                return False

        def _threading_line() -> str:
            cores = os.cpu_count() or 1
            active_threads = threading.active_count()
            return f"  Многопоточность CPU: {cores} логич. потоков | активных потоков Python: {active_threads}"

        def _power_line() -> str:
            try:
                import psutil
                battery = psutil.sensors_battery()
                if battery is None:
                    return "  Питание/мощность: ✅ сеть/стационарный режим (battery sensor отсутствует)"
                src = "🔌 сеть" if battery.power_plugged else "🔋 батарея"
                return f"  Питание/мощность: {src}, заряд {battery.percent:.0f}%"
            except Exception:
                return "  Питание/мощность: ⚠️ недоступно (нет psutil sensors)"

        def _video_line() -> str:
            try:
                import glob
                import shutil
                import subprocess

                trusted_dirs = ("/usr/bin", "/usr/local/bin", "/bin", "/sbin")
                def _trusted_binary(path: str | None) -> str | None:
                    if not path:
                        return None
                    real = os.path.realpath(path)
                    if not isinstance(real, str):
                        return None
                    for directory in trusted_dirs:
                        try:
                            if os.path.commonpath([real, directory]) == directory:
                                return real
                        except Exception:
                            continue
                    return None

                def _sanitize_gpu_name(text: str, max_length: int = 120) -> str:
                    safe = "".join(ch for ch in text if ch.isprintable() and ch != "\x7f")
                    return safe[:max_length]

                details = []
                if glob.glob("/dev/dri/renderD*"):
                    details.append("DRM render nodes")
                nvidia_smi = _trusted_binary(shutil.which("nvidia-smi"))
                if nvidia_smi:
                    result = subprocess.run(
                        [nvidia_smi, "--query-gpu=name", "--format=csv,noheader"],
                        capture_output=True,
                        text=True,
                        timeout=2,
                    )
                    if result.returncode == 0 and result.stdout.strip():
                        raw_gpu_name = result.stdout.strip().splitlines()[0]
                        gpu_name = _sanitize_gpu_name(raw_gpu_name)
                        details.append(f"NVIDIA: {gpu_name}")
                vcgencmd = _trusted_binary(shutil.which("vcgencmd"))
                if vcgencmd:
                    result = subprocess.run(
                        [vcgencmd, "get_mem", "gpu"],
                        capture_output=True,
                        text=True,
                        timeout=2,
                    )
                    if result.returncode == 0 and result.stdout.strip():
                        details.append(f"VideoCore: {result.stdout.strip()}")
                if details:
                    return f"  Видеоядра/GPU: ✅ {'; '.join(details)}"
                return "  Видеоядра/GPU: ⚠️ не обнаружены/драйверы не активны"
            except Exception:
                return "  Видеоядра/GPU: ⚠️ проверка недоступна"

        is_android = os.path.exists("/system/build.prop")
        lines = [
            "🧪 НИЗКОУРОВНЕВЫЕ ДРАЙВЕРЫ (Android / GUI):",
            f"  Режим Android: {'✅' if is_android else '❌ (desktop/linux)'}",
            _threading_line(),
            _power_line(),
            _video_line(),
            "",
            "  Драйверы и библиотеки функций:",
            f"  Android USB API (jnius): {'✅' if _module_ok('jnius') else '❌'}",
            f"  Android UI (kivy): {'✅' if _module_ok('kivy') else '❌'}",
            f"  Android sensors/services (plyer): {'✅' if _module_ok('plyer') else '❌'}",
            f"  USB-Serial (pyserial): {'✅' if _module_ok('serial') else '❌'}",
            f"  GUI Desktop (customtkinter): {'✅' if _module_ok('customtkinter') else '❌'}",
        ]
        if self.otg:
            lines.append("")
            lines.append(self.otg.status())
        return "\n".join(lines)

    def _start_smart_create_wizard(self) -> str:
        if not self.smart_sys:
            return "❌ Умные системы не инициализированы."

        self._smart_create_wizard = {
            "step": "type",
            "type": None,
            "id": None,
            "purpose": "",
            "functions": [],
        }
        types = ", ".join(self.smart_profiles.keys()) if self.smart_profiles else "home, greenhouse, garage, cellar, incubator, aquarium, terrarium"
        return (
            "🧭 Мастер создания умной системы.\n"
            "Шаг 1/4: выбери тип системы:\n"
            f"{types}\n"
            "Пример: greenhouse\n"
            "(для отмены: 'отмена')"
        )

    def _continue_smart_create_wizard(self, text: str) -> str:
        wiz = self._smart_create_wizard
        if not wiz:
            return None

        value = text.strip()
        step = wiz.get("step")

        if step == "type":
            sys_type = value.split()[0].lower()
            if sys_type not in self.smart_profiles:
                types = ", ".join(self.smart_profiles.keys())
                return f"❌ Неизвестный тип. Доступные: {types}\nВведи тип ещё раз."
            wiz["type"] = sys_type
            wiz["step"] = "id"
            profile = self.smart_profiles.get(sys_type, {})
            return (
                f"✅ Тип: {profile.get('icon','⚙️')} {profile.get('name', sys_type)}\n"
                "Шаг 2/4: задай ID системы (латиница/цифры), например: my_greenhouse\n"
                "Или напиши 'авто' для ID по умолчанию."
            )

        if step == "id":
            if value.lower() in ("авто", "auto", "default"):
                wiz["id"] = wiz["type"]
            else:
                wiz["id"] = value.split()[0]
            wiz["step"] = "purpose"
            return (
                f"✅ ID: {wiz['id']}\n"
                "Шаг 3/4: что система должна делать?\n"
                "Пример: поддерживать климат и безопасность, управлять поливом и вентиляцией."
            )

        if step == "purpose":
            wiz["purpose"] = value
            wiz["step"] = "functions"
            profile = self.smart_profiles.get(wiz["type"], {})
            actuators = ", ".join(profile.get("actuators", []))
            return (
                f"✅ Назначение: {wiz['purpose']}\n"
                "Шаг 4/4: какие функции включить сразу?\n"
                f"Доступные функции: {actuators}\n"
                "Введи через запятую (пример: irrigation, ventilation)\n"
                "или напиши 'авто' для стандартного профиля."
            )

        if step == "functions":
            profile = self.smart_profiles.get(wiz["type"], {})
            actuators = profile.get("actuators", [])
            if value.lower() not in ("авто", "auto", "default"):
                selected = [x.strip() for x in value.split(",") if x.strip()]
                valid = [x for x in selected if x in actuators]
                wiz["functions"] = valid
            else:
                wiz["functions"] = []

            create_msg = self.smart_sys.add_system(wiz["type"], wiz["id"])
            if create_msg.startswith("❌"):
                self._smart_create_wizard = None
                return create_msg

            if wiz["functions"]:
                for function_name in wiz["functions"]:
                    self.smart_sys.command(wiz["id"], function_name, "on")

            summary = (
                f"🧾 Создано: {wiz['type']} [{wiz['id']}]\n"
                f"🎯 Назначение: {wiz['purpose']}\n"
                f"🧩 Функции: {', '.join(wiz['functions']) if wiz['functions'] else 'стандартный профиль'}"
            )
            self._smart_create_wizard = None
            return f"{create_msg}\n\n{summary}"

        self._smart_create_wizard = None
        return "⚠️ Мастер сброшен. Запусти заново: 'создай умную систему'."

    def load_skill(self, name: str):
        if self.skill_loader:
            result = self.skill_loader.load(name, core=self)
            return self.skill_loader, result
        import importlib
        try:
            return importlib.import_module(f"src.skills.{name}"), f"✅ '{name}' загружен."
        except ModuleNotFoundError:
            return None, f"❌ '{name}' не найден."
