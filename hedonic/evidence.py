"""Evidence log: one tamper-evident record per captured price quote.

Each record ties a dataset row (obs_id) to the exact bytes that were captured
(screenshot PNG, saved HTML, or raw API JSON), the URL, and the UTC access time.
The SHA-256 checks each capture against its recorded digest. The chain detects
inconsistent edits and interior deletions or reordering. Tail truncation and
a fully recomputed chain require an independently trusted terminal digest and
record count; this demo does not implement that external trust anchor.
"""
from __future__ import annotations

import hashlib
import json
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path

GENESIS = "0" * 64

REQUIRED_FIELDS = (
    "obs_id", "property_id", "source", "url", "accessed_at_utc", "stay_date",
    "lead_days", "capture_method", "capture_path", "capture_sha256", "capture_bytes",
    "price_displayed", "currency", "collector", "prev_record_sha256", "record_sha256",
)
CAPTURE_METHODS = {"screenshot_png", "saved_html", "api_json", "pdf_print"}


@dataclass
class EvidenceRecord:
    obs_id: str
    property_id: str
    source: str                 # e.g. "hotel_direct", "ota_a" (named in the method note)
    url: str
    accessed_at_utc: str        # ISO 8601 with Z suffix
    stay_date: str
    lead_days: int
    capture_method: str
    capture_path: str           # relative to the evidence root
    capture_sha256: str
    capture_bytes: int
    price_displayed: float
    currency: str
    collector: str
    notes: str = ""
    prev_record_sha256: str = GENESIS
    record_sha256: str = ""

    def compute_hash(self) -> str:
        body = {k: v for k, v in asdict(self).items() if k != "record_sha256"}
        return hashlib.sha256(json.dumps(body, sort_keys=True).encode()).hexdigest()


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 16), b""):
            h.update(chunk)
    return h.hexdigest()


def utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


class EvidenceLog:
    """Append-only JSONL ledger with a hash chain."""

    def __init__(self, log_path: Path, evidence_root: Path):
        self.log_path = Path(log_path)
        self.root = Path(evidence_root)
        self.log_path.parent.mkdir(parents=True, exist_ok=True)

    def _last_hash(self) -> str:
        if not self.log_path.exists():
            return GENESIS
        last = GENESIS
        with open(self.log_path) as fh:
            for line in fh:
                if line.strip():
                    last = json.loads(line)["record_sha256"]
        return last

    def append(self, capture_file: Path, **fields) -> EvidenceRecord:
        if fields.get("capture_method") not in CAPTURE_METHODS:
            raise ValueError(f"capture_method must be one of {sorted(CAPTURE_METHODS)}")
        capture_file = Path(capture_file)
        rec = EvidenceRecord(
            capture_path=str(capture_file.relative_to(self.root)),
            capture_sha256=sha256_file(capture_file),
            capture_bytes=capture_file.stat().st_size,
            accessed_at_utc=fields.pop("accessed_at_utc", None) or utc_now(),
            prev_record_sha256=self._last_hash(),
            **fields,
        )
        rec.record_sha256 = rec.compute_hash()
        with open(self.log_path, "a") as fh:
            fh.write(json.dumps(asdict(rec), sort_keys=True) + "\n")
        return rec

    def records(self) -> list[dict]:
        with open(self.log_path) as fh:
            return [json.loads(line) for line in fh if line.strip()]


def verify_log(log_path: Path, evidence_root: Path) -> dict:
    """Re-derive every hash from disk. Returns counts and a list of problems."""
    problems, prev, n = [], GENESIS, 0
    with open(log_path) as fh:
        for lineno, line in enumerate(fh, 1):
            if not line.strip():
                continue
            n += 1
            raw = json.loads(line)
            missing = [f for f in REQUIRED_FIELDS if f not in raw]
            if missing:
                problems.append(f"line {lineno}: missing fields {missing}")
                continue
            rec = EvidenceRecord(**raw)
            if rec.prev_record_sha256 != prev:
                problems.append(f"line {lineno}: chain broken (record removed, reordered or inserted)")
            if rec.compute_hash() != rec.record_sha256:
                problems.append(f"line {lineno}: record fields edited after logging")
            cap = Path(evidence_root) / rec.capture_path
            if not cap.is_file():
                problems.append(f"line {lineno}: capture file missing: {rec.capture_path}")
            elif sha256_file(cap) != rec.capture_sha256:
                problems.append(f"line {lineno}: capture file changed since collection: {rec.capture_path}")
            prev = rec.record_sha256
    return {"records": n, "problems": problems, "ok": not problems}
