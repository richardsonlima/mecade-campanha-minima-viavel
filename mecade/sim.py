"""Backend de simulação, que uso apenas para testar o pipeline sem cluster.

Os dados gerados aqui não são evidência experimental. Toda réplica simulada sai marcada com
backend="sim", vai para data/sim/ e a análise a ignora por padrão.

O modelo é propositalmente simples: uma planta com estado latente por cenário, ruído gaussiano
com semente, uma suavização exponencial que imita a janela rate[30s] do Prometheus e resposta às
mitigações (o restart troca a instância afetada em uns 30 s; escalar para 3 réplicas reduz o
impacto do pod kill).
"""
from __future__ import annotations

import random


class VirtualClock:
    def __init__(self, start: float = 1_800_000_000.0):
        self.t = start

    def now(self) -> float:
        return self.t

    def sleep_until(self, t: float) -> None:
        self.t = max(self.t, t)


class SimWorld:
    BASE = {"p95": 0.12, "p99": 0.25, "error_rate": 0.002, "throughput": 19.5,
            "cpu_boutique": 1.6, "cpu_target": 0.05}

    def __init__(self, clock: VirtualClock, seed: int):
        self.clock = clock
        self.rng = random.Random(seed)
        self.scenario: str | None = None
        self.chaos_on = False
        self.chaos_start = 0.0
        self.instance_replaced_at: float | None = None
        self.replicas = 1
        self.smooth = dict(self.BASE)

    # interface equivalente à do Kubectl
    def pods(self, app: str) -> list[str]:
        return [f"{app}-sim-0"]

    def apply(self, manifest: dict) -> None:
        self.chaos_on = True
        self.chaos_start = self.clock.now()

    def delete(self, kind: str, name: str) -> None:
        self.chaos_on = False

    def delete_all_chaos(self) -> None:
        self.chaos_on = False

    def scale(self, deployment: str, replicas: int) -> None:
        self.replicas = replicas

    def restart(self, deployment: str) -> None:
        # Antes da injeção, o restart só renova as instâncias (a falha será injetada nas novas).
        # Durante a injeção, troca a instância afetada, que fica pronta uns 30 s depois.
        if self.chaos_on:
            self.instance_replaced_at = self.clock.now() + 30.0

    def wait_rollout(self, deployment: str, timeout: str = "300s") -> None:
        pass

    def server_version(self) -> str:
        return "sim"

    def reset(self, scenario: str | None) -> None:
        self.scenario = scenario
        self.chaos_on = False
        self.instance_replaced_at = None
        self.replicas = 1
        self.smooth = dict(self.BASE)

    # interface equivalente à do PromClient
    def _target(self) -> dict:
        t = self.clock.now()
        tgt = dict(self.BASE)
        if not self.chaos_on or self.scenario is None:
            return tgt
        replaced = self.instance_replaced_at is not None and t >= self.instance_replaced_at
        el = t - self.chaos_start
        if self.scenario.startswith("s1") and not replaced:
            tgt.update(p95=0.55, p99=0.75, error_rate=0.004)
        elif self.scenario.startswith("s2") and not replaced:
            if el % 60 < 20:                                  # rajadas de 20 s a cada 60 s
                tgt.update(p95=1.4, p99=2.6, error_rate=0.06)
        elif self.scenario.startswith("s3"):
            if el % 45 < 20:                                  # indisponibilidade até o novo pod ficar pronto
                factor = 0.12 if self.replicas >= 3 else 1.0
                tgt.update(error_rate=0.002 + 0.30 * factor, p99=0.25 + 0.6 * factor, p95=0.12 + 0.2 * factor)
        return tgt

    def instant(self, query: str) -> float | None:
        name = query  # no simulador a "consulta" é o próprio nome do sinal
        tgt = self._target()
        a = 0.35                                              # suavização parecida com a janela de 30 s e passo de 5 s
        self.smooth[name] = (1 - a) * self.smooth.get(name, tgt[name]) + a * tgt[name]
        noise = {"p95": 0.010, "p99": 0.025, "error_rate": 0.0008, "throughput": 0.6,
                 "cpu_boutique": 0.05, "cpu_target": 0.005}[name]
        return max(0.0, self.smooth[name] + self.rng.gauss(0, noise))

    def range(self, query: str, start: float, end: float, step: float) -> list[tuple[float, float]]:
        return []
