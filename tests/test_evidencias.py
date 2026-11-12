"""Manifesto de evidências e `make verify-audit`, sobre dados sintéticos em diretório temporário."""
import hashlib
import json
import re
import shutil
import subprocess
import sys

import pytest

from analysis import evidencias as ev
from mecade.audit import AuditLog
from mecade.config import ROOT


def _trilha(path, n):
    log = AuditLog(path)
    for i in range(n):
        log.record({"event": "STEP", "i": i})
    return log.close()


def _replica(raiz, base, rid, arm="mecade", n_audit=5, commit="c0ffee", audit=True):
    run = raiz / base / "runs" / rid
    run.mkdir(parents=True)
    info = _trilha(raiz / base / "audit" / f"{rid}.jsonl", n_audit) if audit else {"enabled": False}
    meta = {"run_id": rid, "arm": arm, "backend": "k8s", "status": "complete", "wall_start": 1794500000.0,
            "audit": info, "git_commit": commit, "axioms": {"d_on": 0.5, "d_off": 0.3}}
    (run / "meta.json").write_text(json.dumps(meta), encoding="utf-8")
    (run / "steps.csv").write_text("t,D_agr\n0,0.1\n5,0.2\n", encoding="utf-8")
    (run / "tentativas.jsonl").write_text('{"tentativa": 1}\n', encoding="utf-8")


@pytest.fixture
def raiz(tmp_path):
    r = tmp_path / "copia"
    (r / "config").mkdir(parents=True)
    (r / "config" / "campaign.yaml").write_text("campaign_id: teste-01\n", encoding="utf-8")
    (r / "versions.env").write_text("# comentário\nONLINE_BOUTIQUE_VERSION=v0.10.5\nCHAOS_MESH_CHART_VERSION=2.8.4\n",
                                    encoding="utf-8")
    (r / "data" / "runs").mkdir(parents=True)
    (r / "data" / "runs" / ".gitkeep").write_text("")
    (r / "data" / "plan_teste-01.csv").write_text("order,run_id\n1,a\n2,b\n3,c\n", encoding="utf-8")
    (r / "data" / "desvios_execucao.jsonl").write_text('{"tipo": "ordem"}\n', encoding="utf-8")
    _replica(r, "data", "001_s2_mecade_r01")
    _replica(r, "data", "002_s2_baseline_r01", arm="baseline", audit=False)
    _replica(r, "data/calibracao", "cal1_001_c0_mecade_r01", n_audit=3)
    (r / "data" / "audit" / "tentativas").mkdir()
    (r / "data" / "audit" / "tentativas" / "001_parcial.jsonl").write_text("lixo que não é cadeia\n")
    return r


def test_manifesto_tem_hashes_contagens_versoes_e_plano(raiz):
    m = ev.gerar(raiz)
    arq = m["arquivos"]
    p = "data/runs/001_s2_mecade_r01/steps.csv"
    assert arq[p]["sha256"] == hashlib.sha256((raiz / p).read_bytes()).hexdigest()
    assert "data/runs/.gitkeep" not in arq
    assert "data/audit/tentativas/001_parcial.jsonl" in arq          # guardada e com hash, fora do verify-audit
    assert "data/desvios_execucao.jsonl" in arq
    assert m["contagem"]["data/runs"]["arquivos"] == 6
    assert m["contagem"]["data/audit"]["arquivos"] == 2
    assert m["contagem"]["data/calibracao"]["arquivos"] == 4
    assert m["contagem"]["total_arquivos"] == len(arq) == 14
    assert m["plano_oficial"]["caminho"] == "data/plan_teste-01.csv" and m["plano_oficial"]["replicas"] == 3
    assert m["plano_oficial"]["sha256"] == arq["data/plan_teste-01.csv"]["sha256"]
    assert m["versions_env"]["valores"] == {"ONLINE_BOUTIQUE_VERSION": "v0.10.5", "CHAOS_MESH_CHART_VERSION": "2.8.4"}
    assert m["ambiente_analise"]["python"] == ".".join(map(str, sys.version_info[:3]))
    assert m["ambiente_analise"]["pacotes"]["numpy"]
    va = m["verify_audit"]["oficial"]
    assert va["trilhas"] == 1 and va["todas_integras"] and m["verify_audit"]["calibracao"]["integras"] == 1
    assert m["replicas_oficiais"]["por_status"] == {"complete": 2}
    assert m["replicas_oficiais"]["git_commits"] == {"c0ffee": 2}
    assert re.fullmatch(r"\d{4}-\d\d-\d\dT\d\d:\d\d:\d\dZ", m["gerado_em_utc"])
    assert m["replicas_oficiais"]["primeira_wall_start_utc"].endswith("Z")
    assert m["git"]["commit"] is None and any("sem commit" in a for a in m["alertas"])


def test_verificar_confere_copia_intacta_e_acusa_alteracao_falta_e_sobra(raiz, tmp_path):
    assert ev.main(["gerar", "--raiz", str(raiz)]) == 0
    manifesto = raiz / "data" / "EVIDENCIAS_MANIFESTO.json"
    assert ev.main(["verificar", "--raiz", str(raiz)]) == 0

    # segunda cópia (como a do bucket), conferida com o manifesto da primeira
    copia = tmp_path / "bucket"
    shutil.copytree(raiz, copia)
    assert ev.main(["verificar", "--raiz", str(copia), "--manifesto", str(manifesto)]) == 0

    steps = copia / "data" / "runs" / "001_s2_mecade_r01" / "steps.csv"
    steps.write_text(steps.read_text().replace("0.2", "0.3"))
    (copia / "data" / "runs" / "002_s2_baseline_r01" / "tentativas.jsonl").unlink()
    (copia / "data" / "calibracao" / "extra.txt").write_text("x")
    r = ev.comparar(copia, json.loads(manifesto.read_text()))
    assert not r["ok"]
    assert r["alterados"] == ["data/runs/001_s2_mecade_r01/steps.csv"]
    assert r["faltando"] == ["data/runs/002_s2_baseline_r01/tentativas.jsonl"]
    assert r["sobrando"] == ["data/calibracao/extra.txt"]
    assert ev.main(["verificar", "--raiz", str(copia), "--manifesto", str(manifesto)]) == 1


def test_trilha_adulterada_falha_no_gerar_e_no_verificar(raiz):
    assert ev.main(["gerar", "--raiz", str(raiz)]) == 0
    t = raiz / "data" / "audit" / "001_s2_mecade_r01.jsonl"
    linhas = t.read_text().splitlines()
    rec = json.loads(linhas[2]); rec["event"]["i"] = 99
    linhas[2] = json.dumps(rec)
    t.write_text("\n".join(linhas) + "\n")
    assert ev.main(["verificar", "--raiz", str(raiz)]) == 1
    m = ev.gerar(raiz)
    assert not m["verify_audit"]["oficial"]["todas_integras"]
    assert ev.main(["gerar", "--raiz", str(raiz)]) == 1


def test_corte_no_fim_da_trilha_aparece_pela_contagem_do_meta(raiz):
    """A cadeia continua válida se as últimas linhas somem; a contagem em meta.json acusa."""
    t = raiz / "data" / "audit" / "001_s2_mecade_r01.jsonl"
    t.write_text("\n".join(t.read_text().splitlines()[:3]) + "\n")
    m = ev.gerar(raiz)
    assert m["verify_audit"]["oficial"]["todas_integras"]
    assert any("diz 5 registros e a trilha tem 3" in a for a in m["alertas"])


def test_alerta_trilha_ausente_sim_e_commits_misturados(raiz):
    (raiz / "data" / "audit" / "001_s2_mecade_r01.jsonl").unlink()
    _replica(raiz, "data", "003_s3_mecade_r01", commit="outro")
    meta = raiz / "data" / "runs" / "003_s3_mecade_r01" / "meta.json"
    d = json.loads(meta.read_text()); d["backend"] = "sim"; meta.write_text(json.dumps(d))
    al = ev.gerar(raiz)["alertas"]
    assert any("001_s2_mecade_r01: auditoria ligada" in a for a in al)
    assert any("simulação" in a for a in al)
    assert any("2 commits diferentes" in a for a in al)


def test_commit_e_tag_do_head(raiz):
    git = ["git", "-C", str(raiz), "-c", "user.name=t", "-c", "user.email=t@t", "-c", "commit.gpgsign=false"]
    subprocess.run(["git", "init", "-q", str(raiz)], check=True)
    subprocess.run(git + ["add", "-A"], check=True)
    subprocess.run(git + ["commit", "-qm", "dados"], check=True)
    subprocess.run(git + ["tag", "mvc-teste-final"], check=True)
    m = ev.gerar(raiz)
    head = subprocess.run(["git", "-C", str(raiz), "rev-parse", "HEAD"], capture_output=True, text=True).stdout.strip()
    assert m["git"]["commit"] == head and m["git"]["tags"] == ["mvc-teste-final"]
    assert m["git"]["arvore_limpa"] and not any("tag" in a or "commitadas" in a for a in m["alertas"])
    # o próprio manifesto não suja a árvore
    ev.main(["gerar", "--raiz", str(raiz)])
    subprocess.run(git + ["add", "data/EVIDENCIAS_MANIFESTO.json"], check=True)
    subprocess.run(git + ["commit", "-qm", "manifesto"], check=True)
    (raiz / "data" / "EVIDENCIAS_MANIFESTO.json").write_text("{}")
    assert ev.gerar(raiz)["git"]["arvore_limpa"]


@pytest.mark.skipif(shutil.which("make") is None, reason="sem make")
def test_make_verify_audit_falha_se_uma_trilha_do_meio_falhar(tmp_path):
    aud = tmp_path / "audit"
    for nome in ("a", "b", "c"):
        _trilha(aud / f"{nome}.jsonl", 4)
    cmd = ["make", "-s", "-C", str(ROOT), "verify-audit", f"AUDIT_DIR={aud}", f"PY={sys.executable}"]
    assert subprocess.run(cmd, capture_output=True, text=True).returncode == 0
    b = aud / "b.jsonl"
    linhas = b.read_text().splitlines()
    rec = json.loads(linhas[1]); rec["event"]["i"] = 7
    linhas[1] = json.dumps(rec)
    b.write_text("\n".join(linhas) + "\n")
    r = subprocess.run(cmd, capture_output=True, text=True)
    assert r.returncode != 0 and "1 com falha" in r.stdout
