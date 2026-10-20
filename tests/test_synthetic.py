from hedonic.synthetic import SYNTHETIC_LABEL, simulate_panel


def test_every_row_is_labelled_synthetic():
    df = simulate_panel(n_properties=12, n_stay_dates=6)
    assert (df["data_label"] == SYNTHETIC_LABEL).all()
    assert df["property_name"].str.startswith("Synthetic Property").all()


def test_reproducible_with_seed():
    a = simulate_panel(n_properties=10, n_stay_dates=4, seed=7)
    b = simulate_panel(n_properties=10, n_stay_dates=4, seed=7)
    assert a.equals(b)


def test_panel_covers_design_cells():
    df = simulate_panel(n_properties=30, n_stay_dates=24)
    assert set(df["season"]) == {"winter", "spring", "summer", "autumn"}
    assert set(df["weekend"]) == {0, 1}
    assert set(df["rate_plan"]) == {"flexible", "non_refundable"}
    assert df.groupby("property_id")["has_pool"].nunique().max() == 1  # property-level amenity
    assert (df["nightly_rate_eur"] > 0).all()
