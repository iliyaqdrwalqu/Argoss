"""
jarvis_engine.py — HuggingGPT / JARVIS-inspired task orchestration.
4-stage pipeline: Planning → Model Selection → Execution → Synthesis.
"""
import copy
import json
import os
import re
import threading
import time
import uuid
from dataclasses import dataclass, field
from typing import Any, Optional
import requests
from src.argos_logger import get_logger

log = get_logger("argos.jarvis")

TASK_PLANNING_SYSTEM = (
    "Ты ИИ-планировщик задач Argos. Пользователь даёт запрос на естественном языке. "
    "Разбей его на атомарные подзадачи и верни JSON-массив.\n"
    'Каждая задача: {"id": int, "task": str, "args": dict, "dep": [int]}\n'
    "dep содержит id задач-зависимостей (-1 если нет). "
    "task — одна из: text-generation, summarization, translation, question-answering, "
    "text-classification, image-classification, object-detection, image-to-text, "
    "text-to-image, text-to-speech, automatic-speech-recognition, "
    "argos-command, argos-tool-call, argos-vision, argos-iot.\n"
    "Если запрос тривиальный (обычный разговор), верни [].\n"
    "Отвечай ТОЛЬКО JSON."
)

MODEL_SELECTION_SYSTEM = (
    "Ты ИИ-селектор моделей. Даны задача и список кандидатов. "
    'Выбери лучшую модель и ответь JSON: {"id": str, "reason": str}. '
    "Отвечай ТОЛЬКО JSON."
)

RESPONSE_SYNTHESIS_SYSTEM = (
    "Ты Аргос — автономная ИИ-система. "
    "Тебе даны результаты выполненных подзадач. "
    "Синтезируй единый связный ответ пользователю на русском языке."
)

HF_INFERENCE_URL = "https://api-inference.huggingface.co/models"

DEFAULT_MODELS_MAP: dict = {
    "text-generation":   [{"id": "meta-llama/Llama-3.2-3B-Instruct", "likes": 500}],
    "summarization":     [{"id": "facebook/bart-large-cnn", "likes": 2000}],
    "translation":       [{"id": "Helsinki-NLP/opus-mt-ru-en", "likes": 300}],
    "text-classification":[{"id": "cardiffnlp/twitter-roberta-base-sentiment-latest", "likes": 500}],
    "question-answering":[{"id": "deepset/roberta-base-squad2", "likes": 800}],
    "image-to-text":     [{"id": "Salesforce/blip-image-captioning-large", "likes": 1200}],
    "text-to-image":     [{"id": "stabilityai/stable-diffusion-xl-base-1.0", "likes": 5000}],
    "text-to-speech":    [{"id": "facebook/mms-tts-rus", "likes": 50}],
    "automatic-speech-recognition": [{"id": "openai/whisper-large-v3", "likes": 3000}],
}


@dataclass
class TaskResult:
    task: dict
    choose: dict = field(default_factory=dict)
    inference_result: dict = field(default_factory=dict)


class JarvisEngine:
    """HuggingGPT-style orchestration engine для Argos."""

    def __init__(self, core=None):
        self.core = core
        self.hf_token = os.getenv("HUGGINGFACE_TOKEN", "") or os.getenv("HF_TOKEN", "")
        self.hf_headers = {}
        if self.hf_token.startswith("hf_"):
            self.hf_headers = {"Authorization": f"Bearer {self.hf_token}"}
        self.models_map = copy.deepcopy(DEFAULT_MODELS_MAP)
        self.local_endpoint = os.getenv("JARVIS_LOCAL_ENDPOINT", "")
        self.max_parallel = int(os.getenv("JARVIS_MAX_PARALLEL", "4"))
        self.timeout = int(os.getenv("JARVIS_TASK_TIMEOUT", "120"))
        os.makedirs("public/images", exist_ok=True)
        os.makedirs("public/audios", exist_ok=True)
        log.info("JarvisEngine: HF=%s local=%s", "✅" if self.hf_token else "❌",
                 self.local_endpoint or "none")

    def process(self, user_input: str, context: list = None) -> dict:
        t0 = time.time()
        try:
            tasks = self._plan(user_input, context or [])
            if not tasks:
                reply = self._ask_core(user_input, context or [])
                return {"message": reply, "tasks": [], "results": [], "timing": time.time()-t0}

            results = self._execute_parallel(tasks)
            message = self._synthesize(user_input, results)
            return {"message": message, "tasks": tasks, "results": results, "timing": time.time()-t0}
        except Exception as e:
            log.error("Jarvis process: %s", e)
            fallback = self._ask_core(user_input, context or []) if self.core else str(e)
            return {"message": fallback, "tasks": [], "results": [], "timing": time.time()-t0}

    def _plan(self, user_input: str, context: list) -> list:
        prompt = f"Запрос пользователя: {user_input}"
        raw = self._ask_llm(TASK_PLANNING_SYSTEM, prompt, context)
        try:
            raw = re.sub(r"```(?:json)?|```", "", raw).strip()
            return json.loads(raw)
        except Exception:
            return []

    def _execute_parallel(self, tasks: list) -> list:
        results = {}
        remaining = list(tasks)
        max_rounds = len(tasks) + 1

        for _ in range(max_rounds):
            if not remaining:
                break
            runnable = [t for t in remaining if all(
                d == -1 or d in results for d in t.get("dep", [-1])
            )]
            if not runnable:
                break
            threads = []
            local_results = {}

            def run_task(task, _results):
                tid = task["id"]
                r = self._execute_task(task, _results)
                local_results[tid] = r

            for task in runnable[:self.max_parallel]:
                t = threading.Thread(target=run_task, args=(task, results))
                t.start()
                threads.append(t)

            for t in threads:
                t.join(timeout=self.timeout)

            results.update(local_results)
            remaining = [t for t in remaining if t["id"] not in results]

        return list(results.values())

    def _execute_task(self, task: dict, prior_results: dict) -> dict:
        task_type = task.get("task", "")
        args = task.get("args", {})

        # Аргос-нативные задачи
        if task_type == "argos-command" and self.core:
            cmd = args.get("text", args.get("input", ""))
            result = self.core.process(cmd) if cmd else "no command"
            return {"task": task, "result": result}

        # HuggingFace Inference
        model = self._select_model(task_type)
        if model and self.hf_token:
            result = self._hf_inference(model, args)
            return {"task": task, "model": model, "result": result}

        # Локальный endpoint
        if self.local_endpoint:
            result = self._local_inference(task_type, args)
            return {"task": task, "result": result}

        return {"task": task, "result": f"[no backend for {task_type}]"}

    def _select_model(self, task_type: str) -> Optional[str]:
        candidates = self.models_map.get(task_type, [])
        if not candidates:
            return None
        return max(candidates, key=lambda m: m.get("likes", 0))["id"]

    def _hf_inference(self, model_id: str, args: dict) -> str:
        url = f"{HF_INFERENCE_URL}/{model_id}"
        payload = {"inputs": args.get("text", args.get("input", str(args)))}
        try:
            r = requests.post(url, headers=self.hf_headers, json=payload, timeout=60)
            if r.ok:
                data = r.json()
                if isinstance(data, list) and data:
                    return str(data[0].get("generated_text", data[0]))
                return str(data)
            return f"HF error {r.status_code}: {r.text[:100]}"
        except Exception as e:
            return f"HF request: {e}"

    def _local_inference(self, task_type: str, args: dict) -> str:
        try:
            r = requests.post(
                f"{self.local_endpoint}/generate",
                json={"task": task_type, **args},
                timeout=self.timeout
            )
            return r.json().get("result", r.text[:200])
        except Exception as e:
            return f"Local inference: {e}"

    def _synthesize(self, user_input: str, results: list) -> str:
        summary = "\n".join(
            f"[{r.get('task', {}).get('task', '?')}]: {r.get('result', '')[:300]}"
            for r in results
        )
        prompt = f"Запрос: {user_input}\nРезультаты:\n{summary}"
        return self._ask_llm(RESPONSE_SYNTHESIS_SYSTEM, prompt, [])

    def _ask_llm(self, system: str, prompt: str, context: list) -> str:
        if self.core:
            try:
                return self.core._ask_gemini(prompt, system_override=system) or prompt
            except Exception:
                pass
            try:
                return self.core.process(prompt)
            except Exception:
                pass
        return f"[JARVIS no LLM]: {prompt[:100]}"

    def _ask_core(self, user_input: str, context: list) -> str:
        if self.core:
            try:
                return self.core.process(user_input)
            except Exception:
                pass
        return user_input

    def status(self) -> str:
        return (
            f"🤖 JARVIS ENGINE:\n"
            f"  HF Token:  {'✅' if self.hf_token else '❌'}\n"
            f"  Local:     {self.local_endpoint or 'нет'}\n"
            f"  Parallel:  {self.max_parallel}"
        )
