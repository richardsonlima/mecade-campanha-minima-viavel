"""Manifesto de evidências da campanha (docs/EVIDENCIAS.md).

  python -m analysis.evidencias gerar     [--raiz DIR] [--saida ARQ]       (make evidencias)
  python -m analysis.evidencias verificar [--raiz DIR] [--manifesto ARQ]   (make verificar-evidencias)

`gerar` grava data/EVIDENCIAS_MANIFESTO.json com o commit e as tags do HEAD, o SHA-256 do plano oficial e
de cada arquivo de data/runs, data/audit e data/calibracao, as contagens, o resultado do verify-audit, as
versões de versions.env e a data em UTC. Sai com código 1 se alguma trilha de auditoria falhar.

`verificar` recalcula os hashes de uma cópia (VM, bucket baixado ou local) e compara com o manifesto.
Sai com código 0 só quando nenhum arquivo foi alterado, falta ou sobra, e as trilhas continuam íntegras.
Para conferir uma cópia, use o manifesto do commit da tag, não o que veio junto com a cópia.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

import yaml

from mecade.audit import verify
from mecade.config import ROOT

FORMATO = "mecade-evidencias/1"
MANIFESTO = Path("data") / "EVIDENCIAS_MANIFESTO.json"
DIRETORIOS = ("data/runs", "data/audit", "data/calibracao")
IGNORADOS = {".gitkeep"}


def sha256_arquivo(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as fh:
        for bloco in iter(lambda: fh.read(1 << 20), b""):
            h.update(bloco)
    return h.hexdigest()


def _sha256_json(obj) -> str:
    return hashlib.sha256(json.dumps(obj, sort_keys=True, separators=(",", ":")).encode("utf-8")).hexdigest()


def _git(raiz: Path, *args: str) -> str | None:
    try:
        r = subprocess.run(["git", "-C", str(raiz), *args], capture_output=True, text=True, check=True)
        return r.stdout.rstrip("\n")  # sem strip(): o porcelain começa com espaço significativo
    except (OSError, subprocess.CalledProcessError):
        return None


def info_git(raiz: Path) -> dict:
    commit = _git(raiz, "rev-parse", "HEAD")
    if commit is None:
        return {"commit": None, "tags": [], "descricao": None, "arvore_limpa": None, "modificados": []}
    tags = [t for t in (_git(raiz, "tag", "--points-at", "HEAD") or "").splitlines() if t]
    status = _git(raiz, "status", "--porcelain", "--untracked-files=no") or ""
    modificados = [ln[3:] for ln in status.splitlines() if ln[3:] != MANIFESTO.as_posix()]
    return {"commit": commit, "tags": sorted(tags), "descricao": _git(raiz, "describe", "--tags", "--always", "--dirty"),
            "data_commit": _git(raiz, "show", "-s", "--format=%cI", "HEAD"),
            "arvore_limpa": not modificados, "modificados": modificados}


def ler_versions_env(path: Path) -> dict:
    out = {}
    if not path.exists():
        return out
    for ln in path.read_text(encoding="utf-8").splitlines():
        ln = ln.strip()
        if ln and not ln.startswith("#") and "=" in ln:
            k, v = ln.split("=", 1)
            out[k.strip()] = v.strip()
    return out


def ambiente_analise(raiz: Path) -> dict:
    """Python e bibliotecas de quem gerou o manifesto. requirements.txt fixa as bibliotecas, mas não o Python."""
    import platform
    from importlib import metadata
    pacotes = {}
    for nome in ("numpy", "pandas", "scipy", "matplotlib", "nbformat", "nbclient", "PyYAML"):
        try:
            pacotes[nome] = metadata.version(nome)
        except metadata.PackageNotFoundError:
            pacotes[nome] = None
    req = raiz / "requirements.txt"
    return {"python": platform.python_version(), "plataforma": platform.platform(), "pacotes": pacotes,
            "requirements_sha256": sha256_arquivo(req) if req.exists() else None}


def _campaign_id(raiz: Path) -> str | None:
    cfg = raiz / "config" / "campaign.yaml"
    if not cfg.exists():
        return None
    return (yaml.safe_load(cfg.read_text(encoding="utf-8")) or {}).get("campaign_id")


def arquivos_de_evidencia(raiz: Path) -> list[str]:
    """Caminhos relativos (posix) de tudo o que entra no manifesto: os três diretórios e os arquivos
    soltos de data/ que são evidência (planos, log de execução e desvios)."""
    rels = set()
    for d in DIRETORIOS:
        base = raiz / d
        if base.is_dir():
            for p in base.rglob("*"):
                if p.name in IGNORADOS or p.is_dir():
                    continue
                rels.add(p.relative_to(raiz).as_posix())
    data = raiz / "data"
    for padrao in ("plan_*.csv", "campaign.log", "desvios_execucao.jsonl"):
        for p in data.glob(padrao):
            if p.is_file() or p.is_symlink():
                rels.add(p.relative_to(raiz).as_posix())
    return sorted(rels)


def hashes(raiz: Path, rels: list[str]) -> tuple[dict, list[str]]:
    out, problemas = {}, []
    for rel in rels:
        p = raiz / rel
        if p.is_symlink() or not p.is_file():
            problemas.append(f"{rel}: não é arquivo regular (link simbólico ou especial), fica fora do manifesto")
            continue
        out[rel] = {"sha256": sha256_arquivo(p), "bytes": p.stat().st_size}
    return out, problemas


def verificar_trilhas(raiz: Path, pasta: str) -> dict:
    """O mesmo que `make verify-audit`: cada .jsonl do primeiro nível (as tentativas ficam de fora)."""
    trilhas = {}
    for f in sorted((raiz / pasta).glob("*.jsonl")) if (raiz / pasta).is_dir() else []:
        try:
            ok, n, msg = verify(f)
        except (OSError, ValueError, KeyError) as e:  # JSON quebrado ou campo faltando
            ok, n, msg = False, 0, f"ilegível: {type(e).__name__}"
        trilhas[f.relative_to(raiz).as_posix()] = {"integra": ok, "registros": n, "mensagem": msg}
    return {"trilhas": len(trilhas), "integras": sum(t["integra"] for t in trilhas.values()),
            "todas_integras": all(t["integra"] for t in trilhas.values()), "detalhe": trilhas}


def _utc(ts) -> str | None:
    return None if ts is None else datetime.fromtimestamp(float(ts), timezone.utc).isoformat().replace("+00:00", "Z")


def resumo_replicas(raiz: Path, pasta_runs: str, pasta_audit: str, trilhas: dict) -> dict:
    """Cruza meta.json com as trilhas. A cadeia de hash pega alteração e troca de ordem, mas não pega o
    corte das últimas linhas; a contagem de registros em meta.json cobre esse caso."""
    status, backends, commits, axiomas = {}, {}, {}, {}
    inicio, alertas = [], []
    for mp in sorted((raiz / pasta_runs).glob("*/meta.json")) if (raiz / pasta_runs).is_dir() else []:
        try:
            meta = json.loads(mp.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            alertas.append(f"{mp.relative_to(raiz).as_posix()}: meta.json ilegível")
            continue
        st = meta.get("status", "?")
        status[st] = status.get(st, 0) + 1
        if st != "complete":
            continue
        rid = meta.get("run_id", mp.parent.name)
        b = meta.get("backend", "?")
        backends[b] = backends.get(b, 0) + 1
        c = meta.get("git_commit", "?")
        commits[c] = commits.get(c, 0) + 1
        ax = _sha256_json(meta.get("axioms"))
        axiomas[ax] = axiomas.get(ax, 0) + 1
        if meta.get("wall_start") is not None:
            inicio.append(float(meta["wall_start"]))
        aud = meta.get("audit") or {}
        if aud.get("enabled"):
            rel = f"{pasta_audit}/{rid}.jsonl"
            t = trilhas.get(rel)
            if t is None:
                alertas.append(f"{rid}: auditoria ligada em meta.json, mas {rel} não existe")
            elif aud.get("records") is not None and t["integra"] and t["registros"] != aud["records"]:
                alertas.append(f"{rid}: meta.json diz {aud['records']} registros e a trilha tem {t['registros']}")
    if backends.get("sim"):
        alertas.append(f"{pasta_runs}: {backends['sim']} réplicas de simulação, que não são evidência")
    if len(commits) > 1:
        alertas.append(f"{pasta_runs}: réplicas rodaram em {len(commits)} commits diferentes")
    if len(axiomas) > 1:
        alertas.append(f"{pasta_runs}: réplicas com {len(axiomas)} conjuntos diferentes de parâmetros dos axiomas")
    return {"por_status": status, "por_backend": backends, "git_commits": commits, "axiomas_sha256": axiomas,
            "primeira_wall_start_utc": _utc(min(inicio)) if inicio else None,
            "ultima_wall_start_utc": _utc(max(inicio)) if inicio else None, "alertas": alertas}


def gerar(raiz: Path) -> dict:
    raiz = Path(raiz).resolve()
    git = info_git(raiz)
    cid = _campaign_id(raiz)
    rels = arquivos_de_evidencia(raiz)
    arquivos, problemas = hashes(raiz, rels)
    plano_rel = f"data/plan_{cid}.csv" if cid else None
    plano = None
    if plano_rel and (raiz / plano_rel).is_file():
        texto = (raiz / plano_rel).read_text(encoding="utf-8")
        plano = {"caminho": plano_rel, "sha256": arquivos.get(plano_rel, {}).get("sha256"),
                 "replicas": max(len(texto.splitlines()) - 1, 0)}
    contagem = {d: {"existe": (raiz / d).is_dir(),
                    "arquivos": sum(1 for r in arquivos if r.startswith(d + "/")),
                    "bytes": sum(v["bytes"] for r, v in arquivos.items() if r.startswith(d + "/"))}
                for d in DIRETORIOS}
    va = verificar_trilhas(raiz, "data/audit")
    va_cal = verificar_trilhas(raiz, "data/calibracao/audit")
    oficiais = resumo_replicas(raiz, "data/runs", "data/audit", va["detalhe"])
    calibracao = resumo_replicas(raiz, "data/calibracao/runs", "data/calibracao/audit", va_cal["detalhe"])
    venv = raiz / "versions.env"
    alertas = list(problemas)
    if git["commit"] is None:
        alertas.append("fora de um repositório git: sem commit")
    elif not git["arvore_limpa"]:
        alertas.append(f"árvore com mudanças não commitadas: {', '.join(git['modificados'])}")
    if git["commit"] and not git["tags"]:
        alertas.append("HEAD sem tag")
    if git["commit"]:
        versionados = set((_git(raiz, "ls-files", "--", "data") or "").splitlines())
        fora = [r for r in arquivos if r not in versionados]
        git["dados_fora_do_git"] = len(fora)
        if fora:
            alertas.append(f"{len(fora)} arquivos de evidência fora do git (ex.: {fora[0]})")
    if plano is None:
        alertas.append(f"plano oficial {plano_rel} não encontrado")
    if not va["todas_integras"]:
        alertas.append("há trilha de auditoria oficial com falha")
    if not va_cal["todas_integras"]:
        alertas.append("há trilha de auditoria da calibração com falha")
    alertas += oficiais["alertas"] + [f"calibração: {a}" for a in calibracao["alertas"]]
    return {
        "formato": FORMATO,
        "gerado_em_utc": datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z"),
        "git": git,
        "campaign_id": cid,
        "config_sha256": sha256_arquivo(raiz / "config" / "campaign.yaml") if (raiz / "config" / "campaign.yaml").exists() else None,
        "plano_oficial": plano,
        "versions_env": {"sha256": sha256_arquivo(venv) if venv.exists() else None, "valores": ler_versions_env(venv)},
        "ambiente_analise": ambiente_analise(raiz),
        "contagem": {**contagem, "total_arquivos": len(arquivos)},
        "verify_audit": {"oficial": va, "calibracao": va_cal},
        "replicas_oficiais": oficiais,
        "replicas_calibracao": calibracao,
        "alertas": alertas,
        "arquivos": arquivos,
    }


def comparar(raiz: Path, manifesto: dict) -> dict:
    raiz = Path(raiz).resolve()
    esperado = manifesto["arquivos"]
    atual, problemas = hashes(raiz, arquivos_de_evidencia(raiz))
    alterados = sorted(r for r in esperado if r in atual and atual[r]["sha256"] != esperado[r]["sha256"])
    faltando = sorted(r for r in esperado if r not in atual)
    sobrando = sorted(r for r in atual if r not in esperado)
    va = verificar_trilhas(raiz, "data/audit")
    va_cal = verificar_trilhas(raiz, "data/calibracao/audit")
    ok = not (alterados or faltando or sobrando or problemas) and va["todas_integras"] and va_cal["todas_integras"]
    return {"ok": ok, "conferidos": len(esperado), "alterados": alterados, "faltando": faltando,
            "sobrando": sobrando, "problemas": problemas,
            "trilhas_integras": va["todas_integras"] and va_cal["todas_integras"]}


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)
    g = sub.add_parser("gerar")
    g.add_argument("--raiz", default=str(ROOT))
    g.add_argument("--saida", default=None)
    v = sub.add_parser("verificar")
    v.add_argument("--raiz", default=str(ROOT))
    v.add_argument("--manifesto", default=None)
    a = ap.parse_args(argv)
    raiz = Path(a.raiz)

    if a.cmd == "gerar":
        m = gerar(raiz)
        saida = Path(a.saida) if a.saida else raiz / MANIFESTO
        saida.parent.mkdir(parents=True, exist_ok=True)
        saida.write_text(json.dumps(m, indent=2, ensure_ascii=False, sort_keys=False) + "\n", encoding="utf-8")
        va = m["verify_audit"]["oficial"]
        print(f"{saida}: {m['contagem']['total_arquivos']} arquivos, commit {m['git']['commit']}, "
              f"tags {m['git']['tags'] or '-'}, trilhas íntegras {va['integras']}/{va['trilhas']}")
        print(f"SHA-256 do manifesto: {sha256_arquivo(saida)}")
        for al in m["alertas"]:
            print(f"  alerta: {al}")
        return 0 if va["todas_integras"] and m["verify_audit"]["calibracao"]["todas_integras"] else 1

    mpath = Path(a.manifesto) if a.manifesto else raiz / MANIFESTO
    manifesto = json.loads(mpath.read_text(encoding="utf-8"))
    if manifesto.get("formato") != FORMATO:
        print(f"{mpath}: formato desconhecido ({manifesto.get('formato')})")
        return 2
    r = comparar(raiz, manifesto)
    print(f"Manifesto {mpath} (SHA-256 {sha256_arquivo(mpath)}), commit {manifesto['git']['commit']}")
    for chave in ("alterados", "faltando", "sobrando", "problemas"):
        for item in r[chave]:
            print(f"  {chave}: {item}")
    if not r["trilhas_integras"]:
        print("  há trilha de auditoria com falha nesta cópia")
    print(f"{'CONFERE' if r['ok'] else 'NÃO CONFERE'}: {r['conferidos']} arquivos no manifesto, "
          f"{len(r['alterados'])} alterados, {len(r['faltando'])} faltando, {len(r['sobrando'])} sobrando")
    return 0 if r["ok"] else 1


if __name__ == "__main__":
    sys.exit(main())
