"""Fase 0 da campanha 3: diagnóstico do s1 (docs/PROTOCOLO_C3.md, Seção 3.1), antes da calibração.

  python -m orchestrator.fase0 executar [--exec A,B,C1,C2,D] [--prefixo diag_]   (make fase0)
  python -m orchestrator.fase0 analisar [--raiz data/diagnostico]                 (make fase0-analise)

`executar` roda as cinco execuções da tabela da Seção 3.1, fora do plano oficial e da calibração, com prefixo
`diag_` e saída em data/diagnostico/<run_id>/. Cada execução tem a linha do tempo da campanha (warmup, baseline,
falha, recuperação) e só muda quando o restart do alvo e dos clientes acontece:

  A   restart do alvo em t = 15 s, sem clientes     (condição do braço MECADE da campanha 2)
  B   restart do alvo em t = 120 s, sem clientes    (controle de H4)
  C1  restart do alvo em t = 40 s, clientes depois de `clientes_apos_s` (do cenário)
  C2  igual a C1
  D   restart do alvo em t = 425 s, clientes depois de `clientes_apos_s`

Em todas, a coleta é passiva (mecade/coleta_k8s.py): `kubectl get pods -w`, endpoints do alvo, eventos,
restartCount e `ss -tni` do frontend e do checkoutservice a cada 15 s. O tempo do rollout é medido do início de
`kubectl rollout restart deployment/<alvo>` até o fim com sucesso de `kubectl rollout status`. Esta parte só coleta
e mede, não decide.

`analisar` aplica as regras fixas da Seção 3.1 aos dados e imprime o resultado: `clientes_apos_s`, a cascata e a
H4. Não escreve em config nem em cenário: quem fixa o valor sou eu, num commit depois de ler a saída.

Falha de execução (Seção 7.1): até 3 tentativas com o mesmo desenho; sem dado depois disso a execução fica
`falha_execucao`, e a análise trata como a Seção 7.1 manda.
"""
from __future__ import annotations

import argparse
import csv
import json
import math
import re
import shutil
import signal
import statistics
import subprocess
import sys
import threading
import time
from datetime import datetime
from pathlib import Path

from mecade.backends import Kubectl, PromClient, RealClock
from mecade.coleta_k8s import ColetorK8s
from mecade.config import ROOT, load_campaign, load_scenario, render_chaos
from orchestrator.run_campaign import (EXIT_ERRO, EXIT_INTERROMPIDA, EXIT_OK, EXIT_SIGHUP, EXIT_SIGTERM, _scale_zero,
                                       gravar_log, limpar_com_timeout)
from mecade.runner import CLEAN_TARGETS, _config_sha256, _git_commit, _git_dirty

CENARIO = "s1_latencia_productcatalog"
DIR_PADRAO = ROOT / "data" / "diagnostico"
MAX_TENTATIVAS = 3
ESPERA_APOS_FALHA_S = 120
CLIENTES_SS = ("frontend", "checkoutservice")

# id -> (instante do restart do alvo em s depois da injeção, reinicia os clientes?)
EXECUCOES = {
    "A": (15, False),
    "B": (120, False),
    "C1": (40, True),
    "C2": (40, True),
    "D": (425, True),
}

# regras fixas da Seção 3.1
CLIENTES_MIN_S, CLIENTES_MAX_S, CLIENTES_FOLGA_S, CLIENTES_ARRED_S = 20, 60, 10, 5
CASCATA_JANELA_S, CASCATA_INICIO_MAX_S = 60, 150
CASCATA_ERRO_MAX, CASCATA_P95_FATOR = 0.01, 2.0
H4_SUMIR_S = 15
SS_DENSO_S, SS_DENSO_INTERVALO_S = 30.0, 3.0
ROLLOUT_TIMEOUT_S = 300.0   # `wait_rollout` usa --timeout=300s; rollout que estoura entra como 300 s (o corte leva a 60)


def _foi_timeout(e: Exception) -> bool:
    """`rollout_estourou` vale só para timeout (o do `rollout status` ou o do subprocesso). Erro de API é `rollout_erro`."""
    return isinstance(e, subprocess.TimeoutExpired) or "timed out" in str(e).lower()


def _agora() -> str:
    return datetime.now().isoformat(timespec="seconds")


def _write_csv(path: Path, rows: list[dict]) -> None:
    if not rows:
        return
    keys: list[str] = []
    for r in rows:
        for k in r:
            if k not in keys:
                keys.append(k)
    with path.open("w", newline="", encoding="utf-8") as fh:
        w = csv.DictWriter(fh, fieldnames=keys)
        w.writeheader()
        w.writerows(rows)


# ----------------------------------------------------------------------------------------------- execução

def executar(exec_id: str, *, scenario: dict, campaign: dict, prom, kube, clock, out_root: Path,
             prefixo: str = "diag_", coletor: ColetorK8s | None = None, sincrono: bool = False,
             tipos_de_no=None, log=print) -> dict:
    """Uma execução da Fase 0. `sincrono` roda as ações na própria volta (testes com relógio virtual); no real
    elas ficam numa thread, para o `rollout status` não parar a coleta dos sinais."""
    t_restart_s, com_clientes = EXECUCOES[exec_id]
    run_id = f"{prefixo}{exec_id}"
    tm, ns = campaign["timing"], campaign["namespace"]
    step = float(tm["step"])
    target = scenario["alvo"]
    m = scenario.get("mitigacao") or {}
    clientes = list(m.get("clientes") or [])
    apos_s = float(m.get("clientes_apos_s", 0))
    if com_clientes and not clientes:
        raise ValueError("o cenário não declara mitigacao.clientes: C1, C2 e D não têm o que reiniciar")
    out = Path(out_root) / run_id
    out.mkdir(parents=True, exist_ok=True)
    signals = {s: campaign["signals"][s] for s in campaign["axioms"]["decision_signals"]}

    def q(query: str):
        return prom.instant(query.replace("{ns}", ns).replace("{target}", target))

    log(f"[{run_id}] reset do ambiente")
    kube.delete_all_chaos()
    for dep in CLEAN_TARGETS:
        kube.scale(dep, 1)
    kube.restart(target)
    kube.wait_rollout(target)

    t0 = clock.now()
    clock.sleep_until(t0 + tm["warmup"])
    t_base_start = clock.now()
    t_inject = t_base_start + tm["baseline"]
    t_fault_end = t_inject + tm["fault"]
    t_end = t_fault_end + tm["recovery"]
    chaos_name = f"mecade-{run_id.replace('_', '-')}"[:63].lower()
    chaos_kind = (scenario.get("chaos") or {}).get("kind")
    if coletor is not None:
        coletor.iniciar()

    events: list[dict] = []
    medidas: dict = {"rollout_s": None, "rollout_ok": None, "rollout_estourou": False, "rollout_erro": False,
                     "erro_rollout": None}
    base_samples: dict[str, list[float]] = {s: [] for s in signals}
    M_base: dict[str, float | None] | None = None
    rows: list[dict] = []
    phase, chaos_active = "baseline", False
    restart_feito = clientes_feito = False
    t_clientes_abs: float | None = None
    threads: list[threading.Thread] = []
    trava = threading.Lock()

    def emit(t: float, name: str, **extra) -> None:
        with trava:
            events.append({"t": round(t - t_inject, 3), "event": name, **extra})
        log(f"[{run_id}] t={t - t_inject:+.0f}s {name} {extra if extra else ''}")

    def acao_restart_alvo() -> None:
        ini = clock.now()
        emit(ini, "MITIGATION", action="restart", reason="fase0")
        try:
            kube.restart(target)
            kube.wait_rollout(target)
            fim = clock.now()
            medidas.update(rollout_s=round(fim - ini, 3), rollout_ok=True)
            emit(fim, "ROLLOUT_FIM", deployment=target, rollout_s=medidas["rollout_s"])
        except Exception as e:  # noqa: BLE001  (estourou o timeout ou erro de API: entra como 300 s, marcado)
            estourou = _foi_timeout(e)
            medidas.update(rollout_s=ROLLOUT_TIMEOUT_S, rollout_ok=False, rollout_estourou=estourou,
                           rollout_erro=not estourou, erro_rollout=str(e))
            emit(clock.now(), "ROLLOUT_FALHOU", deployment=target, rollout_s=ROLLOUT_TIMEOUT_S, erro=str(e))

    def acao_clientes() -> None:
        for dep in clientes:
            kube.restart(dep)
        emit(clock.now(), "MITIGATION_CLIENTES", deployments=clientes)
        if coletor is not None:   # condição 3 da H4: ss a cada 3 s até +30 s (só densidade de amostragem)
            coletor.amostrar_ss_denso(SS_DENSO_S, SS_DENSO_INTERVALO_S)

    def disparar(fn) -> None:
        if sincrono:
            fn()
        else:
            th = threading.Thread(target=fn, daemon=True)
            th.start()
            threads.append(th)

    t = t_base_start
    try:
        while t < t_end:
            clock.sleep_until(t)
            now = clock.now()
            if phase == "baseline" and now >= t_inject:
                M_base = {s: (statistics.median(v) if v else None) for s, v in base_samples.items()}
                phase = "fault"
                manifest = render_chaos(scenario.get("chaos"), name=chaos_name, ns=ns, pods=kube.pods(target),
                                        fault_s=int(tm["fault"]))
                if manifest is not None:
                    kube.apply(manifest)
                    chaos_active = True
                emit(now, "INJECT", baseline=M_base)
            if phase == "fault" and now >= t_fault_end:
                phase = "recovery"
                if chaos_active:
                    kube.delete(chaos_kind, chaos_name)
                    chaos_active = False
                emit(now, "FAULT_END")
            if phase != "baseline" and not restart_feito and now - t_inject >= t_restart_s:
                restart_feito = True
                if com_clientes:
                    t_clientes_abs = now + apos_s
                disparar(acao_restart_alvo)
            if t_clientes_abs is not None and not clientes_feito and now >= t_clientes_abs:
                clientes_feito = True
                disparar(acao_clientes)

            values = {s: q(cfg["query"]) for s, cfg in signals.items()}
            rows.append({"t": round(now - t_inject, 3), "phase": phase, **values})
            if phase == "baseline":
                for s, v in values.items():
                    if v is not None:
                        base_samples[s].append(v)
            t += step
    finally:
        for th in threads:
            th.join(timeout=360)
        if chaos_active:
            kube.delete(chaos_kind, chaos_name)
        if coletor is not None:
            coletor.parar()

    _write_csv(out / "steps.csv", rows)
    restart_ev = next((e for e in events if e["event"] == "MITIGATION"), None)
    meta = {
        "run_id": run_id, "execucao": exec_id, "alvo": target, "scenario": scenario["id"], "scenario_version": scenario.get("version"),
        "arm": "diagnostico", "backend": "k8s", "status": "complete", "plano": "diagnostico",
        "etapa": "diagnostico", "campaign_id": campaign.get("campaign_id"),
        "wall_start": t_base_start, "t_inject_abs": t_inject, "M_base": M_base, "events": sorted(events, key=lambda e: e["t"]),
        "desenho": {"restart_alvo_s": t_restart_s, "clientes": clientes if com_clientes else [],
                    "clientes_apos_s": apos_s if com_clientes else None},
        "restart_alvo_t": restart_ev["t"] if restart_ev else None,
        "restart_alvo_abs": (t_inject + restart_ev["t"]) if restart_ev else None,
        "clientes_t": next((e["t"] for e in events if e["event"] == "MITIGATION_CLIENTES"), None),
        **medidas,
        "timing": tm, "git_commit": _git_commit(), "git_dirty": _git_dirty(), "config_sha256": _config_sha256(),
        "k8s_server": kube.server_version(),
        "machine_types": (tipos_de_no() if tipos_de_no else {}),
    }
    meta["datapath_peer"] = datapath_casado({"meta": meta, "steps": [], "coleta": [
        r for r in _le_jsonl(out / "k8s_coleta.jsonl") if "pods" in r]})
    (out / "meta.json").write_text(json.dumps(meta, indent=2, ensure_ascii=False), encoding="utf-8")
    log(f"[{run_id}] concluída: {len(rows)} amostras, rollout_s={medidas['rollout_s']}")
    return meta


def _arquivar_tentativa(pasta: Path) -> None:
    """Arquivos de uma tentativa anterior vão para tentativas/t<N>/, porque a coleta acrescenta no fim."""
    antigos = [p for p in pasta.iterdir() if p.name not in ("tentativas.jsonl", "tentativas")] if pasta.exists() else []
    if not antigos:
        return
    base = pasta / "tentativas"
    n = 1
    while (base / f"t{n}").exists():
        n += 1
    destino = base / f"t{n}"
    destino.mkdir(parents=True, exist_ok=True)
    for p in antigos:
        shutil.move(str(p), str(destino / p.name))


def _meta_completa(pasta: Path) -> dict | None:
    mp = pasta / "meta.json"
    if not mp.exists():
        return None
    try:
        meta = json.loads(mp.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return None
    return meta if meta.get("status") == "complete" else None


def executar_com_tentativas(exec_id: str, *, fabrica, out_root: Path, prefixo: str = "diag_",
                            settle_s: float = ESPERA_APOS_FALHA_S, sleep=time.sleep, log=print) -> dict:
    """Até MAX_TENTATIVAS com o mesmo desenho (Seção 7.1). `fabrica()` devolve um dict com os argumentos de
    `executar` que mudam a cada tentativa (kube, prom, clock, coletor...).

    Reexecução: execução com meta.json `complete` é pulada e nunca sobrescrita. Só contam as tentativas que
    terminaram em falha (uma tentativa interrompida no meio não gasta uma das três)."""
    pasta = Path(out_root) / f"{prefixo}{exec_id}"
    pasta.mkdir(parents=True, exist_ok=True)
    pronta = _meta_completa(pasta)
    if pronta is not None:
        log(f"[{prefixo}{exec_id}] já tem meta.json complete: pulada")
        return pronta
    ledger = pasta / "tentativas.jsonl"

    def reg(obj: dict) -> None:
        with ledger.open("a", encoding="utf-8") as fh:
            fh.write(json.dumps({**obj, "quando": _agora()}, ensure_ascii=False) + "\n")

    falhas = sum(1 for ln in ledger.read_text().splitlines() if '"falhou"' in ln) if ledger.exists() else 0
    for n in range(falhas + 1, MAX_TENTATIVAS + 1):
        _arquivar_tentativa(pasta)
        reg({"tentativa": n, "evento": "inicio"})
        try:
            meta = executar(exec_id, out_root=out_root, prefixo=prefixo, log=log, **fabrica())
            reg({"tentativa": n, "evento": "concluida"})
            return meta
        except Exception as e:  # noqa: BLE001
            reg({"tentativa": n, "evento": "falhou", "erro": str(e)})
            log(f"[{prefixo}{exec_id}] FALHOU (tentativa {n}): {e}")
            if n < MAX_TENTATIVAS:
                sleep(settle_s)
    meta = {"run_id": f"{prefixo}{exec_id}", "execucao": exec_id, "status": "falha_execucao", "plano": "diagnostico"}
    if _meta_completa(pasta) is None:   # nunca sobrescreve meta completo
        (pasta / "meta.json").write_text(json.dumps(meta, indent=2, ensure_ascii=False), encoding="utf-8")
    return meta


# ----------------------------------------------------------------------------------------------- análise

_ESTADOS = {"ESTAB", "SYN-SENT", "SYN-RECV", "FIN-WAIT-1", "FIN-WAIT-2", "TIME-WAIT", "CLOSE-WAIT", "LAST-ACK",
            "CLOSING", "CLOSE", "UNCONN", "LISTEN"}


def _ip(addr: str) -> str:
    ip = addr.rsplit(":", 1)[0].strip("[]")
    return ip[7:] if ip.startswith("::ffff:") else ip


def parse_ss(texto: str) -> list[dict]:
    """Conexões de `ss -tni`: estado, peers e contadores de retransmissão (`retrans:atual/total`)."""
    conns: list[dict] = []
    for ln in texto.splitlines():
        if not ln.strip():
            continue
        if not ln[0].isspace():
            campos = ln.split()
            if campos[0] in _ESTADOS and len(campos) >= 5:
                conns.append({"estado": campos[0], "local": campos[3], "peer": campos[4], "peer_ip": _ip(campos[4]),
                              "retrans_total": 0, "bytes_retrans": 0})
        elif conns:
            mm = re.search(r"\bretrans:(\d+)/(\d+)", ln)
            if mm:
                conns[-1]["retrans_total"] = int(mm.group(2))
            mb = re.search(r"\bbytes_retrans:(\d+)", ln)
            if mb:
                conns[-1]["bytes_retrans"] = int(mb.group(1))
    return conns


def _le_jsonl(p: Path) -> list[dict]:
    if not p.exists():
        return []
    out = []
    for ln in p.read_text(encoding="utf-8").splitlines():
        if ln.strip():
            try:
                out.append(json.loads(ln))
            except json.JSONDecodeError:
                pass
    return out


def carregar(raiz: Path, exec_id: str, prefixo: str = "diag_") -> dict | None:
    pasta = Path(raiz) / f"{prefixo}{exec_id}"
    mp = pasta / "meta.json"
    if not mp.exists():
        return None
    meta = json.loads(mp.read_text(encoding="utf-8"))
    if meta.get("status") != "complete":
        return None
    steps = list(csv.DictReader((pasta / "steps.csv").open(encoding="utf-8"))) if (pasta / "steps.csv").exists() else []
    return {"meta": meta, "steps": steps, "coleta": [r for r in _le_jsonl(pasta / "k8s_coleta.jsonl") if "pods" in r]}


def clientes_apos_s(rollouts: list[float]) -> dict:
    """Maior rollout medido mais 10 s, para cima em 5 s, cortado em [20, 60] s."""
    if not rollouts:
        return {"valor": None, "motivo": "nenhuma execução com tempo de rollout"}
    bruto = max(rollouts) + CLIENTES_FOLGA_S
    arred = math.ceil(round(bruto / CLIENTES_ARRED_S, 9)) * CLIENTES_ARRED_S
    valor = min(max(arred, CLIENTES_MIN_S), CLIENTES_MAX_S)
    return {"valor": valor, "maior_rollout_s": max(rollouts), "arredondado": arred, "cortado": valor != arred}


def cascata_ok(d: dict | None) -> dict:
    """error_rate <= 0,01 e p95 <= 2 x M_base de p95 por 60 s seguidos, começando até 150 s depois do restart."""
    if d is None or d["meta"].get("restart_alvo_t") is None:
        return {"ok": False, "motivo": "sem dado"}
    base = (d["meta"].get("M_base") or {}).get("p95")
    if base is None:
        return {"ok": False, "motivo": "sem M_base de p95"}
    t_r = float(d["meta"]["restart_alvo_t"])
    pts = []
    for r in d["steps"]:
        try:
            pts.append((float(r["t"]), float(r["p95"]), float(r.get("error_rate", "nan"))))
        except (ValueError, KeyError):
            pts.append((float(r["t"]), math.nan, math.nan))
    pts.sort()

    def bom(p):
        return (not math.isnan(p[1]) and not math.isnan(p[2]) and p[2] <= CASCATA_ERRO_MAX
                and p[1] <= CASCATA_P95_FATOR * base)

    for i, (ts, *_r) in enumerate(pts):
        if ts < t_r or ts > t_r + CASCATA_INICIO_MAX_S:
            continue
        janela = [p for p in pts[i:] if p[0] <= ts + CASCATA_JANELA_S]
        if janela and janela[-1][0] >= ts + CASCATA_JANELA_S and all(bom(p) for p in janela):
            return {"ok": True, "inicio_t": ts, "depois_do_restart_s": ts - t_r}
    return {"ok": False, "motivo": "nenhuma janela de 60 s dentro das condições começa em até 150 s do restart",
            "limite_p95": CASCATA_P95_FATOR * base}


def _ips_antigos(d: dict) -> set[str]:
    """IPs dos pods do alvo na última coleta antes do restart."""
    t_r = d["meta"].get("restart_alvo_abs")
    alvo = d["meta"]["alvo"]
    antes = [c for c in d["coleta"] if t_r is not None and c["t_abs"] < t_r]
    if not antes:
        return set()
    return {p["ip"] for p in antes[-1]["pods"] if p["app"] == alvo and p["ip"] and not p["removendo"]}


def _saiu_dos_endpoints(d: dict, antigos: set[str]) -> float | None:
    """Instante (absoluto) da primeira coleta, depois do restart, sem o IP antigo nos endpoints."""
    t_r = d["meta"].get("restart_alvo_abs")
    for c in d["coleta"]:
        if t_r is None or c["t_abs"] < t_r or "endpoints_alvo" not in c:
            continue
        ep = c["endpoints_alvo"]
        if not (antigos & (set(ep["prontos"]) | set(ep["nao_prontos"]))):
            return c["t_abs"]
    return None


def _servico(d: dict) -> dict:
    for c in d["coleta"]:
        sv = c.get("servico_alvo") or {}
        if sv.get("cluster_ip"):
            return sv
    return {}


def _cluster_ip(d: dict) -> str | None:
    return _servico(d).get("cluster_ip")


def _porta(peer: str) -> int | None:
    try:
        return int(peer.rsplit(":", 1)[1])
    except (IndexError, ValueError):
        return None


def _casa_peer(conn: dict, cip: str | None, portas: list, portas_pod: list, antigos: set[str]) -> str | None:
    """"clusterip" se o peer é ClusterIP:porta do alvo; "pod_ip" se é IP:porta de um pod antigo do alvo (datapath
    que dá DNAT antes do socket, só como proteção); None se não é do alvo. Sem portas coletadas, vale só o IP."""
    porta = _porta(conn["peer"])
    if cip and conn["peer_ip"] == cip and (not portas or porta in portas):
        return "clusterip"
    if conn["peer_ip"] in antigos and (not portas_pod or porta in portas_pod):
        return "pod_ip"
    return None


# H4, operacionalização para este cluster: o GKE do mecade-mvc não usa Dataplane V2 (kube-proxy em iptables), então o
# `ss` dos clientes mostra o ClusterIP:porta do alvo e nunca o IP do pod. Com replicas_alvo = 1, "conexão para o IP do
# pod antigo" (Seção 3.1) vira "conexão ao ClusterIP:porta do alvo cuja tupla (local ip:porta, peer) já existia na
# última leitura antes do restart do alvo". Por proteção, o peer também casa com IP:porta dos pods antigos do alvo, e
# o meta registra qual dos dois casou. Desvio declarado no CHANGELOG antes de qualquer dado da Fase 0.
def _tuplas_e_tipos(d: dict) -> tuple[dict[tuple, str], dict[str, int]]:
    t_r = d["meta"].get("restart_alvo_abs")
    sv = _servico(d)
    cip, portas, portas_pod = sv.get("cluster_ip"), sv.get("portas") or [], sv.get("portas_pod") or []
    antigos = _ips_antigos(d)
    if t_r is None or (cip is None and not antigos):
        return {}, {}
    ultima: dict[str, tuple[str, list[tuple[dict, str]]]] = {}
    for c in d["coleta"]:
        if c["t_abs"] >= t_r:
            break
        for pod, v in (c.get("ss") or {}).items():
            if "texto" in v:
                achados = [(x, k) for x in parse_ss(v["texto"]) if x["estado"] == "ESTAB"
                           for k in [_casa_peer(x, cip, portas, portas_pod, antigos)] if k]
                ultima[pod] = (v["app"], achados)
    tuplas = {(pod, x["local"], x["peer"]): app for pod, (app, achados) in ultima.items() for x, _ in achados}
    tipos: dict[str, int] = {}
    for _, achados in ultima.values():
        for _, k in achados:
            tipos[k] = tipos.get(k, 0) + 1
    return tuplas, tipos


def _tuplas_anteriores(d: dict) -> dict[tuple, str]:
    """{(pod, local, peer): app} das conexões ESTABLISHED ao alvo na última leitura de cada pod cliente antes do
    restart do alvo."""
    return _tuplas_e_tipos(d)[0]


def datapath_casado(d: dict) -> dict:
    """Qual peer casou nas conexões anteriores ao restart: ClusterIP:porta, IP:porta de pod antigo, os dois ou nenhum."""
    _, tipos = _tuplas_e_tipos(d)
    casou = "nenhum" if not tipos else ("ambos" if len(tipos) > 1 else next(iter(tipos)))
    return {"casou": casou, "conexoes": tipos}


def _leituras(d: dict, desde: float, pods: set[str]):
    """(t_abs, pod, conexões) de cada leitura de ss com dado, a partir de `desde`, nos pods dados."""
    for c in d["coleta"]:
        if c["t_abs"] < desde:
            continue
        for pod, v in (c.get("ss") or {}).items():
            if pod in pods and "texto" in v:
                yield c["t_abs"], pod, parse_ss(v["texto"])


def _presentes(conns: list[dict], pod: str, tuplas: dict) -> list[tuple]:
    return [(pod, x["local"], x["peer"]) for x in conns
            if (pod, x["local"], x["peer"]) in tuplas and x["estado"] != "TIME-WAIT"]


def _contexto_h4(d: dict | None):
    """(tuplas, t_saiu, motivo_sem_dado)."""
    if d is None:
        return {}, None, "sem dado"
    tuplas = _tuplas_anteriores(d)
    if not tuplas:
        return {}, None, "nenhuma conexão ao ClusterIP do alvo na última leitura antes do restart (ou sem ClusterIP)"
    antigos = _ips_antigos(d)
    t_sai = _saiu_dos_endpoints(d, antigos) if antigos else None
    if t_sai is None:
        return tuplas, None, "sem IP antigo ou sem coleta com o IP fora dos endpoints"
    return tuplas, t_sai, None


def h4_condicao_1(d: dict | None) -> dict:
    """A: a tupla anterior ao restart segue ESTABLISHED depois de o pod antigo sair dos endpoints, com
    retransmissões crescentes entre duas coletas seguidas."""
    tuplas, t_sai, motivo = _contexto_h4(d)
    if motivo:
        return {"ok": None, "motivo": motivo}
    pods = {k[0] for k in tuplas}
    serie: dict[tuple, list[tuple[float, int, int]]] = {}
    n = 0
    for t, pod, conns in _leituras(d, t_sai, pods):
        n += 1
        for x in conns:
            k = (pod, x["local"], x["peer"])
            if k in tuplas and x["estado"] == "ESTAB":
                serie.setdefault(k, []).append((t, x["retrans_total"], x["bytes_retrans"]))
    if n == 0:
        return {"ok": None, "motivo": "sem leitura de ss depois da saída dos endpoints"}
    for k, pts in serie.items():
        for (t1, r1, b1), (t2, r2, b2) in zip(pts, pts[1:]):
            if r2 > r1 or b2 > b1:
                return {"ok": True, "conexao": list(k), "retrans": [r1, r2], "bytes_retrans": [b1, b2]}
    if serie and all(len(p) < 2 for p in serie.values()):
        return {"ok": None, "motivo": "a tupla aparece em menos de duas leituras seguidas"}
    return {"ok": False, "motivo": "conexões presas sem retransmissão crescente" if serie
            else "nenhuma tupla anterior segue ESTABLISHED"}


def h4_condicao_2(d: dict | None) -> dict:
    """B: nenhuma tupla anterior ao restart segue depois de o pod antigo sair dos endpoints."""
    tuplas, t_sai, motivo = _contexto_h4(d)
    if motivo:
        return {"ok": None, "motivo": motivo}
    pods = {k[0] for k in tuplas}
    n, achadas = 0, []
    for t, pod, conns in _leituras(d, t_sai, pods):
        n += 1
        achadas += _presentes(conns, pod, tuplas)
    if n == 0:
        return {"ok": None, "motivo": "sem leitura de ss depois da saída dos endpoints"}
    return {"ok": not achadas, "leituras": n, "tuplas_que_seguem": [list(x) for x in achadas[:5]]}


def h4_condicao_3(d: dict | None) -> dict:
    """C: as tuplas anteriores ao restart somem até 15 s depois de MITIGATION_CLIENTES. Leio o ss dos pods
    clientes ANTIGOS enquanto terminam. Se o pod antigo sumir antes de qualquer leitura (a partir de
    MITIGATION_CLIENTES), a condição sai sem dado. Como os clientes são reiniciados, ela tende a ser verdadeira
    por construção (o pod antigo morre); relato assim."""
    if d is None or d["meta"].get("clientes_t") is None:
        return {"ok": None, "motivo": "sem dado ou sem MITIGATION_CLIENTES"}
    tuplas = _tuplas_anteriores(d)
    if not tuplas:
        return {"ok": None, "motivo": "nenhuma conexão ao ClusterIP do alvo na última leitura antes do restart (ou sem ClusterIP)"}
    t_cli = d["meta"]["t_inject_abs"] + float(d["meta"]["clientes_t"])
    por_app: dict[str, dict] = {}
    for app in CLIENTES_SS:
        pods = {k[0] for k, a in tuplas.items() if a == app}
        if not pods:
            por_app[app] = {"ok": None, "motivo": "sem tupla anterior ao restart neste cliente"}
            continue
        leit = [(t, pod, bool(_presentes(conns, pod, tuplas))) for t, pod, conns in _leituras(d, t_cli, pods)]
        if not leit:
            por_app[app] = {"ok": None, "motivo": "o pod antigo sumiu antes de qualquer leitura de ss"}
            continue
        tardias = [x for x in leit if x[0] >= t_cli + H4_SUMIR_S]
        if tardias:
            por_app[app] = {"ok": not any(x[2] for x in tardias), "leituras_depois_de_15s": len(tardias)}
        elif not leit[-1][2]:
            por_app[app] = {"ok": True, "leituras_antes_de_15s": len(leit)}
        else:
            por_app[app] = {"ok": None, "motivo": "o pod antigo sumiu com a tupla ainda presente e sem leitura depois de 15 s"}
    oks = [v["ok"] for v in por_app.values()]
    ok = False if False in oks else (None if None in oks else True)
    r: dict = {"ok": ok, "por_cliente": por_app,
               "nota": "os clientes são reiniciados: tende a ser verdadeira por construção"}
    if ok is None:
        r["motivo"] = "; ".join(f"{a}: {v['motivo']}" for a, v in por_app.items() if v["ok"] is None)
    return r


def analisar(raiz: Path = DIR_PADRAO, prefixo: str = "diag_") -> dict:
    d = {e: carregar(raiz, e, prefixo) for e in EXECUCOES}
    rollouts = [d[e]["meta"]["rollout_s"] for e in EXECUCOES if d[e] is not None and d[e]["meta"].get("rollout_s") is not None]
    estouraram = [e for e in EXECUCOES if d[e] is not None and d[e]["meta"].get("rollout_estourou")]
    com_erro = [e for e in EXECUCOES if d[e] is not None and d[e]["meta"].get("rollout_erro")]
    apos = clientes_apos_s(rollouts)
    apos["estouraram_o_timeout"] = estouraram
    apos["com_erro_de_api"] = com_erro
    c1, c2 = cascata_ok(d["C1"]), cascata_ok(d["C2"])
    cascata_fica = bool(c1["ok"] and c2["ok"]) and apos["valor"] is not None
    k1, k2 = h4_condicao_1(d["A"]), h4_condicao_2(d["B"])
    k3 = {e: h4_condicao_3(d[e]) for e in ("C1", "C2")}
    # Seção 3.1: faltando qualquer condição, a H4 não é confirmada
    motivos = []
    for nome, num, k in (("A", 1, k1), ("B", 2, k2), ("C1", 3, k3["C1"]), ("C2", 3, k3["C2"])):
        if k["ok"] is None:
            motivos.append(f"condição {num} sem dado ({nome})")
        elif not k["ok"]:
            motivos.append(f"condição {num} não satisfeita ({nome})")
    h4 = "confirmada" if not motivos else "não confirmada"
    return {
        "execucoes_com_dado": [e for e in EXECUCOES if d[e] is not None],
        "rollout_s": {e: (d[e]["meta"].get("rollout_s") if d[e] else None) for e in EXECUCOES},
        "clientes_apos_s": apos,
        "cascata": {"fica": cascata_fica, "C1": c1, "C2": c2,
                    "nota": None if cascata_fica else "clientes sai do cenário e s1 volta à mitigação da campanha 2 (Seção 3.1)"},
        "H4": {"resultado": h4, "motivos": motivos, "condicao_1_A": k1, "condicao_2_B": k2, "condicao_3_C": k3},
        "D": {"TTR_nota": "relato só; comparar o TTR de D com a mediana de 525 s do baseline de s1 da campanha 2",
              "dado": d["D"] is not None},
    }


# ----------------------------------------------------------------------------------------------- CLI

def escalar_ao_fim(ligado: bool, log, escalar=None) -> bool:
    """A Fase 0 liga o cluster e não deve deixá-lo cobrando: ao fim (ou em erro) o node pool vai a 0, salvo
    `--nao-escalar`. Falha do gcloud só vai para o log."""
    if not ligado:
        log("--nao-escalar: node pool fica como está.")
        return False
    if escalar is None:
        escalar = _scale_zero
    try:   # primeiro escalo, depois registro
        escalar()
    except Exception as exc:  # noqa: BLE001
        log(f"ATENÇÃO: não consegui levar o node pool a 0 ({exc}). Confira `gcloud compute instances list`.")
        return False
    log("Fim da Fase 0: node pool a 0 (infra/gke/scale.sh 0).")
    return True


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)
    ex = sub.add_parser("executar")
    ex.add_argument("--exec", default=",".join(EXECUCOES), help="execuções, separadas por vírgula (padrão: todas)")
    ex.add_argument("--prefixo", default="diag_")
    ex.add_argument("--saida", default=str(DIR_PADRAO))
    ex.add_argument("--settle", type=float, default=ESPERA_APOS_FALHA_S)
    ex.add_argument("--nao-escalar", action="store_true", help="não leva o node pool a 0 ao fim (padrão: leva)")
    an = sub.add_parser("analisar")
    an.add_argument("--raiz", default=str(DIR_PADRAO))
    an.add_argument("--prefixo", default="diag_")
    a = ap.parse_args(argv)

    if a.cmd == "analisar":
        print(json.dumps(analisar(Path(a.raiz), a.prefixo), indent=2, ensure_ascii=False))
        return 0

    ids = [e.strip() for e in a.exec.split(",") if e.strip()]
    desconhecidas = [e for e in ids if e not in EXECUCOES]
    if desconhecidas:
        raise SystemExit(f"execução desconhecida: {desconhecidas}; valem {list(EXECUCOES)}")
    camp, scenario = load_campaign(), load_scenario(CENARIO)
    out_root = Path(a.saida)
    out_root.mkdir(parents=True, exist_ok=True)
    log_path = out_root / "fase0.log"

    def log(msg: str) -> None:
        gravar_log(log_path, f"{_agora()} {msg}")

    kube = Kubectl(camp["namespace"])

    def fabrica_de(exec_id: str):
        def f() -> dict:
            pasta = out_root / f"{a.prefixo}{exec_id}"
            return dict(scenario=scenario, campaign=camp, prom=PromClient(camp["prometheus_url"]), kube=kube,
                        clock=RealClock(), tipos_de_no=kube.node_machine_types,
                        coletor=ColetorK8s(camp["namespace"], scenario["alvo"], pasta, clientes=CLIENTES_SS,
                                           ss=True, watch=True))
        return f

    def _sinal(signum, _frame):
        raise SystemExit(128 + signum)
    for sg in (signal.SIGHUP, signal.SIGTERM):
        signal.signal(sg, _sinal)
    falhas, codigo = 0, EXIT_ERRO
    try:
        for e in ids:
            meta = executar_com_tentativas(e, fabrica=fabrica_de(e), out_root=out_root, prefixo=a.prefixo,
                                           settle_s=a.settle, log=log)
            falhas += meta.get("status") != "complete"
        codigo = EXIT_OK
    except SystemExit as e:   # sinal: 128 + número
        codigo = e.code if isinstance(e.code, int) else EXIT_ERRO
        raise
    except KeyboardInterrupt:
        codigo = EXIT_INTERROMPIDA
        raise
    finally:
        if codigo in (EXIT_SIGHUP, EXIT_SIGTERM):   # chaos ativo no meio da execução: limpa antes, com prazo curto
            limpar_com_timeout(kube.delete_all_chaos)
        escalar_ao_fim(not a.nao_escalar, log)
    log(f"Fase 0 encerrada: {len(ids) - falhas} de {len(ids)} execuções com dado. `make fase0-analise` aplica as regras.")
    return 0 if falhas == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
