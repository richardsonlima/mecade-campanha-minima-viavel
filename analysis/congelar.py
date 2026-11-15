"""Congelamento da calibração da campanha 3 (docs/PROTOCOLO_C3.md, Seção 4 e Seção 8.1, item 6).

  python -m analysis.congelar --gravar   [--resultado ARQ.json] [--config config/campaign.yaml]
  python -m analysis.congelar --conferir [--resultado ARQ.json] [--config config/campaign.yaml]

O resultado é a saída de `calibrate_c3` (`make calibrar`). Sem `--resultado`, recalculo a partir de
data/calibracao/runs com os mesmos mínimos do config e guardo o JSON em data/calibracao/resultado_r1.json.
Recuso resultado inviável: calibração inviável é desfecho fechado (Seção 7.2) e não vira config.

`--gravar` copia para o config, sem mexer em comentários nem em outras linhas:
  signals.p95.floor e signals.p99.floor   <- pisos de p95 e p99
  axioms.d_on, d_off, deadband, tau_dwell, budget_B, limit_gate
`--conferir` compara o config com o resultado, valor a valor, e sai com 1 se houver diferença.

A trava (`verificar_trava`) é chamada por `make run` no plano oficial: recusa o B ou os pisos da campanha 2.
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

import yaml

from mecade.config import ROOT

# Valores congelados da campanha 2 (tag mvc-2026-11-c2-calibracao). Se o config ainda tiver algum deles, a
# calibração da campanha 3 não foi copiada para o config.
C2 = {("axioms", "budget_B"): 47.0, ("signals", "p95", "floor"): 0.05, ("signals", "p99", "floor"): 0.05}
RESULTADO_PADRAO = ROOT / "data" / "calibracao" / "resultado_r1.json"
CONFIG_PADRAO = ROOT / "config" / "campaign.yaml"


def valores_do_resultado(r: dict) -> dict[tuple, float | int | str]:
    """Caminho no config -> valor, a partir da saída de calibrate_c3."""
    return {
        ("signals", "p95", "floor"): r["pisos"]["p95"],
        ("signals", "p99", "floor"): r["pisos"]["p99"],
        ("axioms", "d_on"): r["d_on"],
        ("axioms", "d_off"): r["d_off"],
        ("axioms", "deadband"): r["deadband"],
        ("axioms", "tau_dwell"): int(r["tau_dwell"]),
        ("axioms", "budget_B"): float(r["budget_B"]),
        ("axioms", "limit_gate"): r["limit_gate"],
    }


def _no_config(cfg: dict, caminho: tuple):
    for k in caminho:
        cfg = cfg[k]
    return cfg


def _igual(a, b) -> bool:
    if isinstance(a, str) or isinstance(b, str):
        return a == b
    return abs(float(a) - float(b)) <= 1e-9


def conferir(config: dict, resultado: dict) -> list[str]:
    """Diferenças entre o config e a saída de calibrate_c3, uma por linha. Lista vazia = confere."""
    if not resultado.get("viavel"):
        return ["resultado inviável: não há o que conferir (Seção 7.2)"]
    difs = []
    for caminho, esperado in valores_do_resultado(resultado).items():
        try:
            atual = _no_config(config, caminho)
        except (KeyError, TypeError):
            difs.append(f"{'.'.join(caminho)}: ausente no config (resultado {esperado})")
            continue
        if not _igual(atual, esperado):
            difs.append(f"{'.'.join(caminho)}: config {atual}, resultado {esperado}")
    piso_erro = resultado["pisos"].get("error_rate")
    try:
        atual_erro = config["signals"]["error_rate"]["floor"]
        if piso_erro is not None and not _igual(atual_erro, piso_erro):
            difs.append(f"signals.error_rate.floor: config {atual_erro}, resultado {piso_erro}")
    except (KeyError, TypeError):
        difs.append("signals.error_rate.floor: ausente no config")
    return difs


def verificar_trava(config: dict, resultado: dict | None = None) -> list[str]:
    """Motivos para recusar o plano oficial. Vazio = pode rodar.

    Recusa se B ou algum piso de latência ainda for o da campanha 2. Se houver resultado de calibração
    (`data/calibracao/resultado_r1.json`), recusa também config que não confere com ele."""
    motivos = []
    for caminho, v2 in C2.items():
        try:
            atual = _no_config(config, caminho)
        except (KeyError, TypeError):
            motivos.append(f"{'.'.join(caminho)} ausente no config")
            continue
        if _igual(atual, v2):
            motivos.append(f"{'.'.join(caminho)} = {atual} é o valor da campanha 2")
    if resultado is not None:
        motivos += [f"não confere com a calibração: {d}" for d in conferir(config, resultado)]
    return motivos


def carregar_resultado(path: Path = RESULTADO_PADRAO) -> dict | None:
    path = Path(path)
    return json.loads(path.read_text(encoding="utf-8")) if path.is_file() else None


# ---------------------------------------------------------------------------------------- escrita no YAML

def _indent(ln: str) -> int:
    return len(ln) - len(ln.lstrip(" "))


def _formata(v) -> str:
    if isinstance(v, bool):
        return "true" if v else "false"
    if isinstance(v, int):
        return str(v)
    if isinstance(v, float):
        return repr(v)
    return str(v)


def editar_valor(texto: str, caminho: tuple, valor) -> str:
    """Troca o valor escalar de `caminho` no texto do YAML, mantendo comentários e as demais linhas."""
    linhas = texto.split("\n")
    ini, fim, nivel = 0, len(linhas), 0
    for i_chave, chave in enumerate(caminho):
        achado = None
        for i in range(ini, fim):
            ln = linhas[i]
            if not ln.strip() or ln.lstrip().startswith("#"):
                continue
            if _indent(ln) < nivel:
                break
            if _indent(ln) == nivel and re.match(rf"{re.escape(chave)}\s*:", ln.lstrip()):
                achado = i
                break
        if achado is None:
            raise KeyError(".".join(caminho))
        if i_chave == len(caminho) - 1:
            m = re.match(r"^(\s*[^:#]+:)(\s*)([^#\n]*?)(\s*)(#.*)?$", linhas[achado])
            if not m or not m.group(3):
                raise ValueError(f"{'.'.join(caminho)} não é um escalar numa linha")
            novo = _formata(valor)
            antigo_largura = len(m.group(3)) + len(m.group(4))
            gap = " " * max(1, antigo_largura - len(novo)) if m.group(5) else ""
            linhas[achado] = f"{m.group(1)}{m.group(2)}{novo}{gap}{m.group(5) or ''}"
            return "\n".join(linhas)
        ini = achado + 1
        nivel = _indent(linhas[achado]) + 2
        fim = len(linhas)
        for j in range(ini, len(linhas)):  # o bloco acaba na primeira linha com recuo menor que o dos filhos
            if linhas[j].strip() and not linhas[j].lstrip().startswith("#") and _indent(linhas[j]) < nivel:
                fim = j
                break
    raise KeyError(".".join(caminho))


def gravar(config_path: Path, resultado: dict) -> list[str]:
    """Copia a calibração para o config. Devolve as linhas alteradas. Recusa resultado inviável."""
    if not resultado.get("viavel"):
        raise SystemExit("Calibração inviável (Seção 7.2): nenhuma execução oficial roda, nada é congelado.")
    texto = Path(config_path).read_text(encoding="utf-8")
    novo = texto
    for caminho, valor in valores_do_resultado(resultado).items():
        novo = editar_valor(novo, caminho, valor)
    Path(config_path).write_text(novo, encoding="utf-8")
    return [f"{'.'.join(c)} = {_formata(v)}" for c, v in valores_do_resultado(resultado).items()]


def calcular(config: dict, raiz_runs: Path) -> dict:
    from analysis.calibrate import calibrate_c3
    from analysis.metrics import load_runs
    cal = config.get("calibracao") or {}
    return calibrate_c3(load_runs(raiz_runs, include_sim=True), piso_erro=float(config["signals"]["error_rate"]["floor"]),
                        tau_sem_solucao=cal.get("tau_sem_solucao"), min_controles=cal.get("controles_minimos"),
                        min_pilotos=cal.get("pilotos_minimos"))


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    modo = ap.add_mutually_exclusive_group(required=True)
    modo.add_argument("--gravar", action="store_true")
    modo.add_argument("--conferir", action="store_true")
    ap.add_argument("--resultado", default=None, help="JSON de calibrate_c3 (padrão: recalcula de data/calibracao/runs)")
    ap.add_argument("--config", default=str(CONFIG_PADRAO))
    ap.add_argument("--runs", default=str(ROOT / "data" / "calibracao" / "runs"))
    a = ap.parse_args(argv)

    cfg_path = Path(a.config)
    cfg = yaml.safe_load(cfg_path.read_text(encoding="utf-8"))
    if a.resultado:
        r = json.loads(Path(a.resultado).read_text(encoding="utf-8"))
    else:
        r = calcular(cfg, Path(a.runs))
        RESULTADO_PADRAO.parent.mkdir(parents=True, exist_ok=True)
        RESULTADO_PADRAO.write_text(json.dumps(r, indent=2, ensure_ascii=False), encoding="utf-8")
        print(f"resultado de calibrate_c3 guardado em {RESULTADO_PADRAO}")
    if a.gravar:
        for ln in gravar(cfg_path, r):
            print("gravei", ln)
        cfg = yaml.safe_load(cfg_path.read_text(encoding="utf-8"))
    difs = conferir(cfg, r)
    for d in difs:
        print("DIFERENÇA", d)
    print("config confere com a calibração" if not difs else f"{len(difs)} diferença(s)")
    return 0 if not difs else 1


if __name__ == "__main__":
    sys.exit(main())
