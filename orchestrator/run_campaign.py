"""Executa o plano da campanha, uma réplica por vez. Dá para retomar: réplicas concluídas são puladas.

  python -m orchestrator.run_campaign                      # cluster real (kubectl e Prometheus)
  python -m orchestrator.run_campaign --limit 4            # só as próximas 4 réplicas
  python -m orchestrator.run_campaign --backend sim        # teste do pipeline sem cluster (data/sim/)
"""
from __future__ import annotations

import argparse
import csv
import json
import sys
from datetime import datetime
from pathlib import Path

from mecade.backends import Kubectl, PromClient, RealClock
from mecade.config import ROOT, load_campaign, load_scenario
from mecade.runner import run_one
from mecade.sim import SimWorld, VirtualClock


def main() -> None:
    camp = load_campaign()
    ap = argparse.ArgumentParser()
    ap.add_argument("--plan", default=str(ROOT / "data" / f"plan_{camp['campaign_id']}.csv"))
    ap.add_argument("--backend", choices=["k8s", "sim"], default="k8s")
    ap.add_argument("--limit", type=int, default=0, help="máximo de réplicas nesta execução (0 = todas)")
    a = ap.parse_args()

    with open(a.plan, encoding="utf-8") as fh:
        plan = list(csv.DictReader(fh))

    if a.backend == "sim":
        out_root = ROOT / "data" / "sim" / "runs"
    else:
        out_root = ROOT / "data" / "runs"
    out_root.mkdir(parents=True, exist_ok=True)
    log_path = out_root.parent / "campaign.log"

    def log(msg: str) -> None:
        line = f"{datetime.now().isoformat(timespec='seconds')} {msg}"
        print(line, flush=True)
        with log_path.open("a", encoding="utf-8") as fh:
            fh.write(line + "\n")

    done = 0
    for row in plan:
        meta_path = out_root / row["run_id"] / "meta.json"
        if meta_path.exists() and json.loads(meta_path.read_text()).get("status") == "complete":
            continue
        if a.limit and done >= a.limit:
            break
        scenario = load_scenario(row["scenario"])
        if a.backend == "sim":
            clock = VirtualClock()
            world = SimWorld(clock, seed=int(camp["seed"]) + int(row["order"]))
            prom = kube = world
        else:
            clock, world = RealClock(), None
            prom, kube = PromClient(camp["prometheus_url"]), Kubectl(camp["namespace"])
        try:
            meta = run_one(run_id=row["run_id"], scenario=scenario, arm=row["arm"], campaign=camp,
                           prom=prom, kube=kube, clock=clock, out_root=out_root,
                           audit_enabled=bool(int(row["audit"])), sim_world=world, log=log)
            meta.update({"pair": row["pair"], "rep": int(row["rep"]), "order": int(row["order"]),
                         "audit_planned": int(row["audit"])})
            meta_path.write_text(json.dumps(meta, indent=2, ensure_ascii=False), encoding="utf-8")
        except KeyboardInterrupt:
            log(f"[{row['run_id']}] interrompida pelo operador; limpando injeções")
            try:
                kube.delete_all_chaos()
            finally:
                sys.exit(130)
        except Exception as exc:  # noqa: BLE001 (registro a falha e sigo para a próxima)
            log(f"[{row['run_id']}] FALHOU: {exc}")
            try:
                kube.delete_all_chaos()
            except Exception:  # noqa: BLE001
                pass
            continue
        done += 1
    log(f"Execução encerrada: {done} réplica(s) concluída(s) nesta sessão.")


if __name__ == "__main__":
    main()
