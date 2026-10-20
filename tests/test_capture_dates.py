import pandas as pd

from main import write_captures
from hedonic.evidence import EvidenceLog
from hedonic.synthetic import simulate_panel


def test_simulated_capture_dates_match_booking_lead_time(tmp_path):
    frame = simulate_panel()
    log = EvidenceLog(tmp_path / "ledger.jsonl", tmp_path)
    write_captures(frame, tmp_path, log, limit=3)
    for record in log.records():
        stay = pd.Timestamp(record["stay_date"], tz="UTC")
        capture = pd.Timestamp(record["accessed_at_utc"])
        assert (stay - capture).days == record["lead_days"]
        assert record["source"] == "synthetic_ota"
