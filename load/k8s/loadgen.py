"""Gerador de carga do MECADE para o Online Boutique (Camada 2, Cenário Base).

Optei por não usar o loadgenerator que vem com o Online Boutique (Locust) por três motivos:
  * Malha aberta: as chegadas seguem um processo de Poisson a uma taxa fixa (RPS), sem depender
    da latência do sistema. Geradores em malha fechada sofrem de "coordinated omission" e
    subestimam a latência justamente durante as falhas, que é o que me interessa medir.
  * Semente fixa, para a sequência de operações ser reprodutível.
  * Métricas Prometheus próprias, do ponto de vista do cliente:
      mecade_loadgen_request_duration_seconds{op}       (histograma)
      mecade_loadgen_requests_total{op, outcome}        (ok, error ou timeout)
      mecade_loadgen_dropped_total                      (descartes pelo limite de concorrência)

A mistura de operações copia os pesos do locustfile oficial do Online Boutique:
index 1, setCurrency 2, browseProduct 10, addToCart 2, viewCart 3, checkout 1.
"""
from __future__ import annotations

import asyncio
import os
import random
import time

import httpx
from prometheus_client import Counter, Gauge, Histogram, start_http_server

FRONTEND = os.environ.get("FRONTEND_ADDR", "http://frontend.boutique.svc.cluster.local")
RPS = float(os.environ.get("RPS", "20"))
TIMEOUT_S = float(os.environ.get("TIMEOUT_S", "3"))
SEED = int(os.environ.get("SEED", "20261011"))
SESSIONS = int(os.environ.get("SESSIONS", "20"))
MAX_INFLIGHT = int(os.environ.get("MAX_INFLIGHT", "200"))
METRICS_PORT = int(os.environ.get("METRICS_PORT", "9100"))

PRODUCTS = ["0PUK6V6EV0", "1YMWWN1N4O", "2ZYFJ3GM2N", "66VCHSJNUP", "6E92ZMYYFZ",
            "9SIQT8TOJO", "L9ECAV7KIM", "LS4PSXUNUM", "OLJCESPC7Z"]
CURRENCIES = ["EUR", "USD", "JPY", "CAD", "GBP", "TRY"]
WEIGHTS = {"index": 1, "setCurrency": 2, "browseProduct": 10, "addToCart": 2, "viewCart": 3, "checkout": 1}

BUCKETS = (0.005, 0.01, 0.025, 0.05, 0.075, 0.1, 0.15, 0.25, 0.4, 0.6, 0.8, 1.0, 1.5, 2.0, 3.0, 5.0)
LAT = Histogram("mecade_loadgen_request_duration_seconds", "Latência percebida pelo cliente", ["op"], buckets=BUCKETS)
REQ = Counter("mecade_loadgen_requests_total", "Requisições por desfecho", ["op", "outcome"])
DROP = Counter("mecade_loadgen_dropped_total", "Requisições descartadas pelo limite de concorrência")
INFLIGHT = Gauge("mecade_loadgen_inflight", "Requisições em voo")
CFG = Gauge("mecade_loadgen_config", "Configuração ativa", ["key"])


async def _call(client: httpx.AsyncClient, op: str, method: str, path: str, data: dict | None = None) -> None:
    t0 = time.perf_counter()
    outcome = "ok"
    try:
        r = await client.request(method, FRONTEND + path, data=data)
        if r.status_code >= 500:
            outcome = "error"
    except httpx.TimeoutException:
        outcome = "timeout"
    except httpx.HTTPError:
        outcome = "error"
    finally:
        LAT.labels(op).observe(time.perf_counter() - t0)
        REQ.labels(op, outcome).inc()


async def run_op(client: httpx.AsyncClient, op: str, rng: random.Random) -> None:
    if op == "index":
        await _call(client, op, "GET", "/")
    elif op == "setCurrency":
        await _call(client, op, "POST", "/setCurrency", {"currency_code": rng.choice(CURRENCIES)})
    elif op == "browseProduct":
        await _call(client, op, "GET", "/product/" + rng.choice(PRODUCTS))
    elif op == "viewCart":
        await _call(client, op, "GET", "/cart")
    elif op in ("addToCart", "checkout"):
        product = rng.choice(PRODUCTS)
        await _call(client, op, "GET", "/product/" + product)
        await _call(client, op, "POST", "/cart", {"product_id": product, "quantity": str(rng.randint(1, 10))})
        if op == "checkout":
            await _call(client, op, "POST", "/cart/checkout", {
                "email": "mvc@example.org", "street_address": "Praca Marechal Eduardo Gomes 50",
                "zip_code": "12228900", "city": "Sao Jose dos Campos", "state": "SP", "country": "Brazil",
                "credit_card_number": "4432801561520454", "credit_card_expiration_month": str(rng.randint(1, 12)),
                "credit_card_expiration_year": "2039", "credit_card_cvv": "672"})


async def main() -> None:
    for k, v in {"rps": RPS, "timeout_s": TIMEOUT_S, "seed": SEED, "sessions": SESSIONS}.items():
        CFG.labels(k).set(v)
    start_http_server(METRICS_PORT)
    rng = random.Random(SEED)
    ops, weights = zip(*WEIGHTS.items())
    limits = httpx.Limits(max_connections=MAX_INFLIGHT)
    clients = [httpx.AsyncClient(timeout=TIMEOUT_S, limits=limits, follow_redirects=True) for _ in range(SESSIONS)]
    for c in clients:  # abre a sessão (cookie shop_session-id) em cada cliente
        try:
            await c.get(FRONTEND + "/")
        except httpx.HTTPError:
            pass
    sem = asyncio.Semaphore(MAX_INFLIGHT)

    async def guarded(client: httpx.AsyncClient, op: str, op_rng: random.Random) -> None:
        INFLIGHT.inc()
        try:
            await run_op(client, op, op_rng)
        finally:
            INFLIGHT.dec()
            sem.release()

    next_t = time.perf_counter()
    while True:
        next_t += rng.expovariate(RPS)  # chegadas de Poisson com taxa RPS
        delay = next_t - time.perf_counter()
        if delay > 0:
            await asyncio.sleep(delay)
        op = rng.choices(ops, weights=weights)[0]
        client = clients[rng.randrange(SESSIONS)]
        op_rng = random.Random(rng.getrandbits(32))
        if sem.locked():
            DROP.inc()
            continue
        await sem.acquire()
        asyncio.create_task(guarded(client, op, op_rng))


if __name__ == "__main__":
    asyncio.run(main())
