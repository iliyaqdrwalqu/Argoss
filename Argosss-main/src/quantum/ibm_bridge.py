\
"""
ibm_bridge.py — Мост к IBM Quantum (Qiskit + IBM Quantum Network)
Активируется в состоянии All-Seeing.
Команды: ibm квантовый | квантовый мост | ibm quantum
"""
import os
from src.argos_logger import get_logger
log = get_logger("argos.ibm_quantum")

IBM_TOKEN = os.getenv("IBM_QUANTUM_TOKEN", "")


class IBMQuantumBridge:
    def __init__(self):
        self.token    = IBM_TOKEN
        self._service = None
        self._connected = False

    @property
    def available(self) -> bool:
        return bool(self.token)

    def connect(self) -> str:
        if not self.token:
            return ("❌ IBM_QUANTUM_TOKEN не задан.\\n"
                    "  Получи токен: https://quantum.ibm.com\\n"
                    "  Добавь в .env: IBM_QUANTUM_TOKEN=xxxxxxx")
        try:
            from qiskit_ibm_runtime import QiskitRuntimeService
            QiskitRuntimeService.save_account(
                channel="ibm_quantum", token=self.token, overwrite=True
            )
            self._service = QiskitRuntimeService(channel="ibm_quantum")
            self._connected = True
            backends = self._service.backends()
            names = [b.name for b in backends[:5]]
            log.info("IBM Quantum: подключён, %d backend(s)", len(backends))
            return (f"✅ IBM Quantum подключён\\n"
                    f"  Backends ({len(backends)}): {', '.join(names)}")
        except ImportError:
            return "❌ Установи: pip install qiskit qiskit-ibm-runtime"
        except Exception as e:
            return f"❌ IBM Quantum: {e}"

    def check_ibm_status(self) -> str:
        if not self.available:
            return ("🌌 IBM Quantum Bridge\\n"
                    "  Статус: ❌ не настроен\\n"
                    "  Токен: IBM_QUANTUM_TOKEN не задан в .env")
        if not self._connected:
            return self.connect()
        try:
            backends = self._service.backends()
            lines = [f"🌌 IBM Quantum Bridge\\n  Статус: ✅ подключён\\n  Backends:"]
            for b in backends[:8]:
                try:
                    status = b.status()
                    op = "✅" if status.operational else "⚠️"
                    queue = getattr(status, "pending_jobs", "?")
                    lines.append(f"    {op} {b.name} | queue: {queue}")
                except Exception:
                    lines.append(f"    • {b.name}")
            return "\\n".join(lines)
        except Exception as e:
            return f"❌ IBM Quantum status: {e}"

    def run_bell_circuit(self) -> str:
        """Тестовый Bell circuit на реальном квантовом железе."""
        if not self._connected:
            r = self.connect()
            if "❌" in r: return r
        try:
            from qiskit import QuantumCircuit
            from qiskit_ibm_runtime import SamplerV2 as Sampler
            qc = QuantumCircuit(2, 2)
            qc.h(0); qc.cx(0, 1); qc.measure_all()
            backend = self._service.least_busy(operational=True, simulator=False)
            sampler = Sampler(backend)
            job = sampler.run([qc], shots=1024)
            result = job.result()
            counts = result[0].data.meas.get_counts()
            return (f"⚛️ Bell Circuit на {backend.name}:\\n"
                    f"  Результат: {counts}\\n"
                    f"  Запутанность подтверждена: {'00' in counts and '11' in counts}")
        except ImportError:
            return "❌ Установи: pip install qiskit qiskit-ibm-runtime"
        except Exception as e:
            return f"❌ Bell circuit: {e}"

    def status(self) -> str:
        return self.check_ibm_status()
