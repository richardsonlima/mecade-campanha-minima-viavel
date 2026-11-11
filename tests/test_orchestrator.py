"""Plano de calibração separado do oficial e regra das 3 falhas do orquestrador."""
import copy
import json

import pytest

from mecade.audit import AuditLog, verify
from mecade.config import load_campaign, load_scenario
from mecade.runner import run_one
from mecade.sim import SimWorld, VirtualClock
from orchestrator.plan_campaign import build_calibration_plan, build_plan
from orchestrator.run_campaign import (EXIT_INSTAVEL, EXIT_INTERROMPIDA, EXIT_LIMITE, EXIT_OK, check_plan_destination,
                                       count_failures, execute_plan, read_attempts, read_status)


def _plan(n: int) -> list[dict]:
    return [{"order": str(i), "run_id": f"{i:03d}_c0_controle_mecade_r{i:02d}", "scenario": "c0_controle",
             "arm": "mecade", "rep": str(i), "pair": "", "audit": "1"} for i in range(1, n + 1)]


class Fake:
    """Executor que falha conforme o roteiro: {run_id: quantas vezes falha antes de dar certo}."""

    def __init__(self, roteiro=None):
        self.roteiro = dict(roteiro or {})
        self.chamadas: list[str] = []
        self.limpezas = 0

    def execute(self, row):
        rid = row["run_id"]
        self.chamadas.append(rid)
        if self.roteiro.get(rid, 0) > 0:
            self.roteiro[rid] -= 1
            raise RuntimeError("kubectl estourou o tempo")
        return {"run_id": rid, "status": "complete"}

    def clean(self):
        self.limpezas += 1


def _run(plan, fake, out, **kw):
    kw.setdefault("check_lost", False)
    return execute_plan(plan, out_root=out, execute=fake.execute, clean=fake.clean, log=lambda *_: None,
                        settle_s=0, sleep=lambda _: None, **kw)


def _desvios(out):
    p = out.parent / "desvios_execucao.jsonl"
    return [json.loads(x) for x in p.read_text().splitlines()] if p.exists() else []


# plano de calibração
def test_calibracao_nao_coincide_com_o_plano_oficial():
    camp = load_campaign()
    oficial = {r["run_id"] for r in build_plan(camp, camp["scenarios"], 10, 10)}
    for rodada in (1, 2):
        cal = build_calibration_plan(camp, rodada)
        assert len(cal) == 9
        assert sum(r["pair"] == "" for r in cal) == 3
        assert not oficial & {r["run_id"] for r in cal}
    assert not {r["run_id"] for r in build_calibration_plan(camp, 1)} & {r["run_id"] for r in build_calibration_plan(camp, 2)}


def test_plano_oficial_nao_muda_com_a_calibracao():
    camp = load_campaign()
    antes = build_plan(camp, camp["scenarios"], 10, 10)
    build_calibration_plan(camp, 1)
    assert antes == build_plan(camp, camp["scenarios"], 10, 10)
    assert len(antes) == 70


def test_destino_do_plano_e_conferido():
    camp = load_campaign()
    cal = build_calibration_plan(camp, 1)
    oficial = build_plan(camp, camp["scenarios"], 1, 1)
    check_plan_destination(cal, True)
    check_plan_destination(oficial, False)
    with pytest.raises(SystemExit):
        check_plan_destination(cal, False)
    with pytest.raises(SystemExit):
        check_plan_destination(oficial, True)


# regra das 3 falhas
def test_terceira_falha_vira_falha_execucao_e_nao_tenta_de_novo(tmp_path):
    out, plan = tmp_path / "runs", _plan(4)
    alvo = plan[1]["run_id"]
    fake = Fake({alvo: 99})
    assert _run(plan, fake, out) == EXIT_OK
    assert fake.chamadas.count(alvo) == 3
    assert read_status(out / alvo) == "falha_execucao"
    assert read_status(out / plan[0]["run_id"]) == "complete"
    assert fake.limpezas == 3
    assert [d["tipo"] for d in _desvios(out)].count("falha_execucao") == 1
    # retomar não tenta outra vez
    fake2 = Fake()
    assert _run(plan, fake2, out) == EXIT_OK
    assert fake2.chamadas == []


def test_refeita_sai_da_ordem_e_fica_registrada(tmp_path):
    out, plan = tmp_path / "runs", _plan(3)
    alvo = plan[0]["run_id"]
    fake = Fake({alvo: 1})
    assert _run(plan, fake, out) == EXIT_OK
    assert fake.chamadas == [alvo, plan[1]["run_id"], plan[2]["run_id"], alvo]
    meta = json.loads((out / alvo / "meta.json").read_text())
    assert meta["status"] == "complete" and meta["tentativa"] == 2 and meta["fora_da_ordem"] is True
    assert [d["tipo"] for d in _desvios(out)] == ["refeita_fora_da_ordem"]


def test_retomada_na_propria_posicao_nao_e_desvio_de_ordem(tmp_path):
    out, plan = tmp_path / "runs", _plan(2)
    ledger = out / plan[0]["run_id"] / "tentativas.jsonl"
    ledger.parent.mkdir(parents=True)
    ledger.write_text(json.dumps({"tentativa": 1, "evento": "inicio", "quando": "x"}) + "\n")  # VM caiu
    assert _run(plan, Fake(), out) == EXIT_OK
    assert _desvios(out) == []
    assert json.loads((out / plan[0]["run_id"] / "meta.json").read_text())["tentativa"] == 2


def test_contagem_de_falhas():
    def e(t, ev):
        return {"tentativa": t, "evento": ev}
    assert count_failures([]) == 0
    assert count_failures([e(1, "inicio"), e(1, "falhou")]) == 1
    assert count_failures([e(1, "inicio")]) == 1  # queda do processo
    assert count_failures([e(1, "inicio"), e(1, "interrompida")]) == 0  # operador não conta
    assert count_failures([e(1, "inicio"), e(1, "falhou"), e(2, "inicio"), e(2, "concluida")]) == 1


def test_queda_na_terceira_tentativa_tambem_fecha_a_replica(tmp_path):
    out, plan = tmp_path / "runs", _plan(1)
    ledger = out / plan[0]["run_id"] / "tentativas.jsonl"
    ledger.parent.mkdir(parents=True)
    ledger.write_text("".join(json.dumps({"tentativa": t, "evento": "inicio"}) + "\n" for t in (1, 2, 3)))
    fake = Fake()
    assert _run(plan, fake, out) == EXIT_OK
    assert fake.chamadas == [] and read_status(out / plan[0]["run_id"]) == "falha_execucao"


def test_falhas_seguidas_param_antes_de_gastar_as_tentativas(tmp_path):
    out, plan = tmp_path / "runs", _plan(6)
    fake = Fake({r["run_id"]: 99 for r in plan})
    assert _run(plan, fake, out) == EXIT_INSTAVEL
    assert len(fake.chamadas) == 3
    assert all(count_failures(read_attempts(out / r["run_id"])) <= 1 for r in plan)


def test_passar_de_10_por_cento_para_a_campanha(tmp_path, monkeypatch):
    monkeypatch.setattr("orchestrator.run_campaign.load_runs", lambda *a, **k: [])
    out, plan = tmp_path / "runs", _plan(5)
    alvo = plan[0]["run_id"]
    fake = Fake({alvo: 99})
    assert _run(plan, fake, out, check_lost=True) == EXIT_LIMITE  # 1 de 5 passa de 10%
    assert read_status(out / alvo) == "falha_execucao"


def test_exatamente_10_por_cento_nao_para(tmp_path, monkeypatch):
    monkeypatch.setattr("orchestrator.run_campaign.load_runs", lambda *a, **k: [])
    out, plan = tmp_path / "runs", _plan(10)
    assert execute_plan(plan, out_root=out, execute=Fake({plan[0]["run_id"]: 99}).execute, clean=lambda: None,
                        log=lambda *_: None, settle_s=0, sleep=lambda _: None, check_lost=True) == EXIT_OK


def test_censurada_conta_para_o_limite(tmp_path, monkeypatch):
    import pandas as pd
    from orchestrator.run_campaign import count_lost
    out, plan = tmp_path / "runs", _plan(4)
    (out / plan[0]["run_id"]).mkdir(parents=True)
    (out / plan[0]["run_id"] / "meta.json").write_text(json.dumps({"status": "falha_execucao"}))
    monkeypatch.setattr("orchestrator.run_campaign.load_runs",
                        lambda *a, **k: [({"run_id": plan[1]["run_id"]}, None), ({"run_id": "de-outro-plano"}, None)])
    monkeypatch.setattr("orchestrator.run_campaign.metrics_table",
                        lambda runs: pd.DataFrame({"censurada": [True] * len(runs), "run_id": [m["run_id"] for m, _ in runs]}))
    c = count_lost(plan, out)
    assert (c["falha_execucao"], c["censurada"], c["total"], c["plano"]) == (1, 1, 2, 4)


def _perdas(tmp_path, monkeypatch, n, status=(), censuradas=()):
    """Plano de n réplicas. status: run_ids em falha_execucao. censuradas: [(índice, braço)] com censurada=True."""
    import pandas as pd
    out, plan = tmp_path / "runs", _plan(n)
    for i in status:
        (out / plan[i]["run_id"]).mkdir(parents=True)
        (out / plan[i]["run_id"] / "meta.json").write_text(json.dumps({"status": "falha_execucao"}))
    runs = [({"run_id": plan[i]["run_id"]}, None) for i, _ in censuradas]
    monkeypatch.setattr("orchestrator.run_campaign.load_runs", lambda *a, **k: runs)
    for i, a in censuradas:
        plan[i]["arm"] = a
    monkeypatch.setattr("orchestrator.run_campaign.metrics_table", lambda r: pd.DataFrame(
        {"censurada": [True] * len(r), "run_id": [m["run_id"] for m, _ in r]}))
    return plan, out


def test_censurada_do_baseline_nao_conta_mas_e_relatada(tmp_path, monkeypatch):
    from orchestrator.run_campaign import count_lost
    plan, out = _perdas(tmp_path, monkeypatch, 10, censuradas=[(0, "baseline"), (1, "baseline"), (2, "baseline")])
    c = count_lost(plan, out)
    assert (c["total"], c["censurada"], c["censurada_baseline"]) == (0, 0, 3)


def test_censurada_do_mecade_conta(tmp_path, monkeypatch):
    from orchestrator.run_campaign import count_lost
    plan, out = _perdas(tmp_path, monkeypatch, 10, censuradas=[(0, "mecade"), (1, "baseline")])
    c = count_lost(plan, out)
    assert (c["total"], c["censurada"], c["censurada_baseline"]) == (1, 1, 1)


def test_falha_execucao_conta_nos_dois_bracos(tmp_path, monkeypatch):
    from orchestrator.run_campaign import count_lost
    plan, out = _perdas(tmp_path, monkeypatch, 10, status=[0, 1])
    plan[0]["arm"], plan[1]["arm"] = "mecade", "baseline"
    assert count_lost(plan, out)["falha_execucao"] == 2


def test_limiar_de_10_por_cento_com_censuradas_dos_dois_bracos(tmp_path, monkeypatch):
    out_dir = tmp_path
    # 10 réplicas, 5 censuradas do baseline: não dispara
    plan, out = _perdas(out_dir, monkeypatch, 10, censuradas=[(i, "baseline") for i in range(5)])
    assert execute_plan(plan, out_root=out, execute=Fake().execute, clean=lambda: None, log=lambda *_: None,
                        settle_s=0, sleep=lambda _: None, check_lost=True) == EXIT_OK
    assert any(d["tipo"] == "censuradas_baseline_fora_do_limite" and d["total"] == 5 for d in _desvios(out))
    # 10 réplicas, 2 censuradas do MECADE: 2 > 1 dispara na retomada
    plan, out = _perdas(tmp_path / "b", monkeypatch, 10, censuradas=[(0, "mecade"), (1, "mecade")])
    assert execute_plan(plan, out_root=out, execute=Fake().execute, clean=lambda: None, log=lambda *_: None,
                        settle_s=0, sleep=lambda _: None, check_lost=True) == EXIT_LIMITE
    # 1 censurada do MECADE em 10: exatamente 10%, não dispara
    plan, out = _perdas(tmp_path / "c", monkeypatch, 10, censuradas=[(0, "mecade")])
    assert execute_plan(plan, out_root=out, execute=Fake().execute, clean=lambda: None, log=lambda *_: None,
                        settle_s=0, sleep=lambda _: None, check_lost=True) == EXIT_OK


def test_controle_nunca_e_censurado_e_replica_sem_deteccao_e():
    from analysis.metrics import run_metrics
    camp = load_campaign()
    df = pd_frame()
    base = {"run_id": "x", "scenario": "s", "arm": "baseline", "timing": camp["timing"], "axioms": camp["axioms"],
            "recovery": camp["recovery"], "events": [], "rto_s": 180}
    assert run_metrics({**base, "mitigation": {"acao": "restart"}}, df)["censurada"] is True
    assert run_metrics({**base, "mitigation": {"acao": "none"}}, df)["censurada"] is False


def pd_frame():
    import pandas as pd
    return pd.DataFrame({"t": [0.0, 5.0], "D_agr": [0.1, 0.1], "D_p95": [0.1, 0.1], "D_p99": [0.1, 0.1],
                         "D_error_rate": [0.0, 0.0], "p95": [0.1, 0.1], "p99": [0.1, 0.1], "error_rate": [0.0, 0.0]})


def test_trilha_da_terceira_falha_sai_de_audit(tmp_path):
    out, plan = tmp_path / "runs", _plan(2)
    rid = plan[0]["run_id"]
    trilha = out.parent / "audit" / f"{rid}.jsonl"

    def execute(row):
        if row["run_id"] == rid:
            trilha.parent.mkdir(parents=True, exist_ok=True)
            trilha.write_text('{"truncad')  # queda no meio de uma escrita
            raise RuntimeError("caiu")
        return {"run_id": row["run_id"], "status": "complete"}

    assert execute_plan(plan, out_root=out, execute=execute, clean=lambda: None, log=lambda *_: None, settle_s=0,
                        sleep=lambda _: None, check_lost=False) == EXIT_OK
    assert read_status(out / rid) == "falha_execucao"
    assert not trilha.exists()
    assert len(list((out.parent / "audit" / "tentativas").glob(f"{rid}.*"))) == 3


def test_tres_quedas_guardam_as_tres_trilhas(tmp_path):
    """Queda do processo não deixa linha `falhou`, e o arquivamento não pode sobrescrever a trilha anterior."""
    out, plan = tmp_path / "runs", _plan(1)
    rid = plan[0]["run_id"]
    trilha = out.parent / "audit" / f"{rid}.jsonl"
    trilha.parent.mkdir(parents=True)
    ledger = out / rid / "tentativas.jsonl"
    ledger.parent.mkdir(parents=True)

    class Queda(BaseException):
        pass

    def execute(row):
        trilha.write_text(f"tentativa {sum(1 for _ in ledger.open())}")
        raise Queda

    for _ in range(3):
        with pytest.raises(Queda):
            execute_plan(plan, out_root=out, execute=execute, clean=lambda: None, log=lambda *_: None, settle_s=0,
                         sleep=lambda _: None, check_lost=False)
    fake = Fake()
    assert _run(plan, fake, out) == EXIT_OK
    assert fake.chamadas == [] and read_status(out / rid) == "falha_execucao" and not trilha.exists()
    guardadas = sorted(p.read_text() for p in (out.parent / "audit" / "tentativas").iterdir())
    assert guardadas == ["tentativa 1", "tentativa 2", "tentativa 3"]


def test_arquivar_nunca_sobrescreve(tmp_path):
    from orchestrator.run_campaign import archive_partial_audit
    out = tmp_path / "runs"
    trilha = out.parent / "audit" / "r.jsonl"
    trilha.parent.mkdir(parents=True)
    for texto in ("a", "b"):
        trilha.write_text(texto)
        archive_partial_audit(out, "r", 2)
    assert sorted(p.read_text() for p in (out.parent / "audit" / "tentativas").iterdir()) == ["a", "b"]


def test_meta_truncado_conta_como_nao_concluida(tmp_path):
    out, plan = tmp_path / "runs", _plan(1)
    d = out / plan[0]["run_id"]
    d.mkdir(parents=True)
    (d / "meta.json").write_text('{"status": "comp')
    fake = Fake()
    assert _run(plan, fake, out) == EXIT_OK
    assert fake.chamadas == [plan[0]["run_id"]] and read_status(d) == "complete"


def test_trilha_existente_na_primeira_tentativa_tambem_e_arquivada(tmp_path):
    out, plan = tmp_path / "runs", _plan(1)
    trilha = out.parent / "audit" / f"{plan[0]['run_id']}.jsonl"
    trilha.parent.mkdir(parents=True)
    trilha.write_text("antiga")
    assert _run(plan, Fake(), out) == EXIT_OK
    assert not trilha.exists()
    assert next((out.parent / "audit" / "tentativas").iterdir()).read_text() == "antiga"


def test_falhas_seguidas_valem_entre_passadas(tmp_path):
    out, plan = tmp_path / "runs", _plan(3)
    # as duas últimas falham na passada 1; o ambiente segue quebrado para a primeira pendente da passada 2
    fake = Fake({plan[1]["run_id"]: 99, plan[2]["run_id"]: 99})
    assert _run(plan, fake, out) == EXIT_INSTAVEL
    assert fake.chamadas == [plan[0]["run_id"], plan[1]["run_id"], plan[2]["run_id"], plan[1]["run_id"]]


def test_queda_entre_as_gravacoes_do_meta_e_reparada(tmp_path):
    out, plan = tmp_path / "runs", [{"order": "1", "run_id": "001_s", "scenario": "s", "arm": "mecade", "rep": "1",
                                     "pair": "s#01", "audit": "1"}]
    d = out / "001_s"
    d.mkdir(parents=True)
    (d / "meta.json").write_text(json.dumps({"run_id": "001_s", "status": "complete"}))
    (d / "tentativas.jsonl").write_text(json.dumps({"tentativa": 1, "evento": "inicio"}) + "\n")
    fake = Fake()
    assert _run(plan, fake, out) == EXIT_OK
    assert fake.chamadas == []
    meta = json.loads((d / "meta.json").read_text())
    assert meta["pair"] == "s#01" and meta["order"] == 1 and meta["tentativa"] == 1
    assert count_failures(read_attempts(d)) == 0


def test_retomada_acima_do_limite_para_sem_gastar_replica(tmp_path, monkeypatch):
    monkeypatch.setattr("orchestrator.run_campaign.load_runs", lambda *a, **k: [])
    out, plan = tmp_path / "runs", _plan(5)
    (out / plan[0]["run_id"]).mkdir(parents=True)
    (out / plan[0]["run_id"] / "meta.json").write_text(json.dumps({"status": "falha_execucao"}))
    fake = Fake()
    assert _run(plan, fake, out, check_lost=True) == EXIT_LIMITE
    assert fake.chamadas == []


def test_plano_existente_nao_e_sobrescrito_sem_substituir(tmp_path, monkeypatch):
    import sys
    from orchestrator import plan_campaign
    out = tmp_path / "plan.csv"
    monkeypatch.setattr(sys, "argv", ["x", "--out", str(out)])
    plan_campaign.main()
    original = out.read_bytes()
    plan_campaign.main()  # regerar igual é permitido
    monkeypatch.setattr(sys, "argv", ["x", "--out", str(out), "--scenarios", "s2_gray_currency,s3_podkill_cart"])
    with pytest.raises(SystemExit):
        plan_campaign.main()
    assert out.read_bytes() == original
    monkeypatch.setattr(sys, "argv", ["x", "--out", str(out), "--scenarios", "s2_gray_currency,s3_podkill_cart", "--substituir"])
    plan_campaign.main()
    assert out.read_bytes() != original


def test_interrupcao_do_operador_limpa_e_nao_conta(tmp_path):
    out, plan = tmp_path / "runs", _plan(1)

    class Interrompe(Fake):
        def execute(self, row):
            raise KeyboardInterrupt

    fake = Interrompe()
    assert _run(plan, fake, out) == EXIT_INTERROMPIDA
    assert fake.limpezas == 1
    assert count_failures(read_attempts(out / plan[0]["run_id"])) == 0


def test_limit_conta_so_concluidas(tmp_path):
    out, plan = tmp_path / "runs", _plan(4)
    fake = Fake({plan[0]["run_id"]: 1})
    assert _run(plan, fake, out, limit=2) == EXIT_OK
    assert [read_status(out / r["run_id"]) for r in plan].count("complete") == 2


def test_trilha_da_tentativa_refeita_verifica_e_a_parcial_fica_guardada(tmp_path):
    """Sem arquivar, a segunda tentativa anexaria uma nova cadeia ao arquivo e o verify() acusaria quebra."""
    out = tmp_path / "runs"
    plan = [{"order": "1", "run_id": "001_x", "scenario": "c0_controle", "arm": "mecade", "rep": "1", "pair": "", "audit": "1"},
            {"order": "2", "run_id": "002_y", "scenario": "c0_controle", "arm": "mecade", "rep": "2", "pair": "", "audit": "1"}]
    trilha = out.parent / "audit" / "001_x.jsonl"
    tentativas = {"n": 0}

    def execute(row):
        if row["run_id"] == "001_x":
            tentativas["n"] += 1
            log = AuditLog(trilha, enabled=True)
            log.record({"event": f"tentativa{tentativas['n']}"})
            log.close()
            if tentativas["n"] == 1:
                raise RuntimeError("caiu")
        return {"run_id": row["run_id"], "status": "complete"}

    assert execute_plan(plan, out_root=out, execute=execute, clean=lambda: None, log=lambda *_: None,
                        settle_s=0, sleep=lambda _: None, check_lost=False) == EXIT_OK
    assert verify(trilha)[0] and verify(trilha)[1] == 1
    guardadas = list((out.parent / "audit" / "tentativas").glob("001_x.*"))
    assert len(guardadas) == 1 and "tentativa1" in guardadas[0].read_text()


def test_falha_execucao_fica_fora_da_analise_e_derruba_o_par(tmp_path):
    from analysis.metrics import execution_failures, load_runs, metrics_table, paired_comparison
    camp = copy.deepcopy(load_campaign())
    out = tmp_path / "runs"
    sc = "s3_podkill_cart"
    plan = []
    i = 0
    for rep in (1, 2):
        for arm in ("baseline", "mecade"):
            i += 1
            plan.append({"order": str(i), "run_id": f"{i:03d}_{sc}_{arm}_r{rep:02d}", "scenario": sc, "arm": arm,
                         "rep": str(rep), "pair": f"{sc}#{rep:02d}", "audit": "1"})

    def execute(row):
        if row["run_id"] == plan[0]["run_id"]:
            raise RuntimeError("sempre falha")
        clock = VirtualClock()
        world = SimWorld(clock, seed=int(row["order"]))
        return run_one(run_id=row["run_id"], scenario=load_scenario(sc), arm=row["arm"], campaign=camp, prom=world,
                       kube=world, clock=clock, out_root=out, sim_world=world, log=lambda *_: None)

    assert execute_plan(plan, out_root=out, execute=execute, clean=lambda: None, log=lambda *_: None, settle_s=0,
                        sleep=lambda _: None, check_lost=False) == EXIT_OK
    m = metrics_table(load_runs(out, include_sim=True))
    assert len(m) == 3
    assert paired_comparison(m, "TTR_capped").iloc[0]["n_pairs"] == 1
    assert [f["run_id"] for f in execution_failures(out)] == [plan[0]["run_id"]]


def _executa(plan, out, log=lambda *_: None):
    return execute_plan(plan, out_root=out, execute=Fake().execute, clean=lambda: None, log=log,
                        settle_s=0, sleep=lambda _: None, check_lost=True)


def test_desvio_de_censurada_do_baseline_nao_repete_na_retomada(tmp_path, monkeypatch):
    plan, out = _perdas(tmp_path, monkeypatch, 10, censuradas=[(i, "baseline") for i in range(3)])
    assert _executa(plan, out) == EXIT_OK
    assert _executa(plan, out) == EXIT_OK
    assert len([d for d in _desvios(out) if d["tipo"] == "censuradas_baseline_fora_do_limite"]) == 1


def test_arm_desconhecido_conta_como_mecade_e_avisa(tmp_path, monkeypatch):
    from orchestrator.run_campaign import count_lost
    plan, out = _perdas(tmp_path, monkeypatch, 10, censuradas=[(0, "xpto"), (1, "xpto")])
    c = count_lost(plan, out)
    assert (c["censurada"], c["censurada_baseline"], len(c["arm_desconhecido"])) == (2, 0, 2)
    logs = []
    assert _executa(plan, out, logs.append) == EXIT_LIMITE
    assert any("AVISO" in x and "xpto" in x for x in logs)
