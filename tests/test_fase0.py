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
        self.erro_rollout = "error: timed out waiting for the condition (rollout travado)"

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
            raise RuntimeError(self.erro_rollout)
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


def test_rollout_que_estoura_entra_como_300s_marcado_e_a_execucao_segue(tmp_path):
    meta, _, _ = _roda("A", tmp_path, falha_rollout=True)
    # estourou o timeout: entra como 300 s (o corte leva a 60) e fica marcado
    assert meta["rollout_s"] == 300.0 and meta["rollout_ok"] is False and meta["rollout_estourou"] is True
    assert "travado" in meta["erro_rollout"]
    assert meta["rollout_erro"] is False
    assert any(e["event"] == "ROLLOUT_FALHOU" for e in meta["events"])


def test_erro_de_api_no_rollout_e_rollout_erro_e_nao_estouro(tmp_path, monkeypatch):
    monkeypatch.setattr(FalsoCluster, "wait_rollout", lambda self, d, timeout="300s": (_ for _ in ()).throw(
        RuntimeError("Unable to connect to the server")) if self.falha else setattr(self.clock, "t", self.clock.t + 17.0))
    meta, _, _ = _roda("A", tmp_path, falha_rollout=True)
    assert meta["rollout_s"] == 300.0 and meta["rollout_ok"] is False
    assert meta["rollout_erro"] is True and meta["rollout_estourou"] is False


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
    assert f0.clientes_apos_s([300.0])["valor"] == 60            # rollout estourado (300 s) leva ao corte
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


CIP = "10.8.0.50"
T_R = 1040.0


def ss_txt(*conns):
    """conns: (local, estado, retrans_total, bytes_retrans). O peer é sempre o ClusterIP:3550."""
    out = "State Recv-Q Send-Q Local Address:Port Peer Address:Port\n"
    for local, estado, r, b in conns:
        out += f"{estado} 0 0 {local} {CIP}:3550\n\t cubic wscale:7,7 retrans:0/{r} bytes_retrans:{b}\n"
    return out


def col(t, ss=None, ep=("10.0.0.9",), pods=None, cip=CIP):
    """ss: {pod: (app, texto, removendo)}"""
    c = {"t_abs": t, "pods": pods or [{"nome": "pc-1", "app": "productcatalogservice", "ip": "10.0.0.9", "removendo": False}],
         "endpoints_alvo": {"prontos": list(ep), "nao_prontos": []}, "servico_alvo": {"cluster_ip": cip, "portas": [3550], "portas_pod": [3550]}}
    if ss:
        c["ss"] = {pod: {"app": a, "ip": "x", "removendo": rem, "texto": txt} for pod, (a, txt, rem) in ss.items()}
    return c


def dado(coleta, clientes_t=None, **meta):
    m = {"scenario": "s1_latencia_productcatalog", "alvo": "productcatalogservice", "M_base": {"p95": 0.1},
         "t_inject_abs": 1000.0, "restart_alvo_t": 40.0, "restart_alvo_abs": T_R, "clientes_t": clientes_t, **meta}
    return {"meta": m, "steps": [], "coleta": coleta}


F_ANTES = {"frontend-1": ("frontend", ss_txt(("10.0.0.1:41000", "ESTAB", 0, 0)), False)}


def test_parse_ss_le_estado_peer_e_retransmissoes():
    cs = f0.parse_ss(ss_txt(("10.0.0.1:41000", "ESTAB", 7, 1448), ("10.0.0.1:41002", "ESTAB", 1, 0)))
    assert [c["peer_ip"] for c in cs] == [CIP, CIP] and cs[0]["local"] == "10.0.0.1:41000"
    assert cs[0]["retrans_total"] == 7 and cs[0]["bytes_retrans"] == 1448
    assert f0.parse_ss("") == []


def test_tuplas_anteriores_so_do_clusterip_e_da_ultima_leitura_antes_do_restart():
    d = dado([col(1020.0, F_ANTES), col(1030.0, {"frontend-1": ("frontend", ss_txt(("10.0.0.1:41001", "ESTAB", 0, 0)), False)}),
              col(1050.0, F_ANTES)])
    assert f0._tuplas_anteriores(d) == {("frontend-1", "10.0.0.1:41001", f"{CIP}:3550"): "frontend"}
    assert f0._tuplas_anteriores(dado([col(1030.0, F_ANTES, cip=None)])) == {}   # sem ClusterIP coletado


def test_h4_condicao_1_tupla_segue_com_retransmissao_crescente_depois_de_sair_dos_endpoints():
    ep = ("10.0.0.5",)
    preso = [col(1030.0, F_ANTES),
             col(1050.0, {"frontend-1": ("frontend", ss_txt(("10.0.0.1:41000", "ESTAB", 1, 100)), False)}, ep),
             col(1065.0, {"frontend-1": ("frontend", ss_txt(("10.0.0.1:41000", "ESTAB", 2, 200)), False)}, ep)]
    assert f0.h4_condicao_1(dado(preso))["ok"] is True
    parado = [preso[0], preso[1], col(1065.0, preso[1]["ss"] and {"frontend-1": ("frontend", ss_txt(("10.0.0.1:41000", "ESTAB", 1, 100)), False)}, ep)]
    assert f0.h4_condicao_1(dado(parado))["ok"] is False
    sumiu = [preso[0], col(1050.0, {"frontend-1": ("frontend", ss_txt(("10.0.0.1:41999", "ESTAB", 0, 0)), False)}, ep)]
    assert f0.h4_condicao_1(dado(sumiu))["ok"] is False
    uma = [preso[0], preso[1]]
    assert f0.h4_condicao_1(dado(uma))["ok"] is None                       # só uma leitura da tupla
    ainda = [preso[0], col(1050.0, F_ANTES)]                               # pod antigo ainda nos endpoints
    assert f0.h4_condicao_1(dado(ainda))["ok"] is None
    assert f0.h4_condicao_1(dado([col(1030.0)]))["ok"] is None             # sem conexão anterior ao restart
    assert f0.h4_condicao_1(None)["ok"] is None


def test_h4_condicao_2_nenhuma_tupla_anterior_segue():
    ep = ("10.0.0.5",)
    limpo = [col(1030.0, F_ANTES), col(1050.0, {"frontend-1": ("frontend", ss_txt(("10.0.0.1:41777", "ESTAB", 0, 0)), False)}, ep)]
    assert f0.h4_condicao_2(dado(limpo))["ok"] is True                      # conexão nova (outra porta local) não conta
    segue = [col(1030.0, F_ANTES), col(1050.0, F_ANTES, ep)]
    r = f0.h4_condicao_2(dado(segue))
    assert r["ok"] is False and r["tuplas_que_seguem"][0][0] == "frontend-1"
    tw = [col(1030.0, F_ANTES), col(1050.0, {"frontend-1": ("frontend", ss_txt(("10.0.0.1:41000", "TIME-WAIT", 0, 0)), False)}, ep)]
    assert f0.h4_condicao_2(dado(tw))["ok"] is True
    sem_leitura = [col(1030.0, F_ANTES), col(1050.0, None, ep)]
    assert f0.h4_condicao_2(dado(sem_leitura))["ok"] is None


def _c(t, pod, app, txt, rem=False):
    return {pod: (app, txt, rem)}


TUP = ss_txt(("10.0.0.1:41000", "ESTAB", 0, 0))
LIMPO = ss_txt()
ANTES2 = {"frontend-1": ("frontend", TUP, False), "checkout-1": ("checkoutservice", ss_txt(("10.0.0.2:42000", "ESTAB", 0, 0)), False)}
T_CLI = 1085.0   # t_inject 1000 + clientes_t 85


def test_h4_condicao_3_le_o_pod_antigo_enquanto_termina():
    ok = [col(1030.0, ANTES2),
          col(1090.0, {"frontend-1": ("frontend", LIMPO, True), "checkout-1": ("checkoutservice", LIMPO, True)}),
          col(1105.0, {"frontend-1": ("frontend", LIMPO, True), "checkout-1": ("checkoutservice", LIMPO, True)})]
    r = f0.h4_condicao_3(dado(ok, clientes_t=85.0))
    assert r["ok"] is True and "por construção" in r["nota"]
    preso = ok[:2] + [col(1105.0, {"frontend-1": ("frontend", TUP, True), "checkout-1": ("checkoutservice", LIMPO, True)})]
    assert f0.h4_condicao_3(dado(preso, clientes_t=85.0))["ok"] is False


def test_h4_condicao_3_pod_antigo_que_some_antes_de_qualquer_leitura_e_sem_dado():
    so_novos = [col(1030.0, ANTES2), col(1110.0, {"frontend-2": ("frontend", LIMPO, False), "checkout-2": ("checkoutservice", LIMPO, False)})]
    r = f0.h4_condicao_3(dado(so_novos, clientes_t=85.0))
    assert r["ok"] is None and "sumiu antes de qualquer leitura" in r["motivo"]
    metade = [col(1030.0, ANTES2), col(1090.0, {"frontend-1": ("frontend", LIMPO, True)})]       # checkout sem leitura
    assert f0.h4_condicao_3(dado(metade, clientes_t=85.0))["ok"] is None
    # a tupla ainda presente na última leitura e sem leitura depois de 15 s: não dá para afirmar
    presa = [col(1030.0, ANTES2), col(1090.0, {"frontend-1": ("frontend", TUP, True), "checkout-1": ("checkoutservice", LIMPO, True)})]
    assert f0.h4_condicao_3(dado(presa, clientes_t=85.0))["ok"] is None
    assert f0.h4_condicao_3(dado(so_novos))["ok"] is None                                    # sem MITIGATION_CLIENTES


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


def test_analisar_sem_dados_nao_confirma_a_h4_e_diz_o_motivo(tmp_path):
    r = f0.analisar(tmp_path)
    assert r["clientes_apos_s"]["valor"] is None and not r["cascata"]["fica"]
    assert r["H4"]["resultado"] == "não confirmada" and "condição 1 sem dado (A)" in r["H4"]["motivos"]


def _cenario(tmp_path, preso_em_a=True, c2_sem_dado=False):
    ep = ("10.0.0.5",)
    cA = [col(1005.0, F_ANTES)] if False else None
    A = dado([col(1005.0, F_ANTES), col(1030.0, {"frontend-1": ("frontend", ss_txt(("10.0.0.1:41000", "ESTAB", 1, 100)), False)}, ep),
              col(1045.0, {"frontend-1": ("frontend", ss_txt(("10.0.0.1:41000", "ESTAB", 2 if preso_em_a else 1, 200 if preso_em_a else 100)), False)}, ep)],
             rollout_s=22.0, rollout_ok=True, restart_alvo_t=15.0, restart_alvo_abs=1015.0)
    A["steps"] = _steps(0, 300, 5.0, 0.9)
    B = dado([col(1110.0, F_ANTES), col(1140.0, {"frontend-1": ("frontend", LIMPO, False)}, ep)], rollout_s=18.0, rollout_ok=True,
             restart_alvo_t=120.0, restart_alvo_abs=1120.0)
    B["steps"] = _steps(0, 300, 0.02, 0.95)

    def C(rollout, sem_dado=False):
        novos = {"frontend-2": ("frontend", LIMPO, False), "checkout-2": ("checkoutservice", LIMPO, False)}
        velhos = {"frontend-1": ("frontend", LIMPO, True), "checkout-1": ("checkoutservice", LIMPO, True)}
        cols = [col(1030.0, ANTES2), col(1090.0, novos if sem_dado else velhos), col(1105.0, novos if sem_dado else velhos)]
        d = dado(cols, clientes_t=85.0, rollout_s=rollout, rollout_ok=True)
        d["steps"] = _steps(0, 400, lambda t: 5.0 if t < 140 else 0.15, lambda t: 0.9 if t < 140 else 0.0)
        return d
    D = dado([], rollout_s=30.0, rollout_ok=True, restart_alvo_t=425.0, restart_alvo_abs=1425.0)
    D["steps"] = _steps(0, 900, 0.15)
    for e, d in (("A", A), ("B", B), ("C1", C(25.0)), ("C2", C(20.0, c2_sem_dado)), ("D", D)):
        _grava(tmp_path, e, d)


def test_analisar_com_cenario_completo_confirma_h4_e_mantem_a_cascata(tmp_path):
    _cenario(tmp_path)
    r = f0.analisar(tmp_path)
    assert r["clientes_apos_s"]["valor"] == 40               # 30 + 10 = 40
    assert r["cascata"]["fica"] is True
    assert r["H4"]["resultado"] == "confirmada" and r["H4"]["motivos"] == [], r["H4"]
    assert r["rollout_s"] == {"A": 22.0, "B": 18.0, "C1": 25.0, "C2": 20.0, "D": 30.0}


def test_analisar_condicao_sem_dado_deixa_a_h4_nao_confirmada(tmp_path):
    _cenario(tmp_path, c2_sem_dado=True)
    h4 = f0.analisar(tmp_path)["H4"]
    assert h4["resultado"] == "não confirmada" and h4["motivos"] == ["condição 3 sem dado (C2)"]


def test_analisar_condicao_nao_satisfeita_tambem_nao_confirma(tmp_path):
    _cenario(tmp_path, preso_em_a=False)
    h4 = f0.analisar(tmp_path)["H4"]
    assert h4["resultado"] == "não confirmada" and h4["motivos"] == ["condição 1 não satisfeita (A)"]


def test_rollout_estourado_entra_na_regra_do_clientes_apos_s_e_fica_marcado(tmp_path):
    _cenario(tmp_path)
    m = json.loads((tmp_path / "diag_B" / "meta.json").read_text())
    m.update(rollout_s=300.0, rollout_ok=False, rollout_estourou=True)
    (tmp_path / "diag_B" / "meta.json").write_text(json.dumps(m))
    r = f0.analisar(tmp_path)
    assert r["clientes_apos_s"]["valor"] == 60 and r["clientes_apos_s"]["cortado"]
    assert r["clientes_apos_s"]["estouraram_o_timeout"] == ["B"]


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


# ------------------------------------------------------------------------------------------ reexecução e escala


def _fab_ok(tmp_path):
    camp, sc = load_campaign(), load_scenario(f0.CENARIO)

    def fabrica():
        clock = VirtualClock()
        c = FalsoCluster(clock)
        return dict(scenario=sc, campaign=camp, prom=c, kube=c, clock=clock, sincrono=True)
    return fabrica


def test_reexecucao_pula_execucao_completa_e_nao_sobrescreve_meta(tmp_path):
    f0.executar_com_tentativas("A", fabrica=_fab_ok(tmp_path), out_root=tmp_path, settle_s=0, sleep=lambda s: None, log=lambda *_: None)
    antes = (tmp_path / "diag_A" / "meta.json").read_bytes()
    chamou = []
    meta = f0.executar_com_tentativas("A", fabrica=lambda: chamou.append(1) or {}, out_root=tmp_path, settle_s=0,
                                      sleep=lambda s: None, log=lambda *_: None)
    assert meta["status"] == "complete" and not chamou and (tmp_path / "diag_A" / "meta.json").read_bytes() == antes


def test_so_contam_tentativas_que_terminaram_em_falha(tmp_path):
    pasta = tmp_path / "diag_A"
    pasta.mkdir()
    (pasta / "tentativas.jsonl").write_text("\n".join(json.dumps(x) for x in (
        {"tentativa": 1, "evento": "inicio"}, {"tentativa": 1, "evento": "falhou"},
        {"tentativa": 2, "evento": "inicio"})) + "\n")     # a 2 foi interrompida: não conta
    n = {"v": 0}

    def fab():
        n["v"] += 1
        raise RuntimeError("x")
    f0.executar_com_tentativas("A", fabrica=fab, out_root=tmp_path, settle_s=0, sleep=lambda s: None, log=lambda *_: None)
    assert n["v"] == 2        # 1 falha anterior + 2 novas = 3


def test_arquivo_de_tentativa_anterior_nao_e_sobrescrito_no_arquivamento(tmp_path):
    pasta = tmp_path / "diag_A"
    (pasta / "tentativas" / "t1").mkdir(parents=True)
    (pasta / "tentativas" / "t1" / "meta.json").write_text("velho")
    (pasta / "k8s_coleta.jsonl").write_text("novo")
    f0._arquivar_tentativa(pasta)
    assert (pasta / "tentativas" / "t1" / "meta.json").read_text() == "velho"
    assert (pasta / "tentativas" / "t2" / "k8s_coleta.jsonl").read_text() == "novo"


def test_make_fase0_escala_a_zero_por_padrao_e_nao_escala_com_a_flag():
    chamadas, logs = [], []
    assert f0.escalar_ao_fim(True, logs.append, escalar=lambda: chamadas.append(1)) is True and chamadas == [1]
    assert f0.escalar_ao_fim(False, logs.append, escalar=lambda: chamadas.append(2)) is False and chamadas == [1]

    def quebra():
        raise RuntimeError("gcloud fora")
    assert f0.escalar_ao_fim(True, logs.append, escalar=quebra) is False and any("não consegui" in m for m in logs)
    mk = (f0.ROOT / "Makefile").read_text()
    assert "NAO_ESCALAR" in mk and "--nao-escalar" in mk


# ------------------------------------------------------------------ peer: ClusterIP ou IP do pod antigo, e meta


def test_peer_casa_com_ip_do_pod_antigo_e_o_meta_registra_qual_casou():
    pod_peer = "State Recv-Q Send-Q Local Address:Port Peer Address:Port\nESTAB 0 0 10.0.0.1:41000 10.0.0.9:3550\n\t cubic retrans:0/0 bytes_retrans:0\n"
    d_pod = dado([col(1030.0, {"frontend-1": ("frontend", pod_peer, False)})])
    assert f0._tuplas_anteriores(d_pod) == {("frontend-1", "10.0.0.1:41000", "10.0.0.9:3550"): "frontend"}
    assert f0.datapath_casado(d_pod) == {"casou": "pod_ip", "conexoes": {"pod_ip": 1}}
    d_cip = dado([col(1030.0, F_ANTES)])
    assert f0.datapath_casado(d_cip) == {"casou": "clusterip", "conexoes": {"clusterip": 1}}
    d_dois = dado([col(1030.0, {"frontend-1": ("frontend", pod_peer + F_ANTES["frontend-1"][1].split("\n", 1)[1], False)})])
    assert f0.datapath_casado(d_dois)["casou"] == "ambos"
    assert f0.datapath_casado(dado([col(1030.0)]))["casou"] == "nenhum"
    # porta errada no pod antigo não casa
    outra = pod_peer.replace("10.0.0.9:3550", "10.0.0.9:9999")
    assert f0._tuplas_anteriores(dado([col(1030.0, {"frontend-1": ("frontend", outra, False)})])) == {}


def test_leitura_densa_sem_endpoints_nao_quebra_a_analise():
    densa = {"t_abs": 1100.0, "denso": True, "pods": [], "ss": {"frontend-1": {"app": "frontend", "ip": "x", "removendo": True, "texto": ss_txt()}}}
    d = dado([col(1030.0, ANTES2), col(1090.0, {"frontend-1": ("frontend", LIMPO, True), "checkout-1": ("checkoutservice", LIMPO, True)}), densa],
             clientes_t=85.0)
    assert f0.h4_condicao_1(d)["ok"] is None and f0.h4_condicao_2(d)["ok"] in (True, None)
    assert f0.h4_condicao_3(d)["ok"] is not False


def test_c1_c2_d_pedem_amostragem_densa_na_mitigacao_dos_clientes(tmp_path):
    chamadas = []

    class Col:
        def iniciar(self): pass
        def amostrar_ss_denso(self, dur, inter): chamadas.append((dur, inter))
        def parar(self): pass
    for e in ("A", "C1"):
        camp, sc = load_campaign(), load_scenario(f0.CENARIO)
        clock = VirtualClock()
        c = FalsoCluster(clock)
        f0.executar(e, scenario=sc, campaign=camp, prom=c, kube=c, clock=clock, out_root=tmp_path / e, sincrono=True,
                    tipos_de_no=lambda: {"e2-standard-2": 3}, log=lambda *_: None, coletor=Col())
        assert chamadas == ([] if e == "A" else [(30.0, 3.0)])
