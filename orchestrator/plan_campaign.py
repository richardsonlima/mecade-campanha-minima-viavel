"""Gera o plano da campanha com randomização em blocos e semente fixa.

Em cada par (cenário, réplica) os dois braços entram em ordem sorteada, e os pares são misturados
com as réplicas de controle. Nos controles alterno auditoria ligada e desligada para medir o
overhead da Camada 6 (Tabela 4.2).

  python -m orchestrator.plan_campaign [--scenarios s2_gray_currency,s3_podkill_cart] [--per-cell N]
"""
from __future__ import annotations

import argparse
import csv
import random
from pathlib import Path

from mecade.config import ROOT, load_campaign


def build_plan(campaign: dict, scenarios: list[str], per_cell: int, control: int) -> list[dict]:
    rng = random.Random(campaign["seed"])
    blocks: list[list[dict]] = []
    for sc in scenarios:
        for rep in range(1, per_cell + 1):
            arms = ["baseline", "mecade"]
            rng.shuffle(arms)
            blocks.append([{"scenario": sc, "arm": a, "rep": rep, "pair": f"{sc}#{rep:02d}", "audit": 1} for a in arms])
    for rep in range(1, control + 1):
        blocks.append([{"scenario": campaign["control_scenario"], "arm": "mecade", "rep": rep,
                        "pair": "", "audit": 1 if rep % 2 else 0}])
    rng.shuffle(blocks)
    plan = [row for b in blocks for row in b]
    for i, row in enumerate(plan, start=1):
        row["order"] = i
        row["run_id"] = f"{i:03d}_{row['scenario']}_{row['arm']}_r{row['rep']:02d}"
    return plan


def main() -> None:
    camp = load_campaign()
    ap = argparse.ArgumentParser()
    ap.add_argument("--scenarios", default=",".join(camp["scenarios"]),
                    help="lista separada por vírgula (contingência: 2 cenários)")
    ap.add_argument("--per-cell", type=int, default=camp["replicas"]["per_cell"])
    ap.add_argument("--control", type=int, default=camp["replicas"]["control"])
    ap.add_argument("--out", default=str(ROOT / "data" / f"plan_{camp['campaign_id']}.csv"))
    a = ap.parse_args()
    plan = build_plan(camp, a.scenarios.split(","), a.per_cell, a.control)
    Path(a.out).parent.mkdir(parents=True, exist_ok=True)
    with open(a.out, "w", newline="", encoding="utf-8") as fh:
        w = csv.DictWriter(fh, fieldnames=["order", "run_id", "scenario", "arm", "rep", "pair", "audit"])
        w.writeheader()
        w.writerows(plan)
    hours = len(plan) * sum(camp["timing"][k] for k in ("warmup", "baseline", "fault", "recovery")) / 3600
    print(f"Plano com {len(plan)} réplicas gravado em {a.out} (~{hours:.1f} h de execução, sem contar resets).")


if __name__ == "__main__":
    main()
