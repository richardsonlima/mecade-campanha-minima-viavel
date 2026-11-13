# Pré-registro da campanha 2 (`mvc-2026-11-c2`)

Escrevi este protocolo em 13/11/2026, depois de fechar a campanha 1 (tag `mvc-2026-11-final`) e antes de
qualquer execução da campanha 2. Ele corresponde à Seção 4.4.3 da v0.9 da dissertação ("Pré-registro da
Campanha 2"). Vale o `docs/PROTOCOLO.md` em tudo o que este documento não muda.

## 1. Pergunta

A campanha 1 testou o MECADE com uma tolerância equivalente à do baseline: a condição (b) da regra de B fez
o orçamento acomodar 300 s de falha, e o BLOCK saiu depois do RTO em s1 e s3 e não saiu em s2. A campanha 2
é confirmatória e testa o MECADE em modo proteção: com B definido só pela margem de ruído, o MECADE reduz o
tempo de exposição ao incidente (TTR) e cumpre o RTO mais vezes que a regra reativa?

As hipóteses são as mesmas H1, H2 e H3 da campanha 1. A campanha 2 não substitui a campanha 1: as duas
entram na dissertação, a 1 como resultado principal e a 2 como confirmação.

## 2. O que fica igual

- Sistema-alvo, versões (`versions.env`), cluster GKE com nós sob demanda e controlador fora do cluster.
- Cenários s1, s2, s3 e o controle c0 (`scenarios/*.yaml`), sem mudança de registro. RTO de 180 s nos três,
  como está no registro de cenário (Camada 1). Não mudei o RTO.
- Braço baseline (regra reativa e atraso do runbook), linha do tempo de cada execução e período de 5 s.
- 10 execuções por cenário e braço e 10 controles, 70 no total. A ordem é sorteada com a semente nova
  `20261113`.
- `k` = 2 de 3 sinais, agregação `max`, pisos M_min.
- Regra de veredito, McNemar exato para proporções, Holm por família como análise secundária, "≤" nos
  limiares (decisões de 12/11 no `docs/PROTOCOLO.md`, Seção 4).
- Limite de 10% de perdidas, regra das 3 falhas e tratamento das censuradas.

## 3. Fase 1: calibração

Plano de calibração separado do oficial (`make plan-calibracao`, prefixo `cal1_`, semente própria):
**10 controles** e 1 par por cenário. Os pares só conferem o pipeline e não entram em nenhuma regra.
Nenhum dado da campanha 1 (calibração ou oficial) entra nesta calibração.

As regras são as da campanha 1, com duas mudanças, e ficam em `analysis/calibrate.py` e na seção
`calibracao` do `config/campaign.yaml`:

| Parâmetro | Regra |
|---|---|
| d_off = deadband | P99 de D_agr nos 10 controles, arredondado para cima na primeira casa |
| d_on | d_off + 0,2 |
| tau_dwell | 15 s; sobe de 5 em 5 até 30 s se houver ALERT espúrio nos controles. **Mudança:** se nenhum valor até 30 s zerar o ALERT espúrio, fica 30 s e a contagem vai para o relatório, sem parar a campanha |
| B | **Mudança:** só a condição (a), B = 2 × o maior I dos controles, arredondado para cima. A condição (b), do piloto de s1, sai |

Por que a condição (b) sai: no Cap. 3 o Chaos Budget é o desvio acumulado que o sistema tolera antes que a
exposição deixe de ser aceitável, um limite de proteção definido pelo estado estacionário. A condição (b)
amarrava B à duração da falha no piloto de s1, e com isso à janela de 300 s da regra reativa. A margem de 2×
sobre o ruído é a mesma condição (a) já pré-registrada na campanha 1; não escolhi outra margem.

O que não usei para definir a regra: a simulação offline sobre as séries da campanha 1 (tempo até esgotar B
com outros valores de B, na análise de sensibilidade do Cap. 5 da v0.9). Ela é descritiva e não fixou nenhum
valor. O valor de B sai da calibração da campanha 2, com os controles da campanha 2.

Se a regra não tiver solução (B = 0, sem desvio acima da zona morta nos controles), paro e registro.

## 4. Critérios de aceitação (Tabela 4.7 da v0.9)

| H | Critério | Componentes que decidem | Mudança em relação à campanha 1 |
|---|---|---|---|
| H2 | Recuperação | `TTR_capped` menor; `rto_ok_ttr` maior (TTR ≤ RTO, contado da injeção), McNemar exato | MTTR passa a descritivo; RTO comparado ao TTR |
| H2 | Convergência | `RRIndex_run` maior | nenhuma; `log10_V` reportado ao lado |
| H2 | Classificação | nenhuma: descritiva | sai do mapa de critérios |
| H1 | Detecção e estabilidade | `TTD_capped`, `area_incidente`, `p95_std`, `p99_std` menores | nenhuma |
| H1 | Falsos bloqueios | taxa ≤ 0,1 | nenhuma |
| H3 | Overhead da auditoria | Δ_audit,p95 ≤ 5 ms e Δcpu ≤ 8% | nenhuma |

Classificação (descritiva): degradada quando D_agr fica acima de d_on por tau_dwell seguidos
(`axioms.envelope: d_on_tau`), crítica quando I > B. Reporto a proporção por classe, cenário e braço.

Também reporto, sem critério: MTTR, I_max/B, log10 V̄, TSR, se houve BLOCK em s2 e a taxa de ALERT nos
controles. Uma taxa de falsos bloqueios acima do limiar é um resultado possível da regra nova de B e entra
como resultado, não como desvio.

## 5. Ordem dos passos

1. Commit deste protocolo, do config e do código no branch `campanha-2`; tag anotada
   `mvc-2026-11-c2-prereg`; push do branch e da tag. Só tag, sem release.
2. Na VM, checkout limpo do branch numa pasta própria, separada da pasta da campanha 1.
3. Calibração (16 execuções), `make calibrar`, congelamento dos valores no config, commit, tag
   `mvc-2026-11-c2-calibracao` e push, antes da primeira execução oficial.
4. 70 execuções oficiais, backup em três cópias (VM, bucket em `oficial-c2/` e `calibracao-c2/`, local).
5. Análise, `RESULTADOS_CAMPANHA.md` da campanha 2, tag `mvc-2026-11-c2-final`, `make evidencias ESTRITO=1`
   e conferência das três cópias.

## 6. Dados da campanha 1 neste branch

O branch `campanha-2` sai do `main` depois da tag `mvc-2026-11-final` e não traz os dados da campanha 1, para
que nenhum controle da campanha 1 entre na calibração da campanha 2 e o manifesto de evidências cubra só a
campanha 2. Os dados da campanha 1 ficam no `main` e na tag `mvc-2026-11-final`, com manifesto
`5d24630b37a99867070b1d151c2e4ff06712e4fff459e551b61ec30c0aed391b`. Os resultados ficam em
`docs/RESULTADOS_CAMPANHA_1.md`.
