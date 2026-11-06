"""A conta de vCPUs do create-cluster.sh, com um gcloud falso no PATH (não toca na nuvem)."""
import json
import os
import stat
import subprocess
from pathlib import Path

import pytest

from mecade.config import ROOT

VCPUS = {"e2-standard-2": 2, "e2-standard-4": 4}


def _run(tmp_path: Path, machine: str, region_quota: int, global_quota: int):
    region = json.dumps({"quotas": [{"metric": "CPUS", "limit": float(region_quota)}]})
    project = json.dumps({"quotas": [{"metric": "CPUS_ALL_REGIONS", "limit": float(global_quota)}]})
    (tmp_path / "region.json").write_text(region)
    (tmp_path / "project.json").write_text(project)
    fake = tmp_path / "gcloud"
    fake.write_text(f"""#!/usr/bin/env bash
case "$*" in
  *machine-types*) echo {VCPUS[machine]} ;;
  *"regions describe"*) cat {tmp_path}/region.json ;;
  *project-info*) cat {tmp_path}/project.json ;;
  *"clusters create"*) echo CRIOU-CLUSTER ;;
esac
""")
    fake.chmod(fake.stat().st_mode | stat.S_IEXEC)
    plugin = tmp_path / "gke-gcloud-auth-plugin"
    plugin.write_text("#!/usr/bin/env bash\n")
    plugin.chmod(plugin.stat().st_mode | stat.S_IEXEC)
    env = {**os.environ, "PATH": f"{tmp_path}:{os.environ['PATH']}", "PROJECT": "teste",
           "MACHINE": machine, "QUOTA_CHECK_ONLY": "1"}
    return subprocess.run([str(ROOT / "infra/gke/create-cluster.sh")], env=env, cwd=tmp_path,
                          capture_output=True, text=True)


def test_e2_standard_2_cabe_em_8_vcpus(tmp_path):
    p = _run(tmp_path, "e2-standard-2", 8, 8)
    assert p.returncode == 0, p.stdout + p.stderr
    assert "preciso de 8" in p.stdout


def test_e2_standard_4_nao_cabe_em_8_vcpus(tmp_path):
    p = _run(tmp_path, "e2-standard-4", 8, 8)
    assert p.returncode == 1
    assert "preciso de 14" in p.stdout


@pytest.mark.parametrize("region,glob", [(32, 8), (8, 32)])
def test_vale_a_menor_das_duas_cotas(tmp_path, region, glob):
    assert _run(tmp_path, "e2-standard-4", region, glob).returncode == 1
