"""Camada 3: avaliação determinística dos axiomas ALERT, LIMIT e BLOCK.

Segue a especificação da Listagem 3.1 da dissertação, com dois ajustes que descobri ao
implementar e que estão registrados em docs/PROTOCOLO.md:

  D1 (zona morta no LIMIT): o desvio acumulado integra max(0, D_agr - deadband) em vez de D_agr.
     Integrando o desvio bruto, o ruído do estado estacionário se acumula a janela inteira e
     acaba estourando o Chaos Budget mesmo sem falha, principalmente em janelas longas.
  D2 (piso no denominador): ver deviation().

Deixei a classe sem nenhuma E/S para poder testar isoladamente e reaproveitar na análise offline.
"""
from __future__ import annotations

import math
from dataclasses import dataclass, field


def deviation(value: float | None, base: float | None, floor: float) -> float | None:
    """Desvio normalizado D = |M - M_base| / max(M_base, floor), a Eq. 3.1 com piso.

    O piso existe por causa de métricas que ficam perto de zero no estado estacionário, como a
    taxa de erro. Sem ele, um único erro isolado já gera um D enorme.
    """
    if value is None or base is None or (isinstance(value, float) and math.isnan(value)):
        return None
    return abs(value - base) / max(base, floor)


@dataclass
class AxiomParams:
    k: int = 2
    d_on: float = 0.5
    d_off: float = 0.3
    tau_dwell: float = 15.0
    aggregation: str = "max"
    deadband: float = 0.3
    budget_B: float = 60.0

    @classmethod
    def from_dict(cls, d: dict) -> "AxiomParams":
        keys = {f for f in cls.__dataclass_fields__}
        return cls(**{k: v for k, v in d.items() if k in keys})


@dataclass
class AxiomEvaluator:
    params: AxiomParams
    I: float = 0.0
    t_above: float = 0.0
    alert: bool = False
    limit: bool = False
    block: bool = False
    last_D_agr: float | None = None
    history: list = field(default_factory=list)

    def aggregate(self, values: list[float]) -> float:
        if self.params.aggregation == "mean":
            return sum(values) / len(values)
        return max(values)

    def step(self, D: dict[str, float | None], dt: float) -> list[str]:
        """Avalia uma janela e devolve os eventos emitidos nela."""
        p = self.params
        vals = [v for v in D.values() if v is not None]
        events: list[str] = []
        if not vals:                       # sem telemetria não mexo no estado; quem chama registra a falta de dado
            self.last_D_agr = None
            return ["NO_DATA"]

        # ALERT: dwell time, correlação k-de-n e histerese
        violados = sum(1 for v in vals if v > p.d_on)
        if violados >= p.k:
            self.t_above += dt
        elif all(v < p.d_off for v in vals):
            self.t_above = 0.0
            if self.alert:
                self.alert = False
                events.append("ALERT_CLEAR")
        if not self.alert and self.t_above >= p.tau_dwell:
            self.alert = True
            events.append("ALERT")

        # LIMIT: desvio acumulado, com zona morta, comparado ao Chaos Budget
        D_agr = self.aggregate(vals)
        self.last_D_agr = D_agr
        self.I += max(0.0, D_agr - p.deadband) * dt
        if not self.limit and self.I > p.budget_B:
            self.limit = True
            events.append("LIMIT")
            if not self.block:             # o BLOCK trava: só existe uma transição para o Safe State
                self.block = True
                events.append("BLOCK")
        return events
