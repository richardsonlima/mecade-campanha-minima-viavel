"""Utilitários de linha de comando.

  python -m mecade.cli smoke           consulta os sinais de decisão no Prometheus antes de rodar
  python -m mecade.cli verify-audit F  confere a integridade de uma trilha de auditoria
"""
from __future__ import annotations

import sys

from .audit import verify
from .backends import PromClient
from .config import load_campaign


def smoke() -> int:
    camp = load_campaign()
    prom = PromClient(camp["prometheus_url"])
    ok = True
    for name, cfg in camp["signals"].items():
        v = prom.instant(cfg["query"])
        print(f"  {name:12s} = {v}")
        ok &= v is not None
    for name, q in camp.get("aux_signals", {}).items():
        v = prom.instant(q.replace("{ns}", camp["namespace"]).replace("{target}", "frontend"))
        print(f"  {name:12s} = {v}")
    print("Todos os sinais de decisão estão respondendo." if ok else "Há sinais sem dados. Conferir se a carga já subiu e se o ServiceMonitor está sendo coletado.")
    return 0 if ok else 1


def main() -> int:
    if len(sys.argv) >= 2 and sys.argv[1] == "smoke":
        return smoke()
    if len(sys.argv) == 3 and sys.argv[1] == "verify-audit":
        ok, n, msg = verify(sys.argv[2])
        print(f"{msg} ({n} registros)")
        return 0 if ok else 1
    print(__doc__)
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
