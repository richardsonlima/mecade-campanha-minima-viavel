"""Camada 6, perfil mínimo: trilha de auditoria em JSONL com hashes encadeados.

A escrita é assíncrona. No caminho de decisão o evento só entra na fila; o hash e a gravação em
disco ficam numa thread separada. Meço o custo desse enfileiramento (enqueue_latency) e reporto
como Δ_audit, que é critério de aceitação na Tabela 4.2.

Cada registro guarda o hash do anterior, então verify() pega qualquer alteração, remoção ou
troca de ordem das linhas.
"""
from __future__ import annotations

import hashlib
import json
import queue
import threading
import time
from pathlib import Path

GENESIS = "0" * 64


def _digest(prev_hash: str, body: dict) -> str:
    canonical = json.dumps(body, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
    return hashlib.sha256((prev_hash + canonical).encode("utf-8")).hexdigest()


class AuditLog:
    def __init__(self, path: str | Path | None, enabled: bool = True):
        self.enabled = bool(enabled and path)
        self.enqueue_latency: list[float] = []
        self._q: queue.Queue = queue.Queue()
        self._seq = 0
        if self.enabled:
            self.path = Path(path)
            self.path.parent.mkdir(parents=True, exist_ok=True)
            self._fh = self.path.open("a", encoding="utf-8")
            self._prev = GENESIS
            self._thread = threading.Thread(target=self._writer, daemon=True)
            self._thread.start()

    def record(self, event: dict) -> None:
        """Roda no caminho de decisão, por isso só enfileira (e mede quanto isso custa)."""
        if not self.enabled:
            return
        t0 = time.perf_counter()
        self._q.put({"wall_time": time.time(), **event})
        self.enqueue_latency.append(time.perf_counter() - t0)

    def _writer(self) -> None:
        while True:
            item = self._q.get()
            if item is None:
                break
            self._seq += 1
            body = {"seq": self._seq, "prev_hash": self._prev, "event": item}
            h = _digest(self._prev, body)
            self._fh.write(json.dumps({**body, "hash": h}, ensure_ascii=False) + "\n")
            self._fh.flush()
            self._prev = h

    def close(self) -> dict:
        if not self.enabled:
            return {"enabled": False}
        self._q.put(None)
        self._thread.join(timeout=10)
        self._fh.close()
        lat = sorted(self.enqueue_latency)
        p95 = lat[int(0.95 * (len(lat) - 1))] if lat else None
        return {"enabled": True, "records": self._seq, "enqueue_p95_ms": None if p95 is None else p95 * 1000}


def verify(path: str | Path) -> tuple[bool, int, str]:
    """Recalcula a cadeia inteira e devolve (íntegra?, registros verificados, mensagem)."""
    prev = GENESIS
    n = 0
    with Path(path).open(encoding="utf-8") as fh:
        for n, line in enumerate(fh, start=1):
            rec = json.loads(line)
            body = {k: rec[k] for k in ("seq", "prev_hash", "event")}
            if rec["prev_hash"] != prev:
                return False, n - 1, f"quebra de encadeamento na linha {n}"
            if _digest(prev, body) != rec["hash"]:
                return False, n - 1, f"hash inválido na linha {n}"
            prev = rec["hash"]
    return True, n, "cadeia íntegra"
