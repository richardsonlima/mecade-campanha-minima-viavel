"""Executa o plano da campanha, uma réplica por vez. Dá para retomar: réplicas concluídas são puladas.

  python -m orchestrator.run_campaign                      # cluster real (kubectl e Prometheus)
  python -m orchestrator.run_campaign --limit 4            # só as próximas 4 réplicas
  python -m orchestrator.run_campaign --calibracao --plan data/calibracao/plan_r1.csv
  python -m orchestrator.run_campaign --backend sim        # teste do pipeline sem cluster (data/sim/)

Falhas de execução: cada réplica guarda as tentativas em tentativas.jsonl. Depois de uma falha limpo
as injeções, espero o ambiente estabilizar e sigo; as réplicas que falharam voltam na passada
seguinte, fora da ordem sorteada, e isso fica registrado como desvio. Na terceira falha a réplica
vira `falha_execucao`, rótulo diferente de `censurada` (sem detecção ou sem restauração).

Códigos de saída: 0 terminou; 3 passou do limite de 10% de réplicas perdidas; 4 falhas seguidas
indicam ambiente instável; 130 interrompido pelo operador. Em 3 e 4 alguém precisa olhar.
"""
from __future__ import annotations

import argparse
import csv
import json
import sys
import time
from datetime import datetime
from pathlib import Path
from typing import Callable

from analysis.metrics import load_runs, metrics_table
from mecade.backends import Kubectl, PromClient, RealClock
from mecade.config import ROOT, load_campaign, load_scenario
from mecade.runner import run_one
from mecade.sim import SimWorld, VirtualClock

MAX_FALHAS = 3
MAX_FALHAS_SEGUIDAS = 3
LIMITE_PERDIDAS = 0.10
ESPERA_APOS_FALHA_S = 120
TERMINAIS = {"complete", "falha_execucao"}

EXIT_OK, EXIT_LIMITE, EXIT_INSTAVEL, EXIT_INTERROMPIDA = 0, 3, 4, 130


def _agora() -> str:
    return datetime.now().isoformat(timespec="seconds")


def _append_jsonl(path: Path, obj: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as fh:
        fh.write(json.dumps(obj, ensure_ascii=False) + "\n")


def read_attempts(run_dir: Path) -> list[dict]:
    p = run_dir / "tentativas.jsonl"
    if not p.exists():
        return []
    return [json.loads(line) for line in p.read_text(encoding="utf-8").splitlines() if line.strip()]


def count_failures(entries: list[dict]) -> int:
    """Conta as tentativas perdidas. Início sem desfecho é queda do processo ou da VM e conta como falha.
    Interrupção pelo operador não conta."""
    por_tentativa: dict[int, str] = {}
    for e in entries:
        por_tentativa[e["tentativa"]] = e["evento"]
    return sum(1 for ev in por_tentativa.values() if ev in ("inicio", "falhou"))


def _read_meta(run_dir: Path) -> dict | None:
    """Metadado truncado por uma queda no meio da escrita conta como réplica não concluída."""
    p = run_dir / "meta.json"
    if not p.exists():
        return None
    try:
        return json.loads(p.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return None


def read_status(run_dir: Path) -> str | None:
    meta = _read_meta(run_dir)
    return meta.get("status") if meta else None


def archive_partial_audit(out_root: Path, run_id: str, tentativa: int) -> Path | None:
    """Trilha parcial de tentativa anterior vai para audit/tentativas/. Nada é apagado, e a trilha da
    nova tentativa começa numa cadeia própria, porque continuar no mesmo arquivo quebraria o verify()."""
    trilha = out_root.parent / "audit" / f"{run_id}.jsonl"
    if not trilha.exists():
        return None
    pasta = out_root.parent / "audit" / "tentativas"
    pasta.mkdir(parents=True, exist_ok=True)
    destino = pasta / f"{run_id}.antes-t{tentativa}.jsonl"
    n = 1
    while destino.exists():  # rename sobrescreveria uma trilha já guardada
        n += 1
        destino = pasta / f"{run_id}.antes-t{tentativa}.{n}.jsonl"
    trilha.rename(destino)
    return destino


def count_lost(plan: list[dict], out_root: Path) -> dict:
    """Réplicas perdidas para o limite de 10% (decisão de 2026-11-11): `falha_execucao` de qualquer braço mais
    `censurada` do braço MECADE. A `censurada` do baseline não entra no total, mas volta em `censurada_baseline`
    para ser relatada. Só olho o agregado, para decidir a parada; isso não alimenta nenhum parâmetro."""
    ids = {r["run_id"] for r in plan}
    falhas = sum(1 for r in plan if read_status(out_root / r["run_id"]) == "falha_execucao")
    runs = [(m, df) for m, df in load_runs(out_root, include_sim=True) if m["run_id"] in ids]
    cens_mecade = cens_baseline = 0
    if runs:
        tabela = metrics_table(runs)
        cens = tabela[tabela["censurada"].astype(bool)]
        cens_mecade = int((cens["arm"] == "mecade").sum())
        cens_baseline = int((cens["arm"] == "baseline").sum())
    return {"falha_execucao": falhas, "censurada": cens_mecade, "censurada_baseline": cens_baseline,
            "total": falhas + cens_mecade, "plano": len(plan)}


def execute_plan(plan: list[dict], *, out_root: Path, execute: Callable[[dict], dict],
                 clean: Callable[[], None], log: Callable[[str], None], limit: int = 0,
                 settle_s: float = ESPERA_APOS_FALHA_S, sleep: Callable[[float], None] = time.sleep,
                 check_lost: bool = True) -> int:
    """Percorre o plano em passadas até toda réplica chegar a um estado final. Devolve o código de saída."""
    desvios = out_root.parent / "desvios_execucao.jsonl"

    def desvio(run_id: str, tipo: str, **extra) -> None:
        _append_jsonl(desvios, {"quando": _agora(), "run_id": run_id, "tipo": tipo, **extra})
        log(f"[{run_id}] DESVIO {tipo} {extra if extra else ''}")

    relatadas = [0]  # censuradas do baseline já registradas como desvio

    def perdeu_demais() -> bool:
        if not check_lost:
            return False
        c = count_lost(plan, out_root)
        if c["censurada_baseline"] > relatadas[0]:  # fora do limite, mas relatada
            relatadas[0] = c["censurada_baseline"]
            desvio("", "censuradas_baseline_fora_do_limite", total=c["censurada_baseline"])
        if c["total"] > LIMITE_PERDIDAS * c["plano"]:
            log(f"PARADA: {c['total']} de {c['plano']} réplicas perdidas ({c['falha_execucao']} falha_execucao, "
                f"{c['censurada']} censuradas do MECADE; {c['censurada_baseline']} censuradas do baseline não contam), "
                f"acima do limite de {LIMITE_PERDIDAS:.0%}.")
            return True
        return False

    if perdeu_demais():  # retomada depois de uma parada: não gasto mais uma réplica para parar de novo
        return EXIT_LIMITE

    done = seguidas = 0  # falhas seguidas valem entre passadas: só um sucesso zera a contagem
    while True:
        falhas_passada = 0
        for row in plan:
            run_id = row["run_id"]
            run_dir = out_root / run_id
            if _repair_incomplete_meta(row, run_dir):
                log(f"[{run_id}] metadados do plano completados depois de uma queda")
            if read_status(run_dir) in TERMINAIS:
                continue

            entries = read_attempts(run_dir)
            if count_failures(entries) >= MAX_FALHAS:
                # acontece quando a terceira tentativa morreu com o processo
                archive_partial_audit(out_root, run_id, max(e["tentativa"] for e in entries) + 1)
                _mark_execution_failure(row, run_dir, entries)
                desvio(run_id, "falha_execucao", par=row["pair"])
                if perdeu_demais():
                    return EXIT_LIMITE
                continue
            if limit and done >= limit:
                log(f"Execução encerrada: {done} réplica(s) concluída(s) nesta sessão.")
                return EXIT_OK

            tentativa = max((e["tentativa"] for e in entries), default=0) + 1
            fora_de_ordem = tentativa > 1 and any(
                int(r["order"]) > int(row["order"]) and (out_root / r["run_id"] / "tentativas.jsonl").exists()
                for r in plan)
            if fora_de_ordem:
                desvio(run_id, "refeita_fora_da_ordem", tentativa=tentativa, ordem=int(row["order"]))
            arquivada = archive_partial_audit(out_root, run_id, tentativa)
            if arquivada:
                log(f"[{run_id}] trilha parcial arquivada em {arquivada}")

            ledger = run_dir / "tentativas.jsonl"
            _append_jsonl(ledger, {"tentativa": tentativa, "evento": "inicio", "quando": _agora()})
            try:
                meta = execute(row)
                meta.update(_plan_fields(row))
                meta.update({"tentativa": tentativa, "fora_da_ordem": fora_de_ordem})
                (run_dir / "meta.json").write_text(json.dumps(meta, indent=2, ensure_ascii=False), encoding="utf-8")
                _append_jsonl(ledger, {"tentativa": tentativa, "evento": "concluida", "quando": _agora()})
            except KeyboardInterrupt:
                _append_jsonl(ledger, {"tentativa": tentativa, "evento": "interrompida", "quando": _agora()})
                log(f"[{run_id}] interrompida pelo operador; limpando injeções")
                try:
                    clean()
                except Exception as exc2:  # noqa: BLE001
                    log(f"[{run_id}] limpeza das injeções falhou: {exc2}")
                return EXIT_INTERROMPIDA
            except Exception as exc:  # noqa: BLE001 (registro a falha e sigo para a próxima)
                _append_jsonl(ledger, {"tentativa": tentativa, "evento": "falhou", "quando": _agora(), "erro": str(exc)})
                log(f"[{run_id}] FALHOU (tentativa {tentativa}): {exc}")
                try:
                    clean()
                except Exception as exc2:  # noqa: BLE001
                    log(f"[{run_id}] limpeza das injeções também falhou: {exc2}")
                falhas_passada += 1
                seguidas += 1
                entries = read_attempts(run_dir)
                if count_failures(entries) >= MAX_FALHAS:
                    archive_partial_audit(out_root, run_id, tentativa + 1)
                    _mark_execution_failure(row, run_dir, entries)
                    desvio(run_id, "falha_execucao", par=row["pair"])
                    if perdeu_demais():
                        return EXIT_LIMITE
                if seguidas >= MAX_FALHAS_SEGUIDAS:
                    log(f"PARADA: {seguidas} falhas seguidas, ambiente instável. Confiro o cluster e rodo de novo.")
                    return EXIT_INSTAVEL
                sleep(settle_s)
                continue
            seguidas = 0
            done += 1
            if perdeu_demais():
                return EXIT_LIMITE
        if falhas_passada == 0:
            log(f"Execução encerrada: {done} réplica(s) concluída(s) nesta sessão.")
            return EXIT_OK
        log(f"Passada com {falhas_passada} falha(s); volto às réplicas pendentes.")


def _plan_fields(row: dict) -> dict:
    return {"pair": row["pair"], "rep": int(row["rep"]), "order": int(row["order"]), "audit_planned": int(row["audit"])}


def _repair_incomplete_meta(row: dict, run_dir: Path) -> bool:
    """O run_one grava meta.json e só depois entram os campos do plano. Se o processo cair nesse intervalo,
    a réplica tem dados válidos, mas sem `pair` a análise a trataria como controle. Completo na retomada."""
    meta = _read_meta(run_dir)
    if meta is None or meta.get("status") != "complete" or "order" in meta:
        return False
    p = run_dir / "meta.json"
    entries = read_attempts(run_dir)
    meta.update(_plan_fields(row))
    meta["tentativa"] = max((e["tentativa"] for e in entries), default=1)
    p.write_text(json.dumps(meta, indent=2, ensure_ascii=False), encoding="utf-8")
    _append_jsonl(run_dir / "tentativas.jsonl", {"tentativa": meta["tentativa"], "evento": "concluida", "quando": _agora()})
    return True


def _mark_execution_failure(row: dict, run_dir: Path, entries: list[dict]) -> None:
    meta = {"run_id": row["run_id"], "status": "falha_execucao", "scenario": row["scenario"], "arm": row["arm"],
            "pair": row["pair"], "rep": int(row["rep"]), "order": int(row["order"]), "tentativas": entries}
    (run_dir / "meta.json").write_text(json.dumps(meta, indent=2, ensure_ascii=False), encoding="utf-8")


def check_plan_destination(plan: list[dict], calibracao: bool) -> None:
    """Plano de calibração só escreve em data/calibracao/, e plano oficial nunca escreve lá."""
    de_calibracao = [r["run_id"] for r in plan if r["run_id"].startswith("cal")]
    if calibracao and len(de_calibracao) != len(plan):
        raise SystemExit("--calibracao exige um plano de calibração (make plan-calibracao).")
    if not calibracao and de_calibracao:
        raise SystemExit("Plano de calibração não pode rodar em data/runs. Uso --calibracao.")


def main() -> None:
    camp = load_campaign()
    ap = argparse.ArgumentParser()
    ap.add_argument("--plan", default=None)
    ap.add_argument("--backend", choices=["k8s", "sim"], default="k8s")
    ap.add_argument("--limit", type=int, default=0, help="máximo de réplicas nesta execução (0 = todas)")
    ap.add_argument("--calibracao", action="store_true", help="grava em data/calibracao/, fora da análise")
    ap.add_argument("--sem-limite-perdidas", action="store_true",
                    help="não para em 10%% de réplicas perdidas; só com decisão minha registrada")
    ap.add_argument("--settle", type=float, default=ESPERA_APOS_FALHA_S, help="espera depois de uma falha (s)")
    a = ap.parse_args()

    plan_path = a.plan or str(ROOT / "data" / f"plan_{camp['campaign_id']}.csv")
    with open(plan_path, encoding="utf-8") as fh:
        plan = list(csv.DictReader(fh))
    check_plan_destination(plan, a.calibracao)

    if a.backend == "sim":
        out_root = ROOT / "data" / "sim" / "runs"
    elif a.calibracao:
        out_root = ROOT / "data" / "calibracao" / "runs"
    else:
        out_root = ROOT / "data" / "runs"
    out_root.mkdir(parents=True, exist_ok=True)
    log_path = out_root.parent / "campaign.log"

    def log(msg: str) -> None:
        line = f"{_agora()} {msg}"
        print(line, flush=True)
        with log_path.open("a", encoding="utf-8") as fh:
            fh.write(line + "\n")

    kube_atual: dict = {}

    def execute(row: dict) -> dict:
        scenario = load_scenario(row["scenario"])
        if a.backend == "sim":
            clock = VirtualClock()
            world = SimWorld(clock, seed=int(camp["seed"]) + int(row["order"]))
            prom = kube = world
        else:
            clock, world = RealClock(), None
            prom, kube = PromClient(camp["prometheus_url"]), Kubectl(camp["namespace"])
        kube_atual["k"] = kube
        meta = run_one(run_id=row["run_id"], scenario=scenario, arm=row["arm"], campaign=camp,
                       prom=prom, kube=kube, clock=clock, out_root=out_root,
                       audit_enabled=bool(int(row["audit"])), sim_world=world, log=log)
        meta["campaign_id"] = camp["campaign_id"]
        meta["etapa"] = "calibracao" if a.calibracao else "oficial"
        return meta

    def clean() -> None:
        if "k" in kube_atual:
            kube_atual["k"].delete_all_chaos()

    # o limite de 10% vale para as réplicas oficiais; calibração e simulação não param por ele
    oficial = a.backend == "k8s" and not a.calibracao
    if oficial and a.sem_limite_perdidas:
        log("Limite de 10% de réplicas perdidas desligado por minha decisão.")
        _append_jsonl(out_root.parent / "desvios_execucao.jsonl",
                      {"quando": _agora(), "run_id": "", "tipo": "limite_de_perdidas_desligado"})
    sys.exit(execute_plan(plan, out_root=out_root, execute=execute, clean=clean, log=log, limit=a.limit,
                          settle_s=0 if a.backend == "sim" else a.settle, check_lost=oficial and not a.sem_limite_perdidas))


if __name__ == "__main__":
    main()
