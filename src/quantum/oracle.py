#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
oracle.py — Квантовый оракул Аргоса.

Генерирует истинно случайные числа:
  1. Через IBM Quantum (если установлен qiskit и есть IBM_TOKEN)
  2. Через локальный симулятор Qiskit Aer (если установлен qiskit-aer)
  3. Через криптографически стойкий PRNG (os.urandom) как запасной вариант

Использование:
    from src.quantum.oracle import QuantumOracle
    oracle = QuantumOracle()
    bits   = oracle.generate_bits(256)    # список из 256 битов
    number = oracle.random_int(0, 1000)   # случайное целое
    seed   = oracle.generate_seed(128)    # bytes
"""
from __future__ import annotations

import os
import struct
import warnings
from typing import List, Optional

# ── Попытка импортировать Qiskit ─────────────────
try:
    from qiskit import QuantumCircuit, transpile
    HAVE_QISKIT = True
except ImportError:
    HAVE_QISKIT = False

try:
    from qiskit_aer import AerSimulator
    HAVE_AER = True
except ImportError:
    HAVE_AER = False


class QuantumOracle:
    """
    Квантовый оракул — источник истинной случайности.

    Параметры
    ---------
    use_real_quantum : bool
        Если True — пытаемся использовать реальный IBM-квантовый компьютер.
    token : str | None
        IBM Quantum API token (берётся из переменной IBM_QUANTUM_TOKEN).
    shots_per_bit : int
        Число прогонов схемы на один бит (по умолчанию 1).
    """

    def __init__(
        self,
        use_real_quantum: bool = False,
        token: Optional[str] = None,
        shots_per_bit: int = 1,
    ):
        self.use_real_quantum = use_real_quantum
        self.token = token or os.getenv("IBM_QUANTUM_TOKEN", "")
        self.shots_per_bit = max(1, shots_per_bit)
        self._backend = None
        self._setup_backend()

    def _setup_backend(self) -> None:
        if self.use_real_quantum and self.token and HAVE_QISKIT:
            try:
                from qiskit_ibm_runtime import QiskitRuntimeService
                svc = QiskitRuntimeService(channel="ibm_quantum", token=self.token)
                self._backend = svc.least_busy(operational=True, simulator=False)
                return
            except Exception as e:
                warnings.warn(f"QuantumOracle: IBM Quantum недоступен ({e}), переключаемся на симулятор.")

        if HAVE_AER:
            self._backend = AerSimulator()
            return

        warnings.warn("QuantumOracle: Qiskit не установлен. Используется os.urandom.")
        self._backend = None

    # ── Генерация битов ──────────────────────────────
    def generate_bits(self, n: int = 256) -> List[int]:
        """
        Генерирует n случайных битов (каждый — 0 или 1).

        Алгоритм:
          - Создаём квантовую схему с 1 кубитом
          - Применяем ворота Адамара (H): суперпозиция |0⟩+|1⟩)/√2
          - Измеряем → истинно случайный бит
          - Повторяем n раз
        """
        if self._backend is None or not HAVE_QISKIT:
            return self._urandom_bits(n)

        bits: List[int] = []
        try:
            # Собираем биты батчами по 64 для скорости
            batch = 64
            while len(bits) < n:
                need = min(batch, n - len(bits))
                qc = QuantumCircuit(need, need)
                for i in range(need):
                    qc.h(i)
                qc.measure(range(need), range(need))
                compiled = transpile(qc, self._backend)
                job    = self._backend.run(compiled, shots=self.shots_per_bit)
                result = job.result()
                counts = result.get_counts()
                # Берём первый (и единственный) измеренный bitstring
                bitstring = max(counts, key=counts.get)
                bits.extend(int(b) for b in reversed(bitstring))
        except Exception as e:
            warnings.warn(f"QuantumOracle: Ошибка квантового запроса ({e}), fallback to urandom.")
            remaining = n - len(bits)
            bits.extend(self._urandom_bits(remaining))

        return bits[:n]

    def _urandom_bits(self, n: int) -> List[int]:
        """Генерирует n битов через os.urandom (криптостойкий PRNG)."""
        raw   = os.urandom((n + 7) // 8)
        bits  = []
        for byte in raw:
            for _ in range(8):
                bits.append(byte & 1)
                byte >>= 1
        return bits[:n]

    # ── Высокоуровневые методы ───────────────────────
    def generate_seed(self, length: int = 1024) -> bytes:
        """
        Генерирует квантовое семя в виде bytes.

        Параметры
        ---------
        length : int
            Длина семени в битах. Будет округлена до ближайшего байта.
        """
        bits   = self.generate_bits(length)
        result = bytearray()
        for i in range(0, len(bits), 8):
            byte_bits = bits[i:i+8]
            # Дополняем нулями, если меньше 8 битов
            while len(byte_bits) < 8:
                byte_bits.append(0)
            byte = sum(b << j for j, b in enumerate(byte_bits))
            result.append(byte)
        return bytes(result)

    def random_int(self, lo: int = 0, hi: int = 255) -> int:
        """
        Возвращает случайное целое число в диапазоне [lo, hi].
        """
        span = hi - lo + 1
        if span <= 0:
            raise ValueError("hi должен быть ≥ lo")
        bits_needed = span.bit_length()
        while True:
            bits  = self.generate_bits(bits_needed)
            value = sum(b << i for i, b in enumerate(bits))
            if value < span:
                return lo + value

    def random_float(self) -> float:
        """Возвращает случайное число [0, 1)."""
        bits = self.generate_bits(53)
        mantissa = sum(b << i for i, b in enumerate(bits))
        return mantissa / (2 ** 53)

    def status(self) -> str:
        """Возвращает строку с описанием текущего бэкенда."""
        if self._backend is None:
            return "⚛️ QuantumOracle: режим os.urandom (Qiskit не установлен)"
        if HAVE_AER:
            name = getattr(self._backend, "name", "AerSimulator")
            return f"⚛️ QuantumOracle: бэкенд {name}"
        return "⚛️ QuantumOracle: IBM Quantum"
