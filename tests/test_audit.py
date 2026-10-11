import json

from mecade.audit import AuditLog, verify


def test_chain_verifies_and_detects_tampering(tmp_path):
    p = tmp_path / "a.jsonl"
    log = AuditLog(p)
    for i in range(20):
        log.record({"event": "STEP", "i": i})
    info = log.close()
    assert info["records"] == 20 and info["enqueue_p95_ms"] is not None
    assert verify(p)[0]
    lines = p.read_text().splitlines()
    rec = json.loads(lines[5]); rec["event"]["i"] = 999
    lines[5] = json.dumps(rec)
    p.write_text("\n".join(lines) + "\n")
    ok, n, msg = verify(p)
    assert not ok and n == 5


def test_disabled_log_is_noop(tmp_path):
    log = AuditLog(tmp_path / "x.jsonl", enabled=False)
    log.record({"e": 1})
    assert log.close() == {"enabled": False}
