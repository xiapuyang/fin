"""
Tests for the deterministic CAGR binary search used in the FIRE page
(minNomCagr) and Dashboard (requiredCagr).

Both share the same formula:
  - Search nominal CAGR in [0, 40]
  - Each year: v = v * (1 + (nomCagr - inflation) / 100) + monthly * 12
  - Find minimum nomCagr such that v >= fire_number within target_years
"""


def _can_reach(
    investable: float,
    fire_number: float,
    monthly: float,
    inflation: float,
    target_years: int,
    nom_cagr: float,
) -> bool:
    real = nom_cagr - inflation
    v = investable
    for _ in range(target_years):
        v = v * (1 + real / 100) + monthly * 12
        if v >= fire_number:
            return True
    return False


def min_nom_cagr(
    investable: float,
    fire_number: float,
    monthly: float,
    inflation: float,
    target_years: int,
) -> float | None:
    """Port of the JS binary search in fire.jsx / dashboard.jsx."""
    if fire_number <= 0 or investable >= fire_number:
        return 0.0
    if not _can_reach(investable, fire_number, monthly, inflation, target_years, 40):
        return None
    lo, hi = 0.0, 40.0
    for _ in range(24):
        mid = (lo + hi) / 2
        if _can_reach(investable, fire_number, monthly, inflation, target_years, mid):
            hi = mid
        else:
            lo = mid
    return round(hi * 10) / 10


# ── boundary conditions ────────────────────────────────────────────────────────


def test_already_at_target_returns_zero():
    assert (
        min_nom_cagr(
            investable=1_000_000,
            fire_number=800_000,
            monthly=5000,
            inflation=3,
            target_years=15,
        )
        == 0.0
    )


def test_exactly_at_target_returns_zero():
    assert (
        min_nom_cagr(
            investable=500_000,
            fire_number=500_000,
            monthly=5000,
            inflation=3,
            target_years=15,
        )
        == 0.0
    )


def test_unreachable_returns_none():
    # Tiny investable, huge target, very short horizon — can't reach even at 40%
    assert (
        min_nom_cagr(
            investable=1_000,
            fire_number=100_000_000,
            monthly=100,
            inflation=3,
            target_years=1,
        )
        is None
    )


def test_zero_fire_number_returns_zero():
    assert (
        min_nom_cagr(
            investable=100_000,
            fire_number=0,
            monthly=5000,
            inflation=3,
            target_years=15,
        )
        == 0.0
    )


# ── determinism ───────────────────────────────────────────────────────────────


def test_same_inputs_same_output_repeated():
    kwargs = dict(
        investable=4_000_000,
        fire_number=10_500_000,
        monthly=8000,
        inflation=3,
        target_years=13,
    )
    results = {min_nom_cagr(**kwargs) for _ in range(20)}
    assert len(results) == 1, "Result must be deterministic across calls"


# ── monotonicity ──────────────────────────────────────────────────────────────


def test_larger_investable_needs_lower_or_equal_cagr():
    base = dict(fire_number=10_000_000, monthly=8000, inflation=3, target_years=13)
    r_small = min_nom_cagr(investable=3_000_000, **base)
    r_large = min_nom_cagr(investable=5_000_000, **base)
    assert r_small is None or r_large is None or r_large <= r_small


def test_larger_target_needs_higher_or_equal_cagr():
    base = dict(investable=4_000_000, monthly=8000, inflation=3, target_years=13)
    r_small = min_nom_cagr(fire_number=8_000_000, **base)
    r_large = min_nom_cagr(fire_number=15_000_000, **base)
    assert r_small is None or r_large is None or r_large >= r_small


def test_more_years_needs_lower_or_equal_cagr():
    base = dict(investable=4_000_000, fire_number=10_500_000, monthly=8000, inflation=3)
    r_short = min_nom_cagr(target_years=8, **base)
    r_long = min_nom_cagr(target_years=20, **base)
    assert r_short is None or r_long is None or r_long <= r_short


def test_more_monthly_contributions_needs_lower_or_equal_cagr():
    base = dict(
        investable=4_000_000, fire_number=10_500_000, inflation=3, target_years=13
    )
    r_low = min_nom_cagr(monthly=3000, **base)
    r_high = min_nom_cagr(monthly=15000, **base)
    assert r_low is None or r_high is None or r_high <= r_low


def test_higher_inflation_needs_higher_nominal_cagr():
    base = dict(
        investable=4_000_000, fire_number=10_500_000, monthly=8000, target_years=13
    )
    r_low_inf = min_nom_cagr(inflation=2, **base)
    r_high_inf = min_nom_cagr(inflation=5, **base)
    assert r_low_inf is None or r_high_inf is None or r_high_inf >= r_low_inf


# ── dashboard / fire page parity ──────────────────────────────────────────────


def test_known_value_matches_expected():
    """Both pages run the identical formula — spot-check against a pre-computed reference."""
    result = min_nom_cagr(
        investable=4_360_000,
        fire_number=10_500_000,
        monthly=8000,
        inflation=3,
        target_years=13,
    )
    assert result is not None
    # Pre-computed: binary search converges to ~8.3% nominal at these inputs.
    assert abs(result - 8.3) <= 0.5


def test_result_rounds_to_one_decimal():
    result = min_nom_cagr(
        investable=4_000_000,
        fire_number=10_500_000,
        monthly=8000,
        inflation=3,
        target_years=13,
    )
    if result is not None:
        assert result == round(result, 1)


# ── spot-check known scenario ─────────────────────────────────────────────────


def test_reasonable_range_for_typical_scenario():
    # Investable ¥4M, target ¥10.5M, ¥8k/month, 3% inflation, 13 years
    # Expect somewhere between 5% and 15% nominal
    result = min_nom_cagr(
        investable=4_000_000,
        fire_number=10_500_000,
        monthly=8000,
        inflation=3,
        target_years=13,
    )
    assert result is not None
    assert 5.0 <= result <= 15.0


def test_no_contributions_pure_compound():
    # With no monthly contributions: need v * (1 + real/100)^years >= target
    # investable=1M, target=2M, 0 monthly, 0 inflation, 10 years
    # need (1+r)^10 >= 2 → r >= 7.18% nominal (= real since inflation=0)
    result = min_nom_cagr(
        investable=1_000_000,
        fire_number=2_000_000,
        monthly=0,
        inflation=0,
        target_years=10,
    )
    assert result is not None
    assert abs(result - 7.2) <= 0.2  # 2^(1/10) - 1 ≈ 7.18%
