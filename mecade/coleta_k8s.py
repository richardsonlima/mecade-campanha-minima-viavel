"""Coleta passiva de dados do Kubernetes: pods, endpoints, restartCount, eventos e, na Fase 0, `ss -tni`.

Só observa. Nada aqui entra em decisão do controlador nem em métrica: os arquivos servem para diagnóstico
depois do fato (docs/PROTOCOLO_C3.md, Seções 3.1 e 8.1, itens 1 e 2). Cada coleta que falha vira uma linha
`erro` no arquivo e a coleta segue; um problema de observação nunca derruba a réplica.

Arquivos gravados em `pasta`:
  k8s_coleta.jsonl   um registro por coleta: pods (IP, fase, prontidão, restartCount), endpoints do alvo, ClusterIP
                     e porta do Service do alvo e, se `ss` estiver ligado, o texto cru de `ss -tni` de cada pod
                     dos clientes (inclusive os que estão terminando)
  k8s_eventos.jsonl  cada evento do namespace, uma vez por (uid, count)
  k8s_pods_watch.log saída de `kubectl get pods -w`, com a hora de cada linha (só se `watch` estiver ligado)
"""
from __future__ import annotations

import json
import subprocess
import threading
import time
from pathlib import Path
from typing import Callable

INTERVALO_S = 15.0
IMAGEM_DEPURACAO = "nicolaka/netshoot:v0.13"   # tem `ss`; contêiner efêmero só para ler os sockets do pod
CONTEINER_DEPURACAO = "mecade-dbg"
# fica vivo enquanto o pod viver; se terminar, `_depurador` cria outro com sufixo
COMANDO_DEPURACAO = ("sh", "-c", "while true; do sleep 3600; done")


def _kubectl(*args: str, timeout: float = 30.0) -> str:
    p = subprocess.run(["kubectl", *args], capture_output=True, text=True, timeout=timeout)
    if p.returncode != 0:
        raise RuntimeError(f"kubectl {' '.join(args)} falhou: {p.stderr.strip()}")
    return p.stdout


def resumo_pods(pods_json: dict) -> list[dict]:
    """Pods com o que importa: nome, app, IP, fase, prontidão, restartCount e se estão sendo removidos."""
    out = []
    for i in pods_json.get("items", []):
        st = i.get("status", {})
        cs = st.get("containerStatuses") or []
        out.append({
            "nome": i["metadata"]["name"],
            "app": (i["metadata"].get("labels") or {}).get("app"),
            "ip": st.get("podIP"),
            "fase": st.get("phase"),
            "pronto": bool(cs) and all(c.get("ready") for c in cs),
            "restart_count": sum(int(c.get("restartCount", 0)) for c in cs),
            "removendo": i["metadata"].get("deletionTimestamp") is not None,
            "criado": i["metadata"].get("creationTimestamp"),
        })
    return sorted(out, key=lambda p: p["nome"])


def ip_do_servico(svc_json: dict) -> dict:
    """ClusterIP e portas do Service. Com kube-proxy em iptables, o `ss` dos clientes mostra este IP, não o do pod."""
    spec = svc_json.get("spec", {})
    return {"cluster_ip": spec.get("clusterIP"), "portas": [p.get("port") for p in spec.get("ports") or []]}


def ips_endpoints(ep_json: dict) -> dict:
    """IPs prontos e não prontos de um objeto Endpoints."""
    prontos, nao = [], []
    for sub in ep_json.get("subsets") or []:
        prontos += [a["ip"] for a in sub.get("addresses") or []]
        nao += [a["ip"] for a in sub.get("notReadyAddresses") or []]
    return {"prontos": sorted(prontos), "nao_prontos": sorted(nao)}


class ColetorK8s:
    """Coleta a cada `intervalo` s numa thread, sem relação com o relógio de decisão do runner."""

    def __init__(self, namespace: str, alvo: str, pasta: Path, *, clientes: tuple[str, ...] = (),
                 ss: bool = False, watch: bool = False, intervalo: float = INTERVALO_S,
                 run: Callable[..., str] = _kubectl, agora: Callable[[], float] = time.time,
                 imagem: str = IMAGEM_DEPURACAO, ate: float | None = None):
        self.ns, self.alvo, self.pasta = namespace, alvo, Path(pasta)
        self.clientes, self.ss, self.watch, self.intervalo = tuple(clientes), ss, watch, intervalo
        self.run, self.agora, self.imagem, self.ate = run, agora, imagem, ate
        self._vistos: set[tuple] = set()
        self._com_depurador: dict[str, str] = {}
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None
        self._watch_proc: subprocess.Popen | None = None
        self._watch_thread: threading.Thread | None = None
        self.pasta.mkdir(parents=True, exist_ok=True)
        self._guardar_anteriores()

    def _guardar_anteriores(self) -> None:
        """Arquivos de uma tentativa anterior na mesma pasta vão para k8s_anteriores/<hora>/: a coleta acrescenta
        no fim, e misturar tentativas confundiria a leitura. Nada é apagado."""
        antigos = [p for p in self.pasta.glob("k8s_*") if p.is_file()]
        if not antigos:
            return
        destino = self.pasta / "k8s_anteriores" / f"{self.agora():.0f}"
        destino.mkdir(parents=True, exist_ok=True)
        for p in antigos:
            p.rename(destino / p.name)

    # ---- gravação
    def _append(self, nome: str, obj: dict) -> None:
        with (self.pasta / nome).open("a", encoding="utf-8") as fh:
            fh.write(json.dumps(obj, ensure_ascii=False) + "\n")

    # ---- uma coleta
    def coletar(self) -> dict:
        t = self.agora()
        reg: dict = {"t_abs": t}
        try:
            pods = resumo_pods(json.loads(self.run("-n", self.ns, "get", "pods", "-o", "json")))
            reg["pods"] = pods
        except Exception as e:  # noqa: BLE001
            pods = []
            reg["erro_pods"] = str(e)
        try:
            reg["endpoints_alvo"] = ips_endpoints(json.loads(
                self.run("-n", self.ns, "get", "endpoints", self.alvo, "-o", "json")))
        except Exception as e:  # noqa: BLE001
            reg["erro_endpoints"] = str(e)
        try:
            reg["servico_alvo"] = ip_do_servico(json.loads(self.run("-n", self.ns, "get", "service", self.alvo, "-o", "json")))
        except Exception as e:  # noqa: BLE001
            reg["erro_servico"] = str(e)
        if self.ss:
            reg["ss"] = self._coletar_ss(pods)
        self._append("k8s_coleta.jsonl", reg)
        self._coletar_eventos(t)
        return reg

    def _coletar_eventos(self, t: float) -> None:
        try:
            itens = json.loads(self.run("-n", self.ns, "get", "events", "-o", "json")).get("items", [])
        except Exception as e:  # noqa: BLE001
            self._append("k8s_eventos.jsonl", {"t_abs": t, "erro": str(e)})
            return
        for ev in itens:
            chave = (ev["metadata"].get("uid"), ev.get("count"), ev.get("lastTimestamp") or ev.get("eventTime"))
            if chave in self._vistos:
                continue
            self._vistos.add(chave)
            self._append("k8s_eventos.jsonl", {
                "t_coleta": t, "tipo": ev.get("type"), "motivo": ev.get("reason"), "mensagem": ev.get("message"),
                "objeto": f"{(ev.get('involvedObject') or {}).get('kind')}/{(ev.get('involvedObject') or {}).get('name')}",
                "count": ev.get("count"), "primeiro": ev.get("firstTimestamp"), "ultimo": ev.get("lastTimestamp"),
                "uid": ev["metadata"].get("uid")})

    def _depurador(self, pod: str) -> str:
        """Nome do contêiner efêmero em execução no pod; cria um se não houver. Lê spec.ephemeralContainers e
        status.ephemeralContainerStatuses antes de criar: reutiliza `mecade-dbg` se estiver rodando e, se tiver
        terminado, cria outro com sufixo (não dá para remover nem recriar um contêiner efêmero com o mesmo nome)."""
        if pod in self._com_depurador:
            return self._com_depurador[pod]
        j = json.loads(self.run("-n", self.ns, "get", "pod", pod, "-o", "json"))
        nomes = [c["name"] for c in j.get("spec", {}).get("ephemeralContainers") or []
                 if c["name"].startswith(CONTEINER_DEPURACAO)]
        estados = {c["name"]: c.get("state") or {} for c in j.get("status", {}).get("ephemeralContainerStatuses") or []}
        for n in nomes:
            if "running" in estados.get(n, {}):
                self._com_depurador[pod] = n
                return n
        novo = CONTEINER_DEPURACAO if not nomes else f"{CONTEINER_DEPURACAO}-{len(nomes) + 1}"
        self.run("-n", self.ns, "debug", pod, "-q", f"--image={self.imagem}", f"--container={novo}",
                 "--", *COMANDO_DEPURACAO)
        self._com_depurador[pod] = novo
        return novo

    def _coletar_ss(self, pods: list[dict]) -> dict:
        """`ss -tni` dentro de cada pod dos clientes que ainda esteja em Running, inclusive o que está sendo
        removido (a leitura dos pods antigos enquanto terminam é a evidência da condição 3 da H4)."""
        out: dict = {}
        for p in pods:
            if p["app"] not in self.clientes or p["fase"] != "Running":
                continue
            nome = p["nome"]
            try:
                c = self._depurador(nome)
                texto = self.run("-n", self.ns, "exec", nome, "-c", c, "--", "ss", "-tni")
                out[nome] = {"app": p["app"], "ip": p["ip"], "removendo": p["removendo"], "texto": texto}
            except Exception as e:  # noqa: BLE001  (o contêiner pode ainda não estar de pé; tento na coleta seguinte)
                self._com_depurador.pop(nome, None)
                out[nome] = {"app": p["app"], "ip": p["ip"], "removendo": p["removendo"], "erro": str(e)}
        return out

    # ---- thread
    def _loop(self) -> None:
        while not self._stop.is_set() and (self.ate is None or self.agora() < self.ate):
            ini = time.monotonic()
            try:
                self.coletar()
            except Exception as e:  # noqa: BLE001
                self._append("k8s_coleta.jsonl", {"t_abs": self.agora(), "erro": str(e)})
            self._stop.wait(max(0.0, self.intervalo - (time.monotonic() - ini)))

    def _ler_watch(self) -> None:
        assert self._watch_proc is not None and self._watch_proc.stdout is not None
        with (self.pasta / "k8s_pods_watch.log").open("a", encoding="utf-8") as fh:
            for linha in self._watch_proc.stdout:
                fh.write(f"{self.agora():.3f} {linha.rstrip()}\n")
                fh.flush()

    def iniciar(self) -> None:
        if self.watch:
            self._watch_proc = subprocess.Popen(["kubectl", "-n", self.ns, "get", "pods", "-w", "-o", "wide"],
                                                stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)
            self._watch_thread = threading.Thread(target=self._ler_watch, daemon=True)
            self._watch_thread.start()
        self._thread = threading.Thread(target=self._loop, daemon=True)
        self._thread.start()

    def parar(self) -> None:
        self._stop.set()
        if self._thread:
            self._thread.join(timeout=60)
        try:
            self.coletar()   # coleta final
        except Exception:  # noqa: BLE001
            pass
        if self._watch_proc:
            self._watch_proc.terminate()
            if self._watch_thread:
                self._watch_thread.join(timeout=5)
