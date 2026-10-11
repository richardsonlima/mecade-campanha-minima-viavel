"""Leitura da configuração da campanha e dos registros de cenário."""
from __future__ import annotations

from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parent.parent


def load_campaign(path: str | Path = ROOT / "config" / "campaign.yaml") -> dict:
    with open(path, encoding="utf-8") as fh:
        return yaml.safe_load(fh)


def load_scenario(scenario_id: str, directory: str | Path = ROOT / "scenarios") -> dict:
    with open(Path(directory) / f"{scenario_id}.yaml", encoding="utf-8") as fh:
        sc = yaml.safe_load(fh)
    if sc.get("id") != scenario_id:
        raise ValueError(f"id do cenário ({sc.get('id')}) difere do nome do arquivo ({scenario_id})")
    return sc


def render_chaos(template: dict | None, *, name: str, ns: str, pods: list[str], fault_s: int) -> dict | None:
    """Troca {name}, {ns} e {fault} em chaves e valores, e "{pods}" pela lista de pods-alvo."""
    if template is None:
        return None

    def walk(obj):
        if isinstance(obj, dict):
            return {walk(k): walk(v) for k, v in obj.items()}
        if isinstance(obj, list):
            return [walk(v) for v in obj]
        if isinstance(obj, str):
            if obj == "{pods}":
                return list(pods)
            return obj.replace("{name}", name).replace("{ns}", ns).replace("{fault}", str(fault_s))
        return obj

    return walk(template)
