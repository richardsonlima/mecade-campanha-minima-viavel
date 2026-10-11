"""Executa o analysis/analysis.ipynb no próprio arquivo, sem precisar do Jupyter instalado.

  python analysis/run_notebook.py
"""
from pathlib import Path

import nbclient
import nbformat

p = Path(__file__).with_name("analysis.ipynb")
nb = nbformat.read(p, as_version=4)
nbclient.NotebookClient(nb, timeout=600, kernel_name="python3",
                        resources={"metadata": {"path": str(p.parent)}}).execute()
nbformat.write(nb, p)
print(f"{p} executado; figuras em analysis/figures/ e métricas em analysis/metricas_por_replica.csv")
