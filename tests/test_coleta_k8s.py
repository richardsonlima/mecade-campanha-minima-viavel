"""Coleta passiva de Kubernetes (PROTOCOLO_C3, 8.1 item 2), com um `kubectl` falso."""
import json

from mecade.coleta_k8s import ColetorK8s, ips_endpoints, resumo_pods


def _pod(nome, app, ip, restarts=0, deleting=False):
    md = {"name": nome, "labels": {"app": app}, "creationTimestamp": "2026-11-15T10:00:00Z"}
    if deleting:
        md["deletionTimestamp"] = "2026-11-15T10:05:00Z"
    return {"metadata": md, "status": {"podIP": ip, "phase": "Running",
                                       "containerStatuses": [{"ready": True, "restartCount": restarts}]}}


class FalsoKubectl:
    def __init__(self):
        self.chamadas = []
        self.pods = [_pod("frontend-1", "frontend", "10.0.0.1"), _pod("productcatalogservice-1", "productcatalogservice", "10.0.0.9", 2)]
        self.eventos = [{"metadata": {"uid": "u1"}, "type": "Normal", "reason": "Killing", "message": "m", "count": 1,
                         "involvedObject": {"kind": "Pod", "name": "x"}, "lastTimestamp": "t1"}]
        self.falha_endpoints = False
        self.efemeros = {}   # pod -> (spec.ephemeralContainers, status.ephemeralContainerStatuses)

    def __call__(self, *args, **kw):
        self.chamadas.append(args)
        if "pods" in args:
            return json.dumps({"items": self.pods})
        if "service" in args:
            return json.dumps({"spec": {"clusterIP": "10.8.0.50", "ports": [{"port": 3550}]}})
        if "pod" in args:
            spec, st = self.efemeros.get(args[args.index("pod") + 1], ([], []))
            return json.dumps({"spec": {"ephemeralContainers": spec}, "status": {"ephemeralContainerStatuses": st}})
        if "endpoints" in args:
            if self.falha_endpoints:
                raise RuntimeError("sem endpoints")
            return json.dumps({"subsets": [{"addresses": [{"ip": "10.0.0.9"}], "notReadyAddresses": [{"ip": "10.0.0.8"}]}]})
        if "events" in args:
            return json.dumps({"items": self.eventos})
        if "debug" in args:
            nome = next(a.split("=", 1)[1] for a in args if a.startswith("--container="))
            self.efemeros.setdefault(args[args.index("debug") + 1], ([], []))
            sp, st = self.efemeros[args[args.index("debug") + 1]]
            sp.append({"name": nome})
            st.append({"name": nome, "state": {"running": {}}})
            return ""
        if "exec" in args:
            return "State Recv-Q Send-Q Local:Port Peer:Port\nESTAB 0 0 10.0.0.1:1 10.0.0.9:3550\n"
        raise AssertionError(args)


def test_resumo_pods_e_endpoints():
    r = resumo_pods({"items": [_pod("b", "x", "1.1.1.1", 3, True), _pod("a", "x", "1.1.1.2")]})
    assert [p["nome"] for p in r] == ["a", "b"] and r[1]["restart_count"] == 3 and r[1]["removendo"] and r[0]["pronto"]
    assert ips_endpoints({"subsets": [{"addresses": [{"ip": "2"}, {"ip": "1"}], "notReadyAddresses": [{"ip": "3"}]}]}) == \
        {"prontos": ["1", "2"], "nao_prontos": ["3"]}
    assert ips_endpoints({}) == {"prontos": [], "nao_prontos": []}


def test_coleta_grava_pods_endpoints_e_eventos_sem_repetir(tmp_path):
    k = FalsoKubectl()
    c = ColetorK8s("boutique", "productcatalogservice", tmp_path, run=k, agora=lambda: 100.0)
    c.coletar()
    c.coletar()
    linhas = [json.loads(x) for x in (tmp_path / "k8s_coleta.jsonl").read_text().splitlines()]
    assert len(linhas) == 2 and linhas[0]["endpoints_alvo"]["prontos"] == ["10.0.0.9"]
    assert linhas[0]["pods"][1]["restart_count"] == 2
    ev = (tmp_path / "k8s_eventos.jsonl").read_text().splitlines()
    assert len(ev) == 1                                     # mesmo (uid, count): uma vez só
    k.eventos[0]["count"] = 2
    c.coletar()
    assert len((tmp_path / "k8s_eventos.jsonl").read_text().splitlines()) == 2


def test_erro_de_coleta_vira_registro_e_nao_excecao(tmp_path):
    k = FalsoKubectl()
    k.falha_endpoints = True
    c = ColetorK8s("boutique", "productcatalogservice", tmp_path, run=k, agora=lambda: 1.0)
    reg = c.coletar()
    assert "erro_endpoints" in reg and "pods" in reg


def test_ss_so_nos_clientes_e_contêiner_efemero_uma_vez_por_pod(tmp_path):
    k = FalsoKubectl()
    c = ColetorK8s("boutique", "productcatalogservice", tmp_path, clientes=("frontend",), ss=True, run=k,
                   agora=lambda: 1.0)
    r1, r2 = c.coletar(), c.coletar()
    assert list(r1["ss"]) == ["frontend-1"] and "ESTAB" in r2["ss"]["frontend-1"]["texto"]
    assert sum(1 for a in k.chamadas if "debug" in a) == 1
    assert sum(1 for a in k.chamadas if "exec" in a) == 2


def test_coleta_traz_o_clusterip_e_a_porta_do_servico_do_alvo(tmp_path):
    c = ColetorK8s("boutique", "productcatalogservice", tmp_path, run=FalsoKubectl(), agora=lambda: 1.0)
    assert c.coletar()["servico_alvo"] == {"cluster_ip": "10.8.0.50", "portas": [3550]}


def test_depurador_reaproveita_o_que_esta_rodando_e_cria_outro_se_terminou(tmp_path):
    k = FalsoKubectl()
    k.efemeros["frontend-1"] = ([{"name": "mecade-dbg"}], [{"name": "mecade-dbg", "state": {"running": {}}}])
    c = ColetorK8s("boutique", "x", tmp_path, clientes=("frontend",), ss=True, run=k, agora=lambda: 1.0)
    c.coletar()
    assert not any("debug" in a for a in k.chamadas)                      # já havia um rodando: reaproveitado
    assert any("--container=mecade-dbg" in a or "mecade-dbg" in a for a in k.chamadas if "exec" in a)
    # terminou: um coletor novo (processo reiniciado) cria com sufixo, sem repetir o nome
    k.efemeros["frontend-1"] = ([{"name": "mecade-dbg"}], [{"name": "mecade-dbg", "state": {"terminated": {}}}])
    c2 = ColetorK8s("boutique", "x", tmp_path / "o", clientes=("frontend",), ss=True, run=k, agora=lambda: 2.0)
    c2.coletar()
    debug = [a for a in k.chamadas if "debug" in a]
    assert len(debug) == 1 and "--container=mecade-dbg-2" in debug[0]
    assert "while true; do sleep 3600; done" in debug[0] and "7200" not in " ".join(debug[0])


def test_ss_de_pod_cliente_em_remocao_tambem_e_lido(tmp_path):
    k = FalsoKubectl()
    k.pods = [_pod("frontend-1", "frontend", "10.0.0.1", deleting=True)]
    c = ColetorK8s("boutique", "x", tmp_path, clientes=("frontend",), ss=True, run=k, agora=lambda: 1.0)
    r = c.coletar()
    assert r["ss"]["frontend-1"]["removendo"] is True and "texto" in r["ss"]["frontend-1"]


def test_exec_que_falha_nao_derruba_e_reavalia_o_depurador_na_proxima(tmp_path):
    k = FalsoKubectl()
    orig = k.__call__
    estado = {"n": 0}

    def quebra(*a, **kw):
        if "exec" in a and estado["n"] == 0:
            estado["n"] = 1
            raise RuntimeError("container terminated")
        return orig(*a, **kw)
    c = ColetorK8s("boutique", "x", tmp_path, clientes=("frontend",), ss=True, run=quebra, agora=lambda: 1.0)
    r1, r2 = c.coletar(), c.coletar()
    assert "erro" in r1["ss"]["frontend-1"] and "texto" in r2["ss"]["frontend-1"]


def test_arquivos_de_tentativa_anterior_sao_guardados_e_nao_misturados(tmp_path):
    (tmp_path / "k8s_coleta.jsonl").write_text('{"antigo": 1}\n')
    ColetorK8s("boutique", "x", tmp_path, run=FalsoKubectl(), agora=lambda: 5.0)
    assert not (tmp_path / "k8s_coleta.jsonl").exists()
    assert (tmp_path / "k8s_anteriores" / "5" / "k8s_coleta.jsonl").read_text() == '{"antigo": 1}\n'


def test_thread_para_no_prazo_e_na_parada(tmp_path):
    k = FalsoKubectl()
    c = ColetorK8s("boutique", "x", tmp_path, run=k, intervalo=0.01)
    c.iniciar()
    import time
    time.sleep(0.15)
    c.parar()
    n = len((tmp_path / "k8s_coleta.jsonl").read_text().splitlines())
    assert n >= 2
    time.sleep(0.05)
    assert len((tmp_path / "k8s_coleta.jsonl").read_text().splitlines()) == n

