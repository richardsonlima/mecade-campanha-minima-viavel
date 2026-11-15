"""Fase 0 (PROTOCOLO_C3, Seção 3.1): execução com cluster falso e as regras fixas aplicadas a dados sintéticos."""
import csv
import json

import pytest

from mecade.config import load_campaign, load_scenario
from mecade.sim import VirtualClock
from orchestrator import fase0 as f0

# ------------------------------------------------------------------------------------------ execução


class FalsoCluster:
    def __init__(self, clock, rollout_s=17.0, falha_rollout=False):
        self.clock, self.rollout_s, self.falha_apos_injecao = clock, rollout_s, falha_rollout
        self.falha = False   # o rollout do reset funciona; o da mitigação (depois do apply) pode travar
        self.log = []

    def _reg(self, *a):
        self.log.append((self.clock.now(), *a))

    def delete_all_chaos(self): self._reg("limpa")
    def scale(self, d, n): self._reg("scale", d, n)
    def pods(self, app): return [f"{app}-0"]
    def apply(self, m):
        self._reg("apply")
        self.falha = self.falha_apos_injecao
    def delete(self, kind, name): self._reg("delete")
    def server_version(self): return "v-falso"
    def restart(self, d): self._reg("restart", d)

    def wait_rollout(self, d, timeout="300s"):
        self._reg("espera", d)
        if self.falha:
            raise RuntimeError("rollout travado")
        self.clock.t += self.rollout_s

    def instant(self, query):
        return 0.0 if "outcome" in query else 0.1


def _roda(exec_id, tmp_path, **kw):
    camp, sc = load_campaign(), load_scenario(f0.CENARIO)
    clock = VirtualClock()
    c = FalsoCluster(clock, **kw)
    meta = f0.executar(exec_id, scenario=sc, campaign=camp, prom=c, kube=c, clock=clock, out_root=tmp_path,
                       sincrono=True, tipos_de_no=lambda: {"e2-standard-2": 3}, log=lambda *_: None)
    return meta, c, sc


@pytest.mark.parametrize("exec_id,t_restart", [("A", 15), ("B", 120), ("D", 425)])
def test_restart_do_alvo_no_instante_da_tabela(exec_id, t_restart, tmp_path):
    meta, c, sc = _roda(exec_id, tmp_path)
    assert meta["run_id"] == f"diag_{exec_id}" and meta["plano"] == "diagnostico"
    assert t_restart <= meta["restart_alvo_t"] < t_restart + 5   # passo de 5 s
    assert meta["rollout_s"] == 17.0 and meta["rollout_ok"] is True
    assert meta["machine_types"] == {"e2-standard-2": 3}
    assert (tmp_path / f"diag_{exec_id}" / "steps.csv").exists()


def test_a_e_b_nao_reiniciam_clientes_e_c_d_reiniciam_depois_de_clientes_apos_s(tmp_path):
    for e in ("A", "B"):
        meta, c, _ = _roda(e, tmp_path / e)
        assert meta["clientes_t"] is None
        assert not [x for x in c.log if x[1] == "restart" and x[2] == "frontend"]
    meta, c, sc = _roda("C1", tmp_path / "C1")
    apos = sc["mitigacao"]["clientes_apos_s"]
    assert apos == 45
    # o atraso conta do início da mitigação (como em mitigate() do runner), não do fim do rollout
    assert meta["clientes_t"] - meta["restart_alvo_t"] == pytest.approx(apos, abs=5)
    reinicios = [x[2] for x in c.log if x[1] == "restart"]
    assert reinicios[-3:] == sc["mitigacao"]["clientes"]
    assert reinicios.index("productcatalogservice") < reinicios.index("frontend")


def test_rollout_travado_fica_sem_tempo_e_a_execucao_segue(tmp_path):
    meta, _, _ = _roda("A", tmp_path, falha_rollout=True)
    assert meta["rollout_s"] is None and meta["rollout_ok"] is False and "travado" in meta["erro_rollout"]
    assert any(e["event"] == "ROLLOUT_FALHOU" for e in meta["events"])


def test_tres_tentativas_e_depois_falha_execucao(tmp_path):
    n = {"v": 0}

    def fabrica():
        n["v"] += 1
        raise RuntimeError("port-forward caiu")

    meta = f0.executar_com_tentativas("A", fabrica=fabrica, out_root=tmp_path, settle_s=0, sleep=lambda s: None,
                                      log=lambda *_: None)
    assert n["v"] == 3 and meta["status"] == "falha_execucao"
    ledger = [json.loads(x) for x in (tmp_path / "diag_A" / "tentativas.jsonl").read_text().splitlines()]
    assert [e["evento"] for e in ledger].count("falhou") == 3


def test_segunda_tentativa_conclui_e_arquiva_a_primeira(tmp_path):
    camp, sc = load_campaign(), load_scenario(f0.CENARIO)
    estado = {"n": 0}

    def fabrica():
        estado["n"] += 1
        if estado["n"] == 1:
            (tmp_path / "diag_A").mkdir(exist_ok=True)
            (tmp_path / "diag_A" / "k8s_coleta.jsonl").write_text("parcial\n")
            raise RuntimeError("falhou no meio")
        clock = VirtualClock()
        c = FalsoCluster(clock)
        return dict(scenario=sc, campaign=camp, prom=c, kube=c, clock=clock, sincrono=True)

    meta = f0.executar_com_tentativas("A", fabrica=fabrica, out_root=tmp_path, settle_s=0, sleep=lambda s: None,
                                      log=lambda *_: None)
    assert meta["status"] == "complete"
    assert (tmp_path / "diag_A" / "tentativas" / "t1" / "k8s_coleta.jsonl").read_text() == "parcial\n"


# ------------------------------------------------------------------------------------------ regras


def test_clientes_apos_s_arredonda_e_corta():
    assert f0.clientes_apos_s([17.0, 22.4]) == {"valor": 35, "maior_rollout_s": 22.4, "arredondado": 35, "cortado": False}
    assert f0.clientes_apos_s([25.0])["valor"] == 35            # 35 exato não sobe
    assert f0.clientes_apos_s([25.1])["valor"] == 40            # 35,1 sobe para 40
    assert f0.clientes_apos_s([3.0])["valor"] == 20 and f0.clientes_apos_s([3.0])["cortado"]
    assert f0.clientes_apos_s([80.0])["valor"] == 60
    assert f0.clientes_apos_s([])["valor"] is None


def _steps(t_ini, t_fim, p95, err=0.0):
    return [{"t": str(t), "p95": str(p95(t) if callable(p95) else p95),
             "error_rate": str(err(t) if callable(err) else err)} for t in range(t_ini, t_fim, 5)]


def _dado(meta_extra, steps, coleta=()):
    meta = {"scenario": "s1_latencia_productcatalog", "alvo": "productcatalogservice", "M_base": {"p95": 0.1},
            "t_inject_abs": 1000.0, "restart_alvo_t": 40.0, "restart_alvo_abs": 1040.0, **meta_extra}
    return {"meta": meta, "steps": steps, "coleta": list(coleta)}


def test_cascata_fica_com_60s_dentro_das_condicoes_ate_150s_do_restart():
    # volta a 100 s depois do restart: janela de 60 s começa em t = 140 <= 40 + 150
    d = _dado({}, _steps(0, 400, lambda t: 5.0 if t < 140 else 0.15, lambda t: 0.9 if t < 140 else 0.0))
    r = f0.cascata_ok(d)
    assert r["ok"] and r["inicio_t"] == 140 and r["depois_do_restart_s"] == 100


def test_cascata_sai_se_a_volta_comeca_depois_de_150s_ou_a_janela_e_curta():
    tarde = _dado({}, _steps(0, 400, lambda t: 5.0 if t < 200 else 0.15, lambda t: 0.9 if t < 200 else 0.0))
    assert not f0.cascata_ok(tarde)["ok"]
    curta = _dado({}, _steps(0, 400, lambda t: 0.15 if 100 <= t < 155 else 5.0, 0.0))   # 55 s só (100..150)
    assert not f0.cascata_ok(curta)["ok"]
    erro = _dado({}, _steps(0, 400, 0.15, lambda t: 0.02))
    assert not f0.cascata_ok(erro)["ok"]
    assert not f0.cascata_ok(None)["ok"]


def test_cascata_limites_exatos_de_erro_e_p95():
    no_limite = _dado({}, _steps(0, 400, 0.2, 0.01))        # p95 = 2 x 0,1 e erro = 0,01: vale "<="
    assert f0.cascata_ok(no_limite)["ok"]
    acima = _dado({}, _steps(0, 400, 0.2001, 0.01))
    assert not f0.cascata_ok(acima)["ok"]


SS_PRESO = """State Recv-Q Send-Q Local Address:Port Peer Address:Port
ESTAB 0 0 10.0.0.1:41000 10.0.0.9:3550
\t cubic wscale:7,7 rto:204 retrans:0/{r} bytes_retrans:{b}
ESTAB 0 0 10.0.0.1:41002 10.0.0.77:3550
\t cubic retrans:0/1
"""
SS_LIMPO = "State Recv-Q Send-Q Local Address:Port Peer Address:Port\nESTAB 0 0 10.0.0.1:41002 10.0.0.77:3550\n"


def _pods(alvo_ip, removendo=False):
    return [{"nome": "p", "app": "productcatalogservice", "ip": alvo_ip, "removendo": removendo}]


def _col(t, ss_texto=None, ep=("10.0.0.9",), app="frontend", pods=None):
    c = {"t_abs": t, "pods": pods if pods is not None else _pods("10.0.0.9"),
         "endpoints_alvo": {"prontos": list(ep), "nao_prontos": []}}
    if ss_texto is not None:
        c["ss"] = {f"{app}-1": {"app": app, "ip": "10.0.0.1", "texto": ss_texto}}
    return c


def test_parse_ss_le_estado_peer_e_retransmissoes():
    cs = f0.parse_ss(SS_PRESO.format(r=7, b=1448))
    assert [c["peer_ip"] for c in cs] == ["10.0.0.9", "10.0.0.77"]
    assert cs[0]["retrans_total"] == 7 and cs[0]["bytes_retrans"] == 1448 and cs[1]["retrans_total"] == 1
    assert f0.parse_ss("") == []


def test_h4_condicao_1_exige_retransmissao_crescente_depois_de_sair_dos_endpoints():
    base = [_col(1030.0)]
    preso = base + [_col(1050.0, SS_PRESO.format(r=1, b=100), ep=("10.0.0.5",)),
                    _col(1065.0, SS_PRESO.format(r=2, b=200), ep=("10.0.0.5",))]
    assert f0.h4_condicao_1(_dado({}, [], preso))["ok"] is True
    parado = base + [_col(1050.0, SS_PRESO.format(r=1, b=100), ep=("10.0.0.5",)),
                     _col(1065.0, SS_PRESO.format(r=1, b=100), ep=("10.0.0.5",))]
    assert f0.h4_condicao_1(_dado({}, [], parado))["ok"] is False
    # ainda nos endpoints: a leitura não vale
    assert f0.h4_condicao_1(_dado({}, [], base + [_col(1050.0, SS_PRESO.format(r=1, b=1))]))["ok"] is None
    assert f0.h4_condicao_1(None)["ok"] is None


def test_h4_condicao_2_nenhuma_conexao_para_o_ip_antigo():
    base = [_col(1030.0)]
    limpo = base + [_col(1050.0, SS_LIMPO, ep=("10.0.0.5",)), _col(1065.0, SS_LIMPO, ep=("10.0.0.5",))]
    assert f0.h4_condicao_2(_dado({}, [], limpo))["ok"] is True
    preso = base + [_col(1050.0, SS_PRESO.format(r=1, b=1), ep=("10.0.0.5",))]
    assert f0.h4_condicao_2(_dado({}, [], preso))["ok"] is False


def test_h4_condicao_3_conexoes_somem_ate_15s_depois_do_mitigation_clientes():
    extra = {"clientes_t": 85.0}                              # absoluto 1085
    pods = [_pods("10.0.0.9"), ]
    antes = [_col(1030.0)]
    # entre o restart e MITIGATION_CLIENTES a conexão presa pode existir (não conta contra); a partir de 1100 não
    ok = antes + [_col(1060.0, SS_PRESO.format(r=1, b=1), ep=("10.0.0.5",)),
                  _col(1100.0, SS_LIMPO, ep=("10.0.0.5",), app="frontend"),
                  _col(1100.0, SS_LIMPO, ep=("10.0.0.5",), app="checkoutservice")]
    ok[2]["ss"].update(ok[3]["ss"]); ok.pop(3)
    assert f0.h4_condicao_3(_dado(extra, [], ok))["ok"] is True
    # leitura de 1100 ainda com a conexão: falha
    ruim = antes + [_col(1100.0, SS_PRESO.format(r=1, b=1), ep=("10.0.0.5",))]
    ruim[1]["ss"]["checkoutservice-1"] = ruim[1]["ss"]["frontend-1"] | {"app": "checkoutservice"}
    assert f0.h4_condicao_3(_dado(extra, [], ruim))["ok"] is False
    # sem leitura em um dos clientes: não testada
    so_front = antes + [_col(1100.0, SS_LIMPO, ep=("10.0.0.5",))]
    assert f0.h4_condicao_3(_dado(extra, [], so_front))["ok"] is None
    assert f0.h4_condicao_3(_dado({}, [], ok))["ok"] is None


# ------------------------------------------------------------------------------------------ analisar (de ponta a ponta)


def _grava(raiz, exec_id, d):
    p = raiz / f"diag_{exec_id}"
    p.mkdir(parents=True)
    (p / "meta.json").write_text(json.dumps({**d["meta"], "status": "complete"}))
    with (p / "steps.csv").open("w", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=["t", "p95", "error_rate"])
        w.writeheader()
        w.writerows(d["steps"])
    (p / "k8s_coleta.jsonl").write_text("".join(json.dumps(c) + "\n" for c in d["coleta"]))


def test_analisar_sem_dados_nao_decide_nada(tmp_path):
    r = f0.analisar(tmp_path)
    assert r["clientes_apos_s"]["valor"] is None and not r["cascata"]["fica"] and r["H4"]["resultado"] == "não testada"


def test_analisar_com_cenario_completo_confirma_h4_e_mantem_a_cascata(tmp_path):
    ss_preso = lambda r: SS_PRESO.format(r=r, b=r * 100)
    saida = dict(ep=("10.0.0.5",))
    A = _dado({"rollout_s": 22.0, "rollout_ok": True, "restart_alvo_t": 15.0, "restart_alvo_abs": 1015.0},
              _steps(0, 300, 5.0, 0.9),
              [_col(1005.0), _col(1030.0, ss_preso(1), **saida), _col(1045.0, ss_preso(2), **saida)])
    B = _dado({"rollout_s": 18.0, "rollout_ok": True, "restart_alvo_t": 120.0, "restart_alvo_abs": 1120.0},
              _steps(0, 300, 0.02, 0.95),
              [_col(1110.0), _col(1140.0, SS_LIMPO, **saida), _col(1155.0, SS_LIMPO, **saida)])

    def cdado(rollout):
        cols = [_col(1030.0), _col(1060.0, ss_preso(1), **saida)]
        for app in ("frontend", "checkoutservice"):
            cols.append(_col(1100.0, SS_LIMPO, app=app, **saida))
        cols[2]["ss"].update(cols[3]["ss"]); cols.pop(3)
        return _dado({"rollout_s": rollout, "rollout_ok": True, "clientes_t": 85.0},
                     _steps(0, 400, lambda t: 5.0 if t < 140 else 0.15, lambda t: 0.9 if t < 140 else 0.0), cols)
    D = _dado({"rollout_s": 30.0, "rollout_ok": True, "restart_alvo_t": 425.0, "restart_alvo_abs": 1425.0}, _steps(0, 900, 0.15), [])
    for e, d in (("A", A), ("B", B), ("C1", cdado(25.0)), ("C2", cdado(20.0)), ("D", D)):
        _grava(tmp_path, e, d)
    r = f0.analisar(tmp_path)
    assert r["clientes_apos_s"]["valor"] == 40               # 30 + 10 = 40
    assert r["cascata"]["fica"] is True
    assert r["H4"]["resultado"] == "confirmada", r["H4"]
    assert r["rollout_s"] == {"A": 22.0, "B": 18.0, "C1": 25.0, "C2": 20.0, "D": 30.0}


def test_analisar_ignora_execucao_sem_dado_e_nao_escreve_no_config(tmp_path):
    antes = (f0.ROOT / "config" / "campaign.yaml").read_bytes()
    antes_sc = (f0.ROOT / "scenarios" / "s1_latencia_productcatalog.yaml").read_bytes()
    p = tmp_path / "diag_C1"
    p.mkdir()
    (p / "meta.json").write_text(json.dumps({"status": "falha_execucao"}))
    r = f0.analisar(tmp_path)
    assert r["execucoes_com_dado"] == [] and not r["cascata"]["fica"]
    assert (f0.ROOT / "config" / "campaign.yaml").read_bytes() == antes
    assert (f0.ROOT / "scenarios" / "s1_latencia_productcatalog.yaml").read_bytes() == antes_sc
