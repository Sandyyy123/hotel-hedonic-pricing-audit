"""Run the full SYNTHETIC demo: data -> evidence ledger -> audit -> hedonic models.

    python main.py            # writes everything to ./output/

All prices are simulated. Nothing here is an observed hotel price.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import pandas as pd

from hedonic.evidence import EvidenceLog, verify_log
from hedonic.model import SPECS, results_table
from hedonic.synthetic import SYNTHETIC_LABEL, TrueEffects, simulate_panel

OUT = Path(__file__).resolve().parent / "output"


def write_captures(df: pd.DataFrame, root: Path, log: EvidenceLog, limit: int) -> None:
    """Write a small synthetic 'saved HTML' capture per quote and log it.

    In the real study this file is the screenshot / saved page / raw API JSON
    captured at the moment of collection; here it is a labelled stand-in.
    """
    cap_dir = root / "captures"
    cap_dir.mkdir(parents=True, exist_ok=True)
    for row in df.head(limit).itertuples():
        url = (f"https://example.invalid/synthetic/{row.property_id}"
               f"?checkin={row.stay_date}&nights=1&adults=2&room={row.room_type}&plan={row.rate_plan}")
        html = (f"<!-- {SYNTHETIC_LABEL} -->\n<html><body><h1>{row.property_name}</h1>"
                f"<p>{row.room_type} | {row.rate_plan} | {row.meal_plan}</p>"
                f"<p class='price'>EUR {row.nightly_rate_eur:.2f}</p></body></html>\n")
        path = cap_dir / f"{row.obs_id}.html"
        path.write_text(html)
        log.append(path, obs_id=row.obs_id, property_id=row.property_id, source="synthetic_ota",
                   url=url, stay_date=row.stay_date, lead_days=int(row.lead_days),
                   capture_method="saved_html", price_displayed=float(row.nightly_rate_eur),
                   currency="EUR", collector="demo-script", notes=SYNTHETIC_LABEL)


def markdown_table(tab: pd.DataFrame) -> str:
    lines = ["| Specification | Amenity | Premium % | 95% CI % | Cluster SE (log) | p | N quotes | Properties |",
             "|---|---|---|---|---|---|---|---|"]
    for r in tab.itertuples():
        lines.append(f"| {r.spec} | {r.term} | {r.premium_pct:.1f} | {r.ci_low_pct:.1f} to {r.ci_high_pct:.1f} | "
                     f"{r.se_cluster:.4f} | {r.p_value:.3g} | {r.n_obs} | {r.n_clusters} |")
    return "\n".join(lines)


def main() -> int:
    OUT.mkdir(exist_ok=True)
    log_path = OUT / "evidence_log.jsonl"
    log_path.write_text("")  # ledger regenerated each run; synthetic stand-ins only

    df = simulate_panel()
    df.to_csv(OUT / "synthetic_hotel_panel.csv", index=False)

    log = EvidenceLog(log_path, OUT)
    write_captures(df, OUT, log, limit=200)
    audit = verify_log(log_path, OUT)

    tab = results_table(df)
    tab.to_csv(OUT / "regression_results.csv", index=False)
    truth = TrueEffects()
    summary = {
        "label": SYNTHETIC_LABEL,
        "n_quotes": int(len(df)),
        "n_properties": int(df.property_id.nunique()),
        "n_stay_dates": int(df.stay_date.nunique()),
        "pool_share_of_properties": float(df.groupby("property_id").has_pool.first().mean()),
        "true_effects_log": {"pool": truth.pool, "jacuzzi": truth.jacuzzi},
        "specs": {k: {"terms": v["terms"], "fixed_effects": v["fe"]} for k, v in SPECS.items()},
        "evidence_audit": audit,
        "results": tab.to_dict(orient="records"),
    }
    (OUT / "results.json").write_text(json.dumps(summary, indent=2, default=float))
    md = (f"# Hedonic demo results\n\n**{SYNTHETIC_LABEL}**\n\n"
          f"Quotes: {summary['n_quotes']}, properties: {summary['n_properties']}, "
          f"stay dates: {summary['n_stay_dates']}. True simulated premiums: pool "
          f"{100 * (2.718281828 ** truth.pool - 1):.1f}%, jacuzzi {100 * (2.718281828 ** truth.jacuzzi - 1):.1f}%.\n\n"
          + markdown_table(tab) + "\n\n"
          f"Evidence ledger: {audit['records']} records, problems: {len(audit['problems'])}.\n")
    (OUT / "regression_table.md").write_text(md)
    print(md)
    return 0 if audit["ok"] else 1


if __name__ == "__main__":
    sys.exit(main())
