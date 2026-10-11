"""Backends reais: Prometheus pela API HTTP, Kubernetes via kubectl e relógio de parede.

O backend de simulação (sim.py) tem a mesma interface, para eu testar o pipeline sem cluster.
"""
from __future__ import annotations

import json
import math
import subprocess
import time

import requests
import yaml


class RealClock:
    def now(self) -> float:
        return time.time()

    def sleep_until(self, t: float) -> None:
        d = t - time.time()
        if d > 0:
            time.sleep(d)


class PromClient:
    def __init__(self, url: str, timeout: float = 5.0):
        self.url = url.rstrip("/")
        self.timeout = timeout

    def instant(self, query: str) -> float | None:
        r = requests.get(f"{self.url}/api/v1/query", params={"query": query}, timeout=self.timeout)
        r.raise_for_status()
        res = r.json()["data"]["result"]
        if not res:
            return None
        v = float(res[0]["value"][1])
        return None if math.isnan(v) or math.isinf(v) else v

    def range(self, query: str, start: float, end: float, step: float) -> list[tuple[float, float]]:
        r = requests.get(f"{self.url}/api/v1/query_range",
                         params={"query": query, "start": start, "end": end, "step": step},
                         timeout=max(self.timeout, 30))
        r.raise_for_status()
        res = r.json()["data"]["result"]
        return [(float(t), float(v)) for t, v in res[0]["values"]] if res else []


class Kubectl:
    """Operações de cluster da campanha. Passo tudo pelo `kubectl` para ficar fácil de auditar no shell."""

    def __init__(self, namespace: str):
        self.ns = namespace

    def _run(self, *args: str, input_text: str | None = None) -> str:
        p = subprocess.run(["kubectl", *args], input=input_text, capture_output=True, text=True)
        if p.returncode != 0:
            raise RuntimeError(f"kubectl {' '.join(args)} falhou: {p.stderr.strip()}")
        return p.stdout

    def pods(self, app: str) -> list[str]:
        out = self._run("-n", self.ns, "get", "pods", "-l", f"app={app}",
                        "--field-selector=status.phase=Running", "-o", "json")
        return sorted(i["metadata"]["name"] for i in json.loads(out)["items"])

    def apply(self, manifest: dict) -> None:
        self._run("apply", "-f", "-", input_text=yaml.safe_dump(manifest))

    def delete(self, kind: str, name: str) -> None:
        self._run("-n", self.ns, "delete", kind, name, "--ignore-not-found", "--wait=false")

    def delete_all_chaos(self) -> None:
        for kind in ("schedules.chaos-mesh.org", "networkchaos.chaos-mesh.org", "podchaos.chaos-mesh.org"):
            self._run("-n", self.ns, "delete", kind, "--all", "--ignore-not-found")

    def scale(self, deployment: str, replicas: int) -> None:
        self._run("-n", self.ns, "scale", f"deployment/{deployment}", f"--replicas={replicas}")

    def restart(self, deployment: str) -> None:
        self._run("-n", self.ns, "rollout", "restart", f"deployment/{deployment}")

    def wait_rollout(self, deployment: str, timeout: str = "300s") -> None:
        self._run("-n", self.ns, "rollout", "status", f"deployment/{deployment}", f"--timeout={timeout}")

    def server_version(self) -> str:
        try:
            return json.loads(self._run("version", "-o", "json"))["serverVersion"]["gitVersion"]
        except Exception:  # noqa: BLE001 (é só metadado)
            return "unknown"
