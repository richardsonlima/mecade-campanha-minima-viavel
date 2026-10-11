"""MECADE, Campanha Mínima Viável.

Implementação de referência das partes do modelo que a campanha exercita:
  axioms.py   Camada 3, axiomas ALERT, LIMIT e BLOCK (Listagem 3.1 da dissertação)
  reactive.py braço baseline, com alerta convencional e runbook com atraso fixo
  audit.py    Camada 6 no perfil mínimo, trilha JSONL com hash encadeado e escrita assíncrona
  runner.py   execução de uma réplica (Camadas 1, 2, 4 e 5 da campanha)
"""
__version__ = "0.1.0"
