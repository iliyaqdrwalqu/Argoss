"""
src/ollama_autoselect.py — Автоподбор модели Ollama под возможности системы.

Учитывает ВСЕ доступные ресурсы:
  - RAM системы
  - VRAM дискретного GPU (NVIDIA / AMD)
  - VRAM встроенного видеоядра (Intel iGPU / AMD APU)
  - CPU ядра и архитектура
  - Суммирует всё для выбора максимально мощной модели

Стратегия использования ресурсов:
  - num_gpu=-1        → Ollama сам решает сколько слоёв на GPU
  - num_ctx           → контекст под доступную память
  - num_thread        → число CPU потоков
  - OLLAMA_MAX_VRAM   → можно ограничить вручную
"""
from __future__ import annotations

import json
import os
import platform
import subprocess
import threading
from typing import Optional

try:
    import psutil
    _PSUTIL = True
except ImportError:
    _PSUTIL = False

try:
    from src.argos_logger import get_logger
    log = get_logger("argos.ollama_autoselect")
except Exception:
    import logging
    log = logging.getLogger("argos.ollama_autoselect")


# ─────────────────────────────────────────────────────────────────────────────
# ПРОФИЛИ МОДЕЛЕЙ
# ─────────────────────────────────────────────────────────────────────────────
# effective_gb = RAM + VRAM_дискретный + VRAM_встроенный * 0.5
# (встроенное видеоядро делит память с системой — коэффициент 0.5)

_PROFILES: list[dict] = [
    {
        "name": "tiny",
        "label": "Tiny (< 4 GB)",
        "max_gb": 4.0,
        "preferred": ["tinyllama:latest", "tinyllama", "qwen2:0.5b", "phi3:mini"],
        "pull": "tinyllama",
        "num_ctx": 1024,
    },
    {
        "name": "small",
        "label": "Small (4–6 GB)",
        "max_gb": 6.0,
        "preferred": ["llama3.2:1b", "phi3:mini", "phi3", "gemma2:2b", "tinyllama"],
        "pull": "phi3:mini",
        "num_ctx": 2048,
    },
    {
        "name": "medium",
        "label": "Medium (6–12 GB)",
        "max_gb": 12.0,
        "preferred": ["llama3.2:3b", "mistral", "phi3", "gemma2:9b", "llama3.2"],
        "pull": "llama3.2:3b",
        "num_ctx": 4096,
    },
    {
        "name": "large",
        "label": "Large (12–24 GB)",
        "max_gb": 24.0,
        "preferred": ["llama3:8b", "llama3", "mistral:7b", "gemma2:27b", "mixtral"],
        "pull": "llama3",
        "num_ctx": 8192,
    },
    {
        "name": "xlarge",
        "label": "XLarge (> 24 GB)",
        "max_gb": 999_999,
        "preferred": ["llama3:70b", "mixtral:8x22b", "mixtral", "llama3"],
        "pull": "llama3:70b",
        "num_ctx": 16384,
    },
]


# ─────────────────────────────────────────────────────────────────────────────
# СБОР ИНФОРМАЦИИ О ЖЕЛЕЗЕ
# ─────────────────────────────────────────────────────────────────────────────

def _run(cmd: list[str], timeout: int = 5) -> str:
    """Запускает команду, возвращает stdout или ''."""
    try:
        r = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)
        return r.stdout.strip() if r.returncode == 0 else ""
    except Exception:
        return ""


def _detect_nvidia() -> dict:
    """NVIDIA GPU через nvidia-smi."""
    result = {"name": "", "vram_gb": 0.0, "driver": ""}
    out = _run([
        "nvidia-smi",
        "--query-gpu=name,memory.total,driver_version",
        "--format=csv,noheader,nounits",
    ])
    if not out:
        return result
    parts = [p.strip() for p in out.split(",")]
    if len(parts) >= 2:
        result["name"] = parts[0]
        try:
            result["vram_gb"] = round(int(parts[1]) / 1024, 1)
        except Exception:
            pass
        if len(parts) >= 3:
            result["driver"] = parts[2]
    return result


def _detect_amd_discrete() -> dict:
    """AMD дискретный GPU через rocm-smi."""
    result = {"name": "", "vram_gb": 0.0}
    out = _run(["rocm-smi", "--showmeminfo", "vram", "--json"])
    if not out:
        return result
    try:
        data = json.loads(out)
        total = 0
        for card in data.values():
            total += int(card.get("VRAM Total Memory (B)", 0))
        result["vram_gb"] = round(total / 1024**3, 1)
        result["name"] = "AMD GPU (ROCm)"
    except Exception:
        pass
    return result


def _detect_intel_igpu() -> dict:
    """
    Intel iGPU / AMD APU — встроенное видеоядро.
    Делит RAM с системой, поэтому считаем его как бонус × 0.5.
    """
    result = {"name": "", "vram_gb": 0.0, "shared": True}

    system = platform.system()

    if system == "Windows":
        # Через WMIC ищем Intel/AMD встроенный адаптер
        out = _run(["wmic", "path", "win32_VideoController",
                    "get", "Name,AdapterRAM", "/format:csv"])
        for line in out.splitlines():
            if not line.strip() or "Node" in line:
                continue
            parts = line.split(",")
            if len(parts) >= 3:
                adapter_ram = parts[1].strip()
                name = parts[2].strip()
                name_lower = name.lower()
                if any(k in name_lower for k in ["intel", "uhd", "iris", "radeon", "vega", "amd"]):
                    # Проверяем что это не дискретная карта
                    if not any(k in name_lower for k in ["rx ", "rtx", "gtx", "arc a"]):
                        try:
                            vram_bytes = int(adapter_ram)
                            result["vram_gb"] = round(vram_bytes / 1024**3, 1)
                            result["name"] = name
                        except Exception:
                            # Shared memory — оцениваем как 1/4 RAM
                            if _PSUTIL:
                                mem = psutil.virtual_memory()
                                result["vram_gb"] = round(mem.total / 1024**3 / 4, 1)
                            result["name"] = name

    elif system == "Linux":
        # Через lspci ищем iGPU
        out = _run(["lspci"])
        for line in out.splitlines():
            line_lower = line.lower()
            if "vga" in line_lower or "display" in line_lower:
                if any(k in line_lower for k in ["intel", "uhd", "iris"]):
                    result["name"] = line.split(":")[-1].strip()
                    # Intel iGPU обычно берёт 256MB–2GB из RAM
                    if _PSUTIL:
                        mem = psutil.virtual_memory()
                        result["vram_gb"] = round(
                            min(2.0, mem.total / 1024**3 / 8), 1
                        )
                elif any(k in line_lower for k in ["amd", "radeon", "vega"]):
                    if "rx " not in line_lower:  # не дискретная
                        result["name"] = line.split(":")[-1].strip()
                        if _PSUTIL:
                            mem = psutil.virtual_memory()
                            result["vram_gb"] = round(
                                min(4.0, mem.total / 1024**3 / 6), 1
                            )

    return result


def _get_cpu_model() -> str:
    system = platform.system()
    if system == "Windows":
        out = _run(["wmic", "cpu", "get", "Name"])
        lines = [l.strip() for l in out.splitlines()
                 if l.strip() and "Name" not in l]
        return lines[0] if lines else platform.processor()
    elif system == "Linux":
        try:
            with open("/proc/cpuinfo", errors="ignore") as f:
                for line in f:
                    if "model name" in line.lower():
                        return line.split(":")[-1].strip()
        except Exception:
            pass
    elif system == "Darwin":
        return _run(["sysctl", "-n", "machdep.cpu.brand_string"])
    return platform.processor() or "unknown"


def get_system_info() -> dict:
    """
    Полная диагностика железа:
    RAM + дискретный GPU (NVIDIA/AMD) + встроенное видеоядро + CPU.
    """
    info = {
        "ram_total_gb":  4.0,
        "ram_avail_gb":  2.0,
        "cpu_model":     "unknown",
        "cpu_cores":     os.cpu_count() or 2,
        "cpu_threads":   os.cpu_count() or 2,
        "os":            platform.system(),
        "arch":          platform.machine(),
        # GPU
        "gpu_discrete":  {"name": "", "vram_gb": 0.0},   # NVIDIA / AMD дискретный
        "gpu_igpu":      {"name": "", "vram_gb": 0.0},    # Intel / AMD встроенный
        # Итоговые
        "vram_discrete_gb": 0.0,
        "vram_igpu_gb":     0.0,
        "effective_gb":     0.0,   # RAM + VRAM_discrete + VRAM_igpu * 0.5
    }

    # RAM
    if _PSUTIL:
        try:
            mem = psutil.virtual_memory()
            info["ram_total_gb"] = round(mem.total   / 1024**3, 1)
            info["ram_avail_gb"] = round(mem.available / 1024**3, 1)
            info["cpu_threads"]  = psutil.cpu_count(logical=True) or 2
        except Exception:
            pass

    # CPU
    info["cpu_model"] = _get_cpu_model()

    # Дискретный GPU — пробуем NVIDIA, потом AMD
    nvidia = _detect_nvidia()
    if nvidia["vram_gb"] > 0:
        info["gpu_discrete"] = nvidia
        info["vram_discrete_gb"] = nvidia["vram_gb"]
    else:
        amd = _detect_amd_discrete()
        if amd["vram_gb"] > 0:
            info["gpu_discrete"] = amd
            info["vram_discrete_gb"] = amd["vram_gb"]

    # Встроенное видеоядро
    igpu = _detect_intel_igpu()
    if igpu["vram_gb"] > 0:
        info["gpu_igpu"] = igpu
        info["vram_igpu_gb"] = igpu["vram_gb"]

    # Effective — сколько памяти реально доступно для модели
    # Встроенное видеоядро × 0.5 (разделяемая память)
    effective = (
        info["ram_avail_gb"]
        + info["vram_discrete_gb"]
        + info["vram_igpu_gb"] * 0.5
    )
    info["effective_gb"] = round(effective, 1)

    return info


def get_profile(info: dict) -> dict:
    """Выбирает профиль по effective_gb."""
    for p in _PROFILES:
        if info["effective_gb"] < p["max_gb"]:
            return p
    return _PROFILES[-1]


def get_ollama_params(info: dict, profile: dict) -> dict:
    """
    Формирует параметры запуска Ollama для максимального использования ресурсов:
      num_gpu    — слои на GPU (-1 = авто)
      num_thread — CPU потоки
      num_ctx    — размер контекста
    """
    params = {
        "num_gpu":    -1,     # Ollama сам распределит по GPU
        "num_thread": max(2, info["cpu_threads"] - 1),  # оставляем 1 поток ОС
        "num_ctx":    profile["num_ctx"],
    }

    # Если нет GPU вообще — явно отключаем GPU слои
    if info["vram_discrete_gb"] == 0 and info["vram_igpu_gb"] == 0:
        params["num_gpu"] = 0

    # Если только iGPU — ограничиваем число GPU слоёв
    elif info["vram_discrete_gb"] == 0 and info["vram_igpu_gb"] > 0:
        # iGPU обычно тянет 10-20 слоёв
        igpu_gb = info["vram_igpu_gb"]
        if igpu_gb < 1:
            params["num_gpu"] = 5
        elif igpu_gb < 2:
            params["num_gpu"] = 15
        else:
            params["num_gpu"] = 25

    # Контекст: ограничим если мало памяти
    avail = info["ram_avail_gb"]
    if avail < 3:
        params["num_ctx"] = min(params["num_ctx"], 1024)
    elif avail < 6:
        params["num_ctx"] = min(params["num_ctx"], 2048)

    return params


# ─────────────────────────────────────────────────────────────────────────────
# РАБОТА С OLLAMA API
# ─────────────────────────────────────────────────────────────────────────────

def get_installed_models(ollama_url: str = "http://localhost:11434") -> list[str]:
    try:
        import requests
        r = requests.get(f"{ollama_url}/api/tags", timeout=5)
        if r.status_code == 200:
            return [m["name"] for m in r.json().get("models", [])]
    except Exception as e:
        log.warning("Ollama models list: %s", e)
    return []


def find_best_model(preferred: list[str], installed: list[str]) -> Optional[str]:
    inst_lower = [m.lower() for m in installed]
    for cand in preferred:
        cl = cand.lower()
        if cl in inst_lower:
            return installed[inst_lower.index(cl)]
        base = cl.split(":")[0]
        for i, inst in enumerate(inst_lower):
            if inst == base or inst.startswith(base + ":"):
                return installed[i]
    return None


def pull_model(model: str, ollama_url: str = "http://localhost:11434") -> bool:
    log.info("Ollama pull: %s ...", model)
    try:
        import requests
        r = requests.post(
            f"{ollama_url}/api/pull",
            json={"name": model, "stream": False},
            timeout=600,
        )
        return r.status_code == 200
    except Exception as e:
        log.error("Ollama pull %s: %s", model, e)
        return False


def apply_ollama_params(params: dict) -> None:
    """
    Применяет параметры через переменные окружения Ollama.
    Ollama читает их при старте модели.
    """
    if params.get("num_gpu") is not None and params["num_gpu"] >= 0:
        os.environ["OLLAMA_NUM_GPU"] = str(params["num_gpu"])
    if params.get("num_thread"):
        os.environ["OLLAMA_NUM_THREAD"] = str(params["num_thread"])
    # num_ctx передаётся в теле запроса к /api/generate — сохраняем в env
    if params.get("num_ctx"):
        os.environ["ARGOS_OLLAMA_CTX"] = str(params["num_ctx"])


# ─────────────────────────────────────────────────────────────────────────────
# ГЛАВНАЯ ФУНКЦИЯ
# ─────────────────────────────────────────────────────────────────────────────

def autoselect(
    ollama_url: str = "http://localhost:11434",
    auto_pull: bool = True,
    force: bool = False,
) -> dict:
    """
    Автовыбор модели Ollama под железо системы.
    Учитывает RAM + дискретный GPU + встроенное видеоядро.
    """
    env_model = os.getenv("ARGOS_OLLAMA_MODEL", "").strip()
    if env_model and not force:
        return {
            "model": env_model, "profile": "manual", "action": "env_set",
            "info": {}, "params": {},
            "message": f"ℹ️ Модель задана вручную: {env_model}",
        }

    info    = get_system_info()
    profile = get_profile(info)
    params  = get_ollama_params(info, profile)

    log.info(
        "Ollama autoselect: RAM=%.1fGB VRAM_discrete=%.1fGB iGPU=%.1fGB "
        "effective=%.1fGB → профиль=%s",
        info["ram_total_gb"], info["vram_discrete_gb"],
        info["vram_igpu_gb"], info["effective_gb"], profile["name"],
    )

    installed = get_installed_models(ollama_url)
    best      = find_best_model(profile["preferred"], installed)

    if best:
        os.environ["OLLAMA_MODEL"] = best
        apply_ollama_params(params)
        msg = _format_report(info, profile, params, best, "found")
        return {"model": best, "profile": profile["name"], "action": "found",
                "info": info, "params": params, "message": msg}

    # Нет подходящей — скачиваем
    pull_target = profile["pull"]
    if auto_pull:
        log.info("Ollama: скачиваю %s ...", pull_target)
        if pull_model(pull_target, ollama_url):
            os.environ["OLLAMA_MODEL"] = pull_target
            apply_ollama_params(params)
            msg = _format_report(info, profile, params, pull_target, "pulled")
            return {"model": pull_target, "profile": profile["name"],
                    "action": "pulled", "info": info, "params": params,
                    "message": msg}

    fallback = installed[0] if installed else "llama3"
    os.environ["OLLAMA_MODEL"] = fallback
    apply_ollama_params(params)
    msg = (
        f"⚠️ Ollama: подходящей модели нет\n"
        f"  Рекомендуется: ollama pull {pull_target}\n"
        f"  Fallback: {fallback}"
    )
    return {"model": fallback, "profile": profile["name"], "action": "none",
            "info": info, "params": params, "message": msg}


def _format_report(info: dict, profile: dict, params: dict,
                   model: str, action: str) -> str:
    gpu_disc = info["gpu_discrete"]
    gpu_igpu = info["gpu_igpu"]

    gpu_lines = []
    if gpu_disc.get("name"):
        gpu_lines.append(
            f"  GPU дискретный: {gpu_disc['name']} "
            f"({gpu_disc['vram_gb']} GB VRAM)"
        )
    if gpu_igpu.get("name"):
        gpu_lines.append(
            f"  GPU встроенный: {gpu_igpu['name']} "
            f"({gpu_igpu['vram_gb']} GB shared)"
        )
    if not gpu_lines:
        gpu_lines.append("  GPU: не обнаружен (CPU-only режим)")

    action_icon = {"found": "✅", "pulled": "📥", "none": "⚠️"}.get(action, "ℹ️")

    return "\n".join([
        f"{action_icon} Ollama автовыбор:",
        f"  Профиль: {profile['label']}",
        f"  RAM: {info['ram_total_gb']} GB (доступно {info['ram_avail_gb']} GB)",
        f"  CPU: {info['cpu_model'][:55]}",
        f"  CPU потоков: {info['cpu_threads']}",
        *gpu_lines,
        f"  Effective память: {info['effective_gb']} GB",
        f"  Выбрана модель: {model}",
        f"  Параметры Ollama:",
        f"    num_gpu={params['num_gpu']} "
        f"num_thread={params['num_thread']} "
        f"num_ctx={params['num_ctx']}",
    ])


def status_report(ollama_url: str = "http://localhost:11434") -> str:
    """Полный отчёт о железе и текущей конфигурации Ollama."""
    info     = get_system_info()
    profile  = get_profile(info)
    params   = get_ollama_params(info, profile)
    installed = get_installed_models(ollama_url)
    current  = os.getenv("OLLAMA_MODEL", "не задана")

    gpu_disc = info["gpu_discrete"]
    gpu_igpu = info["gpu_igpu"]

    lines = [
        "🦙 OLLAMA — СТАТУС СИСТЕМЫ:",
        f"  Профиль: {profile['label']}",
        "  ─────────────────────────────",
        f"  RAM всего:     {info['ram_total_gb']} GB",
        f"  RAM доступно:  {info['ram_avail_gb']} GB",
        f"  CPU:           {info['cpu_model'][:50]}",
        f"  CPU потоков:   {info['cpu_threads']}",
        f"  ОС:            {info['os']} {info['arch']}",
    ]

    if gpu_disc.get("name"):
        lines.append(f"  GPU дискретный: {gpu_disc['name']}")
        lines.append(f"    VRAM: {gpu_disc['vram_gb']} GB")
        if gpu_disc.get("driver"):
            lines.append(f"    Драйвер: {gpu_disc['driver']}")
    else:
        lines.append("  GPU дискретный: не обнаружен")

    if gpu_igpu.get("name"):
        lines.append(f"  GPU встроенный: {gpu_igpu['name']}")
        lines.append(f"    VRAM shared: {gpu_igpu['vram_gb']} GB × 0.5 = {gpu_igpu['vram_gb'] * 0.5:.1f} GB эфф.")
    else:
        lines.append("  GPU встроенный: не обнаружен")

    lines += [
        f"  Effective GB:  {info['effective_gb']} GB (RAM + VRAM)",
        "  ─────────────────────────────",
        f"  Текущая модель: {current}",
        f"  Параметры: num_gpu={params['num_gpu']} "
        f"num_thread={params['num_thread']} "
        f"num_ctx={params['num_ctx']}",
        f"  Установлено моделей: {len(installed)}",
    ]
    if installed:
        lines.append(f"  Модели: {', '.join(installed)}")
    lines.append(f"  Рекомендуемые: {', '.join(profile['preferred'][:3])}")

    return "\n".join(lines)
