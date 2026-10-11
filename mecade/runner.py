"""Execução de uma réplica da campanha (um cenário em um braço).

Fases, com os tempos definidos em config/campaign.yaml:
  reset, warmup, baseline (coleta de M_base), fault (incidente ativo), recovery, cleanup

Braços:
  baseline  alerta reativo convencional (reactive.py) e mitigação do runbook depois de um atraso fixo
  mecade    axiomas ALERT, LIMIT e BLOCK (axioms.py); o BLOCK aciona a mesma mitigação do runbook
  controle  braço mecade sem injeção, onde qualquer BLOCK é falso bloqueio

Cada réplica grava em data/runs/<run_id>/ (ou data/sim/<run_id>/) os arquivos meta.json,
steps.csv e prom_range.csv.
"""
from __future__ import annotations

import csv
import json
import statistics
import subprocess
import time
from pathlib import Path

from .audit import AuditLog
from .axioms import AxiomEvaluator, AxiomParams, deviation
from .config import ROOT, render_chaos
from .reactive import ReactiveRule

CLEAN_TARGETS = ("productcatalogservice", "currencyservice", "cartservice")


def _git_commit() -> str:
    try:
        return subprocess.run(["git", "rev-parse", "HEAD"], cwd=ROOT, capture_output=True,
                              text=True, check=True).stdout.strip()
    except Exception:  # noqa: BLE001
        return "sem-git"


def run_one(*, run_id: str, scenario: dict, arm: str, campaign: dict, prom, kube, clock,
            out_root: Path, audit_enabled: bool | None = None, sim_world=None, log=print) -> dict:
    tm, ns = campaign["timing"], campaign["namespace"]
    step = float(tm["step"])
    target = scenario["alvo"]
    is_sim = sim_world is not None
    out = Path(out_root) / run_id
    out.mkdir(parents=True, exist_ok=True)

    def q(sig_name: str, query: str) -> float | None:
        if is_sim:
            return prom.instant(sig_name)
        return prom.instant(query.replace("{ns}", ns).replace("{target}", target))

    decision_signals = campaign["axioms"]["decision_signals"]
    signals = {s: campaign["signals"][s] for s in decision_signals}
    aux = campaign.get("aux_signals", {})

    # reset
    log(f"[{run_id}] reset do ambiente")
    if is_sim:
        sim_world.reset(scenario["id"])
    kube.delete_all_chaos()
    for dep in CLEAN_TARGETS:
        kube.scale(dep, 1)
    if target in CLEAN_TARGETS:
        kube.restart(target)
        kube.wait_rollout(target)

    t0 = clock.now()
    clock.sleep_until(t0 + tm["warmup"])

    # estado da réplica
    params = AxiomParams.from_dict(campaign["axioms"])
    axioms = AxiomEvaluator(params)
    rc = campaign["reactive"]
    reactive = ReactiveRule(rules=rc["rules"], for_s=rc["for"], response_delay=rc["response_delay"])
    audit_on = campaign["audit"]["enabled"] if audit_enabled is None else audit_enabled
    audit = AuditLog(Path(out_root).parent / "audit" / f"{run_id}.jsonl" if arm == "mecade" else None,
                     enabled=audit_on and arm == "mecade")
    cpu0 = time.process_time()

    t_base_start = clock.now()
    t_inject = t_base_start + tm["baseline"]
    t_fault_end = t_inject + tm["fault"]
    t_end = t_fault_end + tm["recovery"]
    chaos_name = f"mecade-{run_id.replace('_', '-')}"[:63].lower()
    chaos_kind = (scenario.get("chaos") or {}).get("kind")

    base_samples: dict[str, list[float]] = {s: [] for s in signals}
    M_base: dict[str, float] | None = None
    events: list[dict] = []
    rows: list[dict] = []
    chaos_active = False
    mitigated_at: float | None = None
    phase = "baseline"

    def emit(t: float, name: str, **extra) -> None:
        ev = {"t": round(t - t_inject, 3), "event": name, **extra}
        events.append(ev)
        audit.record({"run_id": run_id, **ev})
        log(f"[{run_id}] t={ev['t']:+.0f}s {name} {extra if extra else ''}")

    def mitigate(t: float, reason: str) -> None:
        nonlocal mitigated_at
        if mitigated_at is not None:
            return
        m = scenario.get("mitigacao", {}) or {}
        action = m.get("acao", "none")
        if action == "restart":
            kube.restart(target)
        elif action == "scale":
            kube.scale(target, int(m["replicas"]))
        mitigated_at = t
        emit(t, "MITIGATION", action=action, reason=reason)

    t = t_base_start
    while t < t_end:
        clock.sleep_until(t)
        now = clock.now()

        # transições de fase
        if phase == "baseline" and now >= t_inject:
            M_base = {s: (statistics.median(v) if v else None) for s, v in base_samples.items()}
            reactive.baseline = dict(M_base)
            phase = "fault"
            manifest = render_chaos(scenario.get("chaos"), name=chaos_name, ns=ns,
                                    pods=kube.pods(target), fault_s=int(tm["fault"]))
            if manifest is not None:
                kube.apply(manifest)
                chaos_active = True
            emit(now, "INJECT" if manifest is not None else "CONTROL_START", baseline=M_base)
        if phase == "fault" and now >= t_fault_end:
            phase = "recovery"
            if chaos_active:
                kube.delete(chaos_kind, chaos_name)
                chaos_active = False
            emit(now, "FAULT_END")

        # coleta
        values = {s: q(s, cfg["query"]) for s, cfg in signals.items()}
        aux_values = {s: q(s, query) for s, query in aux.items()}
        row = {"t": round(now - t_inject, 3), "phase": phase, **values, **{f"aux_{k}": v for k, v in aux_values.items()}}

        if phase == "baseline":
            for s, v in values.items():
                if v is not None:
                    base_samples[s].append(v)
        else:
            D = {s: deviation(values[s], M_base.get(s), float(signals[s]["floor"])) for s in signals}
            row.update({f"D_{s}": d for s, d in D.items()})
            # o avaliador roda nos dois braços (no baseline, só em sombra) para a análise offline;
            # apenas no braço mecade ele dispara ações
            ev_ax = axioms.step(D, step)
            row.update({"D_agr": axioms.last_D_agr, "I": round(axioms.I, 4), "alert": int(axioms.alert)})
            if arm == "mecade":
                for e in ev_ax:
                    if e != "NO_DATA":
                        emit(now, e, I=round(axioms.I, 3))
                if "BLOCK" in ev_ax:
                    mitigate(now, "BLOCK")
                    if campaign["block"]["stop_injection"] and chaos_active:
                        kube.delete(chaos_kind, chaos_name)
                        chaos_active = False
                        emit(now, "INJECTION_STOPPED")
            elif arm == "baseline":
                for e in reactive.step(now, values, step):
                    emit(now, e)
                if reactive.mitigation_due(now):
                    mitigate(now, "RUNBOOK")
        rows.append(row)
        t += step

    # limpeza e exportação
    if chaos_active:
        kube.delete(chaos_kind, chaos_name)
    audit_info = audit.close()
    cpu_s = time.process_time() - cpu0

    prom_rows = []
    if not is_sim:
        for s, cfg in {**{k: v["query"] for k, v in signals.items()}, **aux}.items():
            query = cfg if isinstance(cfg, str) else cfg
            for ts, v in prom.range(query.replace("{ns}", ns).replace("{target}", target),
                                    t_base_start, t_end, step):
                prom_rows.append({"signal": s, "t": round(ts - t_inject, 3), "value": v})

    _write_csv(out / "steps.csv", rows)
    if prom_rows:
        _write_csv(out / "prom_range.csv", prom_rows)
    meta = {
        "run_id": run_id, "scenario": scenario["id"], "scenario_version": scenario.get("version"),
        "arm": arm, "backend": "sim" if is_sim else "k8s", "status": "complete",
        "wall_start": t_base_start, "t_inject_abs": t_inject, "M_base": M_base,
        "events": events, "audit": audit_info, "controller_cpu_s": cpu_s,
        "timing": tm, "axioms": campaign["axioms"], "reactive": campaign["reactive"],
        "recovery": campaign["recovery"], "block": campaign["block"],
        "rto_s": scenario.get("rto_s"), "mitigation": scenario.get("mitigacao"),
        "git_commit": _git_commit(), "k8s_server": kube.server_version(),
    }
    (out / "meta.json").write_text(json.dumps(meta, indent=2, ensure_ascii=False), encoding="utf-8")
    log(f"[{run_id}] concluída: {len(rows)} amostras, {len(events)} eventos")
    return meta


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
