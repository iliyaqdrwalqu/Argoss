"""
wake_word.py -- Wake Word "Argos" voice activation.
Backends: porcupine > vosk > speech_recognition > simulation.
"""
import os, threading, time
from typing import Callable, Optional
from src.argos_logger import get_logger
log = get_logger("argos.wakeword")

try:
    import pvporcupine as _porc  # type: ignore
    PORCUPINE_OK = True
except ImportError:
    _porc = None
    PORCUPINE_OK = False

try:
    from vosk import KaldiRecognizer, Model as VoskModel  # type: ignore
    VOSK_OK = True
except ImportError:
    KaldiRecognizer = VoskModel = None
    VOSK_OK = False

try:
    import speech_recognition as _sr  # type: ignore
    SR_OK = True
except ImportError:
    _sr = None
    SR_OK = False

try:
    import sounddevice as _sd  # type: ignore
    AUDIO_OK = True
except ImportError:
    _sd = None
    AUDIO_OK = False

WAKE_WORDS = ["аргос", "argos", "привет аргос", "эй аргос", "аргос слушай"]


class WakeWordDetector:
    """
    Детектор wake word «Аргос».
    Бэкенд выбирается автоматически по доступным библиотекам.
    """

    def __init__(self, on_detected: Optional[Callable] = None,
                 wake_words: Optional[list] = None):
        self._cb = on_detected
        self._words = [w.lower() for w in (wake_words or WAKE_WORDS)]
        self._running = False
        self._thread: Optional[threading.Thread] = None
        self._count = 0
        self._backend = self._pick_backend()
        log.info("WakeWord: backend=%s words=%s", self._backend, self._words[:2])

    @staticmethod
    def _pick_backend() -> str:
        if PORCUPINE_OK and os.getenv("PICOVOICE_ACCESS_KEY"):
            return "porcupine"
        if VOSK_OK and AUDIO_OK:
            return "vosk"
        if SR_OK:
            return "sr_google"
        return "simulation"

    @property
    def backend(self) -> str:
        return self._backend

    def start(self) -> str:
        if self._running:
            return "Wake Word: уже запущен."
        self._running = True
        self._thread = threading.Thread(target=self._loop, daemon=True, name="argos-ww")
        self._thread.start()
        return f"Wake Word активен (backend={self._backend}). Скажи «Аргос»."

    def stop(self) -> str:
        self._running = False
        return "Wake Word остановлен."

    def _loop(self):
        {
            "porcupine":  self._loop_porcupine,
            "vosk":       self._loop_vosk,
            "sr_google":  self._loop_sr,
            "simulation": self._loop_sim,
        }.get(self._backend, self._loop_sim)()

    def _loop_porcupine(self):
        try:
            import struct, pyaudio  # type: ignore
            key = os.getenv("PICOVOICE_ACCESS_KEY", "")
            p = _porc.create(access_key=key, keywords=["porcupine"])
            pa = pyaudio.PyAudio()
            stream = pa.open(rate=p.sample_rate, channels=1,
                             format=pyaudio.paInt16, input=True,
                             frames_per_buffer=p.frame_length)
            while self._running:
                pcm = stream.read(p.frame_length, exception_on_overflow=False)
                if p.process(struct.unpack_from("h" * p.frame_length, pcm)) >= 0:
                    self._fire("porcupine")
            stream.close(); pa.terminate(); p.delete()
        except Exception as e:
            log.warning("Porcupine: %s -> sr_google", e)
            self._backend = "sr_google"
            self._loop_sr()

    def _loop_vosk(self):
        model_path = os.getenv("VOSK_MODEL_PATH", "data/vosk-model-small-ru")
        if not os.path.exists(model_path):
            log.warning("Vosk model not found: %s -> sr_google", model_path)
            self._backend = "sr_google"
            self._loop_sr()
            return
        try:
            model = VoskModel(model_path)
            rec = KaldiRecognizer(model, 16000)
            with _sd.RawInputStream(samplerate=16000, blocksize=8000,
                                    dtype="int16", channels=1) as stream:
                while self._running:
                    data, _ = stream.read(8000)
                    if rec.AcceptWaveform(bytes(data)):
                        txt = rec.Result().lower()
                        if any(w in txt for w in self._words):
                            self._fire("vosk")
        except Exception as e:
            log.warning("Vosk: %s -> simulation", e)
            self._backend = "simulation"
            self._loop_sim()

    def _loop_sr(self):
        if not SR_OK:
            self._backend = "simulation"
            self._loop_sim()
            return
        recognizer = _sr.Recognizer()
        recognizer.energy_threshold = int(os.getenv("ARGOS_SR_ENERGY", "300"))
        while self._running:
            try:
                with _sr.Microphone() as src:
                    recognizer.adjust_for_ambient_noise(src, duration=0.3)
                    audio = recognizer.listen(src, timeout=5, phrase_time_limit=4)
                try:
                    txt = recognizer.recognize_google(audio, language="ru-RU").lower()
                    if any(w in txt for w in self._words):
                        self._fire("sr_google")
                except _sr.UnknownValueError:
                    pass
                except Exception as e:
                    time.sleep(2)
            except Exception:
                time.sleep(1)

    def _loop_sim(self):
        interval = float(os.getenv("ARGOS_WAKE_SIM_INTERVAL", "0"))
        if interval <= 0:
            while self._running:
                time.sleep(1)
            return
        while self._running:
            time.sleep(interval)
            if self._running:
                self._fire("simulation")

    def _fire(self, src: str = "?"):
        self._count += 1
        log.info("WAKE WORD #%d (src=%s)", self._count, src)
        if self._cb:
            try:
                self._cb()
            except Exception as e:
                log.error("Wake cb: %s", e)

    def trigger(self):
        self._fire("manual")

    def status(self) -> str:
        return (f"Wake Word: running={self._running}  backend={self._backend}  "
                f"detected={self._count}")


WakeWord = WakeWordDetector
