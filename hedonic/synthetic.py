"""SYNTHETIC hotel-rate panel for demonstrating a hedonic design.

Every number produced here is simulated. Nothing in this module is an observed
hotel price, a real property, or a real booking-site record. Locality names are
used only so the structure looks like the intended Malta study.

Design choices that mirror the real study:
- A property-level amenity (shared pool) whose presence is correlated with star
  rating and locality, so a naive comparison is biased and controls matter.
- A room-level amenity (in-room jacuzzi / private plunge pool) that is more
  common in suites, so room type is a confounder and a within-property
  comparison is possible.
- Repeated stay dates across seasons and weekday/weekend, each quoted at a
  fixed booking lead time, with rate-plan terms (cancellation, meals).
"""
from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np
import pandas as pd

SYNTHETIC_LABEL = "SYNTHETIC ILLUSTRATIVE DATA - NOT OBSERVED HOTEL PRICES"

LOCALITIES = {
    # name: true log-price shift relative to the reference locality
    "Bugibba": 0.00,
    "Sliema": 0.12,
    "St Julian's": 0.15,
    "Valletta": 0.20,
    "Mellieha": 0.05,
    "Gozo": -0.05,
}
SEASONS = {"winter": 0.00, "spring": 0.18, "summer": 0.45, "autumn": 0.22}
ROOM_TYPES = {"standard": 0.00, "superior": 0.12, "suite": 0.35}
MEALS = {"room_only": 0.00, "breakfast": 0.07, "half_board": 0.18}


@dataclass(frozen=True)
class TrueEffects:
    """The data-generating parameters (log points). Tests check recovery."""

    pool: float = 0.10          # property-level shared pool
    jacuzzi: float = 0.15       # room-level in-room jacuzzi / plunge pool
    stars: float = 0.11         # per star
    review: float = 0.06        # per review-score point (0-10 scale)
    log_room_size: float = 0.30
    sea_km: float = -0.04       # per km from the sea
    weekend: float = 0.08
    non_refundable: float = -0.09
    base: float = 3.40          # about EUR 30 before other effects
    sigma_property: float = 0.06  # unobserved property quality (independent of pool)
    sigma_noise: float = 0.07
    extra: dict = field(default_factory=dict)


def simulate_panel(n_properties: int = 96, n_stay_dates: int = 24, lead_days: int = 30,
                   seed: int = 20261020, effects: TrueEffects | None = None) -> pd.DataFrame:
    """Return one row per (property, room type, rate plan, stay date) quote."""
    eff = effects or TrueEffects()
    rng = np.random.default_rng(seed)
    loc_names = list(LOCALITIES)

    props = []
    for p in range(n_properties):
        loc = loc_names[p % len(loc_names)]
        stars = int(rng.choice([2, 3, 4, 5], p=[0.15, 0.35, 0.35, 0.15]))
        # Confounding by design: pools are likelier at higher-star and resort-area properties.
        logit = -2.2 + 0.75 * (stars - 2) + (0.6 if loc in ("Mellieha", "St Julian's", "Gozo") else 0.0)
        has_pool = int(rng.random() < 1 / (1 + np.exp(-logit)))
        props.append({
            "property_id": f"P{p + 1:03d}",
            "property_name": f"Synthetic Property {p + 1:03d}",
            "locality": loc,
            "property_type": "hotel" if stars >= 3 else "guesthouse",
            "stars": stars,
            "review_score": float(np.clip(rng.normal(7.4 + 0.35 * (stars - 2), 0.45), 5.5, 9.8)),
            "n_rooms": int(rng.integers(8, 40) * (1 + stars // 3)),
            "sea_km": float(np.round(rng.gamma(2.0, 0.6), 2)),
            "has_pool": has_pool,
            "u_property": float(rng.normal(0, eff.sigma_property)),
        })

    # Stay dates: spread across the four seasons, alternating weekday/weekend nights.
    base_date = pd.Timestamp("2025-01-08")
    stay_dates = [base_date + pd.Timedelta(days=int(d)) for d in np.linspace(0, 350, n_stay_dates)]
    stay_dates = [d + pd.Timedelta(days=(4 - d.weekday()) % 7 if i % 2 else 0) for i, d in enumerate(stay_dates)]

    rows = []
    for pr in props:
        n_types = 3 if pr["stars"] >= 4 else 2
        for rt in list(ROOM_TYPES)[:n_types]:
            # Room-level amenity more common in suites (room type is a confounder).
            p_jac = {"standard": 0.05, "superior": 0.25, "suite": 0.65}[rt]
            jac = int(rng.random() < p_jac)
            size = float(np.round(rng.normal({"standard": 18, "superior": 24, "suite": 38}[rt], 3), 1))
            for plan in ("flexible", "non_refundable"):
                meal = str(rng.choice(list(MEALS), p=[0.45, 0.4, 0.15]))
                for sd in stay_dates:
                    season = _season(sd)
                    weekend = int(sd.weekday() in (4, 5))
                    mu = (eff.base + LOCALITIES[pr["locality"]] + eff.stars * pr["stars"]
                          + eff.review * pr["review_score"] + eff.sea_km * pr["sea_km"]
                          + eff.pool * pr["has_pool"] + eff.jacuzzi * jac
                          + ROOM_TYPES[rt] + eff.log_room_size * np.log(size)
                          + SEASONS[season] + eff.weekend * weekend
                          + eff.non_refundable * (plan == "non_refundable") + MEALS[meal]
                          + pr["u_property"])
                    log_rate = mu + rng.normal(0, eff.sigma_noise)
                    rows.append({
                        **{k: v for k, v in pr.items() if k != "u_property"},
                        "room_type": rt,
                        "room_jacuzzi": jac,
                        "room_size_m2": size,
                        "rate_plan": plan,
                        "non_refundable": int(plan == "non_refundable"),
                        "meal_plan": meal,
                        "stay_date": sd.date().isoformat(),
                        "season": season,
                        "weekend": weekend,
                        "lead_days": lead_days,
                        "nightly_rate_eur": float(np.round(np.exp(log_rate), 2)),
                        "data_label": SYNTHETIC_LABEL,
                    })
    df = pd.DataFrame(rows)
    df.insert(0, "obs_id", [f"OBS{i + 1:06d}" for i in range(len(df))])
    df["log_rate"] = np.log(df["nightly_rate_eur"])
    return df


def _season(ts: pd.Timestamp) -> str:
    m = ts.month
    if m in (12, 1, 2):
        return "winter"
    if m in (3, 4, 5):
        return "spring"
    if m in (6, 7, 8, 9):
        return "summer"
    return "autumn"
