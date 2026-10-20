import json

import pytest

from hedonic.evidence import EvidenceLog, verify_log


def _log_three(tmp_path):
    root = tmp_path / "ev"
    (root / "captures").mkdir(parents=True)
    log = EvidenceLog(root / "evidence_log.jsonl", root)
    for i in range(3):
        cap = root / "captures" / f"OBS{i}.html"
        cap.write_text(f"<p>EUR {100 + i}.00</p>")
        log.append(cap, obs_id=f"OBS{i}", property_id="P001", source="synthetic_ota",
                   url=f"https://example.invalid/p1?d={i}", stay_date="2025-07-04", lead_days=30,
                   capture_method="saved_html", price_displayed=100.0 + i, currency="EUR",
                   collector="test", accessed_at_utc="2026-10-20T09:00:00Z")
    return root, log


def test_clean_ledger_verifies(tmp_path):
    root, log = _log_three(tmp_path)
    res = verify_log(log.log_path, root)
    assert res == {"records": 3, "problems": [], "ok": True}
    recs = log.records()
    assert recs[1]["prev_record_sha256"] == recs[0]["record_sha256"]
    assert len(recs[0]["capture_sha256"]) == 64


def test_changed_capture_is_detected(tmp_path):
    root, log = _log_three(tmp_path)
    (root / "captures" / "OBS1.html").write_text("<p>EUR 80.00</p>")
    res = verify_log(log.log_path, root)
    assert not res["ok"] and "changed since collection" in res["problems"][0]


def test_edited_record_is_detected(tmp_path):
    root, log = _log_three(tmp_path)
    lines = log.log_path.read_text().splitlines()
    rec = json.loads(lines[2])
    rec["price_displayed"] = 50.0
    lines[2] = json.dumps(rec, sort_keys=True)
    log.log_path.write_text("\n".join(lines) + "\n")
    assert any("edited after logging" in p for p in verify_log(log.log_path, root)["problems"])


def test_deleted_record_breaks_chain(tmp_path):
    root, log = _log_three(tmp_path)
    lines = log.log_path.read_text().splitlines()
    log.log_path.write_text(lines[0] + "\n" + lines[2] + "\n")
    assert any("chain broken" in p for p in verify_log(log.log_path, root)["problems"])


def test_unknown_capture_method_rejected(tmp_path):
    root, log = _log_three(tmp_path)
    with pytest.raises(ValueError):
        log.append(root / "captures" / "OBS0.html", obs_id="X", property_id="P", source="s", url="u",
                   stay_date="d", lead_days=1, capture_method="memory", price_displayed=1.0,
                   currency="EUR", collector="c")
