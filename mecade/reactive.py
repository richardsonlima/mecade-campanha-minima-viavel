"""Braço baseline: alerta reativo convencional, com a semântica do `for:` do Prometheus.

A regra só dispara quando a condição fica verdadeira de forma contínua por `for` segundos; uma
única avaliação falsa zera a contagem. A mitigação do runbook entra `response_delay` segundos
depois do disparo, representando o tempo de alguém reconhecer o alerta e executar o runbook.
"""
from __future__ import annotations

import operator
from dataclasses import dataclass, field

OPS = {">": operator.gt, ">=": operator.ge, "<": operator.lt, "<=": operator.le}


@dataclass
class ReactiveRule:
    rules: list[dict]
    for_s: float
    response_delay: float
    baseline: dict[str, float] = field(default_factory=dict)
    t_true: float = 0.0
    fired_at: float | None = None

    def _threshold(self, r: dict) -> float | None:
        if "absolute" in r:
            return float(r["absolute"])
        base = self.baseline.get(r["signal"])
        return None if base is None else float(r["factor_of_baseline"]) * base

    def condition(self, values: dict[str, float | None]) -> bool:
        for r in self.rules:
            v, thr = values.get(r["signal"]), self._threshold(r)
            if v is not None and thr is not None and OPS[r["op"]](v, thr):
                return True
        return False

    def step(self, t: float, values: dict[str, float | None], dt: float) -> list[str]:
        if self.fired_at is not None:
            return []
        if self.condition(values):
            self.t_true += dt
            if self.t_true >= self.for_s:
                self.fired_at = t
                return ["REACTIVE_FIRE"]
        else:
            self.t_true = 0.0
        return []

    def mitigation_due(self, t: float) -> bool:
        return self.fired_at is not None and t >= self.fired_at + self.response_delay
