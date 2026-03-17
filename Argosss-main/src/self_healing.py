\
"""self_healing.py — Автоисправление Python-кода Аргоса"""
from __future__ import annotations
import ast, os, sys, importlib
from typing import Optional, Tuple
from src.argos_logger import get_logger
log = get_logger("argos.healing")

class SelfHealingEngine:
    def __init__(self, core=None):
        self.core = core
        self._history: list[dict] = []

    def heal_code(self, code: str, error_msg: str) -> Optional[str]:
        if not self.core: return None
        prompt = (f"Исправь Python-код. Ошибка: {error_msg}\\n\\n"
                  f"Код:\\n{code}\\n\\nВерни только исправленный код без пояснений.")
        try:
            fixed = self.core._ask_gemini("Ты Python-эксперт.", prompt)
            if fixed:
                fixed = fixed.replace("```python","").replace("```","").strip()
                self._history.append({"error":error_msg,"fixed":True})
                log.info("Self-healing: исправление применено")
                return fixed
        except Exception as e:
            log.warning("Self-healing error: %s", e)
        return None

    def validate_code(self, code: str) -> Tuple[bool, str]:
        try:
            ast.parse(code)
            return True, "✅ Синтаксис OK"
        except SyntaxError as e:
            return False, f"❌ SyntaxError: {e}"

    def validate_file(self, path: str) -> Tuple[bool, str]:
        if not os.path.isfile(path):
            return False, f"файл не найден: {path}"
        try:
            with open(path, encoding="utf-8") as f:
                ast.parse(f.read())
            return True, "✅ Синтаксис OK"
        except SyntaxError as e:
            return False, f"❌ SyntaxError: {e}"

    def validate_all_src(self) -> str:
        ok, fail, errors = 0, 0, []
        for root, _, fnames in os.walk("src"):
            for fname in fnames:
                if not fname.endswith(".py"): continue
                fp = os.path.join(root, fname)
                valid, msg = self.validate_file(fp)
                if valid: ok += 1
                else: fail += 1; errors.append(f"  ❌ {fp}: {msg}")
        header = f"🩹 ВАЛИДАЦИЯ: {ok} ✅ / {fail} ❌"
        return header + ("\\n" + "\\n".join(errors) if errors else "\\n  Все файлы валидны.")

    def history(self) -> str:
        if not self._history: return "🩹 История лечений пуста."
        lines = ["🩹 ИСТОРИЯ ЛЕЧЕНИЙ:"]
        for i,h in enumerate(self._history[-10:],1):
            lines.append(f"  {i}. {h['error'][:60]} → {'✅' if h['fixed'] else '❌'}")
        return "\\n".join(lines)

    def status(self) -> str:
        return f"🩹 Self-Healing: активен | Случаев: {len(self._history)}"
